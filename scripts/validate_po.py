#!/usr/bin/env python3
"""
.po ファイルの日本語翻訳品質チェックスクリプト。

WordPress 日本語翻訳スタイルガイドに基づいて、機械的に検出できる
ルール違反を報告する。

ルール出典:
  SKILL.md / references/notation-rules.md

使い方:
    python scripts/validate_po.py path/to/ja.po
    python scripts/validate_po.py path/to/ja.po path/to/other.po
    python scripts/validate_po.py "path/to/*.po"
    python scripts/validate_po.py --errors-only path/to/ja.po

終了コード:
    0 = 違反なし
    1 = 1件以上の違反あり
    2 = 引数エラー / ファイル読み込みエラー

チェック項目:
  PH_MISMATCH           プレースホルダーの数・種類の不一致 [ERROR]
  BRAND_TRANSLITERATION 「WordPress」の音訳(ワードプレス等) [ERROR]
  FULLWIDTH_DIGIT       全角数字 [WARN]
  FULLWIDTH_ALPHA       全角英字 [WARN]
  FULLWIDTH_PUNCT       全角感嘆符・疑問符 (！？) [WARN]
  NUM_SPACING           数字・数値プレースホルダー(%d等)直後の不要なスペース [WARN]
                        (文字列プレースホルダー %s は対象外。公式例では前後にスペースを入れる)
  PUNCT_SPACING         日本語直後の ! / ? にスペースがない [WARN]
  WRITING_CONVENTION    「ください」「すべて」「すでに」等の表記 [WARN]
"""
from __future__ import annotations

import re
import sys
import argparse
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# データモデル
# ---------------------------------------------------------------------------

@dataclass
class PoEntry:
    """1つの翻訳エントリー。"""
    msgid: str = ""
    msgid_plural: str = ""
    msgstr: str = ""
    msgstr_plural: list = field(default_factory=list)
    line: int = 0
    is_fuzzy: bool = False
    location: str = ""


@dataclass
class Violation:
    """チェックで検出された違反 1 件。"""
    filepath: Path
    entry: PoEntry
    rule_id: str
    message: str
    severity: str = "ERROR"  # "ERROR" or "WARN"

    def format(self) -> str:
        tag = f"[{self.severity:<5}]"
        loc = f"{self.filepath}:{self.entry.line}"
        msgid_preview = self.entry.msgid[:80].replace("\n", "\\n")
        return (
            f"{tag} {loc}  {self.rule_id}\n"
            f"  msgid: \"{msgid_preview}\"\n"
            f"  {self.message}"
        )


# ---------------------------------------------------------------------------
# .po パーサー
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


