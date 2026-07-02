#!/usr/bin/env python3
"""
.po ファイルに日本語訳をバッチ書き込みするスクリプト。

モデルには「インデックス番号 → 訳文」のペアだけを渡させ、
生の .po 構文への str_replace を不要にする。

重要(インデックスの再採番):
    インデックスは呼び出しごとに「その時点で未翻訳のエントリー」を 0 から
    振り直す。書き込むたびに未翻訳リストが縮んで後続の番号が繰り上がるため、
    各バッチの JSON を作る直前に必ず --list を取り直すこと。
    古いインデックスのまま適用する事故は、JSON に msgid を添える
    オブジェクト形式(推奨)を使えば検出・自動補正できる。

使い方:
    # 未翻訳エントリーを一覧表示(翻訳前に確認)
    python scripts/apply_translations.py path/to/ja.po --list
    python scripts/apply_translations.py path/to/ja.po --list --start 20 --count 20

    # 翻訳を書き込む(JSON ファイルまたはインライン JSON 文字列)
    python scripts/apply_translations.py path/to/ja.po translations.json
    python scripts/apply_translations.py path/to/ja.po '{"0": "訳文A", "1": "訳文B"}'

    JSON の値は2形式:
      推奨:   {"0": {"msgid": "Original text", "msgstr": "訳文"}}
              インデックス位置の msgid と照合し、ズレていれば msgid で
              書き込み先を再解決する(一意に決まらなければエラーで停止)
      旧形式: {"0": "訳文"}
              照合なし。インデックスがズレていても検出できない

書き込み時の安全チェック:
    - msgid 照合(オブジェクト形式のみ): インデックスのズレを検出・補正する
    - プレースホルダー照合: msgid (複数形は msgid_plural) と訳文の
      プレースホルダー(%s, %1$s など)が一致しないエントリーは書き込まない

複数形エントリー (msgid_plural):
    --list に (plural) マーク付きで表示される。書き込むと、存在する
    すべての msgstr[N] 行に同じ訳文が入る(日本語は単数/複数を区別しないため)。

終了コード:
    0 = 成功(すべて書き込み)
    2 = 引数エラー / ファイルエラー / 一部または全部のエントリーが書き込めず

制限事項:
    - fuzzy エントリーは未翻訳とみなさない
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# データモデル
# ---------------------------------------------------------------------------

@dataclass
class _Entry:
    """未翻訳エントリー 1件の内部表現。"""
    index: int           # 未翻訳エントリー内の 0 始まり連番
    msgid: str           # 原文
    msgid_plural: str    # 複数形の原文("" なら単数形エントリー)
    location: str        # #: コメント(表示用)
    # 書き込み先: (行番号1始まり, 複数形インデックス N または None) のリスト
    # 単数形は [(msgstr行, None)]、複数形は [(msgstr[0]行, 0), (msgstr[1]行, 1), ...]
    msgstr_linenos: list[tuple[int, int | None]]


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

_UNESCAPE_MAP: dict[str, str] = {
    '"': '"', 'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '0': '\0',
}


def _unescape(s: str) -> str:
    result: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            result.append(_UNESCAPE_MAP.get(s[i + 1], s[i + 1]))
            i += 2
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)


def _escape(s: str) -> str:
    """msgstr に書き込む値を .po エスケープする。"""
    return (
        s
        .replace('\\', '\\\\')
        .replace('"', '\\"')
        .replace('\n', '\\n')
        .replace('\t', '\\t')
        .replace('\r', '\\r')
    )


# %s %d %1$s %2$d など。%% はエスケープ済みリテラルなので除外
# (validate_po.py の _PH_RE と同じ定義を使うこと)
_PH_RE = re.compile(r'%%|(%(?:\d+\$)?[-+ 0]*\d*(?:\.\d+)?[sdifu])')


def _extract_placeholders(s: str) -> list[str]:
    """文字列からプレースホルダーを抽出する。%% は除外。ソート済みリストを返す。"""
    return sorted(m for m in _PH_RE.findall(s) if m)


_PH_NUMBERED_RE = re.compile(r'%\d+\$')


def _check_placeholders(expected: list[str], actual: list[str]) -> str | None:
    """
    プレースホルダー照合。不一致があればエラーメッセージを返す。

    - 型文字・個数の一致は必須
    - 番号なし→番号付き(%s→%1$s)は許容(語順変更のため)
    - 番号付き→番号なしの劣化はエラー
    """
    expected_types = sorted(p[-1] for p in expected)
    actual_types = sorted(p[-1] for p in actual)
    if expected_types != actual_types:
        return f"期待値: {expected} / 訳文: {actual}"
    # 番号付き→番号なしの劣化チェック(%1$s → %s は NG)
    if any(_PH_NUMBERED_RE.match(p) for p in expected) and any(
        not _PH_NUMBERED_RE.match(p) for p in actual
    ):
        return (
            f"番号付きプレースホルダーが番号なしに劣化しています\n"
            f"       期待値: {expected} / 訳文: {actual}"
        )
    return None


# ---------------------------------------------------------------------------
# パーサー(未翻訳エントリーと msgstr 行番号を抽出)
# ---------------------------------------------------------------------------

def _find_untranslated(lines: list[str]) -> list[_Entry]:
    """
    .po ファイルの行リストを解析し、未翻訳エントリーを返す。

    - ヘッダーエントリー (msgid が空文字列) は除外
    - fuzzy エントリーは除外
    - obsolete エントリー (#~) は除外
    - 複数形エントリー (msgid_plural あり) は msgstr[0] が空なら未翻訳として含める
    """
    entries: list[_Entry] = []

    # 現在処理中のエントリー情報
    msgid = ""
    msgid_plural = ""
    location = ""
    is_fuzzy = False
    msgstr = ""
    msgstr_lineno = 0
    msgstr_plural: dict[int, str] = {}          # {N: 値}
    msgstr_plural_linenos: dict[int, int] = {}  # {N: 行番号}
    field = ""  # 現在蓄積中のフィールド名

    def flush() -> None:
        nonlocal msgid, msgid_plural, location, is_fuzzy
        nonlocal msgstr, msgstr_lineno, msgstr_plural, msgstr_plural_linenos, field
        if msgid and not is_fuzzy:
            if msgid_plural:
                # 複数形: msgstr[0] が空なら未翻訳
                if msgstr_plural_linenos and not msgstr_plural.get(0, ""):
                    entries.append(_Entry(
                        index=len(entries),
                        msgid=msgid,
                        msgid_plural=msgid_plural,
                        location=location,
                        msgstr_linenos=[
                            (lineno, n)
                            for n, lineno in sorted(msgstr_plural_linenos.items())
                        ],
                    ))
            elif not msgstr and msgstr_lineno:
                entries.append(_Entry(
                    index=len(entries),
                    msgid=msgid,
                    msgid_plural="",
                    location=location,
                    msgstr_linenos=[(msgstr_lineno, None)],
                ))
        msgid = ""
        msgid_plural = ""
        location = ""
        is_fuzzy = False
        msgstr = ""
        msgstr_lineno = 0
        msgstr_plural = {}
        msgstr_plural_linenos = {}
        field = ""

    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()

        if not line:
            flush()
            continue

        if line.startswith('#~'):
            field = ""
            continue

        if line.startswith('#,') and 'fuzzy' in line:
            is_fuzzy = True
            field = ""
            continue

        if line.startswith('#:'):
            loc = line[2:].strip()
            location = f"{location} {loc}".strip() if location else loc
            field = ""
            continue

        if line.startswith('#'):
            field = ""
            continue

        m = re.match(r'^msgid_plural\s+"(.*)"$', line)
        if m:
            msgid_plural = _unescape(m.group(1))
            field = "msgid_plural"
            continue

        m = re.match(r'^msgstr\[(\d+)\]\s+"(.*)"$', line)
        if m:
            n = int(m.group(1))
            msgstr_plural[n] = _unescape(m.group(2))
            msgstr_plural_linenos[n] = lineno
            field = f"msgstr_plural_{n}"
            continue

        m = re.match(r'^msgid\s+"(.*)"$', line)
        if m:
            if msgid:
                flush()
            msgid = _unescape(m.group(1))
            field = "msgid"
            continue

        m = re.match(r'^msgstr\s+"(.*)"$', line)
        if m:
            msgstr = _unescape(m.group(1))
            msgstr_lineno = lineno
            field = "msgstr"
            continue

        m = re.match(r'^"(.*)"$', line)
        if m:
            val = _unescape(m.group(1))
            if field == "msgid":
                msgid += val
            elif field == "msgid_plural":
                msgid_plural += val
            elif field == "msgstr":
                msgstr += val
            elif field.startswith("msgstr_plural_"):
                n = int(field.rsplit("_", 1)[1])
                msgstr_plural[n] = msgstr_plural.get(n, "") + val
            continue

    flush()
    return entries


# ---------------------------------------------------------------------------
# コマンド: --list
# ---------------------------------------------------------------------------

def cmd_list(po_path: Path, start: int, count: int | None) -> int:
    try:
        lines = _read_lines(po_path)
    except OSError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    entries = _find_untranslated(lines)
    total = len(entries)

    if total == 0:
        print(f"未翻訳エントリーなし: {po_path}")
        return 0

    end = total if count is None else min(start + count, total)
    shown = entries[start:end]

    print(f"未翻訳エントリー: 全 {total} 件 / 表示 [{start}–{end - 1}]")
    print()
    for e in shown:
        plural_mark = " (plural)" if e.msgid_plural else ""
        loc_str = f"  ({e.location})" if e.location else ""
        msgid_preview = e.msgid[:120].replace('\n', '\\n')
        print(f"[{e.index:3d}]{plural_mark}{loc_str}")
        print(f"      msgid: \"{msgid_preview}\"")
        if e.msgid_plural:
            plural_preview = e.msgid_plural[:120].replace('\n', '\\n')
            print(f"      msgid_plural: \"{plural_preview}\"")

    return 0


# ---------------------------------------------------------------------------
# コマンド: apply
# ---------------------------------------------------------------------------

def cmd_apply(po_path: Path, translations_arg: str) -> int:
    # translations の読み込み(ファイルパスかインライン JSON か判定)
    try:
        translations = _load_translations(translations_arg)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        print(f"[ERROR] translations の読み込みに失敗しました: {e}", file=sys.stderr)
        return 2

    if not translations:
        print("[ERROR] 翻訳データが空です", file=sys.stderr)
        return 2

    # .po ファイルの読み込み
    try:
        lines = _read_lines(po_path)
    except OSError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    entries = _find_untranslated(lines)
    total = len(entries)

    if total == 0:
        print("未翻訳エントリーなし。書き込む内容がありません。")
        return 0

    # 書き込み先の解決と安全チェック
    writes: dict[int, str] = {}    # {行番号(1始まり): 置換後の行}
    claimed: dict[int, str] = {}   # {エントリー先頭行番号: JSONキー} 重複書き込み検出用
    warns: list[str] = []
    errors: list[str] = []
    written_count = 0

    for idx_str, (expected_msgid, msgstr) in translations.items():
        try:
            idx = int(idx_str)
        except ValueError:
            errors.append(f"インデックス \"{idx_str}\" が整数ではありません")
            continue

        # 1. インデックス位置の msgid と照合
        entry: _Entry | None = None
        if 0 <= idx < total and (expected_msgid is None or entries[idx].msgid == expected_msgid):
            entry = entries[idx]
        elif expected_msgid is not None:
            # 2. ズレている → msgid で再解決
            matches = [e for e in entries if e.msgid == expected_msgid]
            if len(matches) == 1:
                entry = matches[0]
                warns.append(
                    f"インデックス {idx} の msgid が現在のリストと一致しません → "
                    f"msgid 照合で [{entry.index}] に再解決して書き込みます"
                    f"(バッチを作る直前に --list を取り直してください)"
                )
            elif len(matches) > 1:
                errors.append(
                    f"インデックス {idx}: msgid \"{expected_msgid[:60]}\" が複数の"
                    f"未翻訳エントリーに一致します(msgctxt 違いの可能性)。"
                    f"--list を取り直して正しいインデックスで指定し直してください"
                )
                continue
            else:
                errors.append(
                    f"インデックス {idx}: msgid \"{expected_msgid[:60]}\" は未翻訳"
                    f"エントリーに見つかりません(翻訳済みか、原文が異なります)"
                )
                continue
        else:
            errors.append(f"インデックス {idx} は範囲外です(0–{total - 1})")
            continue

        # 3. プレースホルダー照合(複数形は msgid_plural を基準にする)
        base = entry.msgid_plural or entry.msgid
        expected_ph = _extract_placeholders(base)
        actual_ph = _extract_placeholders(msgstr)
        ph_error = _check_placeholders(expected_ph, actual_ph)
        if ph_error:
            errors.append(
                f"[{entry.index}] プレースホルダーが一致しないため書き込みません\n"
                f"       {ph_error}\n"
                f"       msgid: \"{base[:80]}\""
            )
            continue

        # 4. 同一エントリーへの重複書き込みを検出
        first_lineno = entry.msgstr_linenos[0][0]
        if first_lineno in claimed:
            errors.append(
                f"インデックス {idx}: エントリー [{entry.index}] への書き込みが"
                f"重複しています(キー \"{claimed[first_lineno]}\" と同じ書き込み先)"
            )
            continue
        claimed[first_lineno] = idx_str

        escaped = _escape(msgstr)
        for lineno, plural_n in entry.msgstr_linenos:
            if plural_n is None:
                writes[lineno] = f'msgstr "{escaped}"\n'
            else:
                writes[lineno] = f'msgstr[{plural_n}] "{escaped}"\n'
        written_count += 1

    for msg in warns:
        print(f"[WARN] {msg}", file=sys.stderr)
    for msg in errors:
        print(f"[ERROR] {msg}", file=sys.stderr)

    if not writes:
        print("[ERROR] 書き込める翻訳がありません", file=sys.stderr)
        return 2

    # 行の置換
    new_lines = list(lines)
    for lineno, replacement in writes.items():
        new_lines[lineno - 1] = replacement

    # ファイルへ書き戻し
    try:
        po_path.write_text(''.join(new_lines), encoding='utf-8')
    except OSError as e:
        print(f"[ERROR] 書き込みエラー: {e}", file=sys.stderr)
        return 2

    # 書き込み後の残件数(未翻訳 - 今回書いた分)
    remaining = total - written_count
    pct = int(written_count / total * 100) if total else 0

    validate_script = Path(__file__).resolve().parent / "validate_po.py"

    print(
        f"✅ {written_count}件書き込みました。"
        f"進捗: {written_count}/{total} ({pct}%), 残り {remaining}件"
    )
    if errors:
        print(f"⚠️ {len(errors)}件は書き込めませんでした(上記 [ERROR] を確認)")
    print(f"次: python {validate_script} {po_path} で検証してから次のバッチへ")

    return 2 if errors else 0


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _read_lines(po_path: Path) -> list[str]:
    if not po_path.exists():
        raise OSError(f"ファイルが見つかりません: {po_path}")
    try:
        text = po_path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        text = po_path.read_text(encoding='utf-8-sig')
    # splitlines(keepends=True) で改行を保持した行リストにする
    lines = text.splitlines(keepends=True)
    # 末尾に改行がない場合の保険
    if lines and not lines[-1].endswith('\n'):
        lines[-1] += '\n'
    return lines


def _load_translations(arg: str) -> dict[str, tuple[str | None, str]]:
    """
    ファイルパスまたはインライン JSON 文字列を
    {インデックス: (照合用msgid または None, 訳文)} に変換する。

    値は "訳文" の文字列(旧形式、照合なし)、または
    {"msgid": "...", "msgstr": "..."} のオブジェクト(推奨、msgid 照合あり)。
    """
    stripped = arg.strip()
    if stripped.startswith('{'):
        data = json.loads(stripped)
    else:
        path = Path(arg)
        if not path.exists():
            raise OSError(f"ファイルが見つかりません: {path}")
        data = json.loads(path.read_text(encoding='utf-8'))

    if not isinstance(data, dict):
        raise ValueError(
            "JSON はオブジェクト ({\"インデックス\": \"訳文\", ...} または "
            "{\"インデックス\": {\"msgid\": ..., \"msgstr\": ...}, ...}) "
            "でなければなりません"
        )

    result: dict[str, tuple[str | None, str]] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            if "msgstr" not in v:
                raise ValueError(
                    f"インデックス \"{k}\": オブジェクト形式には \"msgstr\" キーが必要です"
                )
            if "msgid" not in v:
                raise ValueError(
                    f"インデックス \"{k}\": オブジェクト形式には \"msgid\" キーが必要です"
                    " (msgid照合なしで使いたい場合は文字列形式を使ってください)"
                )
            result[str(k)] = (str(v["msgid"]), str(v["msgstr"]))
        else:
            result[str(k)] = (None, str(v))
    return result


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(
        description=".po ファイルへの日本語訳バッチ書き込み",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("po_file", metavar="PO_FILE", help=".po ファイルのパス")

    sub = parser.add_subparsers(dest="command")

    # --list サブコマンド
    ls = sub.add_parser("--list", help="未翻訳エントリーを一覧表示する")
    ls.add_argument("--start", type=int, default=0, metavar="N", help="表示開始インデックス(デフォルト: 0)")
    ls.add_argument("--count", type=int, default=None, metavar="N", help="表示件数(省略時: すべて)")

    # apply サブコマンド(位置引数)
    ap = sub.add_parser("apply", help="翻訳を書き込む(通常は省略して直接 TRANSLATIONS を渡す)")
    ap.add_argument("translations", metavar="TRANSLATIONS", help="JSON ファイルパスまたはインライン JSON")

    # argparse のサブコマンドが "--list" に対応しないため手動パース
    args_list = list(argv) if argv is not None else sys.argv[1:]

    if not args_list:
        parser.print_help()
        return 2

    po_path = Path(args_list[0])

    # --list モード
    if len(args_list) >= 2 and args_list[1] == '--list':
        start = 0
        count = None
        i = 2
        while i < len(args_list):
            if args_list[i] == '--start' and i + 1 < len(args_list):
                try:
                    start = int(args_list[i + 1])
                except ValueError:
                    print(f"[ERROR] --start の値が無効です: {args_list[i + 1]}", file=sys.stderr)
                    return 2
                i += 2
            elif args_list[i] == '--count' and i + 1 < len(args_list):
                try:
                    count = int(args_list[i + 1])
                except ValueError:
                    print(f"[ERROR] --count の値が無効です: {args_list[i + 1]}", file=sys.stderr)
                    return 2
                i += 2
            else:
                print(f"[ERROR] 不明なオプション: {args_list[i]}", file=sys.stderr)
                return 2
        return cmd_list(po_path, start, count)

    # apply モード(第2引数が JSON ファイルパスまたはインライン JSON)
    if len(args_list) == 2:
        return cmd_apply(po_path, args_list[1])

    parser.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
