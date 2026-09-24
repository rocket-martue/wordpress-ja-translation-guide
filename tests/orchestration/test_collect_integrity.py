# -*- coding: utf-8 -*-
"""consumed の退避、省略記号の個数、対応表の検証、ctx による番号入れ替えの検出。

Copilot 10 回目レビューの 5 指摘の再現と確認。

Q: consumed/ しか残っていない drafts/ も --force で退避する
R: 末尾の省略記号を個数まで比べる
S: 壊れた chunk_NN.json(n が非整数・重複)を拒否する
T: msgctxt 違いのエントリーで番号が入れ替わったら ctx で検出する
U: 書き戻し先を msgid ではなくエントリー鍵で引く
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from _harness import ROOT, Result, run, write_draft  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check
draft = write_draft

sys.path.insert(0, str(ROOT / "scripts"))

CTX = "Name for the CSS pseudo-class selector"
PO = '''# round10
msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: round10\\n"

#: src/block.js:10
msgctxt "Name for the CSS pseudo-class selector"
msgid "Active"
msgstr ""

#: src/plugins.php:20
msgid "Active"
msgstr ""

#: src/a.php:1
msgid "Save changes"
msgstr ""
'''

def setup(tmp: Path, name: str):
    po = tmp / (name + ".po")
    po.write_text(PO, encoding="utf-8")
    work = tmp / ("work-" + name)
    run(["scripts/po_chunk.py", str(po), "--outdir", str(work), "--no-ref"], check_rc=True)
    idx = json.loads((work / "chunks" / "chunk_00.json").read_text(encoding="utf-8"))
    return po, work, {"%s|%s" % (it.get("msgctxt", ""), it["msgid"]): it for it in idx}


tmp = Path(tempfile.mkdtemp(prefix="po-r10-"))
try:
    # ================================================== R: 省略記号の個数(単体)
    from po_collect import terminal_reason                    # noqa: E402
    check("[R] 原文 1 個に対し訳文 2 個の省略記号は TERMINAL",
          (terminal_reason("Loading...", "読み込み中……") or "").startswith("TERMINAL"),
          repr(terminal_reason("Loading...", "読み込み中……")))
    check("[R] 同じ個数なら `...` と `…` の相互変換は通る",
          terminal_reason("Loading...", "読み込み中…") is None
          and terminal_reason("Loading…", "読み込み中...") is None,
          "%r / %r" % (terminal_reason("Loading...", "読み込み中…"),
                       terminal_reason("Loading…", "読み込み中...")))
    check("[R] 原文 2 個に対し訳文 1 個も TERMINAL",
          (terminal_reason("Wait……", "お待ちください…") or "").startswith("TERMINAL"),
          repr(terminal_reason("Wait……", "お待ちください…")))

    # ================================================== S: 壊れた対応表
    po, work, idx = setup(tmp, "badmap")
    n_save = idx["|Save changes"]["n"]
    good = json.loads((work / "chunks" / "chunk_00.json").read_text(encoding="utf-8"))
    draft(work, "translations_00.json", [{"n": n_save, "id": "Save changes", "msgstr": "変更を保存"}])

    for label, mutate in (
        ("n が重複", lambda d: [dict(d[0]), dict(d[1], n=d[0]["n"])]),
        ("n が文字列", lambda d: [dict(d[0], n=str(d[0]["n"]))] + d[1:]),
        ("n が真偽値", lambda d: [dict(d[0], n=True)] + d[1:]),
        ("n が小数", lambda d: [dict(d[0], n=1.9)] + d[1:]),
    ):
        (work / "chunks" / "chunk_00.json").write_text(
            json.dumps(mutate([dict(x) for x in good]), ensure_ascii=False), encoding="utf-8")
        r = run(["scripts/po_collect.py", "--outdir", str(work)])
        rep = (work / "collect-report.txt").read_text(encoding="utf-8")
        check("[S] 対応表の %s を拒否して形式エラーにする" % label,
              r.returncode == 4 and "PARSE ERROR" in rep,
              "rc=%d\n%s" % (r.returncode, rep[:400]))
    (work / "chunks" / "chunk_00.json").write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
    r = run(["scripts/po_collect.py", "--outdir", str(work)])
    check("[S] 正常な対応表は従来どおり通る", r.returncode in (0, 2, 3), "rc=%d" % r.returncode)

    # ================================================== T: 番号の入れ替え
    po, work2, idx2 = setup(tmp, "ctxswap")
    n_ctx = idx2["%s|Active" % CTX]["n"]
    n_free = idx2["|Active"]["n"]
    # ctx を入れ替えて提出する(id はどちらも "Active" なので id 照合では見抜けない)
    draft(work2, "translations_00.json", [
        {"n": n_ctx, "id": "Active", "ctx": "", "msgstr": "有効"},
        {"n": n_free, "id": "Active", "ctx": CTX, "msgstr": "アクティブ"},
        {"n": idx2["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work2)])
    rep2 = (work2 / "collect-report.txt").read_text(encoding="utf-8")
    check("[T] ctx の入れ替えを CTX_MISMATCH で検出する",
          r.returncode == 3 and rep2.count("CTX_MISMATCH") >= 2,
          "rc=%d\n%s" % (r.returncode, rep2[:600]))

    po, work3, idx3 = setup(tmp, "ctxok")
    draft(work3, "translations_00.json", [
        {"n": idx3["%s|Active" % CTX]["n"], "id": "Active", "ctx": CTX, "msgstr": "アクティブ"},
        {"n": idx3["|Active"]["n"], "id": "Active", "msgstr": "有効"},
        {"n": idx3["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work3)])
    manual3 = json.loads((work3 / "manual.json").read_text(encoding="utf-8"))
    check("[T] 正しい ctx なら通り、候補が 2 件そろう",
          r.returncode == 0 and len(manual3.get("Active", [])) == 2,
          "rc=%d manual=%s" % (r.returncode, json.dumps(manual3, ensure_ascii=False)))

    po, work4, idx4 = setup(tmp, "ctxmissing")
    draft(work4, "translations_00.json", [
        {"n": idx4["%s|Active" % CTX]["n"], "id": "Active", "msgstr": "アクティブ"},   # ctx 無し
        {"n": idx4["|Active"]["n"], "id": "Active", "msgstr": "有効"},
        {"n": idx4["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work4)])
    manual4 = json.loads((work4 / "manual.json").read_text(encoding="utf-8"))
    rep4 = (work4 / "collect-report.txt").read_text(encoding="utf-8")
    check("[T] ctx が無い旧形式は弾かず unverified_ctx を付けて通す",
          r.returncode == 0 and len(manual4.get("Active", [])) == 2
          and any(c.get("unverified_ctx") for c in manual4["Active"])
          and "CTX_UNVERIFIED" in rep4,
          "rc=%d manual=%s" % (r.returncode, json.dumps(manual4, ensure_ascii=False)))

    # ================================================== U: 書き戻し先
    po, work5, idx5 = setup(tmp, "writeback")
    n_ctx5 = idx5["%s|Active" % CTX]["n"]
    n_free5 = idx5["|Active"]["n"]
    draft(work5, "translations_00.json", [
        {"n": n_ctx5, "id": "Active", "ctx": CTX, "msgstr": "アクティブ。"},   # TERMINAL NG
        {"n": n_free5, "id": "Active", "msgstr": "有効"},
        {"n": idx5["|Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work5)])
    rw = json.loads((work5 / "rework.json").read_text(encoding="utf-8"))
    rwname = rw["chunks"][0]
    rwidx = json.loads((work5 / "chunks" / (rwname + ".json")).read_text(encoding="utf-8"))
    draft(work5, "translations_%s.json" % rwname, [
        {"n": rwidx[0]["n"], "id": "Active", "ctx": CTX, "msgstr": "アクティブ"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work5)])
    back = json.loads((work5 / "drafts" / "translations_00.json").read_text(encoding="utf-8"))
    at_ctx = next(b["msgstr"] for b in back if b["n"] == n_ctx5)
    at_free = next(b["msgstr"] for b in back if b["n"] == n_free5)
    check("[U] 書き戻しが該当エントリーに入り、別 msgctxt の訳を潰さない",
          at_ctx == "アクティブ" and at_free == "有効",
          "n=%s -> %r / n=%s -> %r" % (n_ctx5, at_ctx, n_free5, at_free))

    # ================================================== Q: consumed だけ残った drafts/
    live = work5 / "drafts" / "translations_00.json"
    consumed = work5 / "drafts" / "consumed"
    check("[Q] 前提: rework ドラフトが consumed へ移っている",
          consumed.is_dir() and any(consumed.iterdir()),
          str(list(consumed.iterdir()) if consumed.is_dir() else []))
    live.unlink()                     # 直下のドラフトを無くし、consumed だけ残す
    r = run(["scripts/po_chunk.py", str(po), "--outdir", str(work5), "--no-ref"], check_rc=True)
    baks = sorted(work5.glob("backup-*"))
    moved_consumed = any((b / "drafts" / "consumed").is_dir() for b in baks)
    check("[Q] --force 無しでも consumed だけの drafts/ を退避する",
          moved_consumed and not (work5 / "drafts").exists(),
          "backups=%s drafts_exists=%s" % ([b.name for b in baks], (work5 / "drafts").exists()))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
