# -*- coding: utf-8 -*-
"""msgid / msgstr に生の行区切り文字(U+2028 など)を含むエントリーが見えなくなる(#40 の再現)。

`str.splitlines()` は `\\n` のほかに U+2028 / U+2029 / U+0085 / `\\x0b` / `\\x0c` / `\\x1c`〜`\\x1e`
でも行を区切る。`.po` の行分割に使うと、これらを生のまま含む文字列が途中で切れ、
`msgid "..."` の形に一致しなくなって、エントリーごとパーサーから見えなくなる。

A: apply_translations.py --list が、該当エントリーを未翻訳として数える
B: po_chunk.py が、該当エントリーをチャンクに入れる(msgid の文字はそのまま)
C: validate_po.parse_po が、該当エントリーを検査対象として返す
D: apply_translations.py が、該当エントリーとその後ろのエントリーの両方に正しく書き込む
E: fix_spacing.py が、該当文字を含む msgstr を直し、改行コード(CRLF)と該当文字を保つ
F: 該当文字を含まない .po では、行数と行番号が変わらない
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from _harness import ROOT, Result, read_json, run  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check

sys.path.insert(0, str(ROOT / "scripts"))

HEADER = '''msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: linesep\\n"

'''

# str.splitlines() が行の区切りとして扱う文字のうち、\n / \r 以外のもの。
# ソースにも生の文字を置かない(エディタや差分表示で行が割れる)ので chr() で作る。
# ラベルに生の文字を出すと run_all.py の集計(これも行単位で読む)が崩れるので、名前で表示する
SEPARATORS = {
    "U+2028": chr(0x2028),
    "U+2029": chr(0x2029),
    "U+0085": chr(0x85),
    "U+000B": chr(0x0B),
    "U+000C": chr(0x0C),
    "U+001C": chr(0x1C),
    "U+001D": chr(0x1D),
    "U+001E": chr(0x1E),
}


def untranslated_po(sep: str) -> str:
    """該当文字を 2 つ続けて含むエントリーと、その後ろに普通のエントリーを 1 件。"""
    return HEADER + (
        '#: src/a.php:1\n'
        'msgid "First sentence.%s%sSecond sentence follows."\n'
        'msgstr ""\n'
        '\n'
        '#: src/b.php:2\n'
        'msgid "Delete"\n'
        'msgstr ""\n'
    ) % (sep, sep)


def write_po(path: Path, text: str, newline: str = "\n") -> None:
    """改行コードを指定して書く(write_text は Windows で \\n を \\r\\n に変えるため bytes で書く)。"""
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def read_po(path: Path) -> str:
    """改行コードを変換せずに読む。"""
    return path.read_bytes().decode("utf-8")


tmp = Path(tempfile.mkdtemp(prefix="po-ls-"))
try:
    import apply_translations as at  # noqa: E402
    import validate_po as vp  # noqa: E402

    # ============================ A: --list
    for name, sep in SEPARATORS.items():
        po = tmp / ("a-%s-ja-untranslated.po" % name.replace("+", ""))
        write_po(po, untranslated_po(sep))
        r = run(["scripts/apply_translations.py", str(po), "--list"])
        check("[A] --list が %s を含むエントリーを未翻訳として数える" % name,
              r.returncode == 0 and "全 2 件" in r.stdout, (r.stdout + r.stderr)[:200].replace(sep, "<sep>"))

    sep = SEPARATORS["U+2028"]
    msgid = "First sentence.%s%sSecond sentence follows." % (sep, sep)

    # ============================ B: po_chunk
    po = tmp / "b-ja-untranslated.po"
    write_po(po, untranslated_po(sep))
    work = tmp / "work-b"
    run(["scripts/po_chunk.py", str(po), "--outdir", str(work), "--no-ref"], check_rc=True)
    entries = read_json(work / "entries.json")
    check("[B] po_chunk が U+2028 を含むエントリーを落とさない", len(entries) == 2, "%d 件" % len(entries))
    check("[B] entries.json の msgid に U+2028 がそのまま残る",
          any(e["msgid"] == msgid for e in entries),
          json.dumps([e["msgid"] for e in entries], ensure_ascii=True))
    chunk = read_json(work / "chunks" / "chunk_00.json")
    check("[B] チャンクにも U+2028 を含むエントリーが入る",
          any(it["msgid"] == msgid for it in chunk),
          json.dumps([it["msgid"] for it in chunk], ensure_ascii=True))
    first = next((e for e in entries if e["msgid"] == msgid), None)
    check("[B] U+2028 を含むエントリーが自分の location を持つ",
          first is not None and first["location"] == "src/a.php:1", json.dumps(first, ensure_ascii=True))

    # ============================ C: validate_po.parse_po
    parsed = vp.parse_po(untranslated_po(sep))
    check("[C] parse_po が U+2028 を含むエントリーを返す",
          [e.msgid for e in parsed] == [msgid, "Delete"],
          json.dumps([e.msgid for e in parsed], ensure_ascii=True))
    check("[C] 後ろのエントリーの行番号がファイル上の行と一致する",
          len(parsed) == 2 and untranslated_po(sep).split("\n")[parsed[1].line - 1] == 'msgid "Delete"',
          repr([e.line for e in parsed]))

    # ============================ D: 書き込み
    po = tmp / "d-ja-untranslated.po"
    write_po(po, untranslated_po(sep))
    payload = json.dumps({
        "0": {"msgid": msgid, "msgstr": "最初の文です。次の文が続きます。"},
        "1": {"msgid": "Delete", "msgstr": "削除"},
    }, ensure_ascii=False)
    r = run(["scripts/apply_translations.py", str(po), payload])
    check("[D] U+2028 を含むエントリーと後ろのエントリーに書き込める", r.returncode == 0, (r.stdout + r.stderr)[:300])
    after = vp.parse_po(read_po(po))
    got = {e.msgid: e.msgstr for e in after}
    check("[D] 訳文がそれぞれ自分のエントリーに入る",
          got == {msgid: "最初の文です。次の文が続きます。", "Delete": "削除"},
          json.dumps(got, ensure_ascii=True))
    check("[D] 書き込み後も msgid の U+2028 が壊れていない",
          ('msgid "%s"' % msgid) in read_po(po))
    r = run(["scripts/apply_translations.py", str(po), "--list"])
    check("[D] 書き込み後は未翻訳が残らない", "未翻訳エントリーなし" in r.stdout, r.stdout[:200])

    # ============================ E: fix_spacing(CRLF のまま、U+2028 もそのまま)
    translated = HEADER + (
        '#: src/a.php:1\n'
        'msgid "First sentence.%s%sSecond sentence follows."\n'
        'msgstr "最初の文です。%s%s次の文はWordPressの説明です。"\n'
        '\n'
        '#: src/b.php:2\n'
        'msgid "Open Facebook"\n'
        'msgstr "Facebookを開く"\n'
    ) % (sep, sep, sep, sep)
    po = tmp / "e-ja.po"
    write_po(po, translated, newline="\r\n")
    r = run(["scripts/fix_spacing.py", str(po), "--apply"])
    fixed = read_po(po)
    check("[E] fix_spacing が U+2028 を含む msgstr にもスペースを入れる",
          "次の文は WordPress の説明です。" in fixed, (r.stdout + r.stderr)[:300].replace(sep, "<sep>"))
    check("[E] 後ろのエントリーの msgstr も直る", 'msgstr "Facebook を開く"' in fixed)
    check("[E] msgstr の U+2028 が残る", ("最初の文です。%s%s次の文は" % (sep, sep)) in fixed)
    check("[E] 改行コードが CRLF のまま", "\r\n" in fixed and "\n" not in fixed.replace("\r\n", ""))
    check("[E] 行数が変わらない", fixed.count("\r\n") == translated.count("\n"),
          "%d / %d" % (fixed.count("\r\n"), translated.count("\n")))

    # ============================ F: 該当文字が無い .po では行の数え方が変わらない
    plain = untranslated_po("  ")
    for label, text in (("末尾に改行あり", plain), ("末尾に改行なし", plain.rstrip("\n")),
                        ("末尾に空行が続く", plain + "\n\n")):
        po = tmp / "f-ja-untranslated.po"
        write_po(po, text)
        lines = at._read_lines(po)
        check("[F] %s: _read_lines の行数が splitlines と同じ" % label,
              len(lines) == len(text.splitlines()) and all(l.endswith("\n") for l in lines),
              "%d / %d" % (len(lines), len(text.splitlines())))
        ents = at._find_untranslated(lines)
        check("[F] %s: msgstr の行番号がファイル上の行を指す" % label,
              [lines[e.msgstr_linenos[0][0] - 1] for e in ents] == ['msgstr ""\n', 'msgstr ""\n'],
              repr([e.msgstr_linenos for e in ents]))
        check("[F] %s: parse_po の件数が変わらない" % label, len(vp.parse_po(text)) == 2)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
