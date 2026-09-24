# -*- coding: utf-8 -*-
"""po_apply_loop.py の突き合わせと失敗時の挙動(#31 の再現)。

A: msgctxt 違いで同じ msgid が複数あるエントリーには書き込まない(pool に 1 件しか無くても)
B: .po が読めないときは「完了」と言わず exit 2
C: --batch-size 0 は引数エラー(exit 2)
D: 書き込みに失敗しても送信分をまとめて blocked にしない(exit 2 で止まり、blocked.json は空)
E: 先頭 120 文字が同じ 2 つの msgid をどちらも正しく書く(取り違えて blocked にしない)
F: 先頭に訳の無いエントリーが batch-size 件以上並んでいても、後ろの pool 分を書き切る
G: msgctxt 違いの片方が翻訳済みでも、残った方に書かない(判定は全エントリーで行う)
H: apply の「インデックス "N": ...」形式のエラーも blocked に落とし、残りを送り切る
I: --max-batches に達したのに送れるものが残っていれば exit 2(完了扱いにしない)
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

from _harness import ROOT, Result, read_json, run, write_json  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check

HEADER = '''msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: apply-loop\\n"

'''

LONG = "This paragraph is intentionally long so that its first one hundred and twenty characters are shared with another one "


def entry(msgid: str, ctxt: str = "", loc: str = "src/a.php:1", msgstr: str = "") -> str:
    s = "#: %s\n" % loc
    if ctxt:
        s += 'msgctxt "%s"\n' % ctxt
    s += 'msgid "%s"\nmsgstr "%s"\n\n' % (msgid, msgstr)
    return s


IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0   # root は読み取り専用でも書けるので D は飛ばす


def msgstr_of(po: Path, msgid: str, ctxt: str = "") -> list[str]:
    """(msgctxt, msgid) に一致するエントリーの msgstr を全部返す。"""
    out = []
    lines = po.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line == 'msgid "%s"' % msgid:
            prev = lines[i - 1] if i else ""
            has_ctxt = prev.startswith("msgctxt")
            if (ctxt and prev == 'msgctxt "%s"' % ctxt) or (not ctxt and not has_ctxt):
                out.append(lines[i + 1])
    return out


def loop(po: Path, work: Path, *extra: str):
    return run(["scripts/po_apply_loop.py", str(po), "--outdir", str(work), *extra])


tmp = Path(tempfile.mkdtemp(prefix="po-apply-"))
try:
    # ============================ A: msgctxt 違いの同じ msgid
    po = tmp / "a.po"
    po.write_text(HEADER + entry("Settings") + entry("Settings", "verb", "src/b.php:2") + entry("Save changes", loc="src/c.php:3"),
                  encoding="utf-8")
    work = tmp / "work-a"
    write_json(work / "pool.json", {"Settings": "設定", "Save changes": "変更を保存"})
    r = loop(po, work)
    check("[A] exit 0", r.returncode == 0, r.stdout[-400:] + r.stderr[-400:])
    check("[A] msgid が一意なエントリーは書かれる", msgstr_of(po, "Save changes") == ['msgstr "変更を保存"'], str(msgstr_of(po, "Save changes")))
    check("[A] msgctxt 違いで複数ある msgid はどちらにも書かない",
          msgstr_of(po, "Settings") == ['msgstr ""'] and msgstr_of(po, "Settings", "verb") == ['msgstr ""'],
          "%r / %r" % (msgstr_of(po, "Settings"), msgstr_of(po, "Settings", "verb")))
    check("[A] blocked.json は空", read_json(work / "blocked.json") == [], str(read_json(work / "blocked.json")))
    check("[A] 送らなかった理由が出力に出る", "msgctxt" in r.stdout, r.stdout[-600:])

    # ============================ B: .po が読めない
    work = tmp / "work-b"
    write_json(work / "pool.json", {"Settings": "設定"})
    r = loop(tmp / "does-not-exist.po", work)
    check("[B] 存在しない .po は exit 2", r.returncode == 2, "rc=%d %s" % (r.returncode, r.stdout[-300:] + r.stderr[-300:]))
    check("[B] 「完了」と言わない", "完了" not in r.stdout, r.stdout[-300:])

    # ============================ C: --batch-size 0
    po = tmp / "c.po"
    po.write_text(HEADER + entry("Save changes"), encoding="utf-8")
    work = tmp / "work-c"
    write_json(work / "pool.json", {"Save changes": "変更を保存"})
    r = loop(po, work, "--batch-size", "0")
    check("[C] --batch-size 0 は exit 2", r.returncode == 2, "rc=%d %s" % (r.returncode, r.stderr[-300:]))
    check("[C] 何も書かれていない", msgstr_of(po, "Save changes") == ['msgstr ""'], str(msgstr_of(po, "Save changes")))

    # ============================ D: 書き込み失敗
    if IS_ROOT:
        print("SKIP [D] root では読み取り専用でも書けるので再現できない")
    else:
        po = tmp / "d.po"
        po.write_text(HEADER + entry("Save changes") + entry("Delete", loc="src/b.php:2"), encoding="utf-8")
        work = tmp / "work-d"
        write_json(work / "pool.json", {"Save changes": "変更を保存", "Delete": "削除"})
        os.chmod(po, stat.S_IREAD)
        try:
            r = loop(po, work)
        finally:
            os.chmod(po, stat.S_IREAD | stat.S_IWRITE)
        check("[D] 書き込みに失敗したら exit 2 で止まる", r.returncode == 2, "rc=%d %s" % (r.returncode, r.stdout[-500:]))
        check("[D] 送信分を blocked にしない", read_json(work / "blocked.json") == [], str(read_json(work / "blocked.json")))

    # ============================ E: 先頭 120 文字が同じ 2 つの msgid
    a_id = LONG + "alpha."
    b_id = LONG + "beta."
    po = tmp / "e.po"
    po.write_text(HEADER + entry(a_id) + entry(b_id, loc="src/b.php:2"), encoding="utf-8")
    work = tmp / "work-e"
    write_json(work / "pool.json", {a_id: "アルファ。", b_id: "ベータ。"})
    r = loop(po, work, "--batch-size", "5")
    check("[E] exit 0", r.returncode == 0, r.stdout[-500:])
    check("[E] 両方とも自分の訳が入る",
          msgstr_of(po, a_id) == ['msgstr "アルファ。"'] and msgstr_of(po, b_id) == ['msgstr "ベータ。"'],
          "%r / %r" % (msgstr_of(po, a_id), msgstr_of(po, b_id)))
    check("[E] blocked.json は空", read_json(work / "blocked.json") == [], str(read_json(work / "blocked.json")))

    # ============================ F: 先頭に訳の無いエントリーが並ぶ
    po = tmp / "f.po"
    po.write_text(HEADER + entry("Hold one") + entry("Hold two", loc="src/b.php:2") + entry("Hold three", loc="src/c.php:3")
                  + entry("Save changes", loc="src/d.php:4") + entry("Delete", loc="src/e.php:5"), encoding="utf-8")
    work = tmp / "work-f"
    write_json(work / "pool.json", {"Save changes": "変更を保存", "Delete": "削除"})
    r = loop(po, work, "--batch-size", "2")
    check("[F] exit 0", r.returncode == 0, r.stdout[-500:])
    check("[F] 先頭の訳無しを飛ばして後ろの pool 分を書き切る",
          msgstr_of(po, "Save changes") == ['msgstr "変更を保存"'] and msgstr_of(po, "Delete") == ['msgstr "削除"'],
          "%r / %r" % (msgstr_of(po, "Save changes"), msgstr_of(po, "Delete")))
    check("[F] 訳の無いものは未翻訳のまま", msgstr_of(po, "Hold one") == ['msgstr ""'], str(msgstr_of(po, "Hold one")))
    check("[F] 送らなかった理由の一覧に訳の無い 3 件が全部出る",
          r.stdout.count("Hold ") == 3, r.stdout[-700:])

    # ============================ G: msgctxt 違いの片方が翻訳済み
    po = tmp / "g.po"
    po.write_text(HEADER + entry("Settings", msgstr="設定") + entry("Settings", "verb", "src/b.php:2")
                  + entry("Save changes", loc="src/c.php:3"), encoding="utf-8")
    work = tmp / "work-g"
    write_json(work / "pool.json", {"Settings": "設定する", "Save changes": "変更を保存"})
    r = loop(po, work)
    check("[G] exit 0", r.returncode == 0, r.stdout[-400:])
    check("[G] 翻訳済みの変種がある msgid には書かない",
          msgstr_of(po, "Settings", "verb") == ['msgstr ""'], str(msgstr_of(po, "Settings", "verb")))
    check("[G] 一意な msgid は書かれる", msgstr_of(po, "Save changes") == ['msgstr "変更を保存"'], str(msgstr_of(po, "Save changes")))

    # ============================ H: 引用符付きのインデックスエラー(msgstr が空)
    po = tmp / "h.po"
    po.write_text(HEADER + entry("One") + entry("Two", loc="src/b.php:2") + entry("Three", loc="src/c.php:3"), encoding="utf-8")
    work = tmp / "work-h"
    write_json(work / "pool.json", {"One": "", "Two": "二", "Three": "三"})
    r = loop(po, work, "--batch-size", "1")
    check("[H] exit 0", r.returncode == 0, r.stdout[-600:])
    check("[H] 空の訳文は blocked に落ちる", read_json(work / "blocked.json") == ["One"], str(read_json(work / "blocked.json")))
    check("[H] 残りは送り切る",
          msgstr_of(po, "Two") == ['msgstr "二"'] and msgstr_of(po, "Three") == ['msgstr "三"'],
          "%r / %r" % (msgstr_of(po, "Two"), msgstr_of(po, "Three")))

    # ============================ I: --max-batches に達した
    po = tmp / "i.po"
    po.write_text(HEADER + entry("One") + entry("Two", loc="src/b.php:2") + entry("Three", loc="src/c.php:3"), encoding="utf-8")
    work = tmp / "work-i"
    write_json(work / "pool.json", {"One": "一", "Two": "二", "Three": "三"})
    r = loop(po, work, "--batch-size", "1", "--max-batches", "1")
    check("[I] 送れるものが残っていれば exit 2", r.returncode == 2, "rc=%d %s" % (r.returncode, r.stdout[-400:]))
    check("[I] 1 バッチ分は書かれている", msgstr_of(po, "One") == ['msgstr "一"'], str(msgstr_of(po, "One")))
    check("[I] max-batches 到達が出力に出る", "max-batches" in r.stdout, r.stdout[-400:])
    r = loop(po, work, "--batch-size", "1", "--max-batches", "5")
    check("[I] 再実行で送り切って exit 0", r.returncode == 0 and msgstr_of(po, "Three") == ['msgstr "三"'], r.stdout[-400:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