def parse_po(text: str) -> list[PoEntry]:
    """
    .po ファイルのテキストを PoEntry のリストに変換する。

    対応:
    - 複数行文字列 ("..." の継続行)
    - 複数形 (msgid_plural / msgstr[N])
    - fuzzy フラグ
    - obsolete エントリー (#~) は除外
    - ヘッダーエントリー (msgid が空文字列) は除外
    """
    entries: list[PoEntry] = []
    entry: PoEntry | None = None
    field_name: str = ""

    def flush() -> None:
        nonlocal entry, field_name
        if entry is not None and entry.msgid:
            entries.append(entry)
        entry = None
        field_name = ""

    def get_field() -> str:
        if entry is None:
            return ""
        if field_name == "msgid":
            return entry.msgid
        if field_name == "msgid_plural":
            return entry.msgid_plural
        if field_name == "msgstr":
            return entry.msgstr
        if field_name.startswith("msgstr_"):
            idx = int(field_name[7:])
            return entry.msgstr_plural[idx] if idx < len(entry.msgstr_plural) else ""
        return ""

    def set_field(value: str) -> None:
        if entry is None:
            return
        if field_name == "msgid":
            entry.msgid = value
        elif field_name == "msgid_plural":
            entry.msgid_plural = value
        elif field_name == "msgstr":
            entry.msgstr = value
        elif field_name.startswith("msgstr_"):
            idx = int(field_name[7:])
            while len(entry.msgstr_plural) <= idx:
                entry.msgstr_plural.append("")
            entry.msgstr_plural[idx] = value

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()

        # 空行 → エントリー区切り
        if not line:
            flush()
            continue

        # obsolete エントリー (#~) はスキップ
        if line.startswith('#~'):
            continue

        # fuzzy フラグ
        if line.startswith('#,') and 'fuzzy' in line:
            if entry is None:
                entry = PoEntry(line=lineno)
            entry.is_fuzzy = True
            continue

        # ロケーションコメント (#:)
        if line.startswith('#:'):
            if entry is None:
                entry = PoEntry(line=lineno)
            loc = line[2:].strip()
            entry.location = f"{entry.location} {loc}".strip() if entry.location else loc
            continue

        # その他コメント
        if line.startswith('#'):
            continue

        # msgid
        m = re.match(r'^msgid\s+"(.*)"$', line)
        if m:
            # 直前のエントリーを保存してから新規作成
            # (コメントでエントリーを先行作成していた場合はそこにフィールドを書き込む)
            if entry is not None and entry.msgid:
                flush()
                entry = PoEntry(line=lineno)
            elif entry is None:
                entry = PoEntry(line=lineno)
            else:
                entry.line = lineno  # コメント行で作成済みの場合は行番号を更新
            field_name = "msgid"
            entry.msgid = _unescape(m.group(1))
            continue

        # msgid_plural
        m = re.match(r'^msgid_plural\s+"(.*)"$', line)
        if m:
            field_name = "msgid_plural"
            if entry:
                entry.msgid_plural = _unescape(m.group(1))
            continue

        # msgstr[N] (複数形)
        m = re.match(r'^msgstr\[(\d+)\]\s+"(.*)"$', line)
        if m:
            idx = int(m.group(1))
            field_name = f"msgstr_{idx}"
            if entry:
                while len(entry.msgstr_plural) <= idx:
                    entry.msgstr_plural.append("")
                entry.msgstr_plural[idx] = _unescape(m.group(2))
            continue

        # msgstr
        m = re.match(r'^msgstr\s+"(.*)"$', line)
        if m:
            field_name = "msgstr"
            if entry:
                entry.msgstr = _unescape(m.group(1))
            continue

        # 継続行 "..."
        m = re.match(r'^"(.*)"$', line)
        if m and field_name:
            set_field(get_field() + _unescape(m.group(1)))
            continue

    flush()
    return entries


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

# %s %d %1$s %2$d など。%% はエスケープ済みリテラルなので除外
_PH_RE = re.compile(r'%%|(%(?:\d+\$)?[-+ 0]*\d*(?:\.\d+)?[sdifu])')
_PH_NUMBERED_RE = re.compile(r'%\d+\$')
_PH_NUM_CAPTURE_RE = re.compile(r'%(\d+)\$')


def _extract_placeholders(s: str) -> list[str]:
    """
    文字列からプレースホルダーを抽出する。%% は除外。
    ソート済みリストを返す(順序入れ替えを許容するため)。
    """
    return sorted(m for m in _PH_RE.findall(s) if m)


def _placeholders_compat(expected: list[str], actual: list[str]) -> bool:
    """
    apply_translations.py と同じ許容ルールでプレースホルダーを検証する。

    - 型文字・個数の一致は必須
    - expected が全て番号なし、actual が全て番号付き →
      番号が 1..N の連番・重複なしであれば OK(語順変更のため)
    - expected に番号付きあり → actual と multiset(番号+型)が完全一致
    """
    if sorted(p[-1] for p in expected) != sorted(p[-1] for p in actual):
        return False

    expected_has_numbered = any(_PH_NUMBERED_RE.match(p) for p in expected)
    actual_has_numbered   = any(_PH_NUMBERED_RE.match(p) for p in actual)

    if expected_has_numbered:
        return Counter(expected) == Counter(actual)

    if actual_has_numbered:
        if any(not _PH_NUMBERED_RE.match(p) for p in actual):
            return False  # 混在
        nums = [int(_PH_NUM_CAPTURE_RE.match(p).group(1)) for p in actual]  # type: ignore[union-attr]
        return sorted(nums) == list(range(1, len(nums) + 1))

    return True


