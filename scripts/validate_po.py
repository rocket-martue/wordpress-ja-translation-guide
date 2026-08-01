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
    python scripts/validate_po.py --ignore NUM_SPACING_TOKEN path/to/ja.po

--errors-only と --ignore の違い:
    --errors-only  表示だけを ERROR に絞る。終了コードには影響しない
                   (WARN しかなくても 1 で終わる)
    --ignore RULE  指定したルールを表示・件数サマリー・終了コードのすべてから
                   除外する。「このルールは方針として受け入れ済み」の宣言に使う

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
  NUM_SPACING_TOKEN     バージョン番号・識別子トークン直後のスペース [WARN]
                        (例: 「PHP 8.1 以上」「ISO8601 の日時」。公式に規定がない
                         係争点なので NUM_SPACING と分けて報告する)
  ALPHA_SPACING         半角英字と全角文字の間に必要な半角スペースがない [WARN]
                        (例: 「担当者のFacebook」→「担当者の Facebook」)
  PUNCT_SPACING         日本語直後の ! / ? にスペースがない [WARN]
  ELLIPSIS              省略記号にピリオド3個を使っている [WARN]
                        (「読み込み中...」→「読み込み中…」。公式スタイルガイドに
                         規定はなく #ja-docs での合意に基づく)
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
_PH_STRIP_NUM_RE   = re.compile(r'\d+\$')   # %1$02d → %02d


def extract_placeholders(s: str) -> list[str]:
    """
    文字列からプレースホルダーを抽出する。%% は除外。
    ソート済みリストを返す(順序入れ替えを許容するため)。

    fix_spacing.py と共有する公開関数(シグネチャを変えないこと)。
    """
    return sorted(m for m in _PH_RE.findall(s) if m)


def _placeholders_compat(expected: list[str], actual: list[str]) -> bool:
    """
    apply_translations.py と同じ許容ルールでプレースホルダーを検証する。

    ステップ1: 番号除去後の multiset 一致（幅・精度・型を含む）
    ステップ2: expected に番号付きあり → Counter(完全一致)
    ステップ3: expected が全て番号なし、actual が全て番号付き →
      1..N 連番・重複なしであれば OK(語順変更のため)
    """
    # ステップ1: 番号除去後の multiset 一致（幅・精度・型を含む）
    if Counter(_PH_STRIP_NUM_RE.sub('', p, 1) for p in expected) != \
       Counter(_PH_STRIP_NUM_RE.sub('', p, 1) for p in actual):
        return False

    expected_has_numbered = any(_PH_NUMBERED_RE.match(p) for p in expected)
    actual_has_numbered   = any(_PH_NUMBERED_RE.match(p) for p in actual)

    if expected_has_numbered:
        # ステップ2: 完全一致を要求
        return Counter(expected) == Counter(actual)

    if actual_has_numbered:
        # ステップ3: 混在は NG、連番チェック
        if any(not _PH_NUMBERED_RE.match(p) for p in actual):
            return False
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
        expected = extract_placeholders(base)
        for idx, msgstr in enumerate(entry.msgstr_plural):
            if not msgstr:
                continue
            actual = extract_placeholders(msgstr)
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
        expected = extract_placeholders(entry.msgid)
        actual = extract_placeholders(entry.msgstr)
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
_PH_SPACE_RE = re.compile(r'(%(?:\d+\$)?[-+ 0]*\d*(?:\.\d+)?[difu])[ \t]+(?=' + _JA + r')')
_NUM_SPACE_RE = re.compile(r'(\d)[ \t]+(?=' + _JA + r')')

# 数字を含む「半角トークン」を構成する文字。バージョン番号 (8.1 / 2.5.0)、
# 規格名 (ISO8601 / IPv4 / UTC+0)、識別子・プロパティ参照 (run_updates_v1 /
# errors.length) を1つの塊として捉えるために使う
_TOKEN_CHAR_RE = re.compile(r'[A-Za-z0-9_.+-]')


def _is_token_digit(s: str, digit_index: int) -> bool:
    """
    s[digit_index] の数字が、数量ではなく半角トークンの一部とみなせるか。

    1-9「半角数字の前後には半角スペースを入れない」が対象にしているのは数量・
    数値(`1件のコメント`)であり、`PHP 8.1 以上` `ISO8601 の日時` のように数字が
    バージョン番号・規格名・識別子の一部になっている場合の扱いは公式スタイル
    ガイドに規定がない(notation-rules.md 1-9 の補足を参照)。そこで後者を
    NUM_SPACING_TOKEN として切り分け、仕分けできるようにする。

    判定は数字の直前だけを見る:

    1. 数字を含むトークンに ASCII 英字が含まれる
       → ISO8601 / IPv4 / UTC+0 / G2 / v1 / run_updates_v1 / errors.length
    2. トークンが純粋な数字列で、直前が「半角スペース + 半角英字」
       → PHP 8.1 / MainWP 5.0 / LibreSSL 2.5.0 / MainWP 101

    割り切り:

    - `バージョン 5 へ` のように全角語の直後に来る数字はどちらにも当たらず
      NUM_SPACING のまま。公式 1-3 の例が `バージョン5.5` である以上、これは
      真の違反として残すのが正しい
    - `errors.length > 0 で` はトークンが `0` 単体なので NUM_SPACING のまま。
      比較式までさかのぼると判定が過剰に複雑になるため踏み込まない
    - 逆に `Google 5 件のエラー` のような真の違反が 2 に当たって
      NUM_SPACING_TOKEN 側へ回ることはある。握りつぶすのではなく分類が
      変わるだけなので、この取りこぼしは許容する
    """
    start = digit_index
    while start > 0 and _TOKEN_CHAR_RE.match(s[start - 1]):
        start -= 1

    token = s[start:digit_index + 1]
    if any(_is_ascii_alpha(c) for c in token):
        return True

    # 「半角英字 + 半角スペース + 数字」(PHP 8.1)。全角語の直後は対象外
    return start >= 2 and s[start - 1] in ' \t' and _is_ascii_alpha(s[start - 2])


def _spacing_violation(
    entry: PoEntry, filepath: Path, msgstr: str, rule_id: str,
    match_start: int, match_end: int, message: str,
) -> Violation:
    """NUM_SPACING 系の Violation を、前後5文字の抜粋付きで組み立てる。"""
    snippet = msgstr[max(0, match_start - 5):match_end + 5]
    return Violation(
        filepath=filepath,
        entry=entry,
        rule_id=rule_id,
        severity="WARN",
        message=(
            f"{message}: 「...{snippet}...」\n"
            f"  msgstr: \"{msgstr[:80]}\""
        ),
    )


def check_number_spacing(entry: PoEntry, filepath: Path) -> list[Violation]:
    """
    NUM_SPACING       数値プレースホルダー(%d等)・半角数字直後の不要なスペース。
    NUM_SPACING_TOKEN バージョン番号・識別子トークン直後のスペース(公式に規定なし)。

    同一 msgstr からはルールIDごとに最大1件だけ報告する。1件目で打ち切ると
    `ISO8601 の日時と バージョン 5 では` のような訳文で真の違反が隠れるため、
    全マッチを走査したうえで重複排除する。
    """
    violations: list[Violation] = []

    for msgstr in _all_msgstrs(entry):
        reported: set[str] = set()

        m = _PH_SPACE_RE.search(msgstr)
        if m:
            reported.add("NUM_SPACING")
            violations.append(_spacing_violation(
                entry, filepath, msgstr, "NUM_SPACING", m.start(), m.end(),
                "数値プレースホルダー直後のスペースは不要です",
            ))

        for m in _NUM_SPACE_RE.finditer(msgstr):
            if _is_token_digit(msgstr, m.start(1)):
                rule_id = "NUM_SPACING_TOKEN"
                message = (
                    "バージョン番号・識別子とみられるトークン直後のスペースです"
                    " (公式に規定なし。プロジェクトの既存訳に合わせる。意図的なら修正不要)"
                )
            else:
                rule_id = "NUM_SPACING"
                message = "半角数字の直後にスペースは不要です"

            if rule_id in reported:
                continue
            reported.add(rule_id)
            violations.append(_spacing_violation(
                entry, filepath, msgstr, rule_id, m.start(), m.end(), message,
            ))

    return violations


# ---------------------------------------------------------------------------
# ALPHA_SPACING: 半角英字と全角文字の間の必須スペース (notation-rules.md 1-4)
#
# 公式スタイルガイド 1-4「数字を除く半角文字と全角文字の間には、半角文字1字分の
# スペースを入れる」に対応する。fix_spacing.py もここの
# find_alpha_fw_boundaries() を import して使う(検出ロジックを二重に持たない)。
# ---------------------------------------------------------------------------

# 全角文字クラス: 々〆〇、ひらがな、カタカナ(長音記号「ー」を含む)、漢字。
# 「」『』。、・ などの全角約物は 1-4 の例外(前後にスペースを入れない)なので
# 含めない。除外しておくことで例外規定を特別扱いせずに済む。
# (以下のコメントでは、除外対象の全角中点「・」と紛れないよう区切りに「、」を使う)
# カタカナ範囲を 30A0-30FA と 30FC-30FF に分けているのは、全角中点
# 「・」(U+30FB)を意図的に外すため。
_FW_CHAR_RE = re.compile(
    r'[々-〇ぁ-ゟ゠-ヺー-ヿ㐀-䶿一-鿿]'
)

# 判定から除外(マスク)する部分。この順に適用する。
_MASK_RES: list[re.Pattern] = [
    # バックスラッシュ + 1文字。主な目的は fix_spacing.py 対策で、あちらは
    # .po の生の行(エスケープ未展開)を扱うため、"...です\nAPI..." の n が
    # 全角文字と隣接して誤検出・誤挿入されるのを防ぐ。validate_po.py 側は
    # parse_po() で unescape 済みなのでこのケースは起きないが、訳文中に残る
    # リテラルなバックスラッシュ(例: "C:\\nドライブ" → C:\nドライブ)には
    # 同じ保護がかかる
    re.compile(r'\\.', re.DOTALL),
    # HTMLタグ
    re.compile(r'<[^<>]*>'),
    # HTMLエンティティ (&nbsp; &#8217; &#x2019; など)
    re.compile(r'&[A-Za-z][A-Za-z0-9]{0,31};|&#[0-9]{1,7};|&#x[0-9A-Fa-f]{1,6};'),
    # プレースホルダー。マスクしないと「%d件」の d が「件」と隣接して
    # 誤検出され、NUM_SPACING(数値直後はスペース不要)と矛盾する。
    # 定義が二重化して片方だけ更新される事故を防ぐため _PH_RE を再利用する
    # (キャプチャグループがあるが、_mask_ignored は m.group() = マッチ全体を
    #  使うので影響しない)
    _PH_RE,
]

_MASK_CHAR = '\x00'


def _mask_ignored(s: str, patterns: list[re.Pattern] | None = None) -> str:
    """判定対象外の部分を同じ長さの制御文字で潰す(オフセットは保つ)。"""
    masked = s
    for pattern in (_MASK_RES if patterns is None else patterns):
        masked = pattern.sub(lambda m: _MASK_CHAR * len(m.group()), masked)
    return masked


def _is_ascii_alpha(ch: str) -> bool:
    return ch.isascii() and ch.isalpha()


def find_alpha_fw_boundaries(s: str) -> list[int]:
    """
    半角英字と全角文字が直接隣接している位置(= 半角スペースを挿入すべき
    オフセット)のリストを返す。fix_spacing.py と共有する公開関数
    (シグネチャを変えないこと)。

    - 半角数字は対象外(1-9 の「数字の前後にスペースを入れない」が適用される)
    - HTMLタグ、HTMLエンティティ、プレースホルダー、エスケープシーケンスは対象外
    - 全角約物(「」『』。、・)は _FW_CHAR_RE に含めていないため自動的に対象外
    """
    masked = _mask_ignored(s)
    positions: list[int] = []
    for i in range(len(masked) - 1):
        a, b = masked[i], masked[i + 1]
        if (_is_ascii_alpha(a) and _FW_CHAR_RE.match(b)) or \
           (_FW_CHAR_RE.match(a) and _is_ascii_alpha(b)):
            positions.append(i + 1)
    return positions


def check_alpha_spacing(entry: PoEntry, filepath: Path) -> list[Violation]:
    """ALPHA_SPACING: 半角英字と全角文字の間に半角スペースがあるか (1-4)。"""
    violations: list[Violation] = []

    for msgstr in _all_msgstrs(entry):
        positions = find_alpha_fw_boundaries(msgstr)
        if not positions:
            continue

        pos = positions[0]
        snippet = msgstr[max(0, pos - 5):pos + 5]
        more = f"(他 {len(positions) - 1} 箇所)" if len(positions) > 1 else ""
        violations.append(Violation(
            filepath=filepath,
            entry=entry,
            rule_id="ALPHA_SPACING",
            severity="WARN",
            message=(
                f"半角英字と全角文字の間に半角スペースが必要です: 「...{snippet}...」{more}\n"
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


# 省略記号にピリオド3個(以上)を使っている箇所。
# 公式スタイルガイドには規定がなく、Making WordPress Slack #ja-docs での合意と、
# @wordpress/eslint-plugin の i18n-ellipsis ルールに基づく (notation-rules.md 7)
_ELLIPSIS_RE = re.compile(r'\.{3,}')

# ELLIPSIS 判定でだけ追加でマスクするもの。URL 中のピリオドを違反にしないため。
# HTMLタグ・エンティティ・プレースホルダーは _MASK_RES 側で既に除外される
# (`&hellip;` は三点リーダーの別表記なので、そもそもこの正規表現に当たらない)
#
# 末尾は URL に使われる文字だけを許し、ピリオド・カンマ・閉じ括弧などの約物では
# 終わらせない。単純に「空白以外の連続」にすると `(https://example.com)...` の
# `)...` まで URL の一部として飲み込み、URL の外にある省略記号を見逃す。貪欲
# マッチ + 末尾の文字クラスで、直後に続く約物や日本語の手前まで戻して切る
_URL_RE = re.compile(r'(?:https?|ftp)://[^\s"\'<>]*[A-Za-z0-9/#=&%_~+-]')
_ELLIPSIS_MASK_RES = _MASK_RES + [_URL_RE]


def check_ellipsis(entry: PoEntry, filepath: Path) -> list[Violation]:
    """ELLIPSIS: 省略記号にピリオド3個を使っていないか(三点リーダー「…」に統一)。"""
    violations: list[Violation] = []

    for msgstr in _all_msgstrs(entry):
        m = _ELLIPSIS_RE.search(_mask_ignored(msgstr, _ELLIPSIS_MASK_RES))
        if m:
            snippet = msgstr[max(0, m.start() - 8):m.end() + 8]
            violations.append(Violation(
                filepath=filepath,
                entry=entry,
                rule_id="ELLIPSIS",
                severity="WARN",
                message=(
                    f"省略記号はピリオド3個ではなく三点リーダー「…」(U+2026) を使います"
                    f" (#ja-docs での合意。notation-rules.md 7 参照): 「{snippet}」\n"
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
    check_alpha_spacing,
    check_punct_spacing,
    check_ellipsis,
    check_writing_conventions,
]

# --ignore に指定できるルールID。タイポを終了コード 2 で弾くために使う。
# チェック関数を増やしたらここにも追加する
KNOWN_RULE_IDS = frozenset({
    "PH_MISMATCH",
    "BRAND_TRANSLITERATION",
    "FULLWIDTH_DIGIT",
    "FULLWIDTH_ALPHA",
    "FULLWIDTH_PUNCT",
    "NUM_SPACING",
    "NUM_SPACING_TOKEN",
    "ALPHA_SPACING",
    "PUNCT_SPACING",
    "ELLIPSIS",
    "WRITING_CONVENTION",
})


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

def resolve_paths(patterns: list[str]) -> list[Path]:
    """
    ファイルパスまたは glob パターンのリストを実際の Path のリストに展開する。
    Windows でシェルが glob を展開しない場合にも対応。

    fix_spacing.py と共有する公開関数(シグネチャを変えないこと)。
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
        help="ERROR レベルの違反のみ表示する(WARN は表示しない。終了コードは変わらない)",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        metavar="RULE",
        default=[],
        help=(
            "指定したルールIDを表示・件数サマリー・終了コードのすべてから除外する"
            "(複数指定可、カンマ区切り可。例: --ignore NUM_SPACING_TOKEN)"
        ),
    )
    args = parser.parse_args(argv)

    ignored: set[str] = {
        rule.strip() for item in args.ignore for rule in item.split(",") if rule.strip()
    }
    unknown = sorted(ignored - KNOWN_RULE_IDS)
    if unknown:
        print(f"[ERROR] 不明なルールID: {', '.join(unknown)}", file=sys.stderr)
        print(f"  指定できるルールID: {', '.join(sorted(KNOWN_RULE_IDS))}", file=sys.stderr)
        return 2

    paths = resolve_paths(args.files)
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

        if ignored:
            violations = [v for v in violations if v.rule_id not in ignored]

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

    # ルールID別の内訳。ERROR → WARN の順、同一重大度内は件数の多い順
    by_rule = Counter((v.severity, v.rule_id) for v in all_violations)
    for (severity, rule_id), count in sorted(
        by_rule.items(), key=lambda kv: (kv[0][0] != "ERROR", -kv[1], kv[0][1])
    ):
        print(f"  {severity:<5}  {rule_id:<22}{count:>4} 件")

    if errors:
        print("→ ERROR は translate.wordpress.org へ反映する前に必ず修正してください")

    return 1 if all_violations else 0


if __name__ == "__main__":
    sys.exit(main())
