#!/usr/bin/env python3
"""Claude Code プラグインとして配るためのマニフェスト(.claude-plugin/)のテスト。

追加依存なし(標準ライブラリの unittest のみ)。

    python -m unittest discover -s tests

プラグインは「ルートの SKILL.md を単一スキルとして読み込み、assets/agents/ の定義を
plugin.json の agents から名指しする」構成で成り立っている。ファイルを動かしたり
名前を変えたりすると、エラーにならないままエージェントが登録されなくなるので、
マニフェストが指す先と名前の対応をここで固定する。

`claude plugin validate` は Claude Code が要るので、ここからは呼ばない。

このディレクトリは開発用であり、配布物 (.skill) には含めない
(scripts/package_skill.py の EXCLUDE_DIR_NAMES と .gitattributes で除外)。
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO_ROOT / ".claude-plugin"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

import package_skill  # noqa: E402


def load(name: str) -> dict:
    return json.loads((PLUGIN_DIR / name).read_text(encoding="utf-8"))


def frontmatter(path: Path) -> dict[str, str]:
    """先頭の --- 〜 --- から `key: value` の行だけを拾う(入れ子は見ない)。"""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if km:
            out[km.group(1)] = km.group(2).strip()
    return out


class PluginManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = load("plugin.json")
        self.market = load("marketplace.json")

    def test_plugin_name_matches_skill_name(self):
        """手順書に書いた呼び出し名(<プラグイン名>:<スキル名>)が実物と一致する。"""
        skill_name = frontmatter(REPO_ROOT / "SKILL.md").get("name")
        self.assertEqual(self.plugin["name"], "wordpress-ja-translation-guide")
        self.assertEqual(skill_name, "wordpress-ja-translation-guide")

    def test_plugin_has_no_version(self):
        """version を書くと、その文字列を変えるまで利用者の更新が止まる。"""
        self.assertNotIn("version", self.plugin)
        for entry in self.market["plugins"]:
            self.assertNotIn("version", entry)

    def test_agents_point_to_existing_files(self):
        """agents は .md ファイルを名指しする(ディレクトリは受け付けられない)。"""
        agents = self.plugin["agents"]
        self.assertIsInstance(agents, list)
        self.assertTrue(agents)
        for rel in agents:
            with self.subTest(agent=rel):
                self.assertTrue(rel.startswith("./"), rel)
                self.assertNotIn("..", rel)
                path = REPO_ROOT / rel
                self.assertTrue(path.is_file(), f"{rel} が見つかりません")
                self.assertEqual(path.suffix, ".md")

    def test_every_bundled_agent_is_registered(self):
        """assets/agents/ に定義を足したのに plugin.json に書き忘れる、を防ぐ。"""
        bundled = sorted(
            "./" + p.relative_to(REPO_ROOT).as_posix()
            for p in (REPO_ROOT / "assets" / "agents").glob("*.md")
        )
        self.assertEqual(sorted(self.plugin["agents"]), bundled)

    def test_agent_preloads_this_skill(self):
        """エージェント定義の name と、プリロードする Skill の名前が手順書どおり。"""
        path = REPO_ROOT / "assets" / "agents" / "po-draft-translator.md"
        self.assertEqual(frontmatter(path).get("name"), "po-draft-translator")
        self.assertRegex(
            path.read_text(encoding="utf-8"),
            r"skills:\s*\r?\n\s+- wordpress-ja-translation-guide\r?\n",
        )

    def test_no_default_plugin_directories(self):
        """ルートの SKILL.md が単一スキルとして読まれるのは skills/ が無いときだけ。
        agents/ があると、plugin.json の agents と二重管理になる。"""
        for name in ("skills", "agents", "commands"):
            with self.subTest(directory=name):
                self.assertFalse((REPO_ROOT / name).exists(), f"{name}/ を作らない")
        self.assertNotIn("skills", self.plugin)

    def test_marketplace_lists_this_repository(self):
        self.assertTrue(self.market["owner"]["name"])
        self.assertEqual(len(self.market["plugins"]), 1)
        entry = self.market["plugins"][0]
        self.assertEqual(entry["name"], self.plugin["name"])
        self.assertEqual(entry["source"], "./")

    def test_readme_install_lines_match_manifest(self):
        """README のインストール手順が、マニフェストの名前とずれない。"""
        line = "/plugin install %s@%s" % (self.plugin["name"], self.market["name"])
        for name in ("README.md", "README.en.md"):
            with self.subTest(readme=name):
                self.assertIn(line, (REPO_ROOT / name).read_text(encoding="utf-8"))

    def test_manifest_is_not_packaged_into_skill(self):
        """.skill の中身は変えない(マニフェストは .skill の利用者には要らない)。"""
        self.assertTrue(package_skill.is_excluded(Path(".claude-plugin/plugin.json")))
        self.assertTrue(package_skill.is_excluded(Path(".claude-plugin/marketplace.json")))
        self.assertFalse(package_skill.is_excluded(Path("assets/agents/po-draft-translator.md")))
        self.assertFalse(package_skill.is_excluded(Path("SKILL.md")))


if __name__ == "__main__":
    unittest.main()
