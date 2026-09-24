#!/usr/bin/env python3
"""分担パイプライン(po_chunk.py / po_collect.py / po_apply_loop.py)の回帰テストを unittest から呼ぶ。

    python -m unittest discover -s tests

本体は tests/orchestration/ にある自前ハーネス(run_all.py)。各テストは使い捨ての .po と
作業ディレクトリを作り、スクリプトをサブプロセスとして実際に走らせる。ここではそれを
1 つの unittest ケースとして包み、終了コード 0(全ファイル PASS)を検査する。

個別に走らせたいときは直接呼ぶ:

    python tests/orchestration/run_all.py            # 全部
    python tests/orchestration/run_all.py chunk_index  # 名前で絞る
    python tests/orchestration/run_all.py -v         # 各ケースの PASS 行も出す

このディレクトリは開発用であり、配布物 (.skill) には含めない
(scripts/package_skill.py の EXCLUDE_DIR_NAMES と .gitattributes で除外)。
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_ALL = REPO_ROOT / "tests" / "orchestration" / "run_all.py"


class OrchestrationRegressionTest(unittest.TestCase):
    def test_run_all_passes(self) -> None:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run(
            [sys.executable, str(RUN_ALL)],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env,
        )
        self.assertEqual(
            r.returncode, 0,
            "tests/orchestration/run_all.py が失敗しました:\n%s\n%s" % (r.stdout[-3000:], r.stderr[-1000:]),
        )
        self.assertIn("0 failed", r.stdout)


if __name__ == "__main__":
    unittest.main()
