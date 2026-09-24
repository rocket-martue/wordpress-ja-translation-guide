# -*- coding: utf-8 -*-
"""空行で区切られていないエントリーのコメント・msgctxt の取り違え(#33 の再現)。

A: 空行なしで続く 2 エントリーで、後の方が前の msgctxt を引き継がず、自分の translators / location を持つ
B: 参照 .po でも同じ(空行なしの次のエントリーに前の msgctxt が付かない)
C: msgctxt の中のエスケープ(\\" \\\\)は apply_translations と同じ解釈で対応表に入る
D: 空行ありの通常の .po では結果が変わらない
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from _harness import ROOT, Result, read_json, run  # noqa: E402

R = Result(Path(__file__).stem)
check = R.check

sys.path.insert(0, str(ROOT / "scripts"))

HEADER = '''msgid ""
msgstr ""
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=1; plural=0;\\n"
"Language: ja_JP\\n"
"Project-Id-Version: boundary\\n"

'''

# 1 つ目と 2 つ目の間に空行が無い
NO_BLANK = HEADER + '''#: src/a.php:1
msgctxt "noun"
msgid "Filter"
msgstr ""
#. translators: %s: number of items
#: src/b.php:2
msgid "%s items"
msgstr ""

#: src/c.php:3
msgctxt "Adjective: e.g. \\"Comments are open\\""
msgid "Open"
msgstr ""
'''

WITH_BLANK = HEADER + '''#: src/a.php:1
msgctxt "noun"
msgid "Filter"
msgstr ""

#. translators: %s: number of items
#: src/b.php:2
msgid "%s items"
msgstr ""
'''

REF_NO_BLANK = HEADER + '''#: src/x.php:1
msgctxt "noun"
msgid "Filter"
msgstr "フィルター"
#: src/y.php:2
msgid "Name"
msgstr "名前"
'''


def entries_of(work: Path) -> dict[str, dict]:
    return {"%s|%s" % (x.get("msgctxt", ""), x["msgid"]): x for x in read_json(work / "entries.json")}


tmp = Path(tempfile.mkdtemp(prefix="po-bd-"))
try:
    # ============================ A
    po = tmp / "a-ja-untranslated.po"
    po.write_text(NO_BLANK, encoding="utf-8")
    work = tmp / "work-a"
    run(["scripts/po_chunk.py", str(po), "--outdir", str(work), "--no-ref"], check_rc=True)
    ent = entries_of(work)
    second = ent.get("|%s items")
    check("[A] 2 つ目のエントリーが前の msgctxt を引き継がない", second is not None,
          json.dumps(sorted(ent), ensure_ascii=False))
    check("[A] 2 つ目のエントリーが自分の translators を持つ",
          second is not None and second["translators"] == "%s: number of items", json.dumps(second, ensure_ascii=False))
    check("[A] 2 つ目のエントリーが自分の location を持つ",
          second is not None and second["location"] == "src/b.php:2", json.dumps(second, ensure_ascii=False))
    first = ent.get("noun|Filter")
    check("[A] 1 つ目のエントリーは自分の msgctxt / location のまま",
          first is not None and first["location"] == "src/a.php:1", json.dumps(first, ensure_ascii=False))

    # ============================ C: msgctxt のエスケープ
    import apply_translations as at  # noqa: E402
    idx = {it["msgid"]: it for it in read_json(work / "chunks" / "chunk_00.json")}
    want = at._unescape('Adjective: e.g. \\"Comments are open\\"')
    check("[C] msgctxt のエスケープを apply_translations と同じに解く",
          idx["Open"]["msgctxt"] == want == 'Adjective: e.g. "Comments are open"', repr(idx["Open"]["msgctxt"]))

    # ============================ B: 参照 .po
    from po_chunk import RefIndex, load_refs  # noqa: E402
    import validate_po as vp  # noqa: E402
    ref = tmp / "ref-ja-translated.po"
    ref.write_text(REF_NO_BLANK, encoding="utf-8")
    refs = load_refs([ref], po, vp, quiet=True)
    ix = RefIndex(refs)
    name = ix.exact_lookup("Name")
    check("[B] 参照 .po でも空行なしの次のエントリーに前の msgctxt が付かない",
          name is not None and name[1] == "名前" and "~ctxt" not in name[2], repr(name))
    filt = ix.exact_lookup("Filter", "noun")
    check("[B] 参照 .po の msgctxt 付きエントリーは文脈付きで引ける",
          filt is not None and filt[1] == "フィルター" and "~ctxt" not in filt[2], repr(filt))

    # ============================ D: 空行ありは変わらない
    po2 = tmp / "d-ja-untranslated.po"
    po2.write_text(WITH_BLANK, encoding="utf-8")
    work2 = tmp / "work-d"
    run(["scripts/po_chunk.py", str(po2), "--outdir", str(work2), "--no-ref"], check_rc=True)
    ent2 = entries_of(work2)
    check("[D] 空行ありでは 2 件とも正しく分かれる",
          set(ent2) == {"noun|Filter", "|%s items"} and ent2["|%s items"]["translators"] == "%s: number of items",
          json.dumps(ent2, ensure_ascii=False)[:400])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(R.report())
