#!/usr/bin/env python3
"""validate_po.py の NUM_SPACING 系判定と --ignore のテスト (Issue #18)。

追加依存なし(標準ライブラリの unittest / subprocess のみ)。

    python -m unittest discover -s tests

判定ロジックは validate_po を import して直接叩き、CLI の挙動(終了コード・
サマリー)だけサブプロセスで確認する。test_cli.py は終了コードのスモーク
テスト専用なので、そちらとは分けている。

このディレクトリは開発用であり、配布物 (.skill) には含めない
(scripts/package_skill.py の EXCLUDE_DIR_NAMES と .gitattributes で除外)。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
VALIDATE = SCRIPTS_DIR / "validate_po.py"

sys.path.insert(0, str(SCRIPTS_DIR))

import validate_po  # noqa: E402


def rule_ids(msgstr: str) -> list[str]:
    """msgstr を1エントリーとして check_number_spacing にかけ、ルールIDを返す。"""
    entry = validate_po.PoEntry(msgid="dummy", msgstr=msgstr, line=1)
    return [v.rule_id for v in validate_po.check_number_spacing(entry, Path("dummy.po"))]


class NumberSpacingClassificationTest(unittest.TestCase):
    """バージョン番号・識別子トークンを NUM_SPACING_TOKEN に切り分ける (Issue #18)。"""

    def test_token_digits(self):
        """半角トークンの一部の数字は NUM_SPACING_TOKEN。"""
        cases = [
            "PHP 8.1 以上を必要とします。",       # 直前が半角英字 + スペース
            "PHP 8.0 より前のバージョン",
            "MainWP 5.0.2 の更新通知",
            "MainWP 101 動画ツアー",
            "ISO8601 の日時",                      # トークン内に英字
            "IPv4 の使用を強制",
            "UTC+0 のような有効な形式",
            "G2 でレビューする",
            "MainWP v6 では利用できません",        # メジャーバージョン略記
            "REST API v2 のみに対応",
            "v2 への切り替え",
            "run_updates_v1 を使用して",           # 識別子
            "list_sites_v1 を、単一サイトの",
        ]
        for msgstr in cases:
            with self.subTest(msgstr=msgstr):
                self.assertEqual(rule_ids(msgstr), ["NUM_SPACING_TOKEN"])

    def test_quantity_digits_stay_num_spacing(self):
        """数量・全角語直後の数字は NUM_SPACING のまま(退行検知)。"""
        cases = [
            "1 件のコメント。",
            "合計 33 件のエラー。",
            "バージョン 5 へのアップグレード",     # 公式 1-3 の例は「バージョン5.5」
            "バージョン 6.1 には接続処理",
            "LibreSSL をバージョン 2.5.0 以上に更新",
            "errors.length > 0 で確認して",        # トークンは 0 単体
        ]
        for msgstr in cases:
            with self.subTest(msgstr=msgstr):
                self.assertEqual(rule_ids(msgstr), ["NUM_SPACING"])

    def test_numeric_placeholder_stays_num_spacing(self):
        """数値プレースホルダー直後のスペースは従来どおり NUM_SPACING。"""
        self.assertEqual(rule_ids("%d 件の投稿"), ["NUM_SPACING"])
        self.assertEqual(rule_ids("%1$d 件の投稿"), ["NUM_SPACING"])

    def test_no_violation(self):
        """規約どおりの訳文では何も出ない。"""
        cases = [
            "1件のコメント。",
            "%d件の投稿",
            "PHP 8.1以上が必要です。",
            "認証メールを %s へ送信しました。",     # %s は対象外 (notation-rules 6-1)
        ]
        for msgstr in cases:
            with self.subTest(msgstr=msgstr):
                self.assertEqual(rule_ids(msgstr), [])

    def test_both_rules_in_one_msgstr(self):
        """1つの msgstr に両方あれば、それぞれ1件ずつ報告する。

        先頭1件で打ち切ると、トークン由来の WARN の陰に真の違反が隠れる。
        """
        ids = rule_ids("ISO8601 の日時は バージョン 5 では使えません")
        self.assertEqual(sorted(ids), ["NUM_SPACING", "NUM_SPACING_TOKEN"])

    def test_same_rule_reported_once_per_msgstr(self):
        """同一ルールは msgstr ごとに1件までにまとめる。"""
        self.assertEqual(rule_ids("1 件と 2 件と 3 件"), ["NUM_SPACING"])
        self.assertEqual(rule_ids("PHP 8.1 と PHP 8.2 の比較"), ["NUM_SPACING_TOKEN"])

    def test_plural_msgstr_is_checked(self):
        """複数形の msgstr[N] も対象。"""
        entry = validate_po.PoEntry(
            msgid="dummy", msgstr_plural=["ISO8601 の日時", "1 件のコメント"], line=1
        )
        ids = [v.rule_id for v in validate_po.check_number_spacing(entry, Path("dummy.po"))]
        self.assertEqual(sorted(ids), ["NUM_SPACING", "NUM_SPACING_TOKEN"])


SAMPLE_PO = '''msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"

#: t.php:1
msgid "Requires PHP 8.1 or later."
msgstr "PHP 8.1 以上を必要とします。"

#: t.php:2
msgid "1 comment"
msgstr "1 件のコメント。"
'''


class ValidateCliTest(unittest.TestCase):
    """--ignore と件数サマリーの CLI 挙動 (Issue #18)。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.po = Path(tmp.name) / "ja.po"
        self.po.write_text(SAMPLE_PO, encoding="utf-8")

    def run_validate(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATE), str(self.po), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )

    def test_summary_lists_each_rule(self):
        r = self.run_validate()
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("NUM_SPACING_TOKEN", r.stdout)
        self.assertIn("NUM_SPACING ", r.stdout)  # サマリー行(右詰めの件数の前に空白)
        self.assertIn("合計 2 件の違反", r.stdout)

    def test_ignore_hides_rule_from_output_and_summary(self):
        r = self.run_validate("--ignore", "NUM_SPACING_TOKEN")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertNotIn("NUM_SPACING_TOKEN", r.stdout)
        self.assertIn("合計 1 件の違反", r.stdout)

    def test_ignore_affects_exit_code(self):
        """--ignore で全部消えたら終了コード 0(--errors-only との違い)。"""
        r = self.run_validate("--ignore", "NUM_SPACING_TOKEN", "--ignore", "NUM_SPACING")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("違反なし", r.stdout)

    def test_ignore_accepts_comma_separated(self):
        r = self.run_validate("--ignore", "NUM_SPACING_TOKEN,NUM_SPACING")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_errors_only_does_not_change_exit_code(self):
        """--errors-only は表示を絞るだけ(既存挙動の退行検知)。"""
        r = self.run_validate("--errors-only")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertNotIn("[WARN ]", r.stdout)

    def test_unknown_rule_id_is_error(self):
        r = self.run_validate("--ignore", "NO_SUCH_RULE")
        self.assertEqual(r.returncode, 2)
        self.assertIn("不明なルールID", r.stderr)
        self.assertIn("NUM_SPACING_TOKEN", r.stderr)  # 候補一覧を出す

    def test_known_rule_ids_cover_all_emitted_rules(self):
        """チェック関数が出すルールIDが KNOWN_RULE_IDS から漏れていない。"""
        emitted = set()
        for msgstr in (
            "PHP 8.1 以上", "1 件のコメント", "ワードプレスの使い方", "全角０",
            "全角Ａ", "全角！", "担当者のFacebook", "ですか?", "下さい",
        ):
            entry = validate_po.PoEntry(msgid="WordPress", msgstr=msgstr, line=1)
            for check in validate_po._CHECKS:
                emitted.update(v.rule_id for v in check(entry, Path("dummy.po")))
        self.assertLessEqual(emitted, validate_po.KNOWN_RULE_IDS)


if __name__ == "__main__":
    unittest.main()
