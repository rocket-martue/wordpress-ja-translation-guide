# -*- coding: utf-8 -*-
"""中間成果物のスキーマ検証と、PO エスケープ・世代差の扱い。

作業ディレクトリをコミットする運用だと、壊れた entries.json / chunk-meta.json /
対応表が届く前提で、traceback ではなく形式エラーとして止まることを確かめる。
あわせて、msgctxt のエスケープ復元と、旧世代の対応表・旧形式ドラフトの扱いも固定する。
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from _harness import ROOT, Result, chunk_index, read_json, run, write_draft  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check

ESC_CTX = 'Adjective: e.g. "Comments are open"'
PO = '''# schema
msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: schema\\n"

#: src/a.php:1
msgctxt "Adjective: e.g. \\"Comments are open\\""
msgid "Open"
msgstr ""

#: src/b.php:2
msgid "Open"
msgstr ""

#: src/c.php:3
msgid "Save changes"
msgstr ""
'''

BAD_GLOSSARY = b"en,ja,pos,description\n\x82\xa0,\x82\xa2,noun,cp932 \x82\xc5\x8f\x91\x82\xa2\x82\xbd\n"


def setup(tmp: Path, name: str, extra_files=()):
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    po = d / (name + "-ja-untranslated.po")
    po.write_text(PO, encoding="utf-8")
    for fname, data in extra_files:
        (d / fname).write_bytes(data)
    work = tmp / ("work-" + name)
    r = run(["scripts/po_chunk.py", str(po), "--outdir", str(work), "--no-ref"])
    return po, work, r


def collect(work: Path, *extra: str):
    return run(["scripts/po_collect.py", "--outdir", str(work)] + list(extra))


tmp = Path(tempfile.mkdtemp(prefix="po-schema-"))
try:
    # ==================================== msgctxt の PO エスケープを解く
    po, work, r = setup(tmp, "esc")
    idx = chunk_index(work)
    check("[esc] msgctxt の \\\" を復元して対応表に入れる",
          ("%s|Open" % ESC_CTX) in idx, str(sorted(idx)))
    ent = [e for e in read_json(work / "entries.json") if e["msgid"] == "Open"]
    check("[esc] entries.json にも復元した msgctxt が入る",
          sorted(e["msgctxt"] for e in ent) == ["", ESC_CTX], str([e["msgctxt"] for e in ent]))
    md = (work / "chunks" / "chunk_00.md").read_text(encoding="utf-8")
    check("[esc] チャンク md の msgctxt 行にバックスラッシュが残らない",
          ("msgctxt: " + ESC_CTX) in md and "\\\"" not in md, md[:500])
    # 素の引用符で ctx を書けば通る(復元していないと CTX_MISMATCH になる)
    write_draft(work, "translations_00.json", [
        {"n": idx["%s|Open" % ESC_CTX]["n"], "id": "Open", "ctx": ESC_CTX, "msgstr": "受付中"},
        {"n": idx["|Open"]["n"], "id": "Open", "msgstr": "開く"},
        {"n": idx["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r = collect(work)
    rep = (work / "collect-report.txt").read_text(encoding="utf-8")
    check("[esc] 素の引用符の ctx が CTX_MISMATCH にならない",
          "CTX_MISMATCH" not in rep and r.returncode == 0, "rc=%d\n%s" % (r.returncode, rep[:400]))

    # ==================================== 用語集は破壊的操作の前に読む
    po2, work2, r2 = setup(tmp, "badcsv", [("badcsv-glossary.csv", BAD_GLOSSARY)])
    check("[glossary] UTF-8 として読めない用語集でも traceback しない",
          r2.returncode == 0 and "Traceback" not in (r2.stderr or ""),
          "rc=%d stderr=%s" % (r2.returncode, (r2.stderr or "")[:300]))
    check("[glossary] 読めない理由を WARN で出す",
          "WARN: glossary を読めません" in (r2.stdout or ""), (r2.stdout or "")[:400])
    check("[glossary] チャンクは通常どおり書き出される",
          (work2 / "chunks" / "chunk_00.md").is_file() and (work2 / "entries.json").is_file())

    # ==================================== entries.json が壊れている
    po3, work3, _ = setup(tmp, "badentries")
    idx3 = chunk_index(work3)
    write_draft(work3, "translations_00.json",
                [{"n": idx3["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"}])
    for label, payload in (
        ("JSON として壊れている", "{"),
        ("配列でない", '{"a": 1}'),
        ("要素が辞書でない", '["x"]'),
        ("msgid が無い", '[{"msgctxt": "x"}]'),
        ("msgid が数値", '[{"msgid": 1}]'),
    ):
        (work3 / "entries.json").write_text(payload, encoding="utf-8")
        r = collect(work3)
        rep3 = (work3 / "collect-report.txt").read_text(encoding="utf-8")
        check("[entries.json] %s でも exit 4 で止まる" % label,
              r.returncode == 4 and "entries.json が壊れています" in rep3
              and "Traceback" not in (r.stderr or ""),
              "rc=%d stderr=%s" % (r.returncode, (r.stderr or "")[:300]))

    # ==================================== chunk-meta.json のフィールドが壊れている
    po4, work4, _ = setup(tmp, "badmeta2")
    idx4 = chunk_index(work4)
    write_draft(work4, "translations_00.json",
                [{"n": idx4["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存。"}])   # NG
    meta = read_json(work4 / "chunk-meta.json")
    for label, patch in (
        ("refs が null", {"refs": None}),
        ("size が文字列", {"size": "たくさん"}),
        ("max_chars が null", {"max_chars": None}),
        ("ref_limit がリスト", {"ref_limit": [1]}),
    ):
        (work4 / "chunk-meta.json").write_text(
            json.dumps(dict(meta, **patch), ensure_ascii=False), encoding="utf-8")
        r = collect(work4)
        made = read_json(work4 / "rework.json")["chunks"]
        check("[chunk-meta] %s でも traceback せず rework チャンクを作る" % label,
              "Traceback" not in (r.stderr or "") and bool(made),
              "rc=%d stderr=%s" % (r.returncode, (r.stderr or "")[:300]))

    # ==================================== 対応表の rework_of / msgctxt: null
    po5, work5, _ = setup(tmp, "badmap2")
    idx5 = chunk_index(work5)
    good = read_json(work5 / "chunks" / "chunk_00.json")
    write_draft(work5, "translations_00.json",
                [{"n": idx5["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"}])
    (work5 / "chunks" / "chunk_00.json").write_text(
        json.dumps([dict(good[0], rework_of=[["x"], 1])] + [dict(x) for x in good[1:]],
                   ensure_ascii=False), encoding="utf-8")
    r = collect(work5)
    check("[対応表] rework_of の形が違えば exit 4(TypeError にしない)",
          r.returncode == 4 and "Traceback" not in (r.stderr or ""),
          "rc=%d stderr=%s" % (r.returncode, (r.stderr or "")[:300]))

    (work5 / "chunks" / "chunk_00.json").write_text(
        json.dumps([dict(x, msgctxt=None) for x in good], ensure_ascii=False), encoding="utf-8")
    write_draft(work5, "translations_00.json", [
        {"n": idx5["%s|Open" % ESC_CTX]["n"], "id": "Open", "ctx": "", "msgstr": "受付中"},
        {"n": idx5["|Open"]["n"], "id": "Open", "ctx": "", "msgstr": "開く"},
        {"n": idx5["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r = collect(work5)
    check("[対応表] msgctxt が null でも空文字として扱い traceback しない",
          "Traceback" not in (r.stderr or ""), (r.stderr or "")[:300])

    # ==================================== entries.json の任意項目も型を見る
    po8, work8, _ = setup(tmp, "entryfields")
    idx8 = chunk_index(work8)
    write_draft(work8, "translations_00.json",
                [{"n": idx8["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"}])
    good8 = read_json(work8 / "entries.json")
    for label, field, bad in (("msgid_plural が数値", "msgid_plural", 1),
                              ("msgctxt が数値", "msgctxt", 2),
                              ("translators がリスト", "translators", ["x"])):
        broken = [dict(x) for x in good8]
        broken[0][field] = bad
        (work8 / "entries.json").write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
        r = collect(work8)
        rep8 = (work8 / "collect-report.txt").read_text(encoding="utf-8")
        check("[entries.json] %s を exit 4 で弾く" % label,
              r.returncode == 4 and "entries.json が壊れています" in rep8
              and "Traceback" not in (r.stderr or ""),
              "rc=%d stderr=%s" % (r.returncode, (r.stderr or "")[:250]))

    # ==================================== rework_of の役割と旧形式の鍵
    po9, work9, _ = setup(tmp, "reworkof")
    idx9 = chunk_index(work9)
    write_draft(work9, "translations_00.json",
                [{"n": idx9["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"}])
    base9 = read_json(work9 / "chunks" / "chunk_00.json")
    for label, ro, want_ok in (
        ("[チャンクキー, n]", ["00", 1], True),
        ('旧形式の ["-", msgid]', ["-", "Save changes"], True),
        ("順序が逆 [1, チャンクキー]", [1, "00"], False),
        ("n が bool", ["00", True], False),
        ("番号なのに n が文字列", ["00", "x"], False),
    ):
        (work9 / "chunks" / "chunk_00.json").write_text(
            json.dumps([dict(base9[0], rework_of=ro)] + [dict(x) for x in base9[1:]],
                       ensure_ascii=False), encoding="utf-8")
        r = collect(work9)
        ok9 = r.returncode != 4
        check("[rework_of] %s を%s" % (label, "受理する" if want_ok else "exit 4 で弾く"),
              ok9 == want_ok and "Traceback" not in (r.stderr or ""),
              "rc=%d" % r.returncode)

    # ==================================== 旧世代の対応表では ctx 照合をしない
    po10, work10, _ = setup(tmp, "oldctx")
    idx10 = chunk_index(work10)
    n_ctx10, n_free10 = idx10["%s|Open" % ESC_CTX]["n"], idx10["|Open"]["n"]
    old10 = [{"n": it["n"], "msgid": it["msgid"], "msgid_plural": it["msgid_plural"], "kind": it["kind"]}
             for it in read_json(work10 / "chunks" / "chunk_00.json")]
    (work10 / "chunks" / "chunk_00.json").write_text(json.dumps(old10, ensure_ascii=False), encoding="utf-8")
    write_draft(work10, "translations_00.json", [
        {"n": n_ctx10, "id": "Open", "ctx": ESC_CTX, "msgstr": "受付中"},   # 正しい ctx
        {"n": n_free10, "id": "Open", "msgstr": "開く"},
        {"n": idx10["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r = collect(work10)
    rep10 = (work10 / "collect-report.txt").read_text(encoding="utf-8")
    man10 = read_json(work10 / "manual.json").get("Open", [])
    check("[旧世代] msgctxt の項目が無い対応表では ctx を照合せず CTX_MISMATCH にしない",
          "CTX_MISMATCH" not in rep10, rep10[:400])
    check("[旧世代] 照合できない分は unverified_ctx を付けて manual に集める",
          len(man10) == 2 and all(c.get("unverified_ctx") for c in man10),
          json.dumps(man10, ensure_ascii=False))

    # ==================================== ctx が文字列でない
    po11, work11, _ = setup(tmp, "ctxtype")
    idx11 = chunk_index(work11)
    write_draft(work11, "translations_00.json", [
        {"n": idx11["%s|Open" % ESC_CTX]["n"], "id": "Open", "ctx": 1, "msgstr": "受付中"},
        {"n": idx11["|Open"]["n"], "id": "Open", "msgstr": "開く"},
        {"n": idx11["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r = collect(work11)
    rep11 = (work11 / "collect-report.txt").read_text(encoding="utf-8")
    check("[ctx] 数値の ctx は CTX_TYPE で弾く",
          "CTX_TYPE" in rep11 and r.returncode == 3,
          "rc=%d\n%s" % (r.returncode, rep11[:400]))

    # ==================================== 旧世代の対応表(msgctxt の項目なし)
    po6, work6, _ = setup(tmp, "oldschema")
    idx6 = chunk_index(work6)
    n_ctx = idx6["%s|Open" % ESC_CTX]["n"]
    old = [{"n": it["n"], "msgid": it["msgid"], "msgid_plural": it["msgid_plural"], "kind": it["kind"]}
           for it in read_json(work6 / "chunks" / "chunk_00.json")]
    (work6 / "chunks" / "chunk_00.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    write_draft(work6, "translations_00.json", [
        {"n": n_ctx, "id": "Open", "msgstr": "受付中。"},        # NG(原文に終端記号なし)
        {"n": idx6["|Open"]["n"], "id": "Open", "msgstr": "開く"},
        {"n": idx6["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r = collect(work6)
    rwname = read_json(work6 / "rework.json")["chunks"][0]
    rwmd = (work6 / "chunks" / (rwname + ".md")).read_text(encoding="utf-8")
    check("[旧世代] msgctxt の項目が無い対応表で、entries.json 側の文脈を空で潰さない",
          "msgctxt: " in rwmd, rwmd[:400])

    # ==================================== e があるのに引けない対応表
    po12, work12, _ = setup(tmp, "stale_e")
    idx12 = chunk_index(work12)
    n_ctx12 = idx12["%s|Open" % ESC_CTX]["n"]
    write_draft(work12, "translations_00.json", [
        {"n": n_ctx12, "id": "Open", "ctx": ESC_CTX, "msgstr": "受付中。"},        # TERMINAL NG
        {"n": idx12["|Open"]["n"], "id": "Open", "msgstr": "開く"},
        {"n": idx12["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    # e を範囲外にして「対応表と entries.json の世代がずれた」状態を作る
    raw12 = read_json(work12 / "chunks" / "chunk_00.json")
    for it in raw12:
        if it["n"] == n_ctx12:
            it["e"] = 999
    (work12 / "chunks" / "chunk_00.json").write_text(
        json.dumps(raw12, ensure_ascii=False), encoding="utf-8")
    r = collect(work12)
    rep12 = (work12 / "collect-report.txt").read_text(encoding="utf-8")
    check("[e] 無効な e は msgid で代用せず形式エラーにする",
          r.returncode == 4 and "rework チャンクを作れません" in rep12
          and "Traceback" not in (r.stderr or ""),
          "rc=%d\n%s" % (r.returncode, rep12[-500:]))

    # ==================================== 旧形式 × 重複 msgid の候補を rework が潰さない
    po13, work13, _ = setup(tmp, "legacyrework")
    write_draft(work13, "translations_00.json", [
        {"msgid": "Open", "msgstr": "受付中。"},      # TERMINAL NG
        {"msgid": "Open", "msgstr": "開く"},          # 通る。これが消えてはいけない
        {"msgid": "Save changes", "msgstr": "変更を保存"},
    ])
    collect(work13)
    rw13 = read_json(work13 / "rework.json")["chunks"][0]
    rwidx13 = read_json(work13 / "chunks" / (rw13 + ".json"))
    write_draft(work13, "translations_%s.json" % rw13, [
        {"n": rwidx13[0]["n"], "id": "Open", "msgstr": "受付中"},
    ])
    r = collect(work13)
    man13 = read_json(work13 / "manual.json").get("Open", [])
    check("[旧形式] rework の再投入が既存の ambiguous 候補を置き換えない",
          len(man13) == 2 and all(c.get("ambiguous") for c in man13)
          and sorted(c["msgstr"] for c in man13) == ["受付中", "開く"],
          "rc=%d manual=%s" % (r.returncode, json.dumps(man13, ensure_ascii=False)))

    # ==================================== 旧形式ドラフト × 重複 msgid
    po7, work7, _ = setup(tmp, "legacydup")
    write_draft(work7, "translations_00.json", [
        {"msgid": "Open", "msgstr": "受付中。"},      # NG
        {"msgid": "Open", "msgstr": "開く"},          # 通る。前の NG 記録を消してはいけない
        {"msgid": "Save changes", "msgstr": "変更を保存"},
    ])
    r = collect(work7)
    rw7 = read_json(work7 / "rework.json")["items"]
    check("[旧形式] 重複 msgid で、後の正常な項目が前の NG 記録を消さない",
          r.returncode == 3 and any(it["msgid"] == "Open" for it in rw7),
          "rc=%d rework=%s" % (r.returncode, json.dumps(rw7, ensure_ascii=False)[:300]))

    rwname7 = read_json(work7 / "rework.json")["chunks"][0]
    rwidx7 = read_json(work7 / "chunks" / (rwname7 + ".json"))
    write_draft(work7, "translations_%s.json" % rwname7, [
        {"n": rwidx7[0]["n"], "id": "Open", "msgstr": "受付中"},
    ])
    r = collect(work7)
    rep7 = (work7 / "collect-report.txt").read_text(encoding="utf-8")
    check("[旧形式] 重複 msgid では自動で書き戻さず、理由を出して drafts/ に残す",
          "書き戻し先を特定できません" in rep7
          and (work7 / "drafts" / ("translations_%s.json" % rwname7)).is_file(),
          "rc=%d\n%s" % (r.returncode, rep7[-500:]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
