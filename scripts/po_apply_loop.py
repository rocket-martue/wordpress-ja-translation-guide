#!/usr/bin/env python3
"""フェーズ③: 訳文プールを .po へ直列適用する。**並列化禁止**。

1バッチごとに:
    1. apply_translations.py --list --start 0 --count N を取り直す(毎回必ず)
    2. msgid 照合付きオブジェクト形式 JSON を組んで apply
    3. validate_po.py --errors-only を実行し、[ERROR] が出たら即中断

書き込めなかったエントリー(プレースホルダー不一致・msgctxt 重複)は、その場で
blocked.json に落として次バッチから外す。放置すると同じエントリーが毎バッチ
先頭に居座り、ループが空転する。

`.po` への書き込みは必ず apply_translations.py 経由で行い、このスクリプトは
`.po` を直接編集しない。

使い方:
    python /path/to/skill/scripts/po_apply_loop.py path/to/ja.po \
        --outdir .work/plugin-x [--batch-size 20] [--max-batches 100]

Skill の apply_translations.py / validate_po.py と同じディレクトリに置くこと(同じ場所のものを呼ぶ)。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# 同じディレクトリの Skill スクリプトをサブプロセスで呼ぶ
SCRIPTS_DIR = Path(__file__).resolve().parent

# Windows の既定 stdout は cp932。apply_translations.py / validate_po.py の出力に
# 含まれる絵文字をそのまま中継すると UnicodeEncodeError でループが落ちる。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

LIST_IDX_RE = re.compile(r"^\[\s*(\d+)\]")
LIST_MSGID_RE = re.compile(r'^\s+msgid: "(.*)"$')
TOTAL_RE = re.compile(r"全 (\d+) 件")
ERR_IDX_RE = re.compile(r"^\[ERROR\]\s*(?:\[\s*(\d+)\]|インデックス (\d+))")
VALIDATE_ERR_RE = re.compile(r"^\[ERROR")
PREVIEW_LEN = 120  # apply_translations.py の cmd_list が切り詰める長さ


def preview_of(s: str) -> str:
    return s[:PREVIEW_LEN].replace("\n", "\\n")


def run(args: list[str]) -> tuple[int, str]:
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("po_path")
    ap.add_argument("--outdir", required=True, help="pool.json / blocked.json を置く作業ディレクトリ")
    ap.add_argument("--pool", default=None, help="訳文プール JSON(既定: <outdir>/pool.json)")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--max-batches", type=int, default=100)
    args = ap.parse_args()

    APPLY = str(SCRIPTS_DIR / "apply_translations.py")
    VALIDATE = str(SCRIPTS_DIR / "validate_po.py")

    outdir = Path(args.outdir)
    pool_path = Path(args.pool) if args.pool else outdir / "pool.json"
    if not pool_path.is_file():
        sys.exit(f"訳文プールがありません: {pool_path}(先に po_collect.py を実行してください)")
    pool: dict[str, str] = json.loads(pool_path.read_text(encoding="utf-8"))

    blocked_path = outdir / "blocked.json"
    blocked: set[str] = set(json.loads(blocked_path.read_text(encoding="utf-8"))) if blocked_path.is_file() else set()

    by_preview: dict[str, list[tuple[str, str]]] = {}
    for mid, mstr in pool.items():
        by_preview.setdefault(preview_of(mid), []).append((mid, mstr))

    exit_code = 0
    prev_total: int | None = None

    for b in range(args.max_batches):
        _, out = run([APPLY, args.po_path, "--list", "--start", "0", "--count", str(args.batch_size)])
        tm = TOTAL_RE.search(out)
        total = int(tm.group(1)) if tm else None

        listed: list[tuple[int, str]] = []
        cur = None
        for line in out.splitlines():
            m = LIST_IDX_RE.match(line)
            if m:
                cur = int(m.group(1))
                continue
            m = LIST_MSGID_RE.match(line)
            if m and cur is not None:
                listed.append((cur, m.group(1)))
                cur = None

        if not listed:
            print("=== 未翻訳エントリーなし。完了 ===")
            break

        batch: dict[str, dict[str, str]] = {}
        sent_by_idx: dict[int, str] = {}
        skipped: list[tuple[int, str]] = []
        for idx, prev in listed:
            cands = [c for c in by_preview.get(prev, []) if c[0] not in blocked]
            if not cands:
                skipped.append((idx, prev[:70]))
                continue
            mid, mstr = cands[0]
            batch[str(idx)] = {"msgid": mid, "msgstr": mstr}
            sent_by_idx[idx] = mid

        if not batch:
            print("=== batch %d: 送信できるエントリーがない。終了(残 %s 件) ===" % (b, total))
            for s in skipped[:10]:
                print("   SKIP", s)
            break

        fd, tmp = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        Path(tmp).write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
        rc, out = run([APPLY, args.po_path, tmp])
        os.unlink(tmp)

        lines = [l for l in out.splitlines() if l.strip()]
        print("--- batch %d: 残 %s / 送信 %d / skip %d / rc=%d" % (b, total, len(batch), len(skipped), rc))
        for l in lines[-2:]:
            print("   ", l)

        # 書き込めなかったエントリーをその場で blocked に落とす
        newly_blocked = []
        for line in out.splitlines():
            m = ERR_IDX_RE.match(line)
            if not m:
                continue
            idx = int(m.group(1) or m.group(2))
            mid = sent_by_idx.get(idx)
            if mid and mid not in blocked:
                blocked.add(mid)
                newly_blocked.append((mid, line.strip()))
        for mid, line in newly_blocked:
            print("    BLOCKED:", line)
            print("             msgid:", preview_of(mid)[:80])

        # 保険: 1件も減らなかったらこのバッチの送信分をまとめて blocked にする
        if prev_total is not None and total == prev_total and not newly_blocked:
            for mid in sent_by_idx.values():
                blocked.add(mid)
            print("    BLOCKED(進捗なし): このバッチの送信分 %d 件を除外" % len(sent_by_idx))
        prev_total = total

        rc2, out2 = run([VALIDATE, args.po_path, "--errors-only"])
        errs = [l for l in out2.splitlines() if VALIDATE_ERR_RE.match(l)]
        if errs:
            print("=== batch %d の適用後に validate が ERROR。中断 ===" % b)
            for l in errs[:20]:
                print("   ", l)
            exit_code = 2
            break

    blocked_path.write_text(json.dumps(sorted(blocked), ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nblocked: %d 件 -> %s" % (len(blocked), blocked_path))
    if blocked:
        print("blocked のエントリーは未翻訳のまま残ります。人間が個別に判断してください。")
    print("次: validate_po.py をフルで実行し、WARN を目視確認 → 人間レビュー → 手動 Import")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
