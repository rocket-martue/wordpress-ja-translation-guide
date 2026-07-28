#!/usr/bin/env python3
"""
.po の msgstr に「半角英字と全角文字の間の半角スペース」を機械挿入するスクリプト。

WordPress 日本語翻訳スタイルガイド 1-4「数字を除く半角文字と全角文字の間には、
半角文字1字分のスペースを入れる」への違反(例: 「担当者のFacebook」)を、
validate_po.py の ALPHA_SPACING と**同じ検出ロジック**で見つけて修正する。

    担当者のFacebook          → 担当者の Facebook
    拡張機能のAPIキーが必要    → 拡張機能の API キーが必要

対象外(挿入しない):
    - 半角数字とその前後 (1-9「数字の前後にはスペースを入れない」)
    - プレースホルダー (%s %d %1$s など)
    - HTMLタグの内側・HTMLエンティティ (&nbsp; など)
    - 「」『』。、・ などの全角約物の前後 (1-4 の例外規定)
    - msgid / msgid_plural / コメント / obsolete (#~) 行、ヘッダーエントリー

このスクリプトが行うのは**半角スペースの挿入だけ**であり、訳語や文体の
正しさは一切保証しない。適用後も必ず validate_po.py を実行し、
人間が目視レビューしてから translate.wordpress.org へ反映すること。

使い方:
    # dry-run(既定): 挿入候補を表示するだけでファイルは変更しない
    python scripts/fix_spacing.py path/to/ja.po

    # 実際に書き換える
    python scripts/fix_spacing.py path/to/ja.po --apply

    # 複数ファイル / glob も可
    python scripts/fix_spacing.py "path/to/languages/*.po" --apply

終了コード:
    0 = 挿入すべき箇所なし
    1 = 挿入候補あり (dry-run) / 書き換え実施 (--apply)
    2 = 引数エラー / ファイル読み書きエラー / 安全チェックに失敗した箇所あり
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 検出ロジックは validate_po.py と共有する(同じディレクトリに配置されている)
from validate_po import (  # noqa: E402
    extract_placeholders,
    resolve_paths,
    find_alpha_fw_boundaries,
)


# msgstr / msgstr[N] の開始行と、その継続行 ("..." だけの行)
_MSGSTR_START_RE = re.compile(r'^(msgstr(?:\[\d+\])?[ \t]+")(.*)("[ \t]*[\r\n]*)$')
_MSGID_START_RE = re.compile(r'^(msgid(?:_plural)?[ \t]+")(.*)("[ \t]*[\r\n]*)$')
_CONTINUATION_RE = re.compile(r'^(")(.*)("[ \t]*[\r\n]*)$')
_TAG_RE = re.compile(r'<[^<>]*>')


@dataclass
class _Segment:
    """1行分の msgstr 文字列(引用符の中身)。"""
    lineno: int          # 1始まりの行番号
    prefix: str          # 'msgstr "' などの行頭部分
    body: str            # 引用符の中身(生のエスケープ済み文字列)
    suffix: str          # 終端の '"' + 改行


@dataclass
class _Field:
    """1つの msgstr フィールド(継続行を含む)。"""
    segments: list[_Segment] = field(default_factory=list)


def _collect_msgstr_fields(lines: list[str]) -> list[_Field]:
    """
    .po の行リストから、書き換え対象の msgstr フィールドを集める。

    - ヘッダーエントリー (msgid "") はスキップする
      (Last-Translator に日本語が入りうるが、翻訳文字列ではないため)
    - obsolete (#~) 行・コメント行・msgid 系の行には触れない
    """
    fields: list[_Field] = []
    current: _Field | None = None
    in_msgstr = False
    msgid_is_empty = True   # 直前に読んだ msgid が空文字列か(= ヘッダー候補)
    seen_msgid = False

    def close() -> None:
        nonlocal current, in_msgstr
        if current is not None and current.segments:
            fields.append(current)
        current = None
        in_msgstr = False

    for idx, line in enumerate(lines):
        # 空行 = エントリーの区切り
        if not line.strip():
            close()
            seen_msgid = False
            msgid_is_empty = True
            continue

        # obsolete エントリー (#~)・コメント
        if line.startswith('#'):
            close()
            continue

        m = _MSGID_START_RE.match(line)
        if m:
            close()
            # msgid_plural は msgid の空判定(ヘッダーかどうか)を上書きしない
            if not line.startswith('msgid_plural'):
                seen_msgid = True
                msgid_is_empty = (m.group(2) == "")
            in_msgstr = False
            continue

        m = _MSGSTR_START_RE.match(line)
        if m:
            close()
            # ヘッダーエントリー (msgid "") の msgstr は対象外
            if seen_msgid and msgid_is_empty:
                continue
            current = _Field()
            current.segments.append(
                _Segment(lineno=idx + 1, prefix=m.group(1), body=m.group(2), suffix=m.group(3))
            )
            in_msgstr = True
            continue

        m = _CONTINUATION_RE.match(line)
        if m:
            if in_msgstr and current is not None:
                current.segments.append(
                    _Segment(lineno=idx + 1, prefix=m.group(1), body=m.group(2), suffix=m.group(3))
                )
            else:
                # msgid の継続行: 内容があればヘッダーではない
                if m.group(2):
                    msgid_is_empty = False
            continue

        # 想定外の行 → フィールドを閉じる
        close()

    close()
    return fields


def _split_back(positions: list[int], bodies: list[str]) -> list[str]:
    """
    連結文字列へのスペース挿入を、元の行ごとの文字列に割り戻す。

    positions は連結文字列上の挿入オフセット(昇順)。行をまたぐ境界
    (継続行で分割された msgstr)では、手前の行の末尾に挿入する。
    """
    starts: list[int] = []
    pos = 0
    for b in bodies:
        starts.append(pos)
        pos += len(b)

    result = list(bodies)
    # 後ろから挿入すればオフセットがズレない
    for p in reversed(positions):
        seg_idx = len(bodies) - 1
        for i, start in enumerate(starts):
            if start < p <= start + len(bodies[i]):
                seg_idx = i
                break
        result[seg_idx] = result[seg_idx][:p - starts[seg_idx]] + ' ' + result[seg_idx][p - starts[seg_idx]:]

    return result


def _is_safe(old: str, new: str) -> str | None:
    """
    書き換えが「半角スペースの挿入だけ」に収まっているか検証する。
    問題があれば理由(文字列)を返す。
    """
    if new.replace(' ', '') != old.replace(' ', ''):
        return "スペース以外の内容が変化しました"
    if extract_placeholders(new) != extract_placeholders(old):
        return "プレースホルダーの数・種類が変化しました"
    if len(_TAG_RE.findall(new)) != len(_TAG_RE.findall(old)):
        return "HTMLタグの数が変化しました"
    return None


def process_file(filepath: Path, apply: bool) -> tuple[int, int, int]:
    """
    1ファイルを処理する。

    戻り値: (書き換え対象フィールド数, 挿入箇所数, 安全チェック失敗数)
    """
    # newline='' で読み書きし、元の改行コード (LF / CRLF) をそのまま保つ
    try:
        with filepath.open('r', encoding='utf-8', newline='') as f:
            text = f.read()
    except UnicodeDecodeError:
        with filepath.open('r', encoding='utf-8-sig', newline='') as f:
            text = f.read()

    lines = text.splitlines(keepends=True)
    fields = _collect_msgstr_fields(lines)

    changed_fields = 0
    inserted = 0
    unsafe = 0
    new_lines = list(lines)

    for fld in fields:
        bodies = [s.body for s in fld.segments]
        joined = ''.join(bodies)
        positions = find_alpha_fw_boundaries(joined)
        if not positions:
            continue

        new_joined = joined
        for p in reversed(positions):
            new_joined = new_joined[:p] + ' ' + new_joined[p:]

        reason = _is_safe(joined, new_joined)
        if reason:
            unsafe += 1
            print(
                f"[ERROR] {filepath}:{fld.segments[0].lineno} "
                f"{reason}のでスキップしました\n"
                f"  修正前: \"{joined[:80]}\"\n"
                f"  修正後: \"{new_joined[:80]}\"",
                file=sys.stderr,
            )
            continue

        new_bodies = _split_back(positions, bodies)

        changed_fields += 1
        inserted += len(positions)

        print(f"{filepath}:{fld.segments[0].lineno}  ({len(positions)} 箇所)")
        print(f"  - {joined[:100]}")
        print(f"  + {new_joined[:100]}")

        for seg, new_body in zip(fld.segments, new_bodies):
            new_lines[seg.lineno - 1] = f"{seg.prefix}{new_body}{seg.suffix}"

    if apply and changed_fields:
        try:
            with filepath.open('w', encoding='utf-8', newline='') as f:
                f.write(''.join(new_lines))
        except OSError as e:
            print(f"[ERROR] 書き込みエラー: {filepath}: {e}", file=sys.stderr)
            return changed_fields, inserted, unsafe + 1

    return changed_fields, inserted, unsafe


def main(argv: list[str] | None = None) -> int:
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(
        description="半角英字と全角文字の間の半角スペースを .po の msgstr に挿入する",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "files",
        nargs="+",
        metavar="FILE",
        help=".po ファイルのパス(複数指定可、glob パターン可)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="実際にファイルを書き換える(既定は dry-run)",
    )
    args = parser.parse_args(argv)

    paths = resolve_paths(args.files)
    if not paths:
        return 2

    total_fields = 0
    total_inserted = 0
    total_unsafe = 0
    has_error = False

    for filepath in paths:
        if not filepath.exists():
            print(f"[ERROR] ファイルが見つかりません: {filepath}", file=sys.stderr)
            has_error = True
            continue

        print(f"checking: {filepath}")
        try:
            fields, inserted, unsafe = process_file(filepath, args.apply)
        except Exception as e:
            print(f"[ERROR] 処理エラー: {filepath}: {e}", file=sys.stderr)
            has_error = True
            continue

        total_fields += fields
        total_inserted += inserted
        total_unsafe += unsafe

    print()

    if has_error:
        return 2

    if total_fields == 0:
        if total_unsafe:
            # 検出はしたが全件が安全チェックで弾かれた状態。成功と誤解させない
            print(
                f"⚠️ 挿入できた箇所はありません。"
                f"{total_unsafe} 件は安全チェックに失敗したためスキップしました(上記 [ERROR] を確認)"
            )
            return 2
        print("✅ 挿入すべき箇所はありません")
        return 0

    print(f"{'=' * 60}")
    if args.apply:
        print(f"✏️ {total_fields} 件の msgstr に合計 {total_inserted} 個の半角スペースを挿入しました")
        validate_script = Path(__file__).resolve().parent / "validate_po.py"
        print(f"次: python {validate_script} <po_file> で検証し、必ず人間が目視レビューしてください")
        print("   (このスクリプトはスペースを入れるだけで、訳語・文体の正しさは保証しません)")
    else:
        print(f"🔍 {total_fields} 件の msgstr に合計 {total_inserted} 個の半角スペースを挿入できます")
        print("   dry-run のためファイルは変更していません。適用するには --apply を付けて実行してください")

    if total_unsafe:
        print(f"⚠️ {total_unsafe} 件は安全チェックに失敗したためスキップしました(上記 [ERROR] を確認)")
        return 2

    return 1


if __name__ == "__main__":
    sys.exit(main())