def _all_msgstrs(entry: PoEntry) -> list[str]:
    """エントリーの全 msgstr(単数・複数形両方)を返す。"""
    result: list[str] = []
    if entry.msgstr:
        result.append(entry.msgstr)
    result.extend(s for s in entry.msgstr_plural if s)
    return result


def _is_translated(entry: PoEntry) -> bool:
    """msgstr または msgstr_plural[0] が空でなければ翻訳済みとみなす。"""
    if entry.msgstr:
        return True
    if entry.msgstr_plural and entry.msgstr_plural[0]:
        return True
    return False


# ---------------------------------------------------------------------------
# チェック関数
# ---------------------------------------------------------------------------

def check_placeholders(entry: PoEntry, filepath: Path) -> list[Violation]:
    """PH_MISMATCH: プレースホルダーの数・種類が msgid と msgstr で一致するか。"""
    violations: list[Violation] = []

    if entry.msgstr_plural:
        # 複数形: msgstr[N] と msgid_plural (なければ msgid) を比較
        base = entry.msgid_plural or entry.msgid
        expected = _extract_placeholders(base)
        for idx, msgstr in enumerate(entry.msgstr_plural):
            if not msgstr:
                continue
            actual = _extract_placeholders(msgstr)
            if not _placeholders_compat(expected, actual):
                violations.append(Violation(
                    filepath=filepath,
                    entry=entry,
                    rule_id="PH_MISMATCH",
                    severity="ERROR",
                    message=(
                        f"msgstr[{idx}] のプレースホルダーが一致しません\n"
                        f"  期待値 (msgid_plural): {expected}\n"
                        f"  実際値 (msgstr[{idx}]): {actual}"
                    ),
                ))
    elif entry.msgstr:
        expected = _extract_placeholders(entry.msgid)
        actual = _extract_placeholders(entry.msgstr)
        if not _placeholders_compat(expected, actual):
            violations.append(Violation(
                filepath=filepath,
                entry=entry,
                rule_id="PH_MISMATCH",
                severity="ERROR",
                message=(
                    f"プレースホルダーが一致しません\n"
                    f"  期待値 (msgid) : {expected}\n"
                    f"  実際値 (msgstr): {actual}"
                ),
            ))

    return violations


# ワードプレス音訳の検出
_TRANSLITERATION_RE = re.compile(r'ワードプレス[ーア]?')


def check_brand_names(entry: PoEntry, filepath: Path) -> list[Violation]:
    """BRAND_TRANSLITERATION: 「WordPress」を音訳していないか。"""
    # 原文に WordPress が含まれない場合はチェック不要
    if 'WordPress' not in entry.msgid:
        return []

    violations: list[Violation] = []
    for msgstr in _all_msgstrs(entry):
        m = _TRANSLITERATION_RE.search(msgstr)
        if m:
            violations.append(Violation(
                filepath=filepath,
                entry=entry,
                rule_id="BRAND_TRANSLITERATION",
                severity="ERROR",
                message=(
                    f'「WordPress」が音訳されています: "{m.group()}" '
                    f'→ "WordPress" のまま使う\n'
                    f'  msgstr: "{msgstr[:80]}"'
                ),
            ))
            break

    return violations


_FULLWIDTH_DIGIT_RE = re.compile(r'[０-９]')
_FULLWIDTH_ALPHA_RE = re.compile(r'[Ａ-Ｚａ-ｚ]')
_FULLWIDTH_PUNCT_RE = re.compile(r'[！？]')


