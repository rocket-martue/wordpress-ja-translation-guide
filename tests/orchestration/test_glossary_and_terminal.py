# -*- coding: utf-8 -*-
"""Project Glossary の添付（正常系・絞り込み）と、終端記号の連続の検査。

用語集は「読めないとき traceback しない」だけでなく、**正常な用語集がちゃんとチャンクに載る**
ことも固定する。載らなくなる退行はチャンクを開くまで気付けないため。
"""
from __future__ import annotations

import csv
import io
import shutil
import tempfile
from pathlib import Path

from _harness import ROOT, Result, run  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check

PO = '''# glossary
msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: glossary\\n"

#: src/a.php:1
msgid "Save the widget layout"
msgstr ""

#: src/b.php:2
msgid "Delete this item"
msgstr ""
'''


def make_glossary(rows: list[tuple[str, str, str, str]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["en", "ja", "pos", "description"])
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def setup(tmp: Path, name: str, glossary: bytes | None = None):
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    po = d / (name + "-ja-untranslated.po")
    po.write_text(PO, encoding="utf-8")
    if glossary is not None:
        (d / (name + "-glossary.csv")).write_bytes(glossary)
    work = tmp / ("work-" + name)
    r = run(["scripts/po_chunk.py", str(po), "--outdir", str(work), "--no-ref"], check_rc=True)
    return work, (work / "chunks" / "chunk_00.md").read_text(encoding="utf-8"), r


tmp = Path(tempfile.mkdtemp(prefix="po-gloss-"))
try:
    # ============================== 正常な用語集が丸ごと載る（GLOSSARY_FULL_LIMIT 以下）
    small = make_glossary([
        ("widget", "ウィジェット", "noun", "管理画面の部品"),
        ("layout", "レイアウト", "noun", ""),
        ("item", "項目", "noun", ""),
    ])
    work, md, r = setup(tmp, "small", small)
    check("[用語集] 見出しがチャンクに載る",
          "## Project Glossary (small-glossary.csv)" in md, md[-600:])
    check("[用語集] 件数の注記が「全 N 語」になる",
          "全 3 語" in md, md[-600:])
    check("[用語集] CSV のヘッダーと全語が載る",
          "en,ja,pos,description" in md
          and "widget,ウィジェット" in md
          and "layout,レイアウト" in md
          and "item,項目" in md, md[-800:])
    check("[用語集] 読めたときは WARN を出さない",
          "WARN: glossary を読めません" not in (r.stdout or ""), (r.stdout or "")[:300])

    # ============================== CSV のクォートが壊れない（カンマ・引用符入り）
    quoted = make_glossary([
        ("widget", "ウィジェット", "noun", 'カンマ, と "引用符" を含む説明'),
    ])
    work2, md2, _ = setup(tmp, "quoted", quoted)
    body = md2[md2.index("```csv"):]
    rows = list(csv.reader(io.StringIO(body.split("```csv\n", 1)[1].split("```", 1)[0])))
    check("[用語集] カンマと引用符を含む説明が 1 フィールドとして復元できる",
          any(r_[0] == "widget" and r_[3] == 'カンマ, と "引用符" を含む説明' for r_ in rows if len(r_) >= 4),
          str(rows))

    # ============================== GLOSSARY_FULL_LIMIT 超えで絞り込む
    import po_chunk                                              # noqa: E402
    limit = po_chunk.GLOSSARY_FULL_LIMIT
    big_rows = [("widget", "ウィジェット", "noun", ""), ("layout", "レイアウト", "noun", "")]
    # 原文に出てこない語で水増しして上限を超えさせる
    big_rows += [("zzterm%03d" % i, "ダミー%03d" % i, "noun", "") for i in range(limit + 5)]
    work3, md3, _ = setup(tmp, "big", make_glossary(big_rows))
    check("[用語集] 上限超えでは「原文に出現する N 語」の注記になる",
          "このチャンクの原文に出現する" in md3, md3[-700:])
    check("[用語集] 上限超えでは原文に出る語だけ残る",
          "widget,ウィジェット" in md3 and "layout,レイアウト" in md3 and "zzterm001" not in md3,
          md3[-700:])

    # ============================== 用語集が無いときは節ごと出ない
    work4, md4, _ = setup(tmp, "none", None)
    check("[用語集] 用語集が無ければ Project Glossary の節を付けない",
          "## Project Glossary" not in md4, md4[-300:])

    # ============================== 終端記号の連続
    from po_collect import terminal_reason                       # noqa: E402
    check("[終端] 原文の `.` 1 個に対し `。。` を弾く",
          (terminal_reason("Save changes.", "変更を保存。。") or "").startswith("TERMINAL"),
          repr(terminal_reason("Save changes.", "変更を保存。。")))
    check("[終端] `。` 1 個は通る",
          terminal_reason("Save changes.", "変更を保存。") is None,
          repr(terminal_reason("Save changes.", "変更を保存。")))
    check("[終端] 原文の `:` 1 個に対し `::` を弾く",
          (terminal_reason("Required:", "必須::") or "").startswith("TERMINAL"),
          repr(terminal_reason("Required:", "必須::")))
    check("[終端] `:` 1 個は通る",
          terminal_reason("Required:", "必須:") is None,
          repr(terminal_reason("Required:", "必須:")))
    check("[終端] 原文が `::` なら訳文も `::` で通る",
          terminal_reason("Range::", "範囲::") is None,
          repr(terminal_reason("Range::", "範囲::")))
    check("[終端] 句点が無ければ従来どおり弾く",
          (terminal_reason("Save changes.", "変更を保存") or "").startswith("TERMINAL"),
          repr(terminal_reason("Save changes.", "変更を保存")))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
