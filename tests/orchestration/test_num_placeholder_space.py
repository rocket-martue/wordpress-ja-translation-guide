# -*- coding: utf-8 -*-
"""PH_NUM_SPACE: translators コメントから数値に置き換わると分かる %s 系プレースホルダーの前後スペース。

`validate_po.py` の NUM_SPACING は `%d` 系しか見ないので、`Showing %1$s of the %2$s`
(translators: 1: how many comments are listed, 2: how many will be deleted.)の訳文が
`%2$s件中 %1$s件` でも素通りしていた。下訳でこの形が繰り返し出た。

判定は translators を番号ごとの区間に切って行う。date / name の %s を数値扱いしない。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from _harness import ROOT, Result, chunk_index, run, write_draft  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check

sys.path.insert(0, str(ROOT / "scripts"))
from po_collect import num_space_reason, numeric_placeholders  # noqa: E402

# ================================================== 単体: どのプレースホルダーを数値扱いにするか
TR_SHOWING = "1: how many comments are listed, 2: how many will be deleted."
TR_ATTEMPTS = "1: number of blocked attempts, 2: date counting started."

check("[数値判定] `1:` `2:` で区切られた translators は番号ごとに見る(両方 how many → 両方数値)",
      numeric_placeholders("Showing %1$s of the %2$s, newest first:", TR_SHOWING) == ["%1$s", "%2$s"],
      repr(numeric_placeholders("Showing %1$s of the %2$s, newest first:", TR_SHOWING)))
check("[数値判定] number の %1$s だけ数値。date の %2$s は含めない",
      numeric_placeholders("%1$s attempts blocked since %2$s.", TR_ATTEMPTS) == ["%1$s"],
      repr(numeric_placeholders("%1$s attempts blocked since %2$s.", TR_ATTEMPTS)))
check("[数値判定] `%s: number of days.` は無番号 %s を数値扱い",
      numeric_placeholders("%s day", "%s: number of days.") == ["%s"],
      repr(numeric_placeholders("%s day", "%s: number of days.")))
check("[数値判定] name / file name / theme name は数値にしない",
      numeric_placeholders("Blocked: %s", "%s: name of the blocked request type.") == []
      and numeric_placeholders("%s (not in the active theme)", "%s: page template file name.") == []
      and numeric_placeholders("%1$s = %2$s", "%1$s = week id (YYYY-WW), %2$s = week starting YYYY-MM-DD") == [],
      "name 系が数値扱いになっている")
check("[数値判定] translators が無ければ判定しない",
      numeric_placeholders("%s items", "") == [], repr(numeric_placeholders("%s items", "")))
check("[数値判定] 言及が無くても %s が 1 個だけなら translators 全体で判定する",
      numeric_placeholders("%s day", "Number of days since the last backup.") == ["%s"]
      and numeric_placeholders("%1$s of %2$s", "Number of items shown and total.") == [],
      "1 個だけの規則が崩れている")

# ================================================== 単体: スペースの判定
NG = "%2$s件中 %1$s件を新しい順に表示:"
OK = "全%2$s件のうち%1$s件を新しい順に表示:"
check("[スペース] `%2$s件中 %1$s件` を PH_NUM_SPACE で弾く",
      (num_space_reason("Showing %1$s of the %2$s, newest first:", NG, TR_SHOWING) or "").startswith("PH_NUM_SPACE"),
      repr(num_space_reason("Showing %1$s of the %2$s, newest first:", NG, TR_SHOWING)))
check("[スペース] 両側スペース `%2$s 件中 %1$s 件` も弾く",
      (num_space_reason("Showing %1$s of the %2$s, newest first:", "%2$s 件中 %1$s 件を新しい順に表示:", TR_SHOWING) or "").startswith("PH_NUM_SPACE"),
      "両側スペースが通っている")
check("[スペース] `全%2$s件のうち%1$s件` は通る",
      num_space_reason("Showing %1$s of the %2$s, newest first:", OK, TR_SHOWING) is None,
      repr(num_space_reason("Showing %1$s of the %2$s, newest first:", OK, TR_SHOWING)))
check("[スペース] `%s 日` は弾き、`%s日` は通る",
      (num_space_reason("%s day", "%s 日", "%s: number of days.") or "").startswith("PH_NUM_SPACE")
      and num_space_reason("%s day", "%s日", "%s: number of days.") is None,
      "%r / %r" % (num_space_reason("%s day", "%s 日", "%s: number of days."),
                   num_space_reason("%s day", "%s日", "%s: number of days.")))
check("[スペース] date の %2$s の前後スペースは咎めず、number の %1$s だけ見る",
      num_space_reason("%1$s attempts blocked since %2$s.", "%2$s 以降、%1$s回の試行をブロックしました。", TR_ATTEMPTS) is None
      and (num_space_reason("%1$s attempts blocked since %2$s.", "%2$s 以降、%1$s 回の試行をブロックしました。", TR_ATTEMPTS) or "").startswith("PH_NUM_SPACE"),
      "date / number の区別が崩れている")
check("[スペース] 文字列の %s(`%s を削除` の形)は通る",
      num_space_reason("Delete %s", "%s を削除", "%s: name of the item.") is None,
      repr(num_space_reason("Delete %s", "%s を削除", "%s: name of the item.")))
check("[スペース] 半角記号の隣のスペースは咎めない(`件数: %1$s`、`(%1$s)`)",
      num_space_reason("Count: %1$s", "件数: %1$s", "1: number of items.") is None
      and num_space_reason("(%1$s)", "(%1$s)", "1: number of items.") is None,
      "半角記号の隣で誤検出している")
check("[スペース] translators が無ければ `%s 日` でも判定しない",
      num_space_reason("%s day", "%s 日", "") is None,
      repr(num_space_reason("%s day", "%s 日", "")))

# ================================================== 統合: po_collect.py を通す
PO = '''# numspace
msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: numspace\\n"

#. translators: %s: number of days.
#: src/a.php:1
msgid "%s day"
msgstr ""

#. translators: 1: number of blocked attempts, 2: date counting started.
#: src/b.php:2
msgid "%1$s attempts blocked since %2$s."
msgstr ""

#: src/c.php:3
msgid "Save changes"
msgstr ""
'''


def setup(tmp: Path, name: str):
    po = tmp / (name + ".po")
    po.write_text(PO, encoding="utf-8")
    work = tmp / ("work-" + name)
    run(["scripts/po_chunk.py", str(po), "--outdir", str(work), "--no-ref"], check_rc=True)
    return work, chunk_index(work)


tmp = Path(tempfile.mkdtemp(prefix="po-numspace-"))
try:
    work, idx = setup(tmp, "ng")
    n_day = idx["|%s day"]["n"]
    n_att = idx["|%1$s attempts blocked since %2$s."]["n"]
    n_save = idx["|Save changes"]["n"]
    write_draft(work, "translations_00.json", [
        {"n": n_day, "id": "%s day", "msgstr": "%s 日"},
        {"n": n_att, "id": "%1$s attempts blocked since %2$s."[:30], "msgstr": "%2$s 以降、%1$s回の試行をブロックしました。"},
        {"n": n_save, "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work)])
    rework = json.loads((work / "rework.json").read_text(encoding="utf-8")).get("items", [])
    pool = json.loads((work / "pool.json").read_text(encoding="utf-8"))
    rep = (work / "collect-report.txt").read_text(encoding="utf-8")
    hit = [v for v in rework if v.get("msgid") == "%s day"]
    check("[統合] `%s 日` は rework(exit 3)になり、理由が PH_NUM_SPACE",
          r.returncode == 3 and len(rework) == 1 and len(hit) == 1 and "PH_NUM_SPACE" in hit[0].get("reason", ""),
          "rc=%d rework=%s\n%s" % (r.returncode, [v.get("msgid") for v in rework], rep[:400]))
    check("[統合] date の %2$s にスペースがある訳文と、プレースホルダーの無い訳文は pool に入る",
          pool.get("%1$s attempts blocked since %2$s.") == "%2$s 以降、%1$s回の試行をブロックしました。"
          and pool.get("Save changes") == "変更を保存",
          json.dumps(pool, ensure_ascii=False)[:300])
    check("[統合] rework チャンクの reason: 行に PH_NUM_SPACE が載る",
          any("PH_NUM_SPACE" in p.read_text(encoding="utf-8") for p in (work / "chunks").glob("rework_*.md")),
          str(sorted(p.name for p in (work / "chunks").glob("rework_*.md"))))

    work2, idx2 = setup(tmp, "ok")
    write_draft(work2, "translations_00.json", [
        {"n": idx2["|%s day"]["n"], "id": "%s day", "msgstr": "%s日"},
        {"n": idx2["|%1$s attempts blocked since %2$s."]["n"], "id": "%1$s attempts blocked since %2$s."[:30],
         "msgstr": "%2$s 以降、%1$s回の試行をブロックしました。"},
        {"n": idx2["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r2 = run(["scripts/po_collect.py", "--outdir", str(work2)])
    pool2 = json.loads((work2 / "pool.json").read_text(encoding="utf-8"))
    check("[統合] スペースを詰めた訳文は exit 0 で pool 3 件",
          r2.returncode == 0 and len(pool2) == 3,
          "rc=%d pool=%d\n%s" % (r2.returncode, len(pool2), (work2 / "collect-report.txt").read_text(encoding="utf-8")[:300]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
