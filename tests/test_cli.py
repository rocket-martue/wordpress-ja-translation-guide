#!/usr/bin/env python3
"""scripts/ 配下 CLI のスモークテスト。

追加依存なし(標準ライブラリの unittest / subprocess のみ)。

    python -m unittest discover -s tests

各スクリプトを import せずサブプロセスで起動し、**プロセスの終了コード**を
検査する。Issue #13 が問題にしているのは終了コードそのものであり、また
--help は argparse が SystemExit(0) を送出するため main() の戻り値では
判定できないため。

このディレクトリは開発用であり、配布物 (.skill) には含めない
(scripts/package_skill.py の EXCLUDE_DIR_NAMES と .gitattributes で除外)。

注意: update_glossary.py は実行すると外部サイトを取得し、package_skill.py は
.skill をビルドする。このテストではどちらも --help のみを実行する。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
APPLY = SCRIPTS_DIR / "apply_translations.py"

# 未翻訳エントリー2件(ヘッダーは msgid が空なので未翻訳に数えられない)
SAMPLE_PO = '''msgid ""
msgstr ""
"Project-Id-Version: test 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"

#: src/example.php:12
msgid "Save changes"
msgstr ""

#: src/example.php:34
msgid "Delete"
msgstr ""
'''


def run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class HelpExitCodeTest(unittest.TestCase):
    """--help / -h は終了コード 0 で終わる (Issue #13)。"""

    def test_apply_translations_help(self):
        for args in (["--help"], ["-h"]):
            with self.subTest(args=args):
                r = run_script(APPLY, *args)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("PO_FILE", r.stdout)

    def test_apply_translations_help_after_positional(self):
        """PO_FILE の後ろに置いてもヘルプが出て 0 で終わる。"""
        r = run_script(APPLY, "ja.po", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PO_FILE", r.stdout)

    def test_usage_line_matches_actual_interface(self):
        """usage 行に、実際には動かない apply サブコマンドが現れない。"""
        r = run_script(APPLY, "--help")
        # usage は複数行に折り返されるため、最初の空行までをまとめて見る
        usage = r.stdout.split("\n\n")[0]
        self.assertNotIn("apply}", usage)
        self.assertIn("--list", usage)
        self.assertIn("TRANSLATIONS", usage)

    def test_sibling_scripts_help(self):
        """他のスクリプトも 0 のままであること(退行検知)。"""
        for name in (
            "validate_po.py",
            "fix_spacing.py",
            "update_glossary.py",
            "package_skill.py",
        ):
            with self.subTest(script=name):
                r = run_script(SCRIPTS_DIR / name, "--help")
                self.assertEqual(r.returncode, 0, r.stderr)


class ApplyTranslationsArgsTest(unittest.TestCase):
    """apply_translations.py の引数パースの分岐。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_dir = Path(tmp.name)
        self.po = self.tmp_dir / "ja.po"
        self.po.write_text(SAMPLE_PO, encoding="utf-8")

    def test_no_args_shows_help_and_fails(self):
        r = run_script(APPLY)
        self.assertEqual(r.returncode, 2)
        self.assertIn("PO_FILE", r.stdout)

    def test_list(self):
        r = run_script(APPLY, str(self.po), "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("全 2 件", r.stdout)
        self.assertIn("Save changes", r.stdout)
        self.assertIn("Delete", r.stdout)

    def test_list_with_start_and_count(self):
        r = run_script(APPLY, str(self.po), "--list", "--start", "1", "--count", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Delete", r.stdout)
        self.assertNotIn("Save changes", r.stdout)

    def test_apply_inline_json(self):
        payload = json.dumps(
            {"0": {"msgid": "Save changes", "msgstr": "変更を保存"}},
            ensure_ascii=False,
        )
        r = run_script(APPLY, str(self.po), payload)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("変更を保存", self.po.read_text(encoding="utf-8"))

    def test_apply_json_file(self):
        json_path = self.tmp_dir / "translations.json"
        json_path.write_text(
            json.dumps(
                {"1": {"msgid": "Delete", "msgstr": "削除"}},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        r = run_script(APPLY, str(self.po), str(json_path))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("削除", self.po.read_text(encoding="utf-8"))

    def test_list_with_translations_is_error(self):
        r = run_script(APPLY, str(self.po), "--list", "translations.json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("同時に指定できません", r.stderr)

    def test_missing_translations_is_error(self):
        r = run_script(APPLY, str(self.po))
        self.assertEqual(r.returncode, 2)
        self.assertIn("TRANSLATIONS を指定してください", r.stderr)

    def test_start_without_list_is_error(self):
        r = run_script(APPLY, str(self.po), "translations.json", "--start", "20")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--list と一緒に指定してください", r.stderr)

    def test_non_integer_start_is_error(self):
        r = run_script(APPLY, str(self.po), "--list", "--start", "abc")
        self.assertEqual(r.returncode, 2)
        self.assertIn("整数を指定してください", r.stderr)

    def test_missing_po_file_is_error(self):
        r = run_script(APPLY, str(self.tmp_dir / "missing.po"), "--list")
        self.assertEqual(r.returncode, 2)
        self.assertIn("[ERROR]", r.stderr)


if __name__ == "__main__":
    unittest.main()
