# -*- coding: utf-8 -*-
"""チャンク分割の既定動作（文字量で切る・種別でまとめる）と、chunk-meta.json のパスの可搬性。

文字量ベースの分割はこの改修の中心なので、`split_chunks()` の単体ではなく
`po_chunk.py` を通した振る舞いとして固定する。ここが静かに件数ベースへ戻っても
他のテストは緑のままになるため。
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from _harness import FIXTURES, ROOT, Result, read_json, run  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check

HEADER = '''# split
msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: split\\n"
'''


def entry(n: int, text: str, found: str = "") -> str:
    out = "\n"
    if found:
        out += "#. Found in %s.\n" % found
    out += '#: src/f%d.php:%d\nmsgid "%s"\nmsgstr ""\n' % (n, n, text)
    return out


def write_po(path: Path, entries: list[str]) -> None:
    path.write_text(HEADER + "".join(entries), encoding="utf-8")


def chunk_files(work: Path) -> list[Path]:
    return sorted((work / "chunks").glob("chunk_*.json"))


def chunk_chars(work: Path, p: Path) -> int:
    return sum(len(it["msgid"]) + len(it.get("msgid_plural") or "") for it in read_json(p))


tmp = Path(tempfile.mkdtemp(prefix="po-split-"))
try:
    # ============================ 文字量で切る（件数の上限には遠く届かない）
    po = tmp / "chars-ja-untranslated.po"
    # 200 字 × 20 件 = 4,000 字。--size 30 には届かないので、切れたら文字量が理由
    write_po(po, [entry(i, ("Sentence %02d. " % i) + "x" * 185) for i in range(20)])
    work = tmp / "work-chars"
    run(["scripts/po_chunk.py", str(po), "--outdir", str(work), "--no-ref",
         "--max-chars", "1000"], check_rc=True)
    parts = chunk_files(work)
    sizes = [chunk_chars(work, p) for p in parts]
    counts = [len(read_json(p)) for p in parts]
    check("[分割] 件数が上限未満でも文字量で切れる",
          len(parts) >= 4 and max(counts) < 30,
          "chunks=%d counts=%s sizes=%s" % (len(parts), counts, sizes))
    check("[分割] 1 件で上限を超えるものを除き、各チャンクは --max-chars 以下",
          all(s <= 1000 or c == 1 for s, c in zip(sizes, counts)),
          "sizes=%s counts=%s" % (sizes, counts))

    # ============================ 1 件で上限を超える長文は単独チャンクになる
    po2 = tmp / "long-ja-untranslated.po"
    write_po(po2, [entry(0, "short one"), entry(1, "L" * 1500), entry(2, "short two")])
    work2 = tmp / "work-long"
    run(["scripts/po_chunk.py", str(po2), "--outdir", str(work2), "--no-ref",
         "--max-chars", "500"], check_rc=True)
    got = [[it["msgid"][:12] for it in read_json(p)] for p in chunk_files(work2)]
    check("[分割] 1 件で上限を超える長文は単独チャンクになる",
          any(len(g) == 1 and g[0].startswith("LLL") for g in got), str(got))

    # ============================ 件数の上限でも切れる
    po3 = tmp / "count-ja-untranslated.po"
    write_po(po3, [entry(i, "tiny %02d" % i) for i in range(25)])
    work3 = tmp / "work-count"
    run(["scripts/po_chunk.py", str(po3), "--outdir", str(work3), "--no-ref",
         "--size", "10", "--max-chars", "100000"], check_rc=True)
    counts3 = [len(read_json(p)) for p in chunk_files(work3)]
    check("[分割] --size でも切れる（文字量に余裕があるとき）",
          counts3 == [10, 10, 5], str(counts3))

    # ============================ 既定の --size は 30（--size / --max-chars を渡さない）
    # 既定値が静かに変わっても他のケースは緑のままなので、既定値そのものを固定する
    po3b = tmp / "default-ja-untranslated.po"
    write_po(po3b, [entry(i, "tiny %02d" % i) for i in range(35)])
    work3b = tmp / "work-default"
    run(["scripts/po_chunk.py", str(po3b), "--outdir", str(work3b), "--no-ref"], check_rc=True)
    counts3b = [len(read_json(p)) for p in chunk_files(work3b)]
    check("[分割] 既定の --size は 30（35 件の短いラベルは [30, 5] に切れる）",
          counts3b == [30, 5], str(counts3b))

    # ============================ 種別でまとめる / --no-group-by-kind で崩さない
    po4 = tmp / "kind-ja-untranslated.po"
    mixed = []
    for i in range(6):
        mixed.append(entry(i * 2, "changelog line %d" % i, "the changelog"))
        mixed.append(entry(i * 2 + 1, "faq line %d" % i, "the faq"))
    write_po(po4, mixed)
    work4 = tmp / "work-kind"
    run(["scripts/po_chunk.py", str(po4), "--outdir", str(work4), "--no-ref"], check_rc=True)
    kinds = [it["kind"] for p in chunk_files(work4) for it in read_json(p)]
    # 「まとまっている」= 同じ種別が連続して並び、種別の切り替わりが 1 回だけ
    switches = sum(1 for i in range(len(kinds) - 1) if kinds[i] != kinds[i + 1])
    check("[種別] 既定では種別ごとにまとめる（切り替わりは 1 回）",
          switches == 1, "kinds=%s switches=%d" % (kinds, switches))

    work5 = tmp / "work-nogroup"
    run(["scripts/po_chunk.py", str(po4), "--outdir", str(work5), "--no-ref",
         "--no-group-by-kind"], check_rc=True)
    kinds5 = [it["kind"] for p in chunk_files(work5) for it in read_json(p)]
    switches5 = sum(1 for i in range(len(kinds5) - 1) if kinds5[i] != kinds5[i + 1])
    check("[種別] --no-group-by-kind では .po の出現順のまま（交互なので切り替わりが多い）",
          switches5 > 1, "kinds=%s switches=%d" % (kinds5, switches5))

    # ============================ chunk-meta.json のパスは cwd 相対
    meta = read_json(work / "chunk-meta.json")
    # このテストの .po はリポジトリ外（一時ディレクトリ）なので、相対にできず絶対パスに落ちる。
    # それが仕様（リポジトリ外は別チェックアウトで引けないことを隠さない）
    check("[meta] リポジトリ外の .po は絶対パスのまま記録される",
          Path(meta["po_path"]).is_absolute(), meta["po_path"])
    check("[meta] 区切りは OS を問わない posix 形式",
          "\\" not in meta["po_path"], meta["po_path"])

    # 実行ディレクトリ配下の .po を相対で渡したときは、素直にその相対パスが残る
    rel6 = "tests/orchestration/fixtures/core-sample-ja-untranslated.po"
    work6 = tmp / "work-relmeta"
    run(["scripts/po_chunk.py", rel6, "--outdir", str(work6), "--no-ref"], check_rc=True)
    meta6 = read_json(work6 / "chunk-meta.json")
    check("[meta] 実行ディレクトリ配下の .po は cwd 相対で記録される",
          meta6["po_path"] == rel6, meta6["po_path"])

    # ============================ id が文字列でないドラフトを弾く
    po7 = tmp / "idtype-ja-untranslated.po"
    write_po(po7, [entry(0, "123"), entry(1, "Save changes")])
    work7 = tmp / "work-idtype"
    run(["scripts/po_chunk.py", str(po7), "--outdir", str(work7), "--no-ref"], check_rc=True)
    idx7 = {it["msgid"]: it["n"] for it in read_json(work7 / "chunks" / "chunk_00.json")}
    (work7 / "drafts").mkdir(parents=True, exist_ok=True)
    (work7 / "drafts" / "translations_00.json").write_text(json.dumps([
        {"n": idx7["123"], "id": 123, "msgstr": "123"},                      # 数値の id
        {"n": idx7["Save changes"], "id": "Save changes", "msgstr": "変更を保存"},
    ], ensure_ascii=False), encoding="utf-8")
    r7 = run(["scripts/po_collect.py", "--outdir", str(work7)])
    rep7 = (work7 / "collect-report.txt").read_text(encoding="utf-8")
    check("[id] msgid が数字でも、数値の id は ID_TYPE で弾く",
          "ID_TYPE" in rep7 and r7.returncode == 3, "rc=%d\n%s" % (r7.returncode, rep7[:400]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
