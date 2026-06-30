#!/usr/bin/env python3
"""
.po ファイルに日本語訳をバッチ書き込みするスクリプト。

モデルには「インデックス番号 → 訳文」のペアだけを渡させ、
生の .po 構文への str_replace を不要にする。

使い方:
    # 未翻訳エントリーを一覧表示（翻訳前に確認）
    python scripts/apply_translations.py path/to/ja.po --list
    python scripts/apply_translations.py path/to/ja.po --list --start 20 --count 20

    # 翻訳を書き込む（JSON ファイルまたはインライン JSON 文字列）
    python scripts/apply_translations.py path/to/ja.po translations.json
    python scripts/apply_translations.py path/to/ja.po '{"0": "訳文A", "1": "訳文B"}'

    インデックスは --list で表示される 0 始まり連番（未翻訳エントリー内）。

終了コード:
    0 = 成功
    2 = 引数エラー / ファイルエラー

制限事項:
    - 複数形エントリー (msgid_plural) は対象外（--list にも表示しない）
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
    location: str        # #: コメント（表示用）
    msgstr_lineno: int   # msgstr "" が書かれている行番号(1始まり)


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


# ---------------------------------------------------------------------------
# パーサー（未翻訳エントリーと msgstr 行番号を抽出）
# ---------------------------------------------------------------------------

def _find_untranslated(lines: list[str]) -> list[_Entry]:
    """
    .po ファイルの行リストを解析し、未翻訳エントリーを返す。

    - ヘッダーエントリー (msgid が空文字列) は除外
    - fuzzy エントリーは除外
    - obsolete エントリー (#~) は除外
    - 複数形エントリー (msgid_plural あり) は除外
    """
    entries: list[_Entry] = []

    # 現在処理中のエントリー情報
    msgid = ""
    location = ""
    is_fuzzy = False
    has_plural = False
    msgstr = ""
    msgstr_lineno = 0
    field = ""  # 現在蓄積中のフィールド名

    def flush() -> None:
        nonlocal msgid, location, is_fuzzy, has_plural, msgstr, msgstr_lineno, field
        if msgid and not msgstr and not is_fuzzy and not has_plural:
            entries.append(_Entry(
                index=len(entries),
                msgid=msgid,
                location=location,
                msgstr_lineno=msgstr_lineno,
            ))
        msgid = ""
        location = ""
        is_fuzzy = False
        has_plural = False
        msgstr = ""
        msgstr_lineno = 0
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
            has_plural = True
            field = ""
            continue

        m = re.match(r'^msgstr\[', line)
        if m:
            field = ""
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
            elif field == "msgstr":
                msgstr += val
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
        loc_str = f"  ({e.location})" if e.location else ""
        msgid_preview = e.msgid[:120].replace('\n', '\\n')
        print(f"[{e.index:3d}]{loc_str}")
        print(f"      msgid: \"{msgid_preview}\"")

    return 0


# ---------------------------------------------------------------------------
# コマンド: apply
# ---------------------------------------------------------------------------

def cmd_apply(po_path: Path, translations_arg: str) -> int:
    # translations の読み込み（ファイルパスかインライン JSON か判定）
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

    # インデックス検証と書き込み先の特定
    writes: dict[int, str] = {}  # {行番号(1始まり): エスケープ済み訳文}
    skipped: list[str] = []

    for idx_str, msgstr in translations.items():
        try:
            idx = int(idx_str)
        except ValueError:
            skipped.append(f"インデックス \"{idx_str}\" が整数ではありません")
            continue

        if idx < 0 or idx >= total:
            skipped.append(f"インデックス {idx} は範囲外です（0–{total - 1}）")
            continue

        entry = entries[idx]
        writes[entry.msgstr_lineno] = _escape(msgstr)

    if skipped:
        for msg in skipped:
            print(f"[WARN] {msg}", file=sys.stderr)

    if not writes:
        print("[ERROR] 書き込める翻訳がありません", file=sys.stderr)
        return 2

    # 行の置換
    new_lines = list(lines)
    for lineno, escaped in writes.items():
        new_lines[lineno - 1] = f'msgstr "{escaped}"\n'

    # ファイルへ書き戻し
    try:
        po_path.write_text(''.join(new_lines), encoding='utf-8')
    except OSError as e:
        print(f"[ERROR] 書き込みエラー: {e}", file=sys.stderr)
        return 2

    written = len(writes)
    # 書き込み後の残件数（未翻訳 - 今回書いた分）
    remaining = total - written
    pct = int((total - remaining) / total * 100) if total else 0
    already_done = total - remaining

    print(
        f"✅ {written}件書き込みました。"
        f"進捗: {already_done}/{total} ({pct}%), 残り {remaining}件"
    )
    return 0


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


def _load_translations(arg: str) -> dict[str, str]:
    """ファイルパスまたはインライン JSON 文字列を dict に変換する。"""
    stripped = arg.strip()
    if stripped.startswith('{'):
        data = json.loads(stripped)
    else:
        path = Path(arg)
        if not path.exists():
            raise OSError(f"ファイルが見つかりません: {path}")
        data = json.loads(path.read_text(encoding='utf-8'))

    if not isinstance(data, dict):
        raise ValueError("JSON はオブジェクト ({\"インデックス\": \"訳文\", ...}) でなければなりません")

    return {str(k): str(v) for k, v in data.items()}


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
    ls.add_argument("--start", type=int, default=0, metavar="N", help="表示開始インデックス（デフォルト: 0）")
    ls.add_argument("--count", type=int, default=None, metavar="N", help="表示件数（省略時: すべて）")

    # apply サブコマンド（位置引数）
    ap = sub.add_parser("apply", help="翻訳を書き込む（通常は省略して直接 TRANSLATIONS を渡す）")
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

    # apply モード（第2引数が JSON ファイルパスまたはインライン JSON）
    if len(args_list) == 2:
        return cmd_apply(po_path, args_list[1])

    parser.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
