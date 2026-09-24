# -*- coding: utf-8 -*-
"""見本の msgctxt 照合、候補の同一性、旧形式の候補保持、省略記号の終端判定。

Copilot 7 回目レビューの 5 指摘を、実際にスクリプトを走らせて確認する。

A: rework 由来の manual 候補が、同じエントリーで 2 件に増えない
B: 番号キーの無い旧形式ドラフトで、msgctxt 違いの候補を潰さない
C: 原文に終端記号が無いのに訳文が `…` で終わるのを弾く
D: RefIndex が msgctxt 違いの訳を正典の顔で付けない
E: rework チャンクが「msgctxt 無しのエントリー」の文脈を正しく空にする
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from _harness import FIXTURES, ROOT, Result, run, write_draft  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check
draft = write_draft

# 2 つ目の Active は **msgctxt 無し**。E の再現に要る
PO = '''# round7
msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: round7\\n"

#: src/block.js:10
msgctxt "Name for the CSS pseudo-class selector"
msgid "Active"
msgstr ""

#: src/plugins.php:20
msgid "Active"
msgstr ""

#: src/a.php:1
msgid "Continue"
msgstr ""
'''

def setup(tmp: Path, name: str):
    po = tmp / (name + ".po")
    po.write_text(PO, encoding="utf-8")
    work = tmp / ("work-" + name)
    run(["scripts/po_chunk.py", str(po), "--outdir", str(work), "--no-ref"], check_rc=True)
    idx = json.loads((work / "chunks" / "chunk_00.json").read_text(encoding="utf-8"))
    return work, {"%s|%s" % (it.get("msgctxt", ""), it["msgid"]): it for it in idx}


tmp = Path(tempfile.mkdtemp(prefix="po-r7-"))
try:
    CTX = "Name for the CSS pseudo-class selector"

    # ================================================ C: `…` の終端判定(単体)
    sys.path.insert(0, str(ROOT / "scripts"))
    from po_collect import terminal_reason            # noqa: E402
    check("[C] 原文に終端記号が無いのに訳文が `…` で終わると TERMINAL",
          (terminal_reason("Continue", "続行…") or "").startswith("TERMINAL"),
          repr(terminal_reason("Continue", "続行…")))
    check("[C] 原文が `...` で終わるなら `…` は通る",
          terminal_reason("Loading...", "読み込み中…") is None,
          repr(terminal_reason("Loading...", "読み込み中…")))
    check("[C] 終端記号なし同士はこれまでどおり通る",
          terminal_reason("Continue", "続行") is None,
          repr(terminal_reason("Continue", "続行")))

    # ================================================ D: RefIndex の msgctxt
    import validate_po as vp  # noqa: E402
    from po_chunk import RefIndex, load_refs           # noqa: E402
    core = FIXTURES / "core-sample-ja-translated.po"
    refs = load_refs([core], FIXTURES / "core-sample-ja-untranslated.po", vp, quiet=True)
    ix = RefIndex(refs)
    plain = ix.exact_lookup("Name")
    tiny = ix.exact_lookup("Name", "Name of link anchor (TinyMCE)")
    check("[D] msgctxt 無しの Name には「名前」が付く",
          plain is not None and plain[1] == "名前" and "~ctxt" not in plain[2], repr(plain))
    check("[D] msgctxt 付きの Name には「名称」が付く",
          tiny is not None and tiny[1] == "名称" and "~ctxt" not in tiny[2], repr(tiny))
    unknown = ix.exact_lookup("Name", "No such context in core")
    check("[D] 知らない msgctxt には文脈違いとして ~ctxt ラベルが付く",
          unknown is not None and "~ctxt" in unknown[2], repr(unknown))

    # ================================================ E: rework チャンクの文脈
    work, idx = setup(tmp, "ctxfree")
    n_ctx = idx["%s|Active" % CTX]["n"]
    n_free = idx["|Active"]["n"]
    # 並び順は種別ソート次第なので前提にしない。2 つの msgctxt が別エントリーとして
    # 存在することだけを順序に依存しない形で確かめる
    actives = [e for e in json.loads((work / "entries.json").read_text(encoding="utf-8"))
               if e["msgid"] == "Active"]
    check("[E] entries.json に msgctxt 付きと msgctxt 無しの Active が 1 件ずつある",
          sorted(e.get("msgctxt", "") for e in actives) == ["", CTX],
          str([e.get("msgctxt") for e in actives]))
    draft(work, "translations_00.json", [
        {"n": n_ctx, "id": "Active", "msgstr": "アクティブ"},
        {"n": n_free, "id": "Active", "msgstr": "有効。"},          # msgctxt 無しの方を NG に
        {"n": idx["|Continue"]["n"], "id": "Continue", "msgstr": "続行"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work)])
    rw = json.loads((work / "rework.json").read_text(encoding="utf-8"))
    rwname = rw["chunks"][0]
    rwidx = json.loads((work / "chunks" / (rwname + ".json")).read_text(encoding="utf-8"))
    rwmd = (work / "chunks" / (rwname + ".md")).read_text(encoding="utf-8")
    check("[E] msgctxt 無しのエントリーの rework チャンクは msgctxt が空",
          r.returncode == 3 and len(rwidx) == 1 and rwidx[0].get("msgctxt") == "",
          "rc=%d idx=%s" % (r.returncode, json.dumps(rwidx, ensure_ascii=False)))
    check("[E] rework チャンク md に別エントリーの msgctxt が出ない",
          "msgctxt:" not in rwmd, rwmd)
    check("[E] rework_of で元のエントリーを指している",
          rwidx[0].get("rework_of") == ["00", n_free], json.dumps(rwidx, ensure_ascii=False))

    # ============================= A: rework 由来の候補が同じエントリーで重複しない
    # rework ドラフトに不正項目を混ぜて consumed に移らないようにし、次の回でも読ませる
    draft(work, "translations_%s.json" % rwname, [
        {"n": rwidx[0]["n"], "id": "Active", "msgstr": "有効"},
        {"n": 999, "id": "bogus", "msgstr": "x"},                  # 範囲外 -> bad -> drafts/ に残る
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work)])
    kept = (work / "drafts" / ("translations_%s.json" % rwname)).is_file()
    check("[A] 不正項目を含む rework ドラフトは drafts/ に残る", kept,
          str(sorted(p.name for p in (work / "drafts").iterdir())))
    r = run(["scripts/po_collect.py", "--outdir", str(work)])
    manual = json.loads((work / "manual.json").read_text(encoding="utf-8"))
    cands = manual.get("Active", [])
    check("[A] 通常ドラフトと rework ドラフトの両方から来ても候補は 2 エントリー分だけ",
          len(cands) == 2 and sorted(c["msgctxt"] for c in cands) == ["", CTX],
          "候補 %d 件: %s" % (len(cands), json.dumps(cands, ensure_ascii=False)))

    # ============================= B: 旧形式(msgid キー)ドラフトで候補を潰さない
    work2, _ = setup(tmp, "legacy")
    draft(work2, "translations_00.json", [
        {"msgid": "Active", "msgstr": "アクティブ"},
        {"msgid": "Active", "msgstr": "有効"},
        {"msgid": "Continue", "msgstr": "続行"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work2)])
    manual2 = json.loads((work2 / "manual.json").read_text(encoding="utf-8"))
    c2 = manual2.get("Active", [])
    check("[B] 番号キーの無い旧形式でも 2 件の候補が残る",
          len(c2) == 2 and sorted(x["msgstr"] for x in c2) == ["アクティブ", "有効"],
          "rc=%d 候補=%s" % (r.returncode, json.dumps(c2, ensure_ascii=False)))
    check("[B] 特定できない候補に ambiguous の注記が付く",
          all(x.get("ambiguous") for x in c2), json.dumps(c2, ensure_ascii=False))
    check("[B] collect-report に注記が出る",
          "特定できない" in (work2 / "collect-report.txt").read_text(encoding="utf-8"),
          (work2 / "collect-report.txt").read_text(encoding="utf-8")[-600:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
