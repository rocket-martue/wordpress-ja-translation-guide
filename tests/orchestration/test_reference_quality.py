# -*- coding: utf-8 -*-
"""見本から fuzzy と未確定訳を外す、世代の退避、擬似タグ、連続する終端記号。

Copilot 9 回目レビューの 6 指摘の再現と確認。

K: --force が entries.json / wordfreq.txt / chunk-meta.json も同じ世代として退避する
L: [要確認] 付きの訳を見本にしない
M: *-fuzzy.po を見本にしない
N: 書き戻し先の無い rework ドラフトを consumed へ移さない
O: アンダースコア入りの擬似タグを HTML_TAG で数える
P: 末尾の `!` `?` を連続ごと比べる
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

sys.path.insert(0, str(ROOT / "scripts"))

PO = '''# round9
msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: round9\\n"

#: src/a.php:1
msgid "Save changes"
msgstr ""

#: src/b.php:2
msgid "Delete this item"
msgstr ""
'''

# 見本として読ませる .po(確定訳・未確定訳の両方を持つ)
REF_PO = '''# ref
msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: ref\\n"

#: x.php:1
msgid "Save changes"
msgstr "変更を保存"

#: x.php:2
msgid "Delete this item"
msgstr "[要確認: 削除/消去] この項目を削除"
'''

tmp = Path(tempfile.mkdtemp(prefix="po-r9-"))
try:
    # ========================================== P / O: 単体
    from po_collect import terminal_reason, tag_reason           # noqa: E402
    check("[P] 原文 `!!!` を `!` に減らすと TERMINAL",
          (terminal_reason("Deletes them all !!!", "削除します !") or "").startswith("TERMINAL"),
          repr(terminal_reason("Deletes them all !!!", "削除します !")))
    check("[P] `!!!` をそのまま写せば通る",
          terminal_reason("Deletes them all !!!", "すべて削除します !!!") is None,
          repr(terminal_reason("Deletes them all !!!", "すべて削除します !!!")))
    check("[P] 1 個の `!` は従来どおり",
          terminal_reason("Done !", "完了 !") is None
          and (terminal_reason("Done !", "完了") or "").startswith("TERMINAL"),
          "%r / %r" % (terminal_reason("Done !", "完了 !"), terminal_reason("Done !", "完了")))
    check("[P] 記号の直後の `!!` は従来どおり弾く",
          (terminal_reason("Wow !!", "すごい!!") or "").startswith("TERMINAL"),
          repr(terminal_reason("Wow !!", "すごい!!")))

    check("[O] `<custom_icon />` を落とすと HTML_TAG",
          (tag_reason("See <a>account<custom_icon /></a> now", "<a>アカウント</a>を見る") or "").startswith("HTML_TAG"),
          repr(tag_reason("See <a>account<custom_icon /></a> now", "<a>アカウント</a>を見る")))
    check("[O] `<settings_page_link/>` を残せば通る",
          tag_reason("via the <settings_page_link/>.", "<settings_page_link/>を介して。") is None,
          repr(tag_reason("via the <settings_page_link/>.", "<settings_page_link/>を介して。")))
    check("[O] `<?php ?>` は従来どおりタグ扱いしない",
          tag_reason("Run code within <?php ?> tags.", "<?php ?> タグ内でコードを実行する。") is None,
          repr(tag_reason("Run code within <?php ?> tags.", "<?php ?> タグ内でコードを実行する。")))

    # ========================================== L / M: 見本の除外
    import validate_po as vp  # noqa: E402
    from po_chunk import load_refs                               # noqa: E402
    refdir = tmp / "refs"
    refdir.mkdir()
    (refdir / "sample-ja-translated.po").write_text(REF_PO, encoding="utf-8")
    (refdir / "sample-ja-fuzzy.po").write_text(REF_PO, encoding="utf-8")
    target = refdir / "sample-ja-untranslated.po"
    target.write_text(PO, encoding="utf-8")

    refs = load_refs([refdir / "sample-ja-translated.po"], target, vp, quiet=True)
    mids = sorted(r[0] for r in refs)
    check("[L] [要確認] 付きの訳は見本に入らない",
          mids == ["Save changes"], str(mids))

    refs_fz = load_refs([refdir / "sample-ja-fuzzy.po"], target, vp, quiet=True)
    check("[M] *-fuzzy.po からは 1 件も見本を取らない", refs_fz == [], str(refs_fz))

    # GlotPress の fuzzy エクスポートの形(訳あり・`#, fuzzy` 無し)でも確認
    real_fz = FIXTURES / "sample-export-ja-fuzzy.po"
    got = load_refs([real_fz], real_fz, vp, quiet=True)
    check("[M] エクスポート形式の fuzzy .po からも見本を取らない", got == [], str(len(got)))

    # -changesrequested も承認済みではないので見本にしない(GlotPress のステータス別エクスポート)
    (refdir / "sample-ja-changesrequested.po").write_text(REF_PO, encoding="utf-8")
    refs_cr = load_refs([refdir / "sample-ja-changesrequested.po"], target, vp, quiet=True)
    check("[M] *-changesrequested.po からも見本を取らない", refs_cr == [], str(refs_cr))

    # 壊れたエンコーディングの参照 .po があっても、WARN で続けて他の見本は拾う
    (refdir / "broken-ja-translated.po").write_bytes(
        b'msgid "x"\nmsgstr "\x82\xa0"\n')      # cp932 のバイト列。UTF-8 としては読めない
    # --no-ref を付けると見本を読まないので、ここでは付けない
    r_mix = run(["scripts/po_chunk.py", str(target), "--outdir", str(tmp / "work-badref"),
                 "--ref", str(refdir / "broken-ja-translated.po"),
                 "--ref", str(refdir / "sample-ja-translated.po")])
    check("[M] 読めない参照 .po は WARN になる",
          "WARN: --ref を読めません" in (r_mix.stdout or "") and "Traceback" not in (r_mix.stderr or ""),
          "rc=%d out=%s err=%s" % (r_mix.returncode, (r_mix.stdout or "")[:300], (r_mix.stderr or "")[:300]))

    # ========================================== K: --force の退避対象
    work = tmp / "work-force"
    run(["scripts/po_chunk.py", str(target), "--outdir", str(work), "--no-ref"], check_rc=True)
    idx = json.loads((work / "chunks" / "chunk_00.json").read_text(encoding="utf-8"))
    draft(work, "translations_00.json", [{"n": idx[0]["n"], "id": idx[0]["msgid"][:30], "msgstr": "x"}])
    run(["scripts/po_collect.py", "--outdir", str(work)])
    r = run(["scripts/po_chunk.py", str(target), "--outdir", str(work), "--no-ref", "--force"], check_rc=True)
    baks = list(work.glob("backup-*"))
    got = sorted(p.name for p in baks[0].iterdir()) if baks else []
    check("[K] entries.json / wordfreq.txt / chunk-meta.json も退避される",
          len(baks) == 1 and {"entries.json", "wordfreq.txt", "chunk-meta.json", "chunks", "drafts"} <= set(got),
          str(got))
    check("[K] 退避した chunks の e が、同じ backup の entries.json で引ける",
          bool(baks) and all(
              0 <= it["e"] < len(json.loads((baks[0] / "entries.json").read_text(encoding="utf-8")))
              for it in json.loads((baks[0] / "chunks" / "chunk_00.json").read_text(encoding="utf-8"))),
          str(got))

    # ========================================== N: 書き戻し先が無い rework
    work2 = tmp / "work-notarget"
    run(["scripts/po_chunk.py", str(target), "--outdir", str(work2), "--no-ref"], check_rc=True)
    idx2 = json.loads((work2 / "chunks" / "chunk_00.json").read_text(encoding="utf-8"))
    by_mid = {it["msgid"]: it for it in idx2}
    draft(work2, "translations_00.json", [
        {"n": by_mid["Save changes"]["n"], "id": "Save changes", "msgstr": "変更を保存。"},   # TERMINAL NG
        {"n": by_mid["Delete this item"]["n"], "id": "Delete this item", "msgstr": "この項目を削除"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work2)])
    rw = json.loads((work2 / "rework.json").read_text(encoding="utf-8"))
    rwname = rw["chunks"][0]
    rwidx = json.loads((work2 / "chunks" / (rwname + ".json")).read_text(encoding="utf-8"))
    # 通常ドラフトを消して「書き戻し先が無い」状況を作る
    (work2 / "drafts" / "translations_00.json").unlink()
    draft(work2, "translations_%s.json" % rwname, [
        {"n": rwidx[0]["n"], "id": "Save changes", "msgstr": "変更を保存"},
    ])
    r = run(["scripts/po_collect.py", "--outdir", str(work2)])
    still = (work2 / "drafts" / ("translations_%s.json" % rwname)).is_file()
    consumed = list((work2 / "drafts" / "consumed").glob("*")) if (work2 / "drafts" / "consumed").is_dir() else []
    rep = (work2 / "collect-report.txt").read_text(encoding="utf-8")
    check("[N] 書き戻し先が無い rework ドラフトは drafts/ に残る",
          still and not consumed, "still=%s consumed=%s" % (still, [p.name for p in consumed]))
    check("[N] 理由が report に出て、成功扱いで終わらない",
          "書き戻し先の通常ドラフトが見つかりません" in rep and r.returncode != 0,
          "rc=%d\n%s" % (r.returncode, rep))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
