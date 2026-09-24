# -*- coding: utf-8 -*-
"""回帰テストの共通部分。

各テストは `po_chunk.py` / `po_collect.py` を**サブプロセスとして実際に走らせ**、
使い捨ての `.po` と作業ディレクトリで入出力を確かめる。機械チェックのような純粋関数だけは
`scripts/` から import して直接呼ぶ。

テストはすべて「過去に踏んだ壊れ方の再現」で、修正前なら落ちるように書いてある。
新しい不具合を直すときは、まず再現するケースをここに足してから直す。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]      # リポジトリルート
FIXTURES = Path(__file__).resolve().parent / "fixtures"   # 合成フィクスチャ(.po)
PY = sys.executable

# Windows の既定 stdout は cp932。パイプに日本語のラベルを書くと、読む側(run_all.py)が
# UnicodeDecodeError で落ちて集計できない
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# テストから `from po_collect import ...` できるようにする
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


class Result:
    """1 ファイル分の合否。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, cond, detail: str = "") -> bool:
        ok = bool(cond)
        (self.passed if ok else self.failed).append(label)
        print("%s %s%s" % ("PASS" if ok else "FAIL", label,
                           ("  -- " + detail) if detail and not ok else ""))
        return ok

    def report(self) -> int:
        """集計を出して終了コードを返す。"""
        print("\n==== %s: %d passed / %d failed ====" % (self.name, len(self.passed), len(self.failed)))
        for label in self.failed:
            print("  FAILED:", label)
        return 1 if self.failed else 0


def run(args: list[str], check_rc: bool = False) -> subprocess.CompletedProcess:
    """`scripts/` のコマンドをリポジトリルートで実行する。

    `check_rc` は「ここで失敗したらテストの前提が崩れる」ときだけ真にする
    (検証したい終了コードは戻り値で見る)。
    """
    r = subprocess.run([PY] + args, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    if check_rc and r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        raise SystemExit("command failed (%d): %r" % (r.returncode, args))
    return r


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def write_draft(work: Path, name: str, items) -> None:
    """下訳ドラフトを `<work>/drafts/<name>` に置く。"""
    write_json(work / "drafts" / name, items)


def chunk_index(work: Path, name: str = "chunk_00") -> dict[str, dict]:
    """`chunks/<name>.json` を `{"<msgctxt>|<msgid>": 項目}` で返す。

    msgctxt 違いで同じ msgid が複数あるチャンクでも、テスト側が目的のエントリーを
    取り違えずに指せるようにするため msgctxt を鍵に含める。
    """
    return {"%s|%s" % (it.get("msgctxt", ""), it["msgid"]): it
            for it in read_json(work / "chunks" / (name + ".json"))}
