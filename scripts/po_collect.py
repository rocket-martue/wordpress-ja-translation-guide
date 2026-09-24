#!/usr/bin/env python3
"""フェーズ②の回収チェック: サブエージェントが書いた下訳 JSON を検証して訳文プールにまとめる。

チェック内容(ワークフロー「回収時のチェック(メイン)」に対応):
    - JSON としてパースできるか(ドラフトも chunks/*.json も)。`n` は整数のみ
    - 番号キー `n` を chunks/chunk_NN.json で msgid に復元できるか(旧形式の `msgid` キーも受ける)
    - `id` が msgid の先頭と一致するか(番号ズレの検出。欠落・不一致は rework。--no-check で省略)
    - 件数が合っているか / 未回収の msgid が残っていないか / 通常ドラフト同士の重複
      (回収は msgid ではなく (チャンクキー, n) 単位で数える。同じ番号を 2 回出しても 1 件)
    - `[要確認]` 付きの訳文を別プールへ分離する(マーカーを除いた訳文は機械チェックする)
    - msgctxt 違いで同じ msgid が複数エントリーにあるものは pool に入れず manual.json へ(手動処理)。
      その msgid はエントリー数ぶん回収されていなければ missing 扱い。候補はエントリー(番号)ごとに
      1 件ずつ保持し、msgctxt と location を添えるので --list の個別インデックスに割り当てられる
    - ドラフト段階の機械チェック(下記)。NG は rework へ

機械チェック(validate_po.py が apply 後にしか見ないものを、ドラフト段階で弾く):
    PH_MISMATCH  プレースホルダーの数・種類(validate_po.py の判定をそのまま使う。並び替えは通る)
    PH_NUM_SPACE translators コメントから数値に置き換わると分かる %s 系プレースホルダーと日本語の間の
                 半角スペース(validate_po.py の NUM_SPACING は %d 系しか見ない。translators が無ければ判定しない)
    FULLWIDTH    全角記号 ！？（）：；
    TERMINAL     終端記号が原文と対応しているか(. → 。/ ! ? は直前に半角スペース / : はそのまま /
                 原文に無ければ付けない。末尾のタグは剥がして判定)
    HTML_TAG     開始タグ(属性込み・祖先パス付き)と閉じタグの種類と数(入れ子の構造も一致させる。
                 兄弟の順序は問わない)
    ID_MISSING / ID_MISMATCH / ID_TYPE  id が無い・n の msgid と食い違う(番号ズレ)・文字列でない
    CTX_MISMATCH / CTX_TYPE  msgctxt 違いで同じ msgid が複数あるエントリーで、ドラフトの
                  ctx が対応表の msgctxt と食い違う・文字列でない(id は msgid の先頭なので
                  番号の入れ替えを見抜けない)。ctx が無いドラフトと、msgctxt の項目を持たない
                  旧世代の対応表では照合せず、manual 候補に unverified_ctx を付ける
    複数形エントリーは複数形の原文(msgid_plural)で判定する(日本語 .po は nplurals=1 で訳文は msgstr[0] だけ)

出力(--outdir 配下):
    pool.json                    適用対象の訳文(msgid -> msgstr)
    hold.json                    `[要確認]` 付きで保留した訳文
    manual.json                  msgctxt 違いで複数エントリーある msgid の訳文候補(手動適用)。
                                 {msgid: [{msgctxt, location, key, chunk, n, msgstr}, ...]}
                                 key がエントリーの同一性。番号キーの無い旧形式ドラフト由来の
                                 候補は ambiguous 付きで、どのエントリー向けかは特定できない
    missing.json                 どのドラフトにも現れなかった msgid
    rework.json                  機械チェックで弾いた訳文と、再投入用チャンク名
    chunks/rework_NN.md + .json  rework をサブエージェントに再投入するためのチャンク
                                 (chunk-meta.json があれば通常チャンクと同じ見本・Project Glossary 付き)
    collect-report.txt

終了コード: 0 = 問題なし / 4 = ドラフトの形式エラーあり / 2 = 未回収あり / 3 = rework あり

rework の流れ:
    1. exit 3 なら chunks/rework_NN.md をサブエージェントに投げ、drafts/translations_rework_NN.json に書かせる
    2. このスクリプトを再実行する。rework で通った訳文は**元の通常ドラフト(translations_NN.json)に
       書き戻し**、読み終えた rework ドラフトは drafts/consumed/ へ移す(証跡として残す。以後は読まない)。
       通常ドラフトが常に最新の訳を持つので、古い rework ドラフトが後から上書きすることはない。
       書き戻しに失敗した項目や不正な項目を含む rework ドラフトは drafts/ に残す(exit 4)
    3. まだ NG が残れば新しい番号(rework_01 …)で作り直す。ドラフト名も新しくなるので
       「既存ファイルを上書きしない」規則と衝突しない

未回収(exit 2)の再投入:
    同じチャンク(chunks/chunk_NN.md)を投げ直し、書き込み先を translations_NN_2.json
    (以降 _3, _4 …)にする。**NN は元のチャンク番号のまま**にすること(番号キーの復元に
    chunks/chunk_NN.json を使うので、番号を変えると対応表が引けず全件 bad になる)。
    同じ番号は後のファイルの訳文で上書きされ、回収件数は増えない

使い方:
    python /path/to/skill/scripts/po_collect.py --outdir .work/plugin-x

Skill の apply_translations.py / validate_po.py / po_chunk.py と同じディレクトリに置くこと(同じ場所から import する)。
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
import sys
from pathlib import Path

# 同じディレクトリの Skill スクリプトを読み込む。プレースホルダー照合は validate_po.py の判定を
# そのまま使う(apply_translations.py と同じ許容ルールなので、ここで通れば apply でも通る)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_po as vp  # noqa: E402
from po_chunk import (  # noqa: E402
    DEFAULT_MAX_CHARS,
    DEFAULT_SIZE,
    HOLD_MARKER,
    ID_PREVIEW_LEN,
    REF_LIMIT,
    RefIndex,
    assign_refs,
    glossary_section,
    read_glossaries,
    kind_of,
    load_refs,
    split_chunks,
    write_chunk,
)

HOLD_RE = re.compile(r"\s*\[要確認[^\]]*\]")
FULLWIDTH_RE = re.compile(r"[！？（）：；]")
# タグ名に `_` を許す。一部のプラグインには `<custom_icon />` や `<settings_page_link/>` の
# ような擬似タグが実在し、除外すると原文・訳文の両方でトークンが 0 個になって
# HTML_TAG の検査が素通りする(訳文がタグを落としても通ってしまう)
TAG_TOKEN_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9_-]*)((?:\s[^<>]*?)?)(/?)>")
ATTR_RE = re.compile(r"""([A-Za-z_:][-A-Za-z0-9_:.]*)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?""")
PH_NUM_RE = re.compile(r"%(\d+)\$")
TRANSLATABLE_ATTRS = frozenset("title alt aria-label placeholder value label".split())
VOID_TAGS = frozenset("area base br col embed hr img input link meta param source track wbr".split())
TRAILING_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>\s*$")
TERM_RUN_RE = re.compile(r"[!?]+$")   # 末尾の `!` `?` の連続(`!!!` を `!` に減らさせない)
DRAFT_RE = re.compile(r"^translations_(rework_\d+|\d+)(?:_\d+)?\.json$")
# 並べ替え用に「rework か / チャンク番号 / 再投入の回数」へ分解する
DRAFT_PARTS_RE = re.compile(r"^translations_(rework_)?(\d+)(?:_(\d+))?\.json$")
WS_RE = re.compile(r"\s+")
ID_MIN_MATCH = 10   # 切り詰められた id の照合に最低限必要な文字数
REPORT_LIMIT = 40
CONSUMED_DIR = "consumed"

# Windows の既定 stdout は cp932 で、未回収時の警告に含まれる絵文字が
# UnicodeEncodeError になり exit 2 を返せずに落ちる。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# ドラフト段階の機械チェック
# ---------------------------------------------------------------------------

def strip_trailing_tags(s: str) -> str:
    """末尾のタグ(</strong> や <br> など)を剥がす。タグの手前にある終端記号を判定するため。"""
    s = s.rstrip()
    while True:
        m = TRAILING_TAG_RE.search(s)
        if not m:
            return s
        s = s[: m.start()].rstrip()


def run_len(s: str, ch: str) -> int:
    """末尾に ch が何個連続しているか。終端記号を「1 個だけ」に保つために使う。"""
    n = 0
    while s.endswith(ch):
        n += 1
        s = s[: -len(ch)]
    return n


def ellipsis_units(s: str) -> int:
    """末尾の省略記号の個数。`...` と `…` は同じ 1 個として数える。

    個数まで見ないと、原文 `Loading...`(1 個)に対して訳文「読み込み中……」(2 個)が通る。
    """
    t = s.replace("...", "…")
    n = 0
    while t.endswith("…"):
        n += 1
        t = t[:-1]
    return n


def terminal_reason(msgid: str, msgstr: str) -> str | None:
    """終端記号は原文にあるものだけを写す。

    根拠(いずれも公式スタイルガイド由来。references/ の該当節):
    - word-choice-rules.md 2-8「句読点の有無は原文に合わせる」 → 原文の `.` は「。」、原文に無ければ付けない
    - notation-rules.md 1-2「疑問符・感嘆符は半角」+ 1-4「半角文字と全角文字の間にスペース」 → `!` `?` は半角のまま、直前に半角スペース
    - notation-rules.md 1-4「コロン記号 (:) の前にはスペースを入れない」 → `:` は半角のまま写す
    """
    s = strip_trailing_tags(msgid)
    t = strip_trailing_tags(msgstr)
    if not s or not t:
        return None
    if s.endswith(("...", "…")):
        want, got = ellipsis_units(s), ellipsis_units(t)
        if got == want:
            return None
        return ("TERMINAL: 原文の末尾の省略記号は %d 個 → 訳文も同じ数の「…」で終える(訳文は %d 個)"
                % (want, got))
    last = s[-1]
    if last == ".":
        # 連続の長さまで見る。`endswith` だけだと原文の `.` 1 個に対して `。。` が通る
        if run_len(t, "。") == 1:
            return None
        return "TERMINAL: 原文が '.' で終わる → 訳文は「。」1 つで終える"
    if last in "!?":
        # 1 文字ではなく連続で比べる。`Deletes them all !!!` を「削除します !」にすると
        # 原文の終端記号を減らしたことになる
        run = TERM_RUN_RE.search(s).group()
        m = TERM_RUN_RE.search(t)
        if m is None or m.group() != run:
            return "TERMINAL: 原文が '%s' で終わる → 訳文も半角 '%s' で終える(直前に半角スペース)" % (run, run)
        prev = t[: m.start()][-1:]
        if prev == " " or (prev.isascii() and prev.isalnum()):
            return None  # 半角スペース、または半角英数字の直後ならそのまま(記号の直後は不可)
        return "TERMINAL: 日本語の直後の '%s' は直前に半角スペースを入れる" % run
    if last == ":":
        if run_len(t, ":") == run_len(s, ":"):
            return None
        return "TERMINAL: 原文が ':' で終わる → 訳文も同じ数の半角 ':' で終える"
    if last in ")\"'>*]}」』":
        return None  # 閉じ括弧・引用符で終わる原文は判定しない
    # `…` も終端記号として扱う。上で原文末尾の `…` を特別扱いしている以上、原文に無い
    # 省略記号を訳文が足すのも「終端記号は原文にあるものだけ」の規則に反する
    if t[-1] in "。.!?:…":
        return "TERMINAL: 原文に終端記号が無い → 訳文の末尾 '%s' を外す" % t[-1]
    return None


def _attr_key(attrs: str) -> str:
    """属性を「名前=値」に正規化して並べる。

    翻訳対象の属性(title など)は値を比較しないが、属性の有無は比較する。
    値の中の `%1$s` は `%s` に正規化する(番号付けへの並べ替えは placeholder_reason と同じく許容)。
    """
    items = []
    for m in ATTR_RE.finditer(attrs):
        k = m.group(1).lower()
        if k in TRANSLATABLE_ATTRS:
            items.append(k)
            continue
        v = m.group(2) if m.group(2) is not None else (m.group(3) if m.group(3) is not None else (m.group(4) or ""))
        items.append("%s=%s" % (k, PH_NUM_RE.sub("%", WS_RE.sub(" ", v.strip()))))
    return " ".join(sorted(items))


def tag_tokens(s: str) -> list[tuple[bool, str, bool, str]]:
    """(閉じタグか, タグ名, void か, 比較キー) の列。`<?php` はタグ扱いしない。

    比較キーは開始タグなら属性込み(`a href=%s`)、閉じタグなら `</a>`。
    """
    out = []
    for closing, name, attrs, selfclose in TAG_TOKEN_RE.findall(s):
        name = name.lower()
        is_closing = closing == "/"
        void = selfclose == "/" or name in VOID_TAGS
        if is_closing:
            key = "</%s>" % name
        else:
            ak = _attr_key(attrs)
            key = "%s%s" % (name, " " + ak if ak else "")
        out.append((is_closing, name, void, key))
    return out


def tag_profile(toks: list[tuple[bool, str, bool, str]]) -> tuple[collections.Counter, bool]:
    """開始タグは祖先パス付き(`strong>a href=#`)、閉じタグは `</a>` で数える。入れ子が正しいかも返す。

    祖先パスで数えるので `<strong><a>` ⇄ `<a><strong>` の入れ替えは検出でき、兄弟の順序入れ替えは通る。
    """
    stack: list[str] = []
    c: collections.Counter = collections.Counter()
    ok = True
    for closing, name, void, key in toks:
        if closing:
            c[key] += 1
            if stack and stack[-1] == name:
                stack.pop()
            else:
                ok = False
        else:
            c[">".join(stack + [key])] += 1
            if not void:
                stack.append(name)
    if stack:
        ok = False
    return c, ok


def tag_reason(msgid: str, msgstr: str) -> str | None:
    """タグの種類・数・属性・入れ子の構造が原文と一致するか。兄弟の順序は問わない。"""
    a = tag_tokens(msgid)
    b = tag_tokens(msgstr)
    if not a and not b:
        return None

    def fmt(c: collections.Counter) -> str:
        return " ".join("%s×%d" % kv for kv in sorted(c.items())) or "(なし)"

    ca, ok_a = tag_profile(a)
    cb, ok_b = tag_profile(b)
    if not ok_a:
        # 原文自体の入れ子が壊れているときは構造を見ず、種類と数だけ比較する(解消不能な rework を避ける)
        ca = collections.Counter(key for _c, _n, _v, key in a)
        cb = collections.Counter(key for _c, _n, _v, key in b)
    if ca != cb:
        return "HTML_TAG: 原文 %s / 訳文 %s(種類・数・属性・入れ子を原文に合わせる。title などの翻訳対象属性は有無だけ比較)" % (fmt(ca), fmt(cb))
    if ok_a and not ok_b:
        # 祖先パスの数が同じでも、閉じタグが先に来るなど開閉の対応が崩れていることがある
        return "HTML_TAG: 訳文でタグの開閉の対応が崩れている(原文と同じ入れ子にする)"
    return None


# ---------------------------------------------------------------------------
# PH_NUM_SPACE: translators から数値に置き換わると分かる %s 系プレースホルダーの前後スペース
# ---------------------------------------------------------------------------
# notation-rules.md 6-1: スペースの要否は変換指定子ではなく「何に置き換わるか」で決まる。
# validate_po.py の NUM_SPACING(_PH_SPACE_RE)は %d 系しか見ないので、translators コメントで
# 件数と分かる %s(`Showing %1$s of the %2$s` の `%2$s件中 %1$s件`)は apply 後も素通りしていた。
# 下訳でこの形(`%2$s件中 %1$s件`)が繰り返し出たので、ドラフト段階で弾く。
# 判定材料は translators だけ。無い・数値と読めないものは判定しない(誤検出より取りこぼしを選ぶ)
STR_PH_RE = re.compile(r"%(?:(\d+)\$)?[-+ 0]*\d*(?:\.\d+)?s")
# translators 内でプレースホルダーに言及する形: `%1$s` / `%s` / 行頭かカンマ・セミコロン・スラッシュ後の `1:` `1 =` `1)`
TR_MENTION_RE = re.compile(r"%(?:(\d+)\$)?s|(?:^|(?<=[,;、/]))\s*(\d+)\s*[:=)]")
# 「数値が入る」と読む語。size / total / amount は単位や通貨付きの半角トークンになりうるので入れない
NUMERIC_WORD_RE = re.compile(
    r"\b(?:numbers?|counts?|how many|quantity|numeric|integer|digits?)\b|件数|個数|数値|人数|回数|枚数|数量", re.I)
JA_CHAR_RE = re.compile(r"[\u3005\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")


def numeric_placeholders(msgid: str, translators: str) -> list[str]:
    """translators コメントから数値に置き換わると分かる %s 系プレースホルダー(原文中の表記)を返す。

    translators を言及(`%1$s` / `%s` / `1:` …)ごとの区間に切り、数値を示す語を含む区間の
    プレースホルダーだけを数値扱いにする(`1: number of attempts, 2: date` なら %1$s だけ)。
    言及が無く、原文の %s 系が 1 個だけなら translators 全体で判定する。
    """
    if not translators:
        return []
    phs = list(STR_PH_RE.finditer(msgid))
    if not phs:
        return []
    labeled: list[tuple[int, str]] = []
    k = 0
    for m in phs:
        if m.group(1):
            labeled.append((int(m.group(1)), m.group(0)))
        else:
            k += 1
            labeled.append((k, m.group(0)))
    numeric: set[int] = set()
    mentions = list(TR_MENTION_RE.finditer(translators))
    if mentions:
        j = 0
        for i, m in enumerate(mentions):
            end = mentions[i + 1].start() if i + 1 < len(mentions) else len(translators)
            seg = translators[m.end():end]
            if m.group(1):
                num = int(m.group(1))
            elif m.group(2):
                num = int(m.group(2))
            else:
                j += 1
                num = j
            if NUMERIC_WORD_RE.search(seg):
                numeric.add(num)
    elif len(labeled) == 1 and NUMERIC_WORD_RE.search(translators):
        numeric.add(labeled[0][0])
    return [tok for num, tok in labeled if num in numeric]


def num_space_reason(msgid: str, msgstr: str, translators: str) -> str | None:
    """数値扱いのプレースホルダーと日本語の間に半角スペースがあれば rework の理由を返す。

    半角記号の隣(`件数: %1$s`、`(%1$s)`)は 1-4 / 1-5 の規則どおりなので咎めない。
    """
    for tok in numeric_placeholders(msgid, translators):
        for m in re.finditer(re.escape(tok), msgstr):
            before = msgstr[:m.start()]
            after = msgstr[m.end():]
            b = before.rstrip(" \t")
            a = after.lstrip(" \t")
            if (b != before and b and JA_CHAR_RE.match(b[-1])) or (a != after and a and JA_CHAR_RE.match(a[0])):
                return ("PH_NUM_SPACE: %s は translators「%s」から数値に置き換わる → 数字と同じく日本語との間に"
                        "スペースを入れない(%%d件 と同じ扱い。例: %%2$s件中%%1$s件)" % (tok, translators[:60]))
    return None


def placeholder_reason(vp, msgid: str, msgstr: str) -> tuple[str | None, str | None]:
    """(rework にする理由, 注記) を返す。"""
    exp = vp.extract_placeholders(msgid)
    act = vp.extract_placeholders(msgstr)
    if vp._placeholders_compat(exp, act):
        return None, None
    # `100% free` の `% f` は _PH_RE の誤検出(書式フラグに空白を含む)。誤検出分を除いた残りが
    # 一致するなら原因は誤検出だけなので、rework にせず pool に残す(apply で blocked → 人間へ)。
    # 特例にするのは**原文側**に `% ` があるときだけ。原文に無いのに訳文にだけ `% ` が出るのは
    # 誤検出ではなく訳文が余計なプレースホルダーを足している(または本物を落としている)ので rework
    exp2 = [p for p in exp if not p.startswith("% ")]
    if len(exp2) < len(exp):
        act2 = [p for p in act if not p.startswith("% ")]
        if vp._placeholders_compat(exp2, act2):
            return None, "PH_SUSPECT: 原文の '% ' はプレースホルダー誤検出の疑い。pool に残す(apply で blocked になったら人間へ)"
    return "PH_MISMATCH: 原文 %s / 訳文 %s" % (" ".join(exp) or "(なし)", " ".join(act) or "(なし)"), None


def _check_against(vp, src: str, msgstr: str, translators: str = "") -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    notes: list[str] = []
    r, note = placeholder_reason(vp, src, msgstr)
    if r:
        reasons.append(r)
    if note:
        notes.append(note)
    m = FULLWIDTH_RE.search(msgstr)
    if m:
        reasons.append("FULLWIDTH: 全角記号「%s」→ 半角にする(! ? は直前に半角スペース、括弧は半角 + 外側にスペース)" % m.group())
    t = terminal_reason(src, msgstr)
    if t:
        reasons.append(t)
    h = tag_reason(src, msgstr)
    if h:
        reasons.append(h)
    s = num_space_reason(src, msgstr, translators)
    if s:
        reasons.append(s)
    return reasons, notes


def check_draft(vp, msgid: str, msgstr: str, msgid_plural: str = "", translators: str = "") -> tuple[list[str], list[str]]:
    """(rework にする理由, 注記) を返す。注記は報告だけで pool に残す。

    複数形エントリーは訳文が 1 つ(日本語 .po は nplurals=1 で msgstr[0] だけ)で、複数形原文の訳として
    使われる(`%d件` は 1 件のときも表示される)。プレースホルダーは複数形側にあるので複数形の原文で判定する
    (`1件` のように単数形にしか合わない訳文は NG)。単数形と複数形で終端記号やタグが異なると両立
    できないので、単数形とは合わない場合は注記だけ出して人間が判断できるようにする。
    """
    if not msgid_plural:
        return _check_against(vp, msgid, msgstr, translators)
    reasons, notes = _check_against(vp, msgid_plural, msgstr, translators)
    if not reasons:
        r1, _ = _check_against(vp, msgid, msgstr, translators)
        r1 = [r for r in r1 if not r.startswith("PH_")]
        if r1:
            notes.append("PLURAL_DIFF: 単数形の原文とは合わない(%s)。訳文は複数形に合わせた" % " / ".join(r1))
    return reasons, notes


def norm(s: str) -> str:
    return WS_RE.sub(" ", s.strip())


def _id_matches(full: str, given: str) -> bool:
    """id(先頭 30 文字。30 文字以内なら全文)が msgid と一致するか。

    msgid 全体が 30 文字以内なら全文一致を要求する(`Save` に `Save changes` は通さない)。
    30 文字で切り詰められる長い msgid だけ、LLM が文字数を正確に数えないことを考慮して
    前方一致(10 文字以上)を許す。
    """
    expected = full[:ID_PREVIEW_LEN]
    g = given[:ID_PREVIEW_LEN]
    if len(full) <= ID_PREVIEW_LEN:
        return g == expected
    k = min(len(g), len(expected))
    return k >= ID_MIN_MATCH and g[:k] == expected[:k]


def id_reason(given_raw, mid: str, n: int) -> str | None:
    """id(msgid.strip() の先頭 30 文字。30 文字未満なら全文)と n の msgid を照合する。

    まず**エージェントへの契約どおり**、内部の空白をそのままにして比べる。空白を潰してから
    比べると、原文に空白の連続があるときに正しい id が落ちる: `Feature:    value    and    more`
    は生の先頭 30 文字が `Feature:    value    and    mo` なのに、潰した全文は 23 文字なので
    「切り詰められていない」と判定され、全文一致を要求して外れる。

    そのうえで、空白を詰めて書いてくる下訳も通せるよう、潰した形での一致も許す。
    """
    if given_raw is None or given_raw == "":
        return "ID_MISSING: id が無い(番号ズレを検出できない)。msgid の先頭 %d 文字(短ければ全文)を id に書く" % ID_PREVIEW_LEN
    if not isinstance(given_raw, str):
        # str() で潰してから比べると、msgid が "123" のときに id: 123 が通ってしまう
        return "ID_TYPE: id が文字列ではない(%s) -> %r。msgid の先頭 %d 文字を文字列で書く" % (
            type(given_raw).__name__, given_raw, ID_PREVIEW_LEN)
    given = given_raw.strip()
    if not given:
        return "ID_MISSING: id が無い(番号ズレを検出できない)。msgid の先頭 %d 文字(短ければ全文)を id に書く" % ID_PREVIEW_LEN
    if _id_matches(mid.strip(), given) or _id_matches(norm(mid), norm(given)):
        return None
    return "ID_MISMATCH: id %r が n=%d の msgid %r と一致しない(番号ズレの疑い。n を確認する)" % (
        norm(given)[:ID_PREVIEW_LEN], n, norm(mid)[:ID_PREVIEW_LEN])


# ---------------------------------------------------------------------------
# ドラフトファイルとチャンク対応表
# ---------------------------------------------------------------------------

def draft_sort_key(name: str) -> tuple:
    """(rework か, チャンク番号, 再投入の回数, 名前)。後勝ちにするための並び。

    名前の辞書順だと再投入が 2 桁になったとき translations_00_10.json が _2.json より先に来て、
    古い _2 の訳が最新を上書きする。番号は数値として比べる。
    """
    m = DRAFT_PARTS_RE.match(name)
    if not m:
        return (2, 0, 0, name)      # 規則から外れた名前は最後に回す
    return (1 if m.group(1) else 0, int(m.group(2)), int(m.group(3) or 0), name)


def ordered_drafts(draftdir: Path) -> list[Path]:
    """通常のドラフト → rework の順。同じチャンクなら再投入の回数が大きいものを後に(後勝ち)。

    consumed/ は読まない。
    """
    return sorted(draftdir.glob("translations_*.json"), key=lambda p: draft_sort_key(p.name))


def chunk_key(draft_name: str) -> str | None:
    """translations_00.json -> "00" / translations_rework_00.json -> "rework_00" / それ以外 -> None"""
    m = DRAFT_RE.match(draft_name)
    return m.group(1) if m else None


def chunk_name_of(key: str) -> str:
    return key if key.startswith("rework_") else "chunk_" + key


def load_chunk_index(chunkdir: Path, key: str | None, report: list[str]) -> dict[int, dict] | None:
    """番号 n -> {"msgid", "msgctxt", "location"}。msgctxt / location は旧世代のチャンクには無い。

    msgctxt を持ち帰るのは、msgctxt 違いで同じ msgid が複数あるエントリーを manual.json で
    1 件ずつ区別できるようにするため(msgid だけでは apply_translations.py --list の
    個別インデックスと対応付けられない)。

    戻り値は「対応表が無い」と「壊れている」を区別する: 無ければ {}、壊れていれば None。
    None は呼び出し側が形式エラーとして数える(旧形式の msgid キーのドラフトは対応表を
    使わないので、数えないと壊れたまま exit 0 で通ってしまう)。
    """
    if key is None:
        return {}
    name = chunk_name_of(key)
    p = chunkdir / (name + ".json")
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        out: dict[int, dict] = {}
        for it in data:
            # 作業ディレクトリをコミットする運用だと、マージ競合や手編集で壊れた対応表が来うる。
            # int() で緩く受けて後勝ちにすると、ドラフトの id を別エントリーの msgid に対して
            # 検証してしまい、形式エラーにならないまま違うエントリーへ訳が入る
            n = it["n"]
            if isinstance(n, bool) or not isinstance(n, int):
                raise ValueError("n が整数ではありません: %r" % (n,))
            if n in out:
                raise ValueError("n=%d が重複しています" % n)
            # msgid が null や数値だと id_reason() の mid.strip() で traceback 終了し、
            # 意図した exit 4 と collect-report.txt にならない
            for field in ("msgid", "msgid_plural", "msgctxt", "location"):
                if field not in it:
                    continue                      # 旧世代のチャンクには無い項目
                v = it[field]
                # null は「項目なし」と区別できない。空文字に丸めると schema_ctx が真のまま
                # msgctxt だけ空になり、entry_of() が e の一致を拒否して文脈を失う
                if not isinstance(v, str):
                    raise ValueError("n=%d の %s が文字列ではありません: %r" % (n, field, v))
            if not isinstance(it["msgid"], str):
                raise ValueError("n=%d の msgid がありません" % n)
            ro = it.get("rework_of")
            # 鍵は (チャンクキー, n) の順。役割まで見ないと [1, "00"] が通り、
            # entry_key_of() が (1, "00") を返して元の記録 ("00", 1) を消せず、
            # 同じ rework チャンクを作り続ける。bool は int のサブクラスなので明示的に外す。
            # 旧形式(番号キーなし)のドラフト由来の鍵は ("-", msgid) で 2 番目が文字列になる
            if ro is not None and not (
                isinstance(ro, list) and len(ro) == 2 and isinstance(ro[0], str)
                and ((isinstance(ro[1], int) and not isinstance(ro[1], bool))
                     or (ro[0] == "-" and isinstance(ro[1], str)))
            ):
                raise ValueError(
                    'n=%d の rework_of は [チャンクキー(文字列), n(整数)]、'
                    '旧形式なら ["-", msgid(文字列)] にしてください: %r' % (n, ro))
            out[n] = {
                "msgid": it["msgid"],
                # ここに来る時点で項目があれば必ず文字列(null は上で弾いている)
                "msgctxt": it.get("msgctxt", ""),
                "location": it.get("location", ""),
                # 「項目が無い(旧世代)」と「空(複数形なし)」を区別する
                "msgid_plural": it["msgid_plural"] if "msgid_plural" in it else None,
                "e": it.get("e"),            # entries.json 内の位置(旧世代のチャンクには無い)
                "rework_of": ro,
                # msgctxt の項目を持つ世代か。持たない世代の "" を「文脈なし」として
                # 扱うと、entries.json 側の本当の msgctxt を空で上書きしてしまう
                "schema_ctx": "msgctxt" in it,
            }
        return out
    except (OSError, ValueError, TypeError, KeyError) as ex:
        report.append("chunks/%s.json: PARSE ERROR %s(壊れているので po_chunk.py を再実行するか、ファイルを確認してください)" % (name, ex))
        return None


def next_rework_number(chunkdir: Path) -> int:
    nums = []
    for p in chunkdir.glob("rework_*.json"):
        m = re.match(r"rework_(\d+)$", p.stem)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) + 1 if nums else 0


def entry_key_of(mid: str, key: str | None, n: int | None, is_rework: bool,
                 chunk_entry: dict | None) -> tuple:
    """エントリーを一意に指す鍵 (チャンクキー, n)。rework ドラフトは元のエントリーの鍵を引き継ぐ。

    msgid を鍵にできないのは、msgctxt 違いで同じ msgid が複数エントリーあるため。rework チャンクにも
    同じ msgid が複数入りうるので、どの記録への answer かは chunks/rework_NN.json の rework_of
    (元のチャンクキーと n)でしか分からない。
    """
    ro = (chunk_entry or {}).get("rework_of")
    if is_rework and isinstance(ro, list) and len(ro) == 2:
        return (ro[0], ro[1])
    if key is not None and n is not None:
        return (key, n)
    return ("-", mid)          # 旧形式(msgid キー)のドラフトは番号が無い


def prev_key(it: dict) -> tuple:
    """rework.json の 1 項目からエントリー鍵を復元する(旧形式は msgid で代用)。"""
    k = it.get("key")
    if isinstance(k, list) and len(k) == 2:
        return (k[0], k[1])
    return ("-", it.get("msgid"))


def load_prev_rework(path: Path) -> tuple[set[tuple], list[str]]:
    """前回の rework 集合と、そのとき出したチャンク名を復元する。

    rework.json も作業ディレクトリの中間成果物なので、マージや手編集で壊れうる。読めない・形が違う
    ときは「前回は無かった」ことにして rework チャンクを作り直す(ここで例外を投げると
    collector ごと traceback で落ち、形式エラーの報告も終了コードも出せない)。
    """
    if not path.is_file():
        return set(), []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            items, chunks = data.get("items", []), data.get("chunks", [])
        elif isinstance(data, list):
            items, chunks = data, []
        else:
            return set(), []
        if not isinstance(items, list) or not isinstance(chunks, list):
            return set(), []
        keys = set()
        for it in items:
            if not isinstance(it, dict):
                continue
            k = prev_key(it)
            # list などだと set に入れられない。bool は int のサブクラスなので、
            # ["00", true] を通すと ("00", 1) と等価になり、壊れた前回状態を
            # 現在の rework 集合と誤認して古いチャンクを再利用しうる
            if all(isinstance(part, (str, int, type(None))) and not isinstance(part, bool)
                   for part in k):
                keys.add(k)
        return keys, [c for c in chunks if isinstance(c, str)]
    except (OSError, ValueError, TypeError, AttributeError):
        return set(), []


def resolve_from(outdir: Path, p: str) -> Path | None:
    """chunk-meta.json のパスは po_chunk.py 実行時の cwd 基準。cwd と、作業ディレクトリの 2 つ上(`.work/{slug}` ならプロジェクトルート)で試す。"""
    for cand in (Path(p), outdir.resolve().parent.parent / p):
        if cand.is_file():
            return cand
    return None


def ref_context(outdir: Path, report: list[str]) -> tuple[RefIndex | None, Path | None, dict]:
    """po_chunk.py が残した chunk-meta.json から、見本と Project Glossary の文脈を復元する。"""
    meta_path = outdir / "chunk-meta.json"
    if not meta_path.is_file():
        report.append("--- chunk-meta.json が無いので rework チャンクに見本・Project Glossary は付きません(旧 po_chunk.py の出力)")
        return None, None, {}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        report.append("--- chunk-meta.json を読めません: %s" % ex)
        return None, None, {}
    if not isinstance(meta, dict):
        # 構文は通るが形が違う(`[]` など)。直後の meta.get で AttributeError になる
        report.append("--- chunk-meta.json が JSON オブジェクトではありません(型 %s)" % type(meta).__name__)
        return None, None, {}
    po_path = resolve_from(outdir, str(meta.get("po_path", "")))
    if po_path is None:
        report.append("--- chunk-meta.json の po_path が見つかりません: %r" % meta.get("po_path"))
        return None, None, meta
    index = None
    if not meta.get("no_ref"):
        raw_refs = meta.get("refs")
        if not isinstance(raw_refs, list):
            report.append("--- chunk-meta.json の refs が配列ではないので見本は付きません: %r" % (raw_refs,))
            raw_refs = []
        paths = [q for q in (resolve_from(outdir, p) for p in raw_refs if isinstance(p, str))
                 if q is not None]
        refs = load_refs(paths, po_path, vp, quiet=True)
        index = RefIndex(refs) if refs else None
    return index, po_path, meta


def meta_int(meta: dict, key: str, default: int) -> int:
    """chunk-meta.json の数値項目。壊れていれば既定値に落とす(int() で traceback しない)。"""
    try:
        v = int(meta.get(key, default))
    except (TypeError, ValueError):
        return default
    return v if v > 0 else default


def unique_dest(dirpath: Path, name: str) -> Path:
    dest = dirpath / name
    i = 1
    while dest.exists():
        dest = dirpath / ("%s.%d%s" % (Path(name).stem, i, Path(name).suffix))
        i += 1
    return dest


def write_back(written: dict[Path, list[tuple[int, str, Path, str, str | None]]], report: list[str]) -> tuple[int, list[Path]]:
    """rework で通った訳文を通常ドラフトへ書き戻す。(書き戻した件数, 失敗した通常ドラフト) を返す。

    msgstr だけでなく id / ctx も対応表の値で直す。番号ズレ(ID_MISMATCH / CTX_MISMATCH)が
    原因の rework で msgstr だけ書き戻すと、通常ドラフトの id / ctx が間違ったまま残り、次の
    po_collect.py で同じエントリーが再び NG になって rework チャンクが際限なく作られる。
    ctx は None なら触らない(対応表に msgctxt の項目が無い旧世代)、"" なら項目を消す。

    一時ファイルに書いてから置き換えるので、途中で失敗しても通常ドラフトは壊れない。
    """
    nback = 0
    failed: list[Path] = []
    for opath, updates in written.items():
        try:
            data = json.loads(opath.read_text(encoding="utf-8"))
            for idx, mstr, _rpath, new_id, new_ctx in updates:
                data[idx]["msgstr"] = mstr
                data[idx]["id"] = new_id
                if new_ctx is None:
                    pass
                elif new_ctx:
                    data[idx]["ctx"] = new_ctx
                else:
                    data[idx].pop("ctx", None)
            tmp = opath.with_name(opath.name + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(opath)
            nback += len(updates)
        except Exception as ex:
            report.append("%s: rework の書き戻しに失敗 %s(rework ドラフトは drafts/ に残す。直してから再実行)" % (opath.name, ex))
            failed.append(opath)
    return nback, failed


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outdir", required=True, help="po_chunk.py と同じ作業ディレクトリ")
    ap.add_argument("--drafts", default=None, help="下訳 JSON のディレクトリ(既定: <outdir>/drafts)")
    ap.add_argument("--no-check", action="store_true", help="ドラフト段階の機械チェック(id 照合を含む)を行わない")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    chunkdir = outdir / "chunks"
    entries_path = outdir / "entries.json"
    if not entries_path.is_file():
        sys.exit("entries.json がありません: %s(先に po_chunk.py を実行してください)" % entries_path)
    try:
        entries = json.loads(entries_path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError("配列ではありません(型 %s)" % type(entries).__name__)
        for i, x in enumerate(entries):
            if not isinstance(x, dict) or not isinstance(x.get("msgid"), str):
                raise ValueError("%d 番目の要素が壊れています: %r" % (i, str(x)[:80]))
            # 任意項目も、あるなら文字列であること。msgid_plural が数値のまま
            # check_draft() に届くと TypeError で落ち、exit 4 の契約を外れる
            for field in ("msgid_plural", "msgctxt", "translators", "location", "kind"):
                v = x.get(field)
                if v is not None and not isinstance(v, str):
                    raise ValueError("%d 番目の %s が文字列ではありません: %r" % (i, field, v))
    except (OSError, ValueError) as ex:
        # 作業ディレクトリをコミットする運用だと壊れて届きうる。traceback ではなく形式エラーで止める
        msg = "entries.json が壊れています: %s(po_chunk.py を実行し直してください)" % ex
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "collect-report.txt").write_text(msg, encoding="utf-8")
        print(msg)
        return 4
    entries_by_msgid: dict[str, dict] = {}
    for x in entries:
        entries_by_msgid.setdefault(x["msgid"], x)
    expected = set(entries_by_msgid)
    # msgctxt 違いで同じ msgid が複数エントリーにあると、通常ドラフトに同じ msgid がその回数だけ出るのは正常。
    # それを超えた分は重複として報告し、足りなければ missing 扱い。この msgid は pool(msgid キー)に 1 件しか
    # 持てず apply も「複数の未翻訳エントリーに一致」で止めるので、候補を manual.json に集めて手動処理へ回す
    expected_count = collections.Counter(x["msgid"] for x in entries)
    normal_count: collections.Counter = collections.Counter()

    draftdir = Path(args.drafts) if args.drafts else outdir / "drafts"
    files = ordered_drafts(draftdir)
    if not files:
        sys.exit("下訳 JSON が見つかりません: %s/translations_*.json" % draftdir)

    checker = None if args.no_check else vp

    pool: dict[str, str] = {}
    hold: dict[str, str] = {}
    manual: dict[str, list[dict]] = collections.defaultdict(list)
    # エントリー鍵 (チャンクキー, n) -> NG 記録。msgid を鍵にすると、msgctxt 違いで同じ msgid が
    # 2 エントリーあるとき、後から来た方が先のエントリーの NG 記録を消して exit 0 になってしまう
    rework: dict[tuple, dict] = {}
    seen: set[str] = set()
    report: list[str] = []
    bad_total = 0
    origin: dict[str, tuple[Path, int]] = {}             # 旧形式(番号なし)用: msgid -> 位置
    origin_by_ek: dict[tuple, tuple[Path, int]] = {}     # エントリー鍵 -> 通常ドラフト内の位置(書き戻し先)
    # エントリー鍵 -> (msgid, msgstr, そのドラフト, 対応表のエントリー)。対応表は書き戻しで id / ctx を直すのに使う
    rework_hits: dict[tuple, tuple[str, str, Path, dict | None]] = {}
    parsed_rework_files: list[Path] = []
    bad_rework_files: set[Path] = set()
    # 通常ドラフトで回収済みの (チャンクキー, n) -> そのドラフト名。msgid ではなく番号で数える。
    # msgid で数えると、msgctxt 違いで 2 エントリーある msgid について「同じ n を 2 回提出して
    # 別の n を欠落させた」ドラフトが件数だけ揃ってしまい、未回収の検出をすり抜ける
    filled_slots: dict[tuple[str, int], str] = {}
    # msgid でエントリーが一意に決まるものだけ、通常ドラフトで見たエントリー鍵を控える
    ek_by_mid: dict[str, tuple] = {}

    def entry_of(chunk_entry: dict | None, mid: str) -> dict | None:
        """チャンク項目から entries.json の該当エントリーを引く。旧世代のチャンクなら None。

        entries_by_msgid は msgctxt 違いのうち先頭しか持たないので、kind(語尾)・translators
        (プレースホルダーの中身)・msgid_plural まで別エントリーのものを掴んでしまう。
        """
        e = (chunk_entry or {}).get("e")
        if isinstance(e, int) and not isinstance(e, bool) and 0 <= e < len(entries):
            x = entries[e]
            # 世代がずれた対応表で別物を掴まない。msgid だけだと、e が「同じ msgid の
            # 別 msgctxt」を指したときに素通りし、複数形・translators・種別・文脈が入れ替わる
            if (x.get("msgid") == mid
                    and x.get("msgctxt", "") == (chunk_entry or {}).get("msgctxt", "")):
                return x
        return None

    def translators_of(chunk_entry: dict | None, mid: str) -> str:
        """translators コメント。エントリーを特定できるときだけ返す(別エントリーの中身で判定しない)。

        旧世代の対応表(e 無し)は msgctxt 違いが無い msgid に限って entries.json から引く。
        """
        x = entry_of(chunk_entry, mid)
        if x is None and expected_count[mid] == 1:
            x = entries_by_msgid.get(mid)
        return (x.get("translators") or "") if x is not None else ""

    def plural_of(chunk_entry: dict | None, mid: str) -> str:
        """複数形の原文。エントリーを特定できるならそれを、無理なら対応表 → 先頭エントリーの順。"""
        x = entry_of(chunk_entry, mid)
        if x is not None:
            return x.get("msgid_plural") or ""
        if chunk_entry is not None and chunk_entry.get("msgid_plural") is not None:
            return chunk_entry.get("msgid_plural") or ""
        return entries_by_msgid[mid].get("msgid_plural") or ""

    def keep_prior(mid: str) -> None:
        """壊れた項目は前の状態を変えない。何も無ければ missing(再実行対象)になる。"""
        if (mid not in pool and mid not in hold and mid not in manual
                and not any(it["msgid"] == mid for it in rework.values())):
            seen.discard(mid)

    def add_manual(mid: str, mstr: str, ek: tuple, key: str | None, n: int | None,
                   chunk_entry: dict | None) -> dict:
        """msgctxt 違いの候補を「1 エントリーにつき 1 件」持つ。

        同一性はエントリー鍵(ek)で見る。チャンクキーと n で見ると、rework ドラフト由来の候補が
        rework_NN のキーになり、元の通常ドラフト由来の候補と別物に見えて 1 エントリーに 2 件
        並んでしまう(rework ドラフトが consumed に移らず残った回で起きる)。

        番号キーを持たない旧形式(msgid キー)のドラフトは、どのエントリー向けの訳か決めようが
        ないので置き換えず必ず積む。取り違えて 1 件に潰すより、候補を全部見せて人間に選ばせる。
        判定は n ではなく**鍵**で行う: 旧形式由来の rework 再投入は rework チャンクの n を
        持つので、n で見ると同じ ('-', msgid) の既存候補を置き換えて正常な方を消してしまう。
        """
        cand = {
            "msgctxt": (chunk_entry or {}).get("msgctxt", ""),
            "location": (chunk_entry or {}).get("location", ""),
            "key": [ek[0], ek[1]],
            "chunk": key,
            "n": n,
            "msgstr": mstr,
        }
        if ek[0] == "-":
            cand["ambiguous"] = "番号キーの無いドラフト由来。どのエントリー向けかは特定できない"
            manual[mid].append(cand)
            return cand
        for i, c in enumerate(manual[mid]):
            if c.get("key") == cand["key"]:
                manual[mid][i] = cand
                return cand
        manual[mid].append(cand)
        return cand

    def drop_manual(mid: str, ek: tuple) -> None:
        """同じエントリーから出た候補だけ取り下げる(番号の無い旧形式は特定できないので残す)。"""
        if mid not in manual or ek[0] == "-":
            # 旧形式は全候補が同じ鍵 ('-', msgid) になるので、ここで消すと ambiguous 候補を
            # 巻き添えで全滅させる。add_manual 側の「特定できない候補は残す」契約に合わせる
            return
        manual[mid] = [c for c in manual[mid] if c.get("key") != [ek[0], ek[1]]]
        if not manual[mid]:
            manual.pop(mid, None)

    def place(mid: str, mstr, key: str | None, n: int | None, pre_reason: str | None, src: str,
              is_rework: bool, ek: tuple, chunk_entry: dict | None = None, given_ctx=None) -> str:
        loc = "%s [%s#%s]" % (src, key or "-", n if n is not None else "-")
        if not isinstance(mstr, str):
            report.append("%s: msgstr が文字列ではない(%s)。前の状態を保持 -> %r" % (loc, type(mstr).__name__, mid[:60]))
            keep_prior(mid)
            return "bad"
        if not mstr.strip():
            report.append("%s: EMPTY msgstr。前の状態を保持 -> %r" % (loc, mid[:60]))
            keep_prior(mid)
            return "bad"
        slot = (key, n) if key is not None and n is not None else None
        if not is_rework:
            prev_src = filled_slots.get(slot) if slot is not None else None
            if slot is None:
                normal_count[mid] += 1          # 旧形式(msgid キー)は番号が無いので msgid で数えるしかない
            elif prev_src is None:
                filled_slots[slot] = src
                normal_count[mid] += 1
            elif prev_src == src:
                report.append("%s: 同じ番号を同じドラフトで 2 回提出(後の訳文で上書き。回収数には数えない) -> %r"
                              % (loc, mid[:60]))
            else:
                filled_slots[slot] = src        # 未回収の再投入(translations_NN_2.json)。番号は同じなので増やさない
            if normal_count[mid] > expected_count[mid]:
                report.append("%s: 重複 msgid(%d 回目、期待 %d 回。後の訳文で上書き) -> %r"
                              % (loc, normal_count[mid], expected_count[mid], mid[:60]))
        pool.pop(mid, None)
        hold.pop(mid, None)
        if not (ek[0] == "-" and expected_count[mid] >= 2 and not is_rework):
            # 消すのは自分のエントリーの記録だけ(別 msgctxt の NG は残す)。ただし旧形式
            # (番号キーなし)で msgid が重複しているときは全項目が同じ鍵になるため、後の
            # 正常な項目が前の NG 記録を消してしまう。特定できないので消さずに残す
            rework.pop(ek, None)
        seen.add(mid)
        reasons = [pre_reason] if pre_reason else []
        held = HOLD_MARKER in mstr
        # [要確認] 付きでもマーカーを除いた訳文を機械チェックする。番号ズレやプレースホルダー欠落が
        # hold に隠れると rework ループに乗らないので、NG があれば hold より rework を優先する
        core = HOLD_RE.sub("", mstr).strip() if held else mstr
        if checker is not None and core:
            more, notes = check_draft(checker, mid, core, plural_of(chunk_entry, mid), translators_of(chunk_entry, mid))
            reasons += more
            for note in notes:
                report.append("%s NOTE %s -> %r" % (loc, note, mid[:60]))
        # msgctxt 違いで同じ msgid が複数あるエントリーは、id(msgid の先頭)が同じなので
        # 番号を入れ替えて提出されても id 照合では見抜けない。ドラフトの ctx で照合する
        unverified_ctx = False
        # checker is None は --no-check。ヘルプが「ドラフト段階の機械チェックを行わない」と
        # 言っている以上、ctx 照合だけ生かして rework にするのは筋が通らない。
        # schema_ctx が偽(旧世代の対応表)なら msgctxt を持たないので、"" と比べると
        # 正しい ctx を書いたドラフトが必ず CTX_MISMATCH になる。照合せず manual に回す
        if checker is not None and expected_count[mid] >= 2 and chunk_entry is not None:
            if not chunk_entry.get("schema_ctx"):
                unverified_ctx = True
            else:
                want_ctx = chunk_entry.get("msgctxt", "")
                if given_ctx is None:
                    unverified_ctx = True
                elif not isinstance(given_ctx, str):
                    # str() で潰すと ctx: 1 が msgctxt "1" の一致として通ってしまう
                    reasons.append("CTX_TYPE: ctx が文字列ではない(%s) -> %r。msgctxt をそのまま写す"
                                   % (type(given_ctx).__name__, given_ctx))
                elif given_ctx != want_ctx:
                    reasons.append("CTX_MISMATCH: ctx %r が n=%s の msgctxt %r と一致しない(msgctxt 違いのエントリーで番号が入れ替わっている疑い)" % (given_ctx[:40], n, want_ctx[:40]))
        if reasons:
            # 取り下げるのは同じ番号(同じエントリー)から出た候補だけ。msgctxt 違いの別エントリーが
            # 先に出した候補まで消すと、rework 通過後に候補が 1 件しか残らず「候補をすべて集める」を満たせない
            drop_manual(mid, ek)
            rework[ek] = {
                "key": [ek[0], ek[1]], "chunk": key, "n": n, "msgid": mid, "msgstr": mstr,
                "msgctxt": (chunk_entry or {}).get("msgctxt", ""),
                "location": (chunk_entry or {}).get("location", ""),
                # msgctxt の項目を持つ世代の対応表から引けた項目だけ、msgctxt を
                # 「空でも正しい値」として扱える(旧世代の "" は単に項目が無いだけ)
                "from_chunk": bool((chunk_entry or {}).get("schema_ctx")),
                "e": (chunk_entry or {}).get("e"),
                "reason": " / ".join(reasons),
            }
            return "rework"
        if expected_count[mid] >= 2:
            # msgctxt 違いの候補は [要確認] 付きでもすべて manual に集める(hold に入れると後の候補で消える)
            cand = add_manual(mid, mstr, ek, key, n, chunk_entry)
            if unverified_ctx:
                # 置き換えのときは末尾とは限らないので、返ってきた候補そのものに付ける
                cand["unverified_ctx"] = (
                    "ドラフトに ctx が無く、番号の入れ替わりを検証できていない。location で --list のインデックスを確認すること")
                report.append("%s NOTE CTX_UNVERIFIED: msgctxt 違いのエントリーだが ドラフトに ctx が無い -> %r" % (loc, mid[:60]))
            return "manual"
        if held:
            hold[mid] = mstr
            return "hold"
        pool[mid] = mstr
        return "ok"

    for path in files:
        name = path.name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as ex:
            report.append("%s: PARSE ERROR %s" % (name, ex))
            bad_total += 1
            continue
        if not isinstance(data, list):
            report.append("%s: 配列ではありません(型 %s)" % (name, type(data).__name__))
            bad_total += 1
            continue
        key = chunk_key(name)
        is_rework = bool(key and key.startswith("rework_"))
        if is_rework:
            parsed_rework_files.append(path)
        by_n = load_chunk_index(chunkdir, key, report)
        if by_n is None:
            # 壊れた対応表。旧形式(msgid キー)のドラフトは by_n を使わないので、ここで
            # 数えないと壊れたまま exit 0 で通ってしまう
            bad_total += 1
            by_n = {}
        counts: collections.Counter = collections.Counter()
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                report.append("%s: オブジェクトではない要素 -> %r" % (name, str(item)[:80]))
                counts["bad"] += 1
                continue
            pre_reason = None
            n: int | None = None
            chunk_entry: dict | None = None
            if "n" in item:
                if not by_n:
                    report.append("%s: chunks/%s.json が無い(または壊れている)ので n=%r を msgid に戻せません"
                                  % (name, chunk_name_of(key) if key else "?", item.get("n")))
                    counts["bad"] += 1
                    continue
                raw_n = item["n"]
                if isinstance(raw_n, bool) or not isinstance(raw_n, int):
                    # true / 1.9 / "1" は受けない(1.9 は int() で 1 になり番号ズレを隠す)
                    report.append("%s: n が整数ではない -> %r" % (name, raw_n))
                    counts["bad"] += 1
                    continue
                n = raw_n
                chunk_entry = by_n.get(n)
                if chunk_entry is None:
                    report.append("%s: n=%d がチャンクの範囲外" % (name, n))
                    counts["bad"] += 1
                    continue
                mid = chunk_entry["msgid"]
                if not args.no_check:
                    pre_reason = id_reason(item.get("id"), mid, n)
            elif "msgid" in item:
                mid = item["msgid"]
            else:
                report.append("%s: n も msgid も無い要素 -> %r" % (name, str(item)[:80]))
                counts["bad"] += 1
                continue
            if not isinstance(mid, str) or mid not in expected:
                report.append("%s: msgid MISMATCH -> %r" % (name, str(mid or "")[:80]))
                counts["bad"] += 1
                continue
            ek = entry_key_of(mid, key, n, is_rework, chunk_entry)
            if is_rework and not (chunk_entry or {}).get("rework_of") and mid in ek_by_mid:
                # 旧世代の rework チャンクには rework_of が無く、鍵が (rework_NN, n) になる。
                # 通常ドラフト側は (NN, n) なので書き戻し先が引けない。msgid でエントリーが
                # 一意に決まるときだけ、通常ドラフトで見た鍵に寄せる
                ek = ek_by_mid[mid]
            if is_rework and ek not in rework and ek in origin_by_ek:
                # 通常ドラフト側に同じエントリーがあり、そちらは今回通っている項目。ここで place
                # すると古い訳が後勝ちになり、write_back が新しい訳を上書きしてしまう
                # (rework ドラフトは不正項目や書き戻し失敗で drafts/ に残ることがある)。
                # 通常ドラフト側にそのエントリーが無いときは唯一の訳なので読み飛ばさない
                report.append("%s: 通常ドラフトが新しいので rework の項目を読み飛ばします -> %r"
                              % (name, mid[:60]))
                counts["stale"] += 1
                continue
            status = place(mid, item.get("msgstr", ""), key, n, pre_reason, name, is_rework,
                           ek, chunk_entry, item.get("ctx"))
            counts[status] += 1
            if status == "bad":
                continue
            if is_rework:
                if status in ("ok", "hold", "manual"):
                    rework_hits[ek] = (mid, item["msgstr"], path, chunk_entry)
                else:
                    rework_hits.pop(ek, None)
            else:
                origin[mid] = (path, idx)
                # rework に回ったかどうかに関わらず記録する。rework ドラフトの答えを戻す先は
                # 常に「そのエントリーの通常ドラフト内の位置」
                origin_by_ek[ek] = (path, idx)
                if expected_count[mid] == 1:
                    ek_by_mid[mid] = ek     # 旧世代 rework チャンクの鍵を救済するのに使う
        bad_total += counts["bad"]
        if is_rework and counts["bad"]:
            bad_rework_files.add(path)
        report.append(
            "%s: total=%d ok=%d hold=%d manual=%d rework=%d bad=%d stale=%d"
            % (name, len(data), counts["ok"], counts["hold"], counts["manual"], counts["rework"],
               counts["bad"], counts["stale"])
        )

    missing = [m for m in expected if m not in seen]
    # msgctxt 違いの msgid はエントリー数ぶん回収されていなければ未回収扱い
    short = [m for m in expected if m in seen and expected_count[m] >= 2 and normal_count[m] < expected_count[m]]
    missing += short
    report.append(
        "--- pool=%d hold=%d manual=%d rework=%d missing=%d bad=%d / expected=%d"
        % (len(pool), len(hold), len(manual), len(rework), len(missing), bad_total, len(expected))
    )
    for it in list(rework.values())[:REPORT_LIMIT]:
        report.append("REWORK [%s#%s] %s | %r" % (it["chunk"] or "-", it["n"] if it["n"] is not None else "-", it["reason"], it["msgid"][:60]))
    if len(rework) > REPORT_LIMIT:
        report.append("REWORK: ... 他 %d 件" % (len(rework) - REPORT_LIMIT))
    for mid, cands in list(manual.items())[:REPORT_LIMIT]:
        report.append("MANUAL(msgctxt 違い %d エントリー、候補 %d 件): %r" % (expected_count[mid], len(cands), mid[:60]))
        for c in cands:
            report.append("    msgctxt=%r location=%r -> %r%s"
                          % (c.get("msgctxt", ""), (c.get("location") or "")[:60],
                             (c.get("msgstr") or "")[:60],
                             "  [" + c["ambiguous"] + "]" if c.get("ambiguous") else ""))
    for m in missing[:REPORT_LIMIT]:
        if m in short:
            report.append("MISSING(msgctxt 違い %d 件中 %d 件のみ回収): %r" % (expected_count[m], normal_count[m], m[:80]))
        else:
            report.append("MISSING: %r" % m[:80])
    if len(missing) > REPORT_LIMIT:
        report.append("MISSING: ... 他 %d 件" % (len(missing) - REPORT_LIMIT))

    # rework で通った訳文を元の通常ドラフトに書き戻し、読み終えた rework ドラフトを consumed/ へ移す。
    # 通常ドラフトが常に最新の訳を持つので、古い rework ドラフトが後から上書きすることはない
    written: dict[Path, list[tuple[int, str, Path, str, str | None]]] = collections.defaultdict(list)
    no_target: set[Path] = set()      # 書き戻し先が見つからなかった rework ドラフト
    for ek, (mid, mstr, rpath, rw_entry) in rework_hits.items():
        final = pool.get(mid, hold.get(mid))
        if final is None and any(c.get("msgstr") == mstr for c in manual.get(mid, [])):
            final = mstr
        # 書き戻し先は rework に回った項目の位置。msgctxt 違いで同じ msgid が複数あるとき、
        # 「最後に読んだ位置」に書くと別エントリーの訳文を潰し、次回の回収で候補が 1 件に潰れる
        if ek[0] == "-" and expected_count[mid] >= 2:
            # 旧形式は全項目が ('-', msgid) になるので、origin_by_ek も最後に読んだ位置。
            # 複数エントリーある msgid でこれを使うと別コンテキストへ書き戻す
            report.append("%s: 旧形式(番号キーなし)で msgid が重複しているため書き戻し先を特定できません(rework ドラフトは drafts/ に残す。manual.json の候補から手動で当てる) -> %r"
                          % (rpath.name, mid[:60]))
            no_target.add(rpath)
            continue
        target = origin_by_ek.get(ek)
        if target is None and (ek[0] == "-" or expected_count[mid] == 1):
            # 旧形式(番号なし)と、msgid でエントリーが一意に決まる場合だけ msgid で引く。
            # 複数エントリーある msgid でこれをやると、別コンテキストの位置を掴んで潰す
            target = origin.get(mid)
        if final != mstr:
            continue
        if target is None:
            # 書き戻せないまま consumed/ へ移すと、次回はこの訳がどこにも無くなり未回収に戻る。
            # 書き戻し失敗と同じ扱いにして drafts/ に残す
            report.append("%s: 書き戻し先の通常ドラフトが見つかりません(rework ドラフトは drafts/ に残す) -> %r"
                          % (rpath.name, mid[:60]))
            no_target.add(rpath)
            continue
        opath, idx = target
        # id は契約どおり msgid の先頭 30 文字。ctx は対応表に msgctxt があるときだけ直す
        new_id = mid.strip()[:ID_PREVIEW_LEN]
        new_ctx = rw_entry.get("msgctxt", "") if rw_entry and rw_entry.get("schema_ctx") else None
        written[opath].append((idx, mstr, rpath, new_id, new_ctx))
    nback, failed_back = write_back(written, report)
    bad_total += len(failed_back)
    # 書き戻せなかった項目や不正な項目を含む rework ドラフトは drafts/ に残す(次回もう一度読む)
    bad_total += len(no_target)
    keep_files = ({rpath for opath in failed_back for _i, _m, rpath in written[opath]}
                  | bad_rework_files | no_target)
    moved: list[str] = []
    for path in parsed_rework_files:
        if path in keep_files:
            report.append("%s: 不正な項目か書き戻し失敗を含むので drafts/ に残します" % path.name)
            continue
        consumed = draftdir / CONSUMED_DIR
        consumed.mkdir(exist_ok=True)
        shutil.move(str(path), str(unique_dest(consumed, path.name)))
        moved.append(path.name)
    if nback or moved:
        report.append(
            "--- rework の結果 %d 件を通常ドラフトに書き戻し、%s を drafts/%s/ へ移動"
            % (nback, ", ".join(moved) or "(なし)", CONSUMED_DIR)
        )

    # rework チャンクの生成
    rework_path = outdir / "rework.json"
    prev_set, prev_chunks = load_prev_rework(rework_path)
    rework_chunks: list[str] = []
    if rework:
        def draft_submitted(c: str) -> bool:
            # 再投入(translations_NN_2.json)も同じチャンクの提出として数える
            return any(
                chunk_key(q.name) == c
                for d in (draftdir, draftdir / CONSUMED_DIR)
                for q in (d.glob("translations_*.json") if d.is_dir() else ())
            )

        prev_md_ok = bool(prev_chunks) and all((chunkdir / (c + ".md")).is_file() for c in prev_chunks)
        prev_drafts_done = bool(prev_chunks) and all(draft_submitted(c) for c in prev_chunks)
        if set(rework) == prev_set and prev_md_ok and not prev_drafts_done:
            # 前回の rework チャンクがまだ投入されていない → そのまま使う(単なる再実行で増やさない)
            rework_chunks = prev_chunks
        else:
            # 投入済みなのに残った、または集合が変わった → 新しい番号で作り直す。
            # ドラフト名も新しくなるので、サブエージェントの「既存ファイルを上書きしない」規則と衝突しない
            index, po_path, meta = ref_context(outdir, report)
            start = next_rework_number(chunkdir)
            items = []
            for it in rework.values():
                # NG になったエントリーそのものを entries.json から引く。msgid で引くと
                # msgctxt だけでなく kind(語尾)・translators(プレースホルダーの中身)まで
                # 別エントリーのものが再投入チャンクに載る
                # entry_of は msgctxt も照合するので、記録した文脈を一緒に渡す。
                # e だけ渡すと msgctxt 付きエントリーで必ず不一致になり、先頭エントリーへ落ちる
                src = entry_of({"e": it.get("e"), "msgctxt": it.get("msgctxt", "")}, it["msgid"])
                if src is not None:
                    x = dict(src)
                elif it.get("e") is not None:
                    # e があるのに引けない = 対応表が entries.json とずれている。msgid で
                    # 代用すると、別エントリーの translators(プレースホルダーの中身)と
                    # msgid_plural・kind(語尾)を載せた再投入チャンクを配ることになる
                    report.append(
                        "rework チャンクを作れません: e=%r が entries.json の該当エントリーを指していません"
                        "(対応表と entries.json の世代がずれています) -> %r"
                        % (it.get("e"), it["msgid"][:60]))
                    bad_total += 1
                    continue
                else:
                    # e を持たない旧世代の対応表。msgid で代用し、拾えた分だけ上書きする。
                    # msgctxt は**空でも上書きする**(NG が msgctxt 無しのエントリーのとき、
                    # truthy 判定だと別エントリーの msgctxt が残って違う文脈の訳が返る)
                    x = dict(entries_by_msgid[it["msgid"]])
                    if it.get("from_chunk"):
                        x["msgctxt"] = it.get("msgctxt", "")
                    if it.get("location"):
                        x["location"] = it["location"]
                x["kind"] = x.get("kind") or kind_of(x)
                x["rework_of"] = list(it["key"])   # 回収時にどの記録への answer か分かるように
                x["_prev"] = it["msgstr"]
                x["_reason"] = it["reason"]
                items.append(x)
            glossaries = read_glossaries(po_path) if po_path else []
            size = meta_int(meta, "size", DEFAULT_SIZE)
            max_chars = meta_int(meta, "max_chars", DEFAULT_MAX_CHARS)
            for i, part in enumerate(split_chunks(items, size, max_chars), start):
                cname = "rework_%02d" % i
                refs_by_n = assign_refs(part, index, meta_int(meta, "ref_limit", REF_LIMIT)) if index else {}
                texts = [x["msgid"] for x in part] + [x.get("msgid_plural") or "" for x in part]
                glossary_md = glossary_section(glossaries, texts)
                extra = {n: (x["_prev"], x["_reason"]) for n, x in enumerate(part, 1)}
                write_chunk(chunkdir, cname, part, refs_by_n, glossary_md, extra)
                rework_chunks.append(cname)
        report.append("--- rework チャンク: %s" % ", ".join("chunks/%s.md" % c for c in rework_chunks))

    (outdir / "pool.json").write_text(json.dumps(pool, ensure_ascii=False, indent=1), encoding="utf-8")
    (outdir / "hold.json").write_text(json.dumps(hold, ensure_ascii=False, indent=1), encoding="utf-8")
    (outdir / "manual.json").write_text(json.dumps(dict(manual), ensure_ascii=False, indent=1), encoding="utf-8")
    (outdir / "missing.json").write_text(json.dumps(missing, ensure_ascii=False, indent=1), encoding="utf-8")
    rework_path.write_text(
        json.dumps({"chunks": rework_chunks, "items": list(rework.values())}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    text = "\n".join(report)
    (outdir / "collect-report.txt").write_text(text, encoding="utf-8")
    print(text)

    if bad_total:
        print("\n⚠️ ドラフトの形式エラーが %d 件あります(壊れた JSON・未知の msgid・範囲外の n など)。"
              "collect-report.txt を確認して直してから再実行してください。" % bad_total)
    if missing:
        print("\n⚠️ 未回収の msgid があります。該当するチャンク(chunks/chunk_NN.md)をそのまま"
              "サブエージェントに再投入し、書き込み先を drafts/translations_NN_2.json(以降 _3, _4 …)に"
              "してください。NN は元のチャンク番号のままにすること(番号キーの復元に chunks/chunk_NN.json を"
              "使うので、番号が変わると回収できません)。同じ番号は後のファイルの訳文で上書きされます。")
    if rework:
        print(
            "\n⚠️ 機械チェック NG が %d 件あります。%s を、書き込み先 drafts/translations_<同名>.json で"
            "サブエージェントに再投入し、po_collect.py を再実行してください。"
            % (len(rework), ", ".join("chunks/%s.md" % c for c in rework_chunks))
        )
    if manual:
        print(
            "\nℹ️ msgctxt 違いで同じ msgid が複数あるエントリーが %d 件あります(manual.json)。pool には入れていないので、"
            "apply_translations.py --list の個別インデックスで 1 件ずつ手動で適用してください。" % len(manual)
        )
    if bad_total:
        return 4
    if missing:
        return 2
    if rework:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