def check_fullwidth(entry: PoEntry, filepath: Path) -> list[Violation]:
    """FULLWIDTH_DIGIT / FULLWIDTH_ALPHA / FULLWIDTH_PUNCT: 全角数字・全角英字・全角記号を使っていないか。"""
    violations: list[Violation] = []

    for msgstr in _all_msgstrs(entry):
        m = _FULLWIDTH_DIGIT_RE.search(msgstr)
        if m:
            violations.append(Violation(
                filepath=filepath,
                entry=entry,
                rule_id="FULLWIDTH_DIGIT",
                severity="WARN",
                message=(
                    f"全角数字が含まれています: 「{m.group()}」→ 半角数字を使う\n"
                    f"  msgstr: \"{msgstr[:80]}\""
                ),
            ))

        m = _FULLWIDTH_ALPHA_RE.search(msgstr)
        if m:
            violations.append(Violation(
                filepath=filepath,
                entry=entry,
                rule_id="FULLWIDTH_ALPHA",
                severity="WARN",
                message=(
                    f"全角英字が含まれています: 「{m.group()}」→ 半角英字を使う\n"
                    f"  msgstr: \"{msgstr[:80]}\""
                ),
            ))

        m = _FULLWIDTH_PUNCT_RE.search(msgstr)
        if m:
            violations.append(Violation(
                filepath=filepath,
                entry=entry,
                rule_id="FULLWIDTH_PUNCT",
                severity="WARN",
                message=(
                    f"全角記号が含まれています: 「{m.group()}」→ 半角 (! または ?) + 直前に半角スペースを使う\n"
                    f"  msgstr: \"{msgstr[:80]}\""
                ),
            ))

    return violations


# 日本語文字クラス(ひらがな・カタカナ・CJK)
_JA = r'[぀-ゟ゠-ヿ一-鿿㐀-䶿]'
# 数値プレースホルダー(%d 等)の直後に不要なスペースが入っているパターン。
# 文字列プレースホルダー(%s)は対象外: 公式スタイルガイド8章の例
# 「認証メールを %s へ送信しました。」の通り、単語相当の置換では
# 前後にスペースを入れる(1-4)ため、スペースの有無を機械判定できない
_PH_SPACE_RE = re.compile(r'(%(?:\d+\$)?[difu])[ \t]+(?=' + _JA + r')')
_NUM_SPACE_RE = re.compile(r'(\d)[ \t]+(?=' + _JA + r')')


def check_number_spacing(entry: PoEntry, filepath: Path) -> list[Violation]:
    """NUM_SPACING: 数字・プレースホルダー直後の不要なスペース。"""
    violations: list[Violation] = []

    for msgstr in _all_msgstrs(entry):
        m = _PH_SPACE_RE.search(msgstr)
        if m:
            # 前後の文脈を取得
            start = max(0, m.start() - 5)
            snippet = msgstr[start:m.end() + 5]
            violations.append(Violation(
                filepath=filepath,
                entry=entry,
                rule_id="NUM_SPACING",
                severity="WARN",
                message=(
                    f"数値プレースホルダー直後のスペースは不要です: 「...{snippet}...」\n"
                    f"  msgstr: \"{msgstr[:80]}\""
                ),
            ))
            continue  # 同一 msgstr で重複報告しない

        m = _NUM_SPACE_RE.search(msgstr)
        if m:
            start = max(0, m.start() - 5)
            snippet = msgstr[start:m.end() + 5]
            violations.append(Violation(
                filepath=filepath,
                entry=entry,
                rule_id="NUM_SPACING",
                severity="WARN",
                message=(
                    f"半角数字の直後にスペースは不要です: 「...{snippet}...」\n"
                    f"  msgstr: \"{msgstr[:80]}\""
                ),
            ))

    return violations


# 日本語直後の ! / ? にスペースがないパターン
# 例: 「〜ですか?」→「〜ですか ?」
_PUNCT_NOSPACE_RE = re.compile(r'(' + _JA + r')([!?])')


def check_punct_spacing(entry: PoEntry, filepath: Path) -> list[Violation]:
    """PUNCT_SPACING: 日本語の直後に来る ! / ? の前に半角スペースがあるか。"""
    violations: list[Violation] = []

    for msgstr in _all_msgstrs(entry):
        m = _PUNCT_NOSPACE_RE.search(msgstr)
        if m:
            start = max(0, m.start() - 5)
            snippet = msgstr[start:m.end() + 5]
            violations.append(Violation(
                filepath=filepath,
                entry=entry,
                rule_id="PUNCT_SPACING",
                severity="WARN",
                message=(
                    f"「{m.group(2)}」の前に半角スペースが必要です: 「...{snippet}...」\n"
                    f"  msgstr: \"{msgstr[:80]}\""
                ),
            ))

    return violations


