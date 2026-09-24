# -*- coding: utf-8 -*-
"""番号ズレ由来の rework を書き戻したあと、再実行で同じ rework が再生成されない(#32 の再現)。

A: id を入れ替えたドラフト → rework → 正しい答え → 書き戻し後の通常ドラフトは id も直っている
B: 3 回目の po_collect.py が exit 0 で、rework_01 が作られない
C: msgctxt 違いの同じ msgid で ctx を入れ替えたドラフトも同じ(書き戻しで ctx が直る)
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from _harness import ROOT, Result, chunk_index, read_json, run, write_draft  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check

PO = '''msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: writeback\\n"

#: src/a.php:1
msgid "Delete"
msgstr ""

#: src/b.php:2
msgid "Save changes"
msgstr ""

#: src/c.php:3
msgctxt "noun"
msgid "Filter"
msgstr ""

#: src/d.php:4
msgctxt "verb"
msgid "Filter"
msgstr ""
'''


def collect(work: Path):
    return run(["scripts/po_collect.py", "--outdir", str(work)])


def n_of(idx: dict, ctxt: str, msgid: str) -> int:
    return idx["%s|%s" % (ctxt, msgid)]["n"]


tmp = Path(tempfile.mkdtemp(prefix="po-wb-"))
try:
    po = tmp / "wb.po"
    po.write_text(PO, encoding="utf-8")
    work = tmp / "work"
    run(["scripts/po_chunk.py", str(po), "--outdir", str(work), "--no-ref"], check_rc=True)
    idx = chunk_index(work)
    n_del, n_save = n_of(idx, "", "Delete"), n_of(idx, "", "Save changes")
    n_noun, n_verb = n_of(idx, "noun", "Filter"), n_of(idx, "verb", "Filter")

    # id を入れ替え、ctx も入れ替えたドラフト(番号ズレの疑い → rework)
    write_draft(work, "translations_00.json", [
        {"n": n_del, "id": "Save changes", "msgstr": "削除"},
        {"n": n_save, "id": "Delete", "msgstr": "変更を保存"},
        {"n": n_noun, "id": "Filter", "ctx": "verb", "msgstr": "フィルター"},
        {"n": n_verb, "id": "Filter", "ctx": "noun", "msgstr": "絞り込む"},
    ])
    r1 = collect(work)
    rw = read_json(work / "rework.json")
    check("[A] 1 回目: 番号ズレで rework(exit 3)", r1.returncode == 3 and rw["chunks"] == ["rework_00"],
          "rc=%d chunks=%r" % (r1.returncode, rw.get("chunks")))

    # rework チャンクに正しい答えを書く
    ridx = chunk_index(work, "rework_00")
    answer = []
    for key, it in ridx.items():
        ctxt, mid = key.split("|", 1)
        mstr = {"Delete": "削除", "Save changes": "変更を保存"}.get(mid) or ("フィルター" if ctxt == "noun" else "絞り込む")
        item = {"n": it["n"], "id": mid[:30], "msgstr": mstr}
        if ctxt:
            item["ctx"] = ctxt
        answer.append(item)
    write_draft(work, "translations_rework_00.json", answer)
    r2 = collect(work)
    check("[A] 2 回目: rework が通って exit 0", r2.returncode == 0, "rc=%d\n%s" % (r2.returncode, r2.stdout[-800:]))
    check("[A] rework ドラフトは consumed/ へ", (work / "drafts" / "consumed" / "translations_rework_00.json").is_file(),
          str(sorted(p.name for p in (work / "drafts").rglob("*.json"))))

    draft = {it["n"]: it for it in read_json(work / "drafts" / "translations_00.json")}
    check("[A] 書き戻し後の通常ドラフトは id が直っている",
          draft[n_del]["id"] == "Delete" and draft[n_save]["id"] == "Save changes",
          json.dumps([draft[n_del], draft[n_save]], ensure_ascii=False))
    check("[C] 書き戻し後の通常ドラフトは ctx が直っている",
          draft[n_noun].get("ctx") == "noun" and draft[n_verb].get("ctx") == "verb",
          json.dumps([draft[n_noun], draft[n_verb]], ensure_ascii=False))
    check("[A] 訳文も書き戻されている",
          draft[n_del]["msgstr"] == "削除" and draft[n_save]["msgstr"] == "変更を保存",
          json.dumps([draft[n_del], draft[n_save]], ensure_ascii=False))

    # 3 回目(別チャンクの回収などで再実行): 同じエントリーが再び rework にならない
    r3 = collect(work)
    rw3 = read_json(work / "rework.json")
    check("[B] 3 回目: exit 0 で rework が再生成されない",
          r3.returncode == 0 and rw3["chunks"] == [] and not (work / "chunks" / "rework_01.md").exists(),
          "rc=%d chunks=%r\n%s" % (r3.returncode, rw3.get("chunks"), r3.stdout[-600:]))
    pool = read_json(work / "pool.json")
    manual = read_json(work / "manual.json")
    check("[B] pool と manual が揃っている",
          pool.get("Delete") == "削除" and pool.get("Save changes") == "変更を保存" and len(manual.get("Filter", [])) == 2,
          json.dumps({"pool": pool, "manual": manual}, ensure_ascii=False)[:500])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
