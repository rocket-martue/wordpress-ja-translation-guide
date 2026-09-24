#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下訳パイプライン(po_chunk.py / po_collect.py)の回帰テストをまとめて走らせる。

    python scripts/tests/run_all.py            # 全部
    python scripts/tests/run_all.py chunk_index  # 名前に一致するものだけ
    python scripts/tests/run_all.py -v         # 各ケースの PASS 行も出す

各テストは使い捨ての `.po` と作業ディレクトリを作り、スクリプトをサブプロセスとして
実際に走らせる。**リポジトリ内のファイルは書き換えない**(見本として読むだけ)。
外部ネットワークにも触らないので、いつ走らせても同じ結果になる。

テストはすべて「過去に踏んだ壊れ方の再現」で、修正前なら落ちる。新しい不具合を直すときは、
まず再現するケースを足してから直す。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PY = sys.executable
SUMMARY_RE = "===="


def main() -> int:
    args = [a for a in sys.argv[1:]]
    verbose = "-v" in args or "--verbose" in args
    patterns = [a for a in args if not a.startswith("-")]

    files = sorted(HERE.glob("test_*.py"))
    if patterns:
        files = [p for p in files if any(pat in p.name for pat in patterns)]
    if not files:
        print("一致するテストがありません: %s" % ", ".join(patterns))
        return 2

    failed: list[str] = []
    total_pass = total_fail = 0
    for p in files:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([PY, str(p)], cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        summary = ""
        for line in (r.stdout or "").splitlines():
            if line.startswith(SUMMARY_RE):
                summary = line
            if verbose or line.startswith("FAIL") or line.startswith("SKIP"):
                print("  " + line)
        # 「N passed / M failed」を拾って合計する
        nums = [int(t) for t in summary.replace("=", " ").replace("/", " ").split() if t.isdigit()]
        if len(nums) >= 2:
            total_pass += nums[0]
            total_fail += nums[1]
        print("%-6s %-30s %s" % ("OK" if r.returncode == 0 else "FAIL", p.name, summary.strip("= ")))
        if r.returncode != 0:
            failed.append(p.name)
            if not verbose:      # 失敗したファイルは出力を全部見せる
                print(r.stdout)
                print(r.stderr, file=sys.stderr)

    print("\n======== 合計 %d passed / %d failed (%d ファイル) ========" % (total_pass, total_fail, len(files)))
    for name in failed:
        print("  FAILED:", name)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