# 表記統一チェック: 「下さい」→「ください」等
_WRITING_CHECKS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'下さい'),  '「下さい」ではなく「ください」を使う'),
    (re.compile(r'全て'),    '「全て」ではなく「すべて」を使う'),
    (re.compile(r'既に'),    '「既に」ではなく「すでに」を使う'),
]


def check_writing_conventions(entry: PoEntry, filepath: Path) -> list[Violation]:
    """WRITING_CONVENTION: 「ください」「すべて」「すでに」等の指定表記。"""
    violations: list[Violation] = []

    for msgstr in _all_msgstrs(entry):
        for pattern, description in _WRITING_CHECKS:
            if pattern.search(msgstr):
                violations.append(Violation(
                    filepath=filepath,
                    entry=entry,
                    rule_id="WRITING_CONVENTION",
                    severity="WARN",
                    message=(
                        f"{description}\n"
                        f"  msgstr: \"{msgstr[:80]}\""
                    ),
                ))

    return violations


# ---------------------------------------------------------------------------
# ファイル単位の検証
# ---------------------------------------------------------------------------

_CHECKS = [
    check_placeholders,
    check_brand_names,
    check_fullwidth,
    check_number_spacing,
    check_punct_spacing,
    check_writing_conventions,
]


def validate_file(filepath: Path) -> tuple[list[PoEntry], list[Violation]]:
    """
    .po ファイルを読み込み、全チェックを実行する。
    (entries, violations) を返す。
    """
    try:
        text = filepath.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        text = filepath.read_text(encoding='utf-8-sig')  # BOM 付き UTF-8 フォールバック

    entries = parse_po(text)
    violations: list[Violation] = []

    for entry in entries:
        if not _is_translated(entry):
            continue  # 未翻訳エントリーはスキップ
        for check in _CHECKS:
            violations.extend(check(entry, filepath))

    return entries, violations


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def _resolve_paths(patterns: list[str]) -> list[Path]:
    """
    ファイルパスまたは glob パターンのリストを実際の Path のリストに展開する。
    Windows でシェルが glob を展開しない場合にも対応。
    """
    paths: list[Path] = []
    for pattern in patterns:
        if any(c in pattern for c in ('*', '?', '[')):
            p = Path(pattern)
            matched = sorted(p.parent.glob(p.name))
            if not matched:
                print(f"警告: パターンに一致するファイルがありません: {pattern}", file=sys.stderr)
            paths.extend(matched)
        else:
            paths.append(Path(pattern))
    return paths


def main(argv: list[str] | None = None) -> int:
    # Windows の端末エンコーディングを UTF-8 に統一
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(
        description="WordPress 日本語翻訳 .po ファイルの品質チェック",
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
        "--errors-only",
        action="store_true",
        help="ERROR レベルの違反のみ表示する(WARN は表示しない)",
    )
    args = parser.parse_args(argv)

    paths = _resolve_paths(args.files)
    if not paths:
        return 2

    all_violations: list[Violation] = []
    has_read_error = False

    for filepath in paths:
        if not filepath.exists():
            print(f"[ERROR] ファイルが見つかりません: {filepath}", file=sys.stderr)
            has_read_error = True
            continue

        try:
            entries, violations = validate_file(filepath)
        except Exception as e:
            print(f"[ERROR] 読み込みエラー: {filepath}: {e}", file=sys.stderr)
            has_read_error = True
            continue

        translated = sum(1 for e in entries if _is_translated(e))
        print(f"checking: {filepath} ({len(entries)} エントリー、翻訳済み {translated} 件)")

        visible = [v for v in violations if not (args.errors_only and v.severity != "ERROR")]
        for v in visible:
            print()
            print(v.format())

        all_violations.extend(violations)

    print()

    if has_read_error:
        return 2

    if not all_violations:
        print("✅ 違反なし")
        return 0

    errors = [v for v in all_violations if v.severity == "ERROR"]
    warns = [v for v in all_violations if v.severity == "WARN"]
    print(f"{'=' * 60}")
    print(f"合計 {len(all_violations)} 件の違反  ({len(errors)} ERROR / {len(warns)} WARN)")
    if errors:
        print("→ ERROR は translate.wordpress.org へ反映する前に必ず修正してください")

    return 1 if all_violations else 0


if __name__ == "__main__":
    sys.exit(main())
