#!/usr/bin/env python3
"""
translate.wordpress.org の日本語ロケール公式用語集 (glossary) を取得し、
references/glossary.md の自動生成ブロックを更新するスクリプト。

依存ライブラリなし(Python標準ライブラリのみ)。Python 3.10以降で動作確認。
package_skill.py と同じくメンテナンス用ツールであり、.skill には同梱しない。

使い方:
    python scripts/update_glossary.py            # 取得して references/glossary.md を更新
    python scripts/update_glossary.py --check    # 差分があれば終了コード1(更新漏れの検出用)
    python scripts/update_glossary.py --from-file glossary.html  # 取得済みHTMLから生成

references/glossary.md の
    <!-- glossary:begin --> 〜 <!-- glossary:end -->
の間だけを置き換える。マーカーの外側(前書き・使い方など手書きの部分)は変更しない。
"""
import argparse
import datetime
import html
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

# このスクリプトの一つ上の階層 = リポジトリルート
REPO_DIR = Path(__file__).resolve().parent.parent

GLOSSARY_URL = "https://translate.wordpress.org/locale/ja/default/glossary/"
DEFAULT_OUTPUT = "references/glossary.md"

BEGIN_MARKER = "<!-- glossary:begin -->"
END_MARKER = "<!-- glossary:end -->"

# 取得日の行は内容が同じでも毎回変わるため、差分比較の対象から外す
FETCHED_AT_PREFIX = "<!-- 取得日:"

USER_AGENT = (
    "wordpress-ja-translation-guide update_glossary.py "
    "(+https://github.com/rocket-martue/wordpress-ja-translation-guide)"
)

NEW_FILE_TEMPLATE = """# WordPress 日本語用語集(公式 glossary のスナップショット)

{begin}
{end}
"""


class GlossaryParser(HTMLParser):
    """GlotPress の用語集ページから <tr class="view"> の行を抜き出す。

    同じテーブルには編集フォームの <tr id="editor-..."> も含まれるが、
    class="view" を持たないため対象外になる。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._cells: list[str] = []
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        if tag == "table" and attr.get("id") == "glossary":
            self._in_table = True
            return
        if not self._in_table:
            return
        if tag == "tr" and "view" in attr.get("class", "").split():
            self._in_row = True
            self._cells = []
            return
        if tag == "td" and self._in_row:
            self._in_cell = True
            self._buffer = []
        elif tag == "br" and self._in_cell:
            self._buffer.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self._in_table:
            return
        if tag == "table":
            self._in_table = False
        elif tag == "td" and self._in_cell:
            self._in_cell = False
            self._cells.append("".join(self._buffer).strip())
        elif tag == "tr" and self._in_row:
            self._in_row = False
            if len(self._cells) >= 4:
                self.rows.append(self._cells[:4])

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._buffer.append(data)


def fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_glossary(page: str) -> list[list[str]]:
    parser = GlossaryParser()
    parser.feed(page)
    entries = [[html.unescape(cell) for cell in row] for row in parser.rows]
    # 差分を安定させるため、公式ページと同じ「原語のアルファベット順」で並べ直す
    entries.sort(key=lambda row: (row[0].lower(), row[1], row[2]))
    return entries


def escape_cell(text: str) -> str:
    """Markdownのテーブルセルとして安全な1行の文字列にする。"""
    text = text.replace("|", r"\|")
    text = re.sub(r"\s*\n\s*", "<br>", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def render_block(entries: list[list[str]], fetched_at: str) -> str:
    lines = [
        BEGIN_MARKER,
        "<!-- ここから下は scripts/update_glossary.py が自動生成します。手で編集しないでください。 -->",
        f"<!-- 取得日: {fetched_at} / 収録件数: {len(entries)}件 -->",
        "",
        "| 英語 | 品詞 | 日本語訳 | 補足 |",
        "|---|---|---|---|",
    ]
    for term, part_of_speech, translation, comment in entries:
        cells = [escape_cell(cell) for cell in (term, part_of_speech, translation, comment)]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(END_MARKER)
    return "\n".join(lines)


def strip_volatile(block: str) -> str:
    """取得日の行を除いたブロックを返す(内容比較用)。"""
    return "\n".join(
        line for line in block.splitlines() if not line.startswith(FETCHED_AT_PREFIX)
    )


def extract_block(text: str) -> str | None:
    start = text.find(BEGIN_MARKER)
    if start == -1:
        return None
    # 手書き部分に END_MARKER と同じ文字列があっても拾わないよう、
    # 開始マーカーより後ろから終了マーカーを探す
    end = text.find(END_MARKER, start + len(BEGIN_MARKER))
    if end == -1:
        return None
    return text[start:end + len(END_MARKER)]


def update_file(output_path: Path, block: str, check_only: bool) -> bool:
    """ファイルを更新したら True、内容に変更がなければ False を返す。"""
    if not output_path.exists():
        if check_only:
            sys.exit(f"エラー: {output_path} が存在しません")
        text = NEW_FILE_TEMPLATE.format(begin=BEGIN_MARKER, end=END_MARKER)
    else:
        text = output_path.read_text(encoding="utf-8")

    current = extract_block(text)
    if current is None:
        sys.exit(
            f"エラー: {output_path} に {BEGIN_MARKER} / {END_MARKER} が見つかりません。"
            "手書き部分を巻き込まないよう、マーカーを追加してから実行してください"
        )

    if strip_volatile(current) == strip_volatile(block):
        return False

    if not check_only:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # 置換は1回だけ(同じ内容がファイル内に複数あっても巻き込まない)
        output_path.write_text(text.replace(current, block, 1), encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="公式用語集を取得して references/glossary.md を更新する"
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT,
        help=f"出力先(デフォルト: {DEFAULT_OUTPUT}。リポジトリルートからの相対パス)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="ファイルを書き換えず、差分があれば終了コード1で終了する",
    )
    parser.add_argument(
        "--from-file",
        help="取得済みのHTMLファイルから生成する(ネットワークにアクセスしない)",
    )
    parser.add_argument(
        "--url",
        default=GLOSSARY_URL,
        help=f"取得元URL(デフォルト: {GLOSSARY_URL})",
    )
    args = parser.parse_args(argv)

    if args.from_file:
        page = Path(args.from_file).read_text(encoding="utf-8", errors="replace")
        print(f"📄 HTMLを読み込み: {args.from_file}")
    else:
        print(f"🌐 取得中: {args.url}")
        page = fetch_html(args.url)

    entries = parse_glossary(page)
    if not entries:
        sys.exit("エラー: 用語集のエントリーを1件も取得できませんでした(ページ構造の変更を確認してください)")
    print(f"　 {len(entries)}件のエントリーを取得しました")

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = REPO_DIR / output_path

    fetched_at = datetime.date.today().isoformat()
    block = render_block(entries, fetched_at)
    changed = update_file(output_path, block, args.check)

    if not changed:
        print(f"✅ 変更はありません: {output_path}")
        return 0
    if args.check:
        print(f"❌ {output_path} が最新ではありません。`python scripts/update_glossary.py` を実行してください")
        return 1
    print(f"✅ 更新しました: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
