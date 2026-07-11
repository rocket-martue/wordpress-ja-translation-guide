#!/usr/bin/env python3
"""
wordpress-ja-translation-guide の .skill ファイル(zip)を生成するスクリプト。

依存ライブラリなし(Python標準ライブラリのみ)。Python 3.8以降で動作確認。
リポジトリのルート(このファイルの一つ上の階層)を1つのスキルフォルダとして
zip化し、Claude.ai / Claude Code にアップロードできる .skill ファイルを作る。

使い方:
    python scripts/package_skill.py
    python scripts/package_skill.py --output-dir dist

出力:
    dist/wordpress-ja-translation-guide.skill (デフォルト)
"""
import argparse
import sys
import zipfile
from pathlib import Path

# このスクリプトの一つ上の階層 = リポジトリルート = スキルフォルダそのもの
SKILL_DIR = Path(__file__).resolve().parent.parent

# .skill に含めないディレクトリ・ファイル
# 注: scripts/ ディレクトリ自体は同梱する(apply_translations.py と validate_po.py は
# SKILL.md が参照するランタイムツールのため)。ビルドツールの package_skill.py のみ除外する
EXCLUDE_DIR_NAMES = {".git", ".github", ".claude", "__pycache__", "node_modules", "dist", "evals"}
EXCLUDE_FILE_NAMES = {".DS_Store", ".gitignore", ".gitattributes", "CLAUDE.md", "package_skill.py"}
EXCLUDE_SUFFIXES = {".pyc", ".skill"}


def is_excluded(rel_path: Path) -> bool:
    """skill_dir からの相対パスを見て、zipに含めないかどうかを判定する。"""
    if any(part in EXCLUDE_DIR_NAMES for part in rel_path.parts[:-1]):
        return True
    if rel_path.name in EXCLUDE_FILE_NAMES:
        return True
    if rel_path.suffix in EXCLUDE_SUFFIXES:
        return True
    return False


def validate_skill_md(skill_dir: Path) -> None:
    """SKILL.md が存在し、最低限の frontmatter (name, description) を
    持っているかをチェックする。Claude.ai / Claude Code はこの2つが
    ないとSkillとして認識しない。"""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        sys.exit(f"エラー: {skill_md} が見つかりません")

    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        sys.exit("エラー: SKILL.md の先頭にYAML frontmatter (---) がありません")

    parts = text.split("---", 2)
    if len(parts) < 3:
        sys.exit("エラー: SKILL.md の frontmatter (--- 〜 ---) が閉じられていません")

    frontmatter = parts[1]
    if "name:" not in frontmatter or "description:" not in frontmatter:
        sys.exit("エラー: frontmatterに name または description がありません")


def package_skill(skill_dir: Path, output_dir: Path) -> Path:
    validate_skill_md(skill_dir)

    skill_name = skill_dir.name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{skill_name}.skill"

    print(f"📦 スキルをパッケージング中: {skill_dir}")

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_dir.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(skill_dir)
            if is_excluded(rel):
                continue
            # zip内では skill_name/ をルートにする
            # (アップロード時に展開すると skill_name フォルダができる形)
            arcname = f"{skill_name}/{rel.as_posix()}"
            zf.write(path, arcname=arcname)
            print(f"  追加: {arcname}")

    print(f"\n✅ 生成しました: {output_path}")
    return output_path


def main() -> None:
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(
        description=f"{SKILL_DIR.name} の .skill ファイルを生成する"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="dist",
        help="出力先ディレクトリ(デフォルト: dist。リポジトリルートからの相対パス)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = SKILL_DIR / output_dir

    package_skill(SKILL_DIR, output_dir)


if __name__ == "__main__":
    main()
