# -*- coding: utf-8 -*-
"""対応表からのエントリー一意引き、再投入の並び順、id 照合の空白。

Copilot 8 回目レビューの 5 指摘の再現と確認。

F: rework チャンクが、NG になったエントリーの kind / translators / msgctxt を引き継ぐ
G: 旧形式ドラフトで、後から NG が出ても ambiguous 候補を消さない
H: msgctxt 違いで複数形原文が違うとき、該当エントリーの複数形で機械チェックする
I: 再投入が 2 桁(_10)になっても後勝ちの順序が保たれる
J: 原文に空白の連続があっても、契約どおりの id が ID_MISMATCH にならない
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from _harness import ROOT, Result, run, write_draft  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check
draft = write_draft

sys.path.insert(0, str(ROOT / "scripts"))

# 同じ msgid "Item" を、msgctxt / kind / translators / msgid_plural が違う 2 エントリーで持つ
PO = '''# round8
msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: round8\\n"

#. translators: %d: number of files.
#: src/a.php:1
msgctxt "file counter"
msgid "%d Item"
msgid_plural "%d Items"
msgstr[0] ""

#. translators: %d: number of users.
#: src/b.php:2
msgid "%d Item"
msgid_plural "%d Users selected"
msgstr[0] ""

#: src/c.php:3
msgid "Feature:    value    and    more"
msgstr ""

#: src/d.php:4
msgid "Save changes"
msgstr ""
'''

def setup(tmp: Path, name: str):
    po = tmp / (name + ".po")
    po.write_text(PO, encoding="utf-8")
    work = tmp / ("work-" + name)
    run(["scripts/po_chunk.py", str(po), "--outdir", str(work), "--no-ref"], check_rc=True)
    idx = json.loads((work / "chunks" / "chunk_00.json").read_text(encoding="utf-8"))
    return work, {"%s|%s" % (it.get("msgctxt", ""), it["msgid"]): it for it in idx}


tmp = Path(tempfile.mkdtemp(prefix="po-r8-"))
try:
    # ================================================== J: id 照合(単体)
    from po_collect import id_reason, draft_sort_key       # noqa: E402
    mid = "Feature:    value    and    more"
    check("[J] 契約どおり(空白そのまま)の id が通る",
          id_reason(mid.strip()[:30], mid, 1) is None, repr(id_reason(mid.strip()[:30], mid, 1)))
    check("[J] 空白を詰めて書いた id も引き続き通る",
          id_reason("Feature: value and more", mid, 1) is None,
          repr(id_reason("Feature: value and more", mid, 1)))
    check("[J] 別の msgid の id は従来どおり弾く",
          (id_reason("Save changes", "Save", 1) or "").startswith("ID_MISMATCH"),
          repr(id_reason("Save changes", "Save", 1)))
    check("[J] タブ・改行入りの msgid でも契約どおりの id が通る",
          id_reason("Line one\n\n\tLine two continues here".strip()[:30],
                    "Line one\n\n\tLine two continues here", 1) is None,
          repr(id_reason("Line one\n\n\tLine two continues here".strip()[:30],
                         "Line one\n\n\tLine two continues here", 1)))

    # ================================================== I: 並び順(単体)
    names = ["translations_00.json", "translations_00_2.json", "translations_00_10.json",
             "translations_01.json", "translations_rework_00.json", "translations_rework_00_2.json"]
    got = [n for n in sorted(names, key=draft_sort_key)]
    check("[I] _10 が _2 より後、rework は最後",
          got == ["translations_00.json", "translations_00_2.json", "translations_00_10.json",
                  "translations_01.json", "translations_rework_00.json", "translations_rework_00_2.json"],
          str(got))

    # ================================================== I: 実際に後勝ちになる
    work, idx = setup(tmp, "order")
    n_save = idx["|Save changes"]["n"]
    draft(work, "translations_00.json", [{"n": n_save, "id": "Save changes", "msgstr": "初回"}])
    draft(work, "translations_00_2.json", [{"n": n_save, "id": "Save changes", "msgstr": "2 回目"}])
    draft(work, "translations_00_10.json", [{"n": n_save, "id": "Save changes", "msgstr": "10 回目"}])
    r = run(["scripts/po_collect.py", "--outdir", str(work)])
    pool = json.loads((work / "pool.json").read_text(encoding="utf-8"))
    check("[I] 一番新しい再投入(_10)の訳が残る",
          pool.get("Save changes") == "10 回目",
          "rc=%d pool=%s" % (r.returncode, json.dumps(pool, ensure_ascii=False)))

    # ================================================== H: エントリーごとの複数形で判定
    work2, idx2 = setup(tmp, "plural")
    n_file = idx2["file counter|%d Item"]["n"]
    n_user = idx2["|%d Item"]["n"]
    check("[H] チャンク対応表がエントリーごとの msgid_plural を持つ",
          idx2["file counter|%d Item"]["msgid_plural"] == "%d Items"
          and idx2["|%d Item"]["msgid_plural"] == "%d Users selected",
          json.dumps([idx2["file counter|%d Item"], idx2["|%d Item"]], ensure_ascii=False))
    check("[H] チャンク対応表が entries.json 内の位置(e)を持つ",
          isinstance(idx2["file counter|%d Item"].get("e"), int)
          and idx2["file counter|%d Item"]["e"] != idx2["|%d Item"]["e"],
          json.dumps([idx2["file counter|%d Item"], idx2["|%d Item"]], ensure_ascii=False))
    draft(work2, "translations_00.json", [
        {"n": n_file, "id": "%d Item", "msgstr": "%d件のファイル"},
        {"n": n_user, "id": "%d Item", "msgstr": "%d人のユーザーを選択"},
        {"n": idx2["|Feature:    value    and    more"]["n"],
         "id": "Feature:    value    and    more".strip()[:30], "msgstr": "機能: 値とその他"},
        {"n": idx2["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work2)])
    rep = (work2 / "collect-report.txt").read_text(encoding="utf-8")
    manual2 = json.loads((work2 / "manual.json").read_text(encoding="utf-8"))
    check("[H] 2 エントリーとも機械チェックを通り manual に 2 件そろう",
          r.returncode == 0 and len(manual2.get("%d Item", [])) == 2,
          "rc=%d manual=%s\n%s" % (r.returncode, json.dumps(manual2, ensure_ascii=False), rep))
    check("[J] 空白の連続を含む msgid が ID_MISMATCH にならない",
          "ID_MISMATCH" not in rep, rep)

    # ================================================== F: rework チャンクが正しいエントリーを使う
    work3, idx3 = setup(tmp, "reworkmeta")
    n_file3 = idx3["file counter|%d Item"]["n"]
    n_user3 = idx3["|%d Item"]["n"]
    draft(work3, "translations_00.json", [
        {"n": n_file3, "id": "%d Item", "msgstr": "%d件のファイル"},
        {"n": n_user3, "id": "%d Item", "msgstr": "%d人のユーザーを選択。"},     # TERMINAL NG(msgctxt 無しの方)
        {"n": idx3["|Feature:    value    and    more"]["n"],
         "id": "Feature:    value    and    more".strip()[:30], "msgstr": "機能: 値とその他"},
        {"n": idx3["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work3)])
    rw = json.loads((work3 / "rework.json").read_text(encoding="utf-8"))
    rwname = rw["chunks"][0]
    rwmd = (work3 / "chunks" / (rwname + ".md")).read_text(encoding="utf-8")
    rwidx = json.loads((work3 / "chunks" / (rwname + ".json")).read_text(encoding="utf-8"))
    check("[F] rework チャンクが NG エントリーの translators を載せる",
          "translators: %d: number of users." in rwmd, rwmd)
    check("[F] rework チャンクに別エントリーの translators / msgctxt が出ない",
          "number of files" not in rwmd and "msgctxt:" not in rwmd, rwmd)
    check("[F] rework チャンクが NG エントリーの複数形原文を載せる",
          "%d Users selected" in rwmd and "%d Items" not in rwmd, rwmd)
    check("[F] rework チャンク対応表の msgid_plural も NG エントリーのもの",
          rwidx[0].get("msgid_plural") == "%d Users selected", json.dumps(rwidx, ensure_ascii=False))

    # entry_of は msgctxt も照合するので、rework 記録から msgctxt を渡していないと必ず不一致になり、
    # entries_by_msgid の**先頭**エントリーへ落ちる。これを検出するには、NG にするエントリーが
    # その msgid の先頭でない並びにする(先頭だとフォールバックしても同じ物を掴んで素通りする)
    po_rev = tmp / "ctxsecond.po"
    po_rev.write_text(PO.replace(
        '''#. translators: %d: number of files.
#: src/a.php:1
msgctxt "file counter"
msgid "%d Item"
msgid_plural "%d Items"
msgstr[0] ""

#. translators: %d: number of users.
#: src/b.php:2
msgid "%d Item"
msgid_plural "%d Users selected"
msgstr[0] ""''',
        '''#. translators: %d: number of users.
#: src/b.php:2
msgid "%d Item"
msgid_plural "%d Users selected"
msgstr[0] ""

#. translators: %d: number of files.
#: src/a.php:1
msgctxt "file counter"
msgid "%d Item"
msgid_plural "%d Items"
msgstr[0] ""'''), encoding="utf-8")
    work3b = tmp / "work-ctxsecond"
    run(["scripts/po_chunk.py", str(po_rev), "--outdir", str(work3b), "--no-ref"], check_rc=True)
    idx3b = {"%s|%s" % (it.get("msgctxt", ""), it["msgid"]): it
             for it in json.loads((work3b / "chunks" / "chunk_00.json").read_text(encoding="utf-8"))}
    ent3b = [e for e in json.loads((work3b / "entries.json").read_text(encoding="utf-8"))
             if e["msgid"] == "%d Item"]
    check("[F] 前提: entries.json では msgctxt 無しの方が先頭",
          ent3b[0].get("msgctxt", "") == "", str([e.get("msgctxt") for e in ent3b]))
    draft(work3b, "translations_00.json", [
        {"n": idx3b["file counter|%d Item"]["n"], "id": "%d Item", "ctx": "file counter",
         "msgstr": "%d件のファイル。"},                                  # TERMINAL NG(先頭でない方)
        {"n": idx3b["|%d Item"]["n"], "id": "%d Item", "msgstr": "%d人のユーザーを選択"},
        {"n": idx3b["|Feature:    value    and    more"]["n"],
         "id": "Feature:    value    and    more".strip()[:30], "msgstr": "機能: 値とその他"},
        {"n": idx3b["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    run(["scripts/po_collect.py", "--outdir", str(work3b)])
    rw3b = json.loads((work3b / "rework.json").read_text(encoding="utf-8"))["chunks"][0]
    md3b = (work3b / "chunks" / (rw3b + ".md")).read_text(encoding="utf-8")
    check("[F] NG が先頭でない msgctxt 付きエントリーでも、そのエントリーのメタデータで作る",
          "translators: %d: number of files." in md3b
          and "%d Items" in md3b
          and "number of users" not in md3b and "%d Users selected" not in md3b,
          md3b)

    # ================================================== G: 旧形式の ambiguous 候補を消さない
    work4, _ = setup(tmp, "legacydrop")
    draft(work4, "translations_00.json", [
        {"msgid": "%d Item", "msgstr": "%d件のファイル"},           # 通る
        {"msgid": "%d Item", "msgstr": "%d人のユーザーを選択。"},    # TERMINAL NG
        {"msgid": "Feature:    value    and    more", "msgstr": "機能: 値とその他"},
        {"msgid": "Save changes", "msgstr": "変更を保存"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work4)])
    manual4 = json.loads((work4 / "manual.json").read_text(encoding="utf-8"))
    c4 = manual4.get("%d Item", [])
    check("[G] 後から NG が出ても先に集めた ambiguous 候補が残る",
          len(c4) == 1 and c4[0]["msgstr"] == "%d件のファイル" and c4[0].get("ambiguous"),
          "rc=%d manual=%s" % (r.returncode, json.dumps(manual4, ensure_ascii=False)))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
