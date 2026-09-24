# -*- coding: utf-8 -*-
"""旧世代のチャンク対応表・旧形式(msgid キー)ドラフト・実ファイルでの通し。

後方互換と実ファイルでの通し確認。

- 旧世代の chunks/chunk_NN.json(msgctxt / location / rework_of が無い)から回収できるか
- 旧形式の msgid キーのドラフトが従来どおり通るか
- 実在の .po でチャンク分割が落ちないか
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from _harness import FIXTURES, ROOT, Result, run  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check

PO = '''# compat test
msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: compat\\n"

#: src/a.php:1
msgid "Save changes"
msgstr ""

#: src/b.php:2
msgid "Delete this item"
msgstr ""
'''

tmp = Path(tempfile.mkdtemp(prefix="po-compat-"))
try:
    po = tmp / "compat.po"
    po.write_text(PO, encoding="utf-8")
    work = tmp / "work"
    run(["scripts/po_chunk.py", str(po), "--outdir", str(work), "--no-ref"], check_rc=True)

    # chunks/chunk_00.json を旧世代の形(n / msgid / msgid_plural / kind だけ)に落とす
    cj = work / "chunks" / "chunk_00.json"
    data = json.loads(cj.read_text(encoding="utf-8"))
    legacy = [{"n": it["n"], "msgid": it["msgid"], "msgid_plural": it["msgid_plural"], "kind": it["kind"]}
              for it in data]
    cj.write_text(json.dumps(legacy, ensure_ascii=False, indent=1), encoding="utf-8")
    n_of = {it["msgid"]: it["n"] for it in legacy}

    drafts = work / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "translations_00.json").write_text(json.dumps([
        {"n": n_of["Save changes"], "id": "Save changes", "msgstr": "変更を保存"},
        {"n": n_of["Delete this item"], "id": "Delete this item", "msgstr": "この項目を削除"},
    ], ensure_ascii=False), encoding="utf-8")
    r = run(["scripts/po_collect.py", "--outdir", str(work)])
    pool = json.loads((work / "pool.json").read_text(encoding="utf-8"))
    check("[compat] msgctxt/location の無い旧 chunk json から回収できる",
          r.returncode == 0 and pool.get("Save changes") == "変更を保存" and len(pool) == 2,
          "rc=%d pool=%s" % (r.returncode, json.dumps(pool, ensure_ascii=False)))

    # 旧形式(msgid キー)のドラフト
    work2 = tmp / "work2"
    run(["scripts/po_chunk.py", str(po), "--outdir", str(work2), "--no-ref"], check_rc=True)
    d2 = work2 / "drafts"
    d2.mkdir(parents=True, exist_ok=True)
    (d2 / "translations_00.json").write_text(json.dumps([
        {"msgid": "Save changes", "msgstr": "変更を保存"},
        {"msgid": "Delete this item", "msgstr": "この項目を削除"},
    ], ensure_ascii=False), encoding="utf-8")
    r = run(["scripts/po_collect.py", "--outdir", str(work2)])
    pool2 = json.loads((work2 / "pool.json").read_text(encoding="utf-8"))
    check("[compat] msgid キーの旧形式ドラフトが通る",
          r.returncode == 0 and len(pool2) == 2,
          "rc=%d pool=%s" % (r.returncode, json.dumps(pool2, ensure_ascii=False)))

    # rework も旧形式ドラフトで回る(番号が無いので ('-', msgid) の鍵になる)
    work3 = tmp / "work3"
    run(["scripts/po_chunk.py", str(po), "--outdir", str(work3), "--no-ref"], check_rc=True)
    d3 = work3 / "drafts"
    d3.mkdir(parents=True, exist_ok=True)
    (d3 / "translations_00.json").write_text(json.dumps([
        {"msgid": "Save changes", "msgstr": "変更を保存。"},        # TERMINAL NG
        {"msgid": "Delete this item", "msgstr": "この項目を削除"},
    ], ensure_ascii=False), encoding="utf-8")
    r = run(["scripts/po_collect.py", "--outdir", str(work3)])
    rw = json.loads((work3 / "rework.json").read_text(encoding="utf-8"))
    check("[compat] 旧形式ドラフトでも rework 記録とチャンクができる",
          r.returncode == 3 and len(rw["items"]) == 1 and rw["chunks"],
          "rc=%d rework=%s" % (r.returncode, json.dumps(rw, ensure_ascii=False)[:300]))
    rwname = rw["chunks"][0]
    rwidx = json.loads((work3 / "chunks" / (rwname + ".json")).read_text(encoding="utf-8"))
    (d3 / ("translations_%s.json" % rwname)).write_text(json.dumps([
        {"n": rwidx[0]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ], ensure_ascii=False), encoding="utf-8")
    r = run(["scripts/po_collect.py", "--outdir", str(work3)])
    pool3 = json.loads((work3 / "pool.json").read_text(encoding="utf-8"))
    back3 = json.loads((d3 / "translations_00.json").read_text(encoding="utf-8"))
    check("[compat] 旧形式ドラフトへの rework 書き戻しが効く",
          r.returncode == 0 and pool3.get("Save changes") == "変更を保存"
          and back3[0]["msgstr"] == "変更を保存",
          "rc=%d pool=%s back=%s" % (r.returncode, json.dumps(pool3, ensure_ascii=False),
                                     json.dumps(back3, ensure_ascii=False)))

    # GlotPress エクスポートの形をした .po(合成フィクスチャ)で通し(分割まで)
    real = FIXTURES / "core-sample-ja-untranslated.po"
    w = tmp / "work-real"
    r = run(["scripts/po_chunk.py", str(real), "--outdir", str(w),
             "--ref", str(FIXTURES / "core-sample-ja-translated.po")])
    idx = json.loads((w / "chunks" / "chunk_00.json").read_text(encoding="utf-8")) if r.returncode == 0 else []
    ctxt = sorted(it["msgctxt"] for it in idx if it.get("msgctxt"))
    check("[real] エクスポート形式の .po で分割でき、msgctxt 付き 4 件を拾う",
          r.returncode == 0 and ctxt == ["Name for the CSS pseudo-class selector"] * 4,
          "rc=%d ctxt=%r out=%s" % (r.returncode, ctxt, r.stdout[-400:] + r.stderr[-400:]))
    md = (w / "chunks" / "chunk_00.md").read_text(encoding="utf-8")
    check("[real] チャンク md に msgctxt 行が出る",
          md.count("msgctxt: Name for the CSS pseudo-class selector") == 4, md[:600])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
