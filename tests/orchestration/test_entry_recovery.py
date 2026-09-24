# -*- coding: utf-8 -*-
"""msgctxt のエントリー単位の保持、番号単位の回収、manual 候補、退避の順序。

Copilot 6 回目レビューの 6 指摘を、実際に po_chunk.py / po_collect.py を走らせて確認する。

各ケースは「直す前なら通ってしまう」筋を踏む。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from _harness import ROOT, Result, chunk_index, run, write_draft  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check
ids = chunk_index

PO = '''# Translation test
msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: smoke\\n"

#: src/block.js:10
msgctxt "Name for the CSS pseudo-class selector"
msgid "Active"
msgstr ""

#: src/plugins.php:20
msgctxt "plugin status"
msgid "Active"
msgstr ""

#: src/a.php:1
msgid "Save changes"
msgstr ""

#: src/b.php:2
msgid "Delete this item"
msgstr ""
'''


def setup(tmp: Path, name: str) -> tuple[Path, Path]:
    po = tmp / (name + ".po")
    po.write_text(PO, encoding="utf-8")
    work = tmp / ("work-" + name)
    r = run(["scripts/po_chunk.py", str(po), "--outdir", str(work), "--no-ref"], check_rc=True)
    return po, work


ok = []
ng = []


tmpdir = Path(tempfile.mkdtemp(prefix="po-smoke-"))
try:
    # ---------------------------------------------------------------- 指摘3: msgctxt の保持
    po, work = setup(tmpdir, "ctxt")
    idx = ids(work)
    check("[3] chunk_00.json が msgctxt を持つ",
          "Name for the CSS pseudo-class selector|Active" in idx and "plugin status|Active" in idx,
          str(sorted(idx)))
    check("[3] chunk_00.json が location を持つ",
          idx.get("plugin status|Active", {}).get("location") == "src/plugins.php:20",
          repr(idx.get("plugin status|Active")))
    md = (work / "chunks" / "chunk_00.md").read_text(encoding="utf-8")
    check("[3] chunk_00.md に msgctxt 行が出る", md.count("msgctxt: ") == 2, md)
    ent = json.loads((work / "entries.json").read_text(encoding="utf-8"))
    check("[3] entries.json の location がエントリーごとに違う",
          sorted(e["location"] for e in ent if e["msgid"] == "Active") == ["src/block.js:10", "src/plugins.php:20"],
          str([e["location"] for e in ent if e["msgid"] == "Active"]))

    n_block = idx["Name for the CSS pseudo-class selector|Active"]["n"]
    n_status = idx["plugin status|Active"]["n"]
    n_save = idx["|Save changes"]["n"]
    n_del = idx["|Delete this item"]["n"]

    # ------------------------------------ 指摘4: 同じ番号を 2 回出して別の番号を欠落させる
    write_draft(work, "translations_00.json", [
        {"n": n_block, "id": "Active", "msgstr": "アクティブ"},
        {"n": n_block, "id": "Active", "msgstr": "アクティブ"},      # 同じ番号を 2 回
        {"n": n_save, "id": "Save changes", "msgstr": "変更を保存"},
        {"n": n_del, "id": "Delete this item", "msgstr": "この項目を削除"},
    ])                                                                # n_status が欠落
    r = run(["scripts/po_collect.py", "--outdir", str(work)])
    missing = json.loads((work / "missing.json").read_text(encoding="utf-8"))
    check("[4] 同じ番号の 2 回提出を回収数に数えず未回収(exit 2)にする",
          r.returncode == 2 and "Active" in missing, "rc=%d missing=%r" % (r.returncode, missing))
    check("[4] 同じ番号の重複を報告する",
          "同じ番号を同じドラフトで 2 回提出" in (work / "collect-report.txt").read_text(encoding="utf-8"))

    # ------------------------------------------- 指摘1: 未回収の再投入(translations_00_2.json)
    write_draft(work, "translations_00_2.json", [
        {"n": n_status, "id": "Active", "msgstr": "有効"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work)])
    manual = json.loads((work / "manual.json").read_text(encoding="utf-8"))
    missing = json.loads((work / "missing.json").read_text(encoding="utf-8"))
    check("[1] translations_NN_2.json が同じチャンクの続きとして回収される",
          r.returncode == 0 and not missing, "rc=%d missing=%r" % (r.returncode, missing))
    check("[1] 再投入で msgctxt 違い 2 件ぶんの候補が揃う",
          len(manual.get("Active", [])) == 2, json.dumps(manual, ensure_ascii=False))
    check("[3] manual.json の候補に msgctxt と location が付く",
          sorted(c["msgctxt"] for c in manual["Active"])
          == ["Name for the CSS pseudo-class selector", "plugin status"]
          and all(c["location"] for c in manual["Active"]),
          json.dumps(manual, ensure_ascii=False))

    # -------------------- 指摘6: 片方が機械チェック NG でも、もう片方の候補を消さない
    po2, work2 = setup(tmpdir, "keep")
    idx2 = ids(work2)
    n_block2 = idx2["Name for the CSS pseudo-class selector|Active"]["n"]
    n_status2 = idx2["plugin status|Active"]["n"]
    write_draft(work2, "translations_00.json", [
        {"n": n_block2, "id": "Active", "msgstr": "アクティブ。"},     # TERMINAL NG(原文に終端記号なし)
        {"n": n_status2, "id": "Active", "msgstr": "有効"},            # こちらは通る
        {"n": idx2["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
        {"n": idx2["|Delete this item"]["n"], "id": "Delete this item", "msgstr": "この項目を削除"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work2)])
    manual2 = json.loads((work2 / "manual.json").read_text(encoding="utf-8"))
    check("[6] 片方が rework でも、もう片方の manual 候補が残る",
          r.returncode == 3 and len(manual2.get("Active", [])) == 1
          and manual2["Active"][0]["msgctxt"] == "plugin status",
          "rc=%d manual=%s" % (r.returncode, json.dumps(manual2, ensure_ascii=False)))

    rework_chunks = json.loads((work2 / "rework.json").read_text(encoding="utf-8"))["chunks"]
    rw = rework_chunks[0]
    rw_idx = json.loads((work2 / "chunks" / (rw + ".json")).read_text(encoding="utf-8"))
    check("[3] rework チャンクが NG になった側の msgctxt を引き継ぐ",
          rw_idx[0].get("msgctxt") == "Name for the CSS pseudo-class selector", json.dumps(rw_idx, ensure_ascii=False))
    write_draft(work2, "translations_%s.json" % rw, [
        {"n": rw_idx[0]["n"], "id": "Active", "msgstr": "アクティブ"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work2)])
    manual2 = json.loads((work2 / "manual.json").read_text(encoding="utf-8"))
    check("[6] rework 通過後に候補が 2 件そろう",
          r.returncode == 0 and len(manual2.get("Active", [])) == 2
          and sorted(c["msgstr"] for c in manual2["Active"]) == ["アクティブ", "有効"],
          "rc=%d manual=%s" % (r.returncode, json.dumps(manual2, ensure_ascii=False)))
    back = json.loads((work2 / "drafts" / "translations_00.json").read_text(encoding="utf-8"))
    check("[6] 書き戻しが NG だった側の位置に入り、もう片方を潰さない",
          [b["msgstr"] for b in back][:2] == ["アクティブ", "有効"],
          json.dumps(back, ensure_ascii=False))

    # ------------------------------------------- 指摘5: 訳文にだけ現れる `% ` は特例にしない
    sys.path.insert(0, str(ROOT / "scripts"))
    import validate_po as vp  # noqa: E402
    from po_collect import placeholder_reason                # noqa: E402
    r1, n1 = placeholder_reason(vp, "Delete this item", "この項目を 100% f 削除")
    check("[5] 原文に '% ' が無いのに訳文に出たら PH_MISMATCH",
          r1 is not None and r1.startswith("PH_MISMATCH"), "reason=%r note=%r" % (r1, n1))
    r2, n2 = placeholder_reason(vp, "Get 100% free hosting", "100% 無料のホスティング")
    check("[5] 原文側の '% ' 誤検出はこれまでどおり NOTE で pool に残す",
          r2 is None and n2 is not None and n2.startswith("PH_SUSPECT"), "reason=%r note=%r" % (r2, n2))
    r3, n3 = placeholder_reason(vp, "Delete %s now", "%s を削除")
    check("[5] 正常なプレースホルダーは素通り", r3 is None and n3 is None, "reason=%r note=%r" % (r3, n3))

    # --------------------- 指摘2: 前提の読み込みで落ちても chunks/ を失わない
    po3, work3 = setup(tmpdir, "guard")
    before = sorted(p.name for p in (work3 / "chunks").iterdir())
    r = run(["scripts/po_chunk.py", str(po3), "--outdir", str(work3), "--no-ref",
             "--skill-scripts", str(tmpdir / "does-not-exist")])
    after = sorted(p.name for p in (work3 / "chunks").iterdir()) if (work3 / "chunks").is_dir() else []
    check("[2] Skill 読み込み失敗時に前世代の chunks/ が残る",
          r.returncode != 0 and after == before, "rc=%d before=%r after=%r" % (r.returncode, before, after))
    check("[2] 失敗時に backup-*/ を作っていない",
          not list(work3.glob("backup-*")), str([p.name for p in work3.glob("backup-*")]))

    # 正常な --force では chunks/ が退避される(削除ではない)
    write_draft(work3, "translations_00.json", [{"n": 1, "id": "x", "msgstr": "y"}])
    r = run(["scripts/po_chunk.py", str(po3), "--outdir", str(work3), "--no-ref", "--force"], check_rc=True)
    baks = list(work3.glob("backup-*"))
    check("[2] --force で chunks/ を削除せず backup-*/ に退避する",
          len(baks) == 1 and (baks[0] / "chunks").is_dir() and (baks[0] / "drafts").is_dir(),
          r.stdout)
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

raise SystemExit(R.report())
