# -*- coding: utf-8 -*-
"""壊れた中間成果物と、古くなった rework ドラフトの扱い。

作業ディレクトリをコミットする運用だと、マージ競合や手編集で壊れたものが来る。
その場合に collector が traceback で落ちず、形式エラーとして報告して止まることを確かめる。
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from _harness import ROOT, Result, chunk_index, read_json, run, write_draft  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check

CTX = "Name for the CSS pseudo-class selector"
PO = '''# broken workdir
msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: broken\\n"

#: src/block.js:10
msgctxt "Name for the CSS pseudo-class selector"
msgid "Active"
msgstr ""

#: src/plugins.php:20
msgid "Active"
msgstr ""

#: src/a.php:1
msgid "Save changes"
msgstr ""

#: src/b.php:2
msgid "Delete this item"
msgstr ""
'''


def setup(tmp: Path, name: str):
    po = tmp / (name + ".po")
    po.write_text(PO, encoding="utf-8")
    work = tmp / ("work-" + name)
    run(["scripts/po_chunk.py", str(po), "--outdir", str(work), "--no-ref"], check_rc=True)
    return po, work, chunk_index(work)


def collect(work: Path, *extra: str):
    return run(["scripts/po_collect.py", "--outdir", str(work)] + list(extra))


tmp = Path(tempfile.mkdtemp(prefix="po-broken-"))
try:
    # ============================ 対応表の msgid が壊れている(旧形式ドラフトでも exit 4)
    po, work, idx = setup(tmp, "badmsgid")
    good = read_json(work / "chunks" / "chunk_00.json")
    write_draft(work, "translations_00.json",
                [{"n": idx["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"}])
    for label, mutate in (
        ("msgid が null", lambda d: [dict(d[0], msgid=None)] + d[1:]),
        ("msgid が数値", lambda d: [dict(d[0], msgid=123)] + d[1:]),
        ("msgctxt が数値", lambda d: [dict(d[0], msgctxt=1)] + d[1:]),
    ):
        (work / "chunks" / "chunk_00.json").write_text(
            json.dumps(mutate([dict(x) for x in good]), ensure_ascii=False), encoding="utf-8")
        r = collect(work)
        rep = (work / "collect-report.txt").read_text(encoding="utf-8")
        check("[対応表] %s を拒否し、traceback ではなく exit 4 で止まる" % label,
              r.returncode == 4 and "PARSE ERROR" in rep and "Traceback" not in (r.stderr or ""),
              "rc=%d stderr=%s" % (r.returncode, (r.stderr or "")[:300]))

    # 旧形式(msgid キー)のドラフトでも、壊れた対応表は形式エラーとして数える
    (work / "chunks" / "chunk_00.json").write_text(
        json.dumps([dict(good[0], msgid=None)] + [dict(x) for x in good[1:]], ensure_ascii=False),
        encoding="utf-8")
    write_draft(work, "translations_00.json", [{"msgid": "Save changes", "msgstr": "変更を保存"}])
    r = collect(work)
    check("[対応表] 旧形式ドラフトでも壊れた対応表で exit 0 にならない",
          r.returncode == 4, "rc=%d" % r.returncode)

    # ============================ rework.json が壊れている
    po, work2, idx2 = setup(tmp, "badrework")
    write_draft(work2, "translations_00.json", [
        {"n": idx2["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存。"},   # NG
        {"n": idx2["|Delete this item"]["n"], "id": "Delete this item", "msgstr": "この項目を削除"},
    ])
    collect(work2)
    for label, payload in (
        ("要素が辞書でない", {"chunks": ["rework_00"], "items": ["こわれた"]}),
        ("key の要素がリスト", {"chunks": ["rework_00"], "items": [{"key": [["x"], 1], "msgid": "Save changes"}]}),
        ("chunks が文字列", {"chunks": "rework_00", "items": []}),
        ("トップレベルが文字列", "broken"),
    ):
        (work2 / "rework.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        r = collect(work2)
        check("[rework.json] %s でも traceback せず動く" % label,
              r.returncode in (0, 2, 3, 4) and "Traceback" not in (r.stderr or ""),
              "rc=%d stderr=%s" % (r.returncode, (r.stderr or "")[:300]))

    # ============================ chunk-meta.json が JSON オブジェクトでない
    po, work3, idx3 = setup(tmp, "badmeta")
    write_draft(work3, "translations_00.json", [
        {"n": idx3["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存。"},   # NG
    ])
    (work3 / "chunk-meta.json").write_text("[]", encoding="utf-8")
    r = collect(work3)
    rep3 = (work3 / "collect-report.txt").read_text(encoding="utf-8")
    check("[chunk-meta] 配列でも traceback せず、report に理由が出る",
          "Traceback" not in (r.stderr or "") and "JSON オブジェクトではありません" in rep3,
          "rc=%d stderr=%s\n%s" % (r.returncode, (r.stderr or "")[:200], rep3[-300:]))

    # ============================ 古い rework ドラフトが新しい通常ドラフトを上書きしない
    po, work4, idx4 = setup(tmp, "stale")
    n_save = idx4["|Save changes"]["n"]
    write_draft(work4, "translations_00.json", [
        {"n": n_save, "id": "Save changes", "msgstr": "変更を保存。"},                        # NG
        {"n": idx4["|Delete this item"]["n"], "id": "Delete this item", "msgstr": "この項目を削除"},
    ])
    r = collect(work4)
    rwname = read_json(work4 / "rework.json")["chunks"][0]
    rwidx = read_json(work4 / "chunks" / (rwname + ".json"))
    # rework の答え + 不正項目 -> このファイルは drafts/ に残る
    write_draft(work4, "translations_%s.json" % rwname, [
        {"n": rwidx[0]["n"], "id": "Save changes", "msgstr": "古い訳"},
        {"n": 999, "id": "bogus", "msgstr": "x"},
    ])
    collect(work4)
    check("[stale] 不正項目を含む rework ドラフトが drafts/ に残る",
          (work4 / "drafts" / ("translations_%s.json" % rwname)).is_file(),
          str(sorted(p.name for p in (work4 / "drafts").iterdir())))
    # 人が通常ドラフトを新しい訳に直した
    write_draft(work4, "translations_00.json", [
        {"n": n_save, "id": "Save changes", "msgstr": "新しい訳"},
        {"n": idx4["|Delete this item"]["n"], "id": "Delete this item", "msgstr": "この項目を削除"},
    ])
    r = collect(work4)
    pool4 = read_json(work4 / "pool.json")
    back4 = read_json(work4 / "drafts" / "translations_00.json")
    rep4 = (work4 / "collect-report.txt").read_text(encoding="utf-8")
    check("[stale] 古い rework の訳が新しい通常ドラフトを上書きしない",
          pool4.get("Save changes") == "新しい訳"
          and next(b["msgstr"] for b in back4 if b["n"] == n_save) == "新しい訳",
          "pool=%s back=%s" % (json.dumps(pool4, ensure_ascii=False), json.dumps(back4, ensure_ascii=False)))
    check("[stale] 読み飛ばした理由が report に出る",
          "通常ドラフトが新しいので rework の項目を読み飛ばします" in rep4, rep4[-400:])

    # ============================ --no-check では ctx 照合もしない
    po, work5, idx5 = setup(tmp, "nocheck")
    write_draft(work5, "translations_00.json", [
        {"n": idx5["%s|Active" % CTX]["n"], "id": "Active", "ctx": "でたらめ", "msgstr": "アクティブ"},
        {"n": idx5["|Active"]["n"], "id": "Active", "msgstr": "有効"},
        {"n": idx5["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
        {"n": idx5["|Delete this item"]["n"], "id": "Delete this item", "msgstr": "この項目を削除"},
    ])
    r_on = collect(work5)
    rep_on = (work5 / "collect-report.txt").read_text(encoding="utf-8")
    r_off = collect(work5, "--no-check")
    rep_off = (work5 / "collect-report.txt").read_text(encoding="utf-8")
    check("[--no-check] 既定では ctx の不一致を CTX_MISMATCH で弾く",
          r_on.returncode == 3 and "CTX_MISMATCH" in rep_on, "rc=%d" % r_on.returncode)
    check("[--no-check] --no-check なら ctx 照合もしない",
          "CTX_MISMATCH" not in rep_off and r_off.returncode != 3,
          "rc=%d\n%s" % (r_off.returncode, rep_off[-400:]))

    # ============================ unverified_ctx が正しい候補に付く
    po, work6, idx6 = setup(tmp, "unverified")
    n_ctx6 = idx6["%s|Active" % CTX]["n"]
    n_free6 = idx6["|Active"]["n"]
    write_draft(work6, "translations_00.json", [
        {"n": n_ctx6, "id": "Active", "msgstr": "アクティブ"},                 # ctx 無し
        {"n": n_free6, "id": "Active", "ctx": "", "msgstr": "有効"},           # ctx あり
        {"n": idx6["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
        {"n": idx6["|Delete this item"]["n"], "id": "Delete this item", "msgstr": "この項目を削除"},
    ])
    # 同じ番号を再提出して「置き換え」を起こす(注記が末尾の別候補に付かないことの確認)
    write_draft(work6, "translations_00_2.json", [
        {"n": n_ctx6, "id": "Active", "msgstr": "アクティブ2"},
    ])
    r = collect(work6)
    cands = read_json(work6 / "manual.json").get("Active", [])
    by_ctx = {c["msgctxt"]: c for c in cands}
    check("[unverified_ctx] ctx の無い候補にだけ注記が付く",
          len(cands) == 2
          and by_ctx.get(CTX, {}).get("unverified_ctx")
          and not by_ctx.get("", {}).get("unverified_ctx"),
          json.dumps(cands, ensure_ascii=False))

    # ============================ entry_of は msgctxt も照合する
    po, work7, idx7 = setup(tmp, "entryof")
    ctx_item = idx7["%s|Active" % CTX]
    free_item = idx7["|Active"]
    raw = read_json(work7 / "chunks" / "chunk_00.json")
    for it in raw:
        if it["n"] == ctx_item["n"]:
            it["e"] = free_item["e"]        # 同じ msgid の別 msgctxt を指すよう壊す
    (work7 / "chunks" / "chunk_00.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    write_draft(work7, "translations_00.json", [
        {"n": ctx_item["n"], "id": "Active", "ctx": CTX, "msgstr": "アクティブ"},
        {"n": free_item["n"], "id": "Active", "msgstr": "有効"},
        {"n": idx7["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
        {"n": idx7["|Delete this item"]["n"], "id": "Delete this item", "msgstr": "この項目を削除"},
    ])
    r = collect(work7)
    cands7 = read_json(work7 / "manual.json").get("Active", [])
    check("[entry_of] e が別 msgctxt を指していても文脈が入れ替わらない",
          sorted(c["msgctxt"] for c in cands7) == ["", CTX]
          and "Traceback" not in (r.stderr or ""),
          "rc=%d cands=%s" % (r.returncode, json.dumps(cands7, ensure_ascii=False)))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
