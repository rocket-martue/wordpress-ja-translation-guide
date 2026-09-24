#!/usr/bin/env python3
"""フェーズ③: 訳文プールを .po へ直列適用する。**並列化禁止**。

1バッチごとに:
    1. 未翻訳エントリーの一覧を取り直す(毎回必ず。apply_translations.py の判定関数を
       同じディレクトリから読み込むので、--list と同じ順序・同じインデックス)
    2. 一覧の先頭から、プールに訳文があるエントリーを batch-size 件拾い、
       msgid 照合付きオブジェクト形式 JSON を組んで apply
    3. validate_po.py --errors-only を実行し、[ERROR] が出たら即中断

送らないもの:
    - msgctxt 違いで同じ msgid が複数のエントリーにあるもの。プールは msgid をキーに
      1 件しか持てず、どのエントリー向けか区別できないので、po_collect.py の manual.json と
      同じく人間が --list の個別インデックスで 1 件ずつ適用する(この判定は .po の全エントリーで
      行う。翻訳済みの変種や po_chunk.py --skip-low で除外されたエントリーも数える。片方を
      手動で適用したあとの再実行で、残った方に黙って書き込まないため)
    - プールに訳文が無いもの([要確認] で hold に分離されたものなど)。先頭に何件並んでいても
      飛ばして、後ろのプール分を送る
    - 書き込めなかったエントリー(プレースホルダー不一致など)。その場で blocked.json に落として
      次バッチから外す。放置すると同じエントリーが毎バッチ先頭に居座り、ループが空転する

apply が 1 件も書けず、書けなかった理由も個別に返ってこないとき(.po が読み取り専用など)は、
送信分を blocked に落とさず、apply の出力を表示して exit 2 で止まる(blocked.json に入れると、
原因を直したあとも再試行されなくなる)。

`.po` への書き込みは必ず apply_translations.py 経由で行い、このスクリプトは
`.po` を直接編集しない。

終了コード:
    0 = 完了(送れるものを送り切った。送らなかったものは末尾に理由別で一覧)
    2 = 中断(.po が読めない / apply が 1 件も書けない / validate が ERROR /
        --max-batches に達したのに送れるエントリーが残っている)

使い方:
    python /path/to/skill/scripts/po_apply_loop.py path/to/ja.po \\
        --outdir .work/plugin-x [--batch-size 20] [--max-batches 100]

Skill の apply_translations.py / validate_po.py と同じディレクトリに置くこと(同じ場所のものを呼ぶ)。
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# 同じディレクトリの Skill スクリプトを読み込む(未翻訳判定・全エントリーの列挙)・
# サブプロセスで呼ぶ(書き込み・validate)
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import apply_translations as at  # noqa: E402
import validate_po as vp  # noqa: E402

# Windows の既定 stdout は cp932。apply_translations.py / validate_po.py の出力に
# 含まれる絵文字をそのまま中継すると UnicodeEncodeError でループが落ちる。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# apply_translations.py のエントリー単位のエラー。`[N] ...`、`インデックス N ...`、
# `インデックス "N": ...`(JSON のキーをそのまま引用する形)のどれも拾う
ERR_IDX_RE = re.compile(r'^\[ERROR\]\s*(?:\[\s*(\d+)\]|インデックス\s+"?(\d+)"?)')
VALIDATE_ERR_RE = re.compile(r"^\[ERROR")
PREVIEW_LEN = 80
SKIP_SHOW = 10
REASON_DUP = "msgctxt 違いで複数エントリーに一致(manual.json と同じく --list の個別インデックスで手動適用)"
REASON_BLOCKED = "blocked(書き込めなかったもの。blocked.json)"
REASON_NOPOOL = "プールに訳文が無い"


def preview_of(s: str) -> str:
    return s[:PREVIEW_LEN].replace("\n", "\\n")


def run(args: list[str]) -> tuple[int, str]:
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def positive_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("整数を指定してください: %r" % value)
    if n < 1:
        raise argparse.ArgumentTypeError("1 以上を指定してください: %d" % n)
    return n


def load_po(po_path: Path):
    """(未翻訳エントリーの一覧, 全エントリーの msgid の出現回数)。読めなければ None。

    未翻訳の一覧は --list と同じ判定・同じ順序。出現回数は翻訳済みも含めた全エントリーで数える
    (msgctxt 違いの判定に使う)。
    """
    try:
        lines = at._read_lines(po_path)
        text = "".join(lines)
    except (OSError, UnicodeDecodeError) as ex:
        print("[ERROR] .po を読めません: %s" % ex)
        return None
    untranslated = at._find_untranslated(lines)
    counts = collections.Counter(e.msgid for e in vp.parse_po(text))
    return untranslated, counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("po_path")
    ap.add_argument("--outdir", required=True, help="pool.json / blocked.json を置く作業ディレクトリ")
    ap.add_argument("--pool", default=None, help="訳文プール JSON(既定: <outdir>/pool.json)")
    ap.add_argument("--batch-size", type=positive_int, default=20)
    ap.add_argument("--max-batches", type=positive_int, default=100)
    args = ap.parse_args()

    APPLY = str(SCRIPTS_DIR / "apply_translations.py")
    VALIDATE = str(SCRIPTS_DIR / "validate_po.py")
    po_path = Path(args.po_path)

    outdir = Path(args.outdir)
    pool_path = Path(args.pool) if args.pool else outdir / "pool.json"
    if not pool_path.is_file():
        sys.exit("訳文プールがありません: %s(先に po_collect.py を実行してください)" % pool_path)
    pool: dict[str, str] = json.loads(pool_path.read_text(encoding="utf-8"))

    blocked_path = outdir / "blocked.json"
    blocked: set[str] = set(json.loads(blocked_path.read_text(encoding="utf-8"))) if blocked_path.is_file() else set()

    exit_code = 0
    skipped: dict[str, list[tuple[int, str]]] = {}   # 最後に走査した時点の「送らなかったエントリー」(理由別)
    loaded = load_po(po_path)
    if loaded is None:
        return 2
    total = -1
    for b in range(args.max_batches + 1):
        entries, counts = loaded
        total = len(entries)
        if total == 0:
            print("=== 未翻訳エントリーなし。完了 ===")
            break

        # 一覧全体を走査して、送るもの(先頭から batch-size 件)と送らないもの(理由別)に分ける。
        # 走査を打ち切らないのは、末尾の一覧に手動適用が必要な残件を漏らさず出すため
        batch: dict[str, dict[str, str]] = {}
        sent_by_idx: dict[int, str] = {}
        skipped = collections.defaultdict(list)
        for e in entries:
            if counts[e.msgid] >= 2:
                skipped[REASON_DUP].append((e.index, e.msgid))
            elif e.msgid in blocked:
                skipped[REASON_BLOCKED].append((e.index, e.msgid))
            elif e.msgid not in pool:
                skipped[REASON_NOPOOL].append((e.index, e.msgid))
            elif len(batch) < args.batch_size:
                batch[str(e.index)] = {"msgid": e.msgid, "msgstr": pool[e.msgid]}
                sent_by_idx[e.index] = e.msgid

        if not batch:
            print("=== batch %d: 送信できるエントリーがない。終了(残 %d 件) ===" % (b, total))
            break
        if b == args.max_batches:
            print("=== --max-batches %d に達しました。送れるエントリーが残っています(残 %d 件)。再実行してください ==="
                  % (args.max_batches, total))
            exit_code = 2
            break

        fd, tmp = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        Path(tmp).write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
        rc, out = run([APPLY, str(po_path), tmp])
        os.unlink(tmp)

        lines = [l for l in out.splitlines() if l.strip()]
        nskip = sum(len(v) for v in skipped.values())
        print("--- batch %d: 残 %d / 送信 %d / skip %d / rc=%d" % (b, total, len(batch), nskip, rc))
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
            print("             msgid:", preview_of(mid))

        # 1 件も減らず、個別の理由も返ってこない = エントリーではなく書き込み自体の失敗。
        # 送信分を blocked にすると原因を直したあとも再試行されないので、止めて人間に見せる。
        # 読み直した一覧は次バッチの入力として持ち越す(同じ .po を 2 回解析しない)
        loaded = load_po(po_path)
        if loaded is None:
            return 2
        if len(loaded[0]) == total and not newly_blocked:
            print("=== batch %d: apply が 1 件も書き込めませんでした。出力を確認してください ===" % b)
            for l in lines[-8:]:
                print("   ", l)
            exit_code = 2
            break

        rc2, out2 = run([VALIDATE, str(po_path), "--errors-only"])
        errs = [l for l in out2.splitlines() if VALIDATE_ERR_RE.match(l)]
        if errs:
            print("=== batch %d の適用後に validate が ERROR。中断 ===" % b)
            for l in errs[:20]:
                print("   ", l)
            exit_code = 2
            break

    for reason, items in skipped.items():
        print("\n送らなかったエントリー(%s): %d 件" % (reason, len(items)))
        for idx, mid in items[:SKIP_SHOW]:
            print("   [%3d] %s" % (idx, preview_of(mid)))
        if len(items) > SKIP_SHOW:
            print("   ... 他 %d 件" % (len(items) - SKIP_SHOW))

    blocked_path.parent.mkdir(parents=True, exist_ok=True)
    blocked_path.write_text(json.dumps(sorted(blocked), ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nblocked: %d 件 -> %s" % (len(blocked), blocked_path))
    if blocked:
        print("blocked のエントリーは未翻訳のまま残ります。人間が個別に判断してください。")
    if exit_code == 0:
        print("次: validate_po.py をフルで実行し、WARN を目視確認 → 人間レビュー → 手動 Import")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
