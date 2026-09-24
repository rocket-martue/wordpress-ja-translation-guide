#!/usr/bin/env python3
"""フェーズ①〜②: .po の未翻訳エントリーを抽出し、サブエージェント用チャンクに分割する。

Skill の `apply_translations.py` の判定をそのまま使うので、ここで抽出される
エントリーと `--list` に出るエントリーは完全に一致する。

出力(すべて --outdir 配下):
    entries.json          全未翻訳エントリー(msgid・種別・gp-priority・ロケーション)
    wordfreq.txt          頻出英単語(訳語リストを作るときの材料)
    chunks/chunk_NN.md    サブエージェントへ渡すチャンク(既存訳の見本・Project Glossary 付き)
    chunks/chunk_NN.json  番号 → msgid/msgctxt/location と entries.json 内の位置(e)の対応表。
                          po_collect.py が回収に使う(サブエージェントには渡さない)
    chunk-meta.json       対象 .po と --ref の記録。po_collect.py が rework チャンクに同じ見本を付けるのに使う

分割は「件数」と「msgid の合計文字数」の両方で切る(既定 30 件 / 3,000 字。どちらかに達したら次)。
所要時間は件数と文字量の両方で決まり、1 本あたりの固定費もあるので、細かく割っても速くならない。
件数の方が効くので件数側の上限を 30 件にしてある。件数だけで切ると changelog のような長文が集まったとき
に重いチャンクができるので文字上限も要る。種別ごとにまとめてから切る。

既存訳の見本(`ref:` 行)は翻訳済み .po から引く。対象 .po 自身と同じディレクトリの
*-translated.po は自動で拾い、コア訳は --ref で足す:
    --ref path/to/core-ja-translated.po
サブエージェントに .po を Grep させない代わりにここで添付する(.po を Grep しに行かせると
1 本の所要が大きく延びる)。*-glossary.csv(GlotPress の Project Glossary エクスポート)が
あればチャンク末尾に付ける。

チャンクの msgid は `<<<MSGID` / `>>>MSGID` で囲む。改行を含む msgid を事故なく受け渡すための
区切り。訳者に渡すものと下訳 JSON の形式は references/contribution-workflow.md の 1.4 にある。

使い方:
    python /path/to/skill/scripts/po_chunk.py path/to/ja.po \
        --outdir .work/plugin-x [--size 30] [--max-chars 3000] [--skip-low] \
        [--ref other-translated.po ...] [--no-ref] [--no-group-by-kind] [--force]

Skill の apply_translations.py / validate_po.py と同じディレクトリに置くこと(同じ場所から import する)。

drafts/ にドラフトが残っている作業ディレクトリでは止まる(番号と msgid の対応が変わり、古い
ドラフトが別の msgid に付くため)。作り直すなら --force(drafts/ と chunks/ を backup-<時刻>/ に退避)。
退避は .po の解析・見本の読み込みがすべて成功したあとに行う(途中で落ちても前世代の対応表が残る)。
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import io
import json
import re
import sys
from pathlib import Path

# 同じディレクトリの Skill スクリプトを読み込む。未翻訳判定(apply_translations)と
# 見本抽出・プレースホルダー照合(validate_po)を Skill 本体と完全に一致させるため
sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_translations as at  # noqa: E402
import validate_po as vp  # noqa: E402

# Windows の既定 stdout は cp932。サマリーに含まれる記号で落ちないようにする
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


FOUND_IN_RE = re.compile(r"#\.\s*Found in (.*?)\.?\s*$")
TRANSLATORS_RE = re.compile(r"#\.\s*translators:\s*(.*)$")
TAG_RE = re.compile(r"<[^>]+>")
URL_RE = re.compile(r"(?:https?://|www\.)\S+")
# GlotPress のステータス別エクスポート(ファイル名末尾の -fuzzy / -translated / -changesrequested は
# エクスポート時のステータスフィルター違い)。どちらも承認済みの訳ではないので見本にしない
UNAPPROVED_PO_RE = re.compile(r"-(fuzzy|changesrequested)\.po$", re.I)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\-]{2,}")
STOPWORDS = frozenset(
    """
    the and for you your this that with are not can will from have has all any set use
    been was were its our they them then than when what which into about only also more
    some such each other there here these those how who why one two new get add see via
    per but out off yes should would could may might must does did don doesn isn aren let
    just like make made need want used using able after before while between over under
    above below upon onto against please click now own very still both either
    http https www com org net html php
    """.split()
)

HOLD_MARKER = "[要確認"      # 未確定の訳の印。見本にしない(po_collect.py も同じ印を使う)
DEFAULT_SIZE = 30            # 1 チャンクの最大件数(理由は冒頭の docstring)
DEFAULT_MAX_CHARS = 3000     # 1 チャンクの msgid 合計文字数の上限
ID_PREVIEW_LEN = 30          # ドラフト JSON の "id"(msgid.strip() の先頭 N 文字)
REF_MSGSTR_LEN = 120         # ref 行の訳文をこの長さで切る
REF_MAX_MSGID_LEN = 300      # これより長い既存訳は見本にしない
REF_SIMILAR_K = 2            # 長文 1 件あたりに付ける類似見本の数
REF_LIMIT = 30               # 1 チャンクあたりの ref 行の上限
SHORT_WORDS = 3              # この語数以下は「短いラベル」扱い(完全一致の見本だけ付ける)
GLOSSARY_FULL_LIMIT = 150    # *-glossary.csv がこの行数以下なら丸ごと添付
KIND_ORDER = [
    "description header", "description paragraph", "description list item",
    "installation header", "installation paragraph", "installation list item",
    "faq header", "faq paragraph", "faq list item", "ui string", "changelog",
]


# ---------------------------------------------------------------------------
# .po のコメント・種別
# ---------------------------------------------------------------------------

FIELD_RE = re.compile(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+"(.*)"$')
CONT_RE = re.compile(r'^"(.*)"$')


def po_fields(text: str):
    """.po をフィールド単位で返す軽量パーサー。(行番号, 種別, 値) を順に yield する。

    種別は "blank" / "comment"(値は行そのもの)/ "msgctxt" / "msgid" / "msgid_plural" /
    "msgstr"(msgstr[N] も含む)。継続行(`"..."`)は直前のフィールドに連結し、行番号は
    フィールドの開始行(msgstr なら `msgstr` の行 = apply_translations の msgstr_lineno)。
    エスケープは apply_translations._unescape で解く(独自の表を持たない。表がずれると
    chunks/*.json の msgctxt と _find_untranslated の msgid が食い違い、CTX_MISMATCH の誤検出になる)。

    collect_comments()(対象 .po)と ref_msgctxts()(参照 .po)の両方がこれを使う。
    """
    cur: list | None = None   # [lineno, kind, [values]]

    def flush():
        nonlocal cur
        if cur is not None:
            yield cur[0], cur[1], "".join(cur[2])
            cur = None

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            yield from flush()
            yield lineno, "blank", ""
            continue
        m = CONT_RE.match(line)
        if m and cur is not None:
            cur[2].append(at._unescape(m.group(1)))
            continue
        yield from flush()
        if line.startswith("#"):
            yield lineno, "comment", line
            continue
        m = FIELD_RE.match(line)
        if m:
            kind = "msgstr" if m.group(1).startswith("msgstr") else m.group(1)
            cur = [lineno, kind, [at._unescape(m.group(2))]]
    yield from flush()


def collect_comments(po_path: Path) -> dict[int, dict]:
    """msgstr の行番号(1 始まり) -> コメント情報 のマップを作る。

    `#. Found in ...` / `#, gp-priority: low` / `#. translators: ...` / `#:` / `msgctxt` を拾う。

    キーを msgid ではなく msgstr の行番号にするのは、msgctxt 違いで同じ msgid が複数あるときに
    取り違えないため。msgid をキーにすると後のエントリーで上書きされ、location も msgctxt も
    別エントリーのものが付いてしまう。`apply_translations.py` の `_Entry.msgstr_linenos[0][0]`
    (単数形なら msgstr、複数形なら msgstr[0] の行)と突き合わせる。

    エントリーの区切りは空行に加えて、「msgstr を記録したあとに来るコメント・msgctxt・msgid」。
    空行で区切られていない .po では、次のエントリーのコメントが前のエントリーに混ざり、
    msgctxt を引き継いだうえ translators / location を失っていた。
    """
    info: dict[int, dict] = {}
    found = translators = location = ctxt = ""
    low = high = False
    recorded = False

    def reset() -> None:
        nonlocal found, translators, location, ctxt, low, high, recorded
        found = translators = location = ctxt = ""
        low = high = False
        recorded = False

    for lineno, kind, value in po_fields(po_path.read_text(encoding="utf-8")):
        if kind == "blank":
            reset()
            continue
        if recorded and kind in ("comment", "msgctxt", "msgid"):
            reset()          # 空行なしで次のエントリーが始まった
        if kind == "comment":
            # obsolete(#~)も fuzzy フラグもここを通す
            fm = FOUND_IN_RE.match(value)
            if fm:
                found = fm.group(1)
            tm = TRANSLATORS_RE.match(value)
            if tm:
                translators = tm.group(1)
            if value.startswith("#:") and not location:
                location = value[2:].strip()
            if "gp-priority: low" in value:
                low = True
            if "gp-priority: high" in value:
                high = True
        elif kind == "msgctxt":
            ctxt = value
        elif kind == "msgstr" and not recorded:
            # ブロック内で最初の msgstr 行(複数形なら msgstr[0])だけを記録する
            info[lineno] = {
                "found": found,
                "low": low,
                "high": high,
                "translators": translators,
                "location": location,
                "msgctxt": ctxt,
            }
            recorded = True
    return info


def kind_of(meta: dict) -> str:
    """エントリーの種別タグ。訳者が種別ごとに語尾を決めるための文字列を返す。"""
    if meta.get("low") and (not meta.get("found") or "changelog" in meta["found"]):
        return "changelog"
    kind = (meta.get("found") or "ui string").strip().rstrip(".").strip()
    return kind or "ui string"


def kind_rank(kind: str) -> int:
    return KIND_ORDER.index(kind) if kind in KIND_ORDER else len(KIND_ORDER)


# ---------------------------------------------------------------------------
# 分割
# ---------------------------------------------------------------------------

def portable_path(p: Path) -> str:
    """chunk-meta.json に書くパス。可能なら実行ディレクトリ相対にする。

    作業ディレクトリをコミットして別のチェックアウトで続きをする運用だと、絶対パスでは
    resolve_from() が引けず、rework チャンクが見本と Project Glossary を失う。実行ディレクトリ外の
    ファイルは相対にできないので絶対パスのまま残す(その環境でしか引けないことは変わらない)。
    """
    rp = p.resolve()
    try:
        return rp.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return rp.as_posix()


def unique_dir(parent: Path, base: str) -> Path:
    """同じ秒に 2 回走っても衝突しない退避先を返す(backup-… / backup-…-1 / …)。"""
    cand = parent / base
    i = 1
    while cand.exists():
        cand = parent / ("%s-%d" % (base, i))
        i += 1
    return cand


def split_chunks(entries: list[dict], size: int, max_chars: int) -> list[list[dict]]:
    """件数 size か msgid 合計 max_chars のどちらかに達したら次のチャンクへ。

    1 件で max_chars を超える長文は単独チャンクになる。
    """
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    cur_chars = 0
    for x in entries:
        n = len(x["msgid"]) + len(x.get("msgid_plural") or "")
        if cur and (len(cur) >= size or cur_chars + n > max_chars):
            chunks.append(cur)
            cur, cur_chars = [], 0
        cur.append(x)
        cur_chars += n
    if cur:
        chunks.append(cur)
    return chunks


# ---------------------------------------------------------------------------
# 既存訳の見本
# ---------------------------------------------------------------------------

def tokens(s: str) -> list[str]:
    """類似検索用の語。HTML タグと URL は除く(URL の語で無関係な文がヒットする)。"""
    s = URL_RE.sub(" ", TAG_RE.sub(" ", s))
    return [w.lower() for w in WORD_RE.findall(s) if w.lower() not in STOPWORDS]


def one_line(s: str) -> str:
    return s.replace("\n", "\\n")


def quoted(s: str) -> str:
    """ref / previous 行の引用符内に埋め込むための 1 行化。`\\` `"` 改行をエスケープする。

    原文に `Click "Install"` のような引用符があっても見本の境界が曖昧にならない。
    """
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


class RefIndex:
    """翻訳済みエントリー (msgid, msgstr, label, msgctxt) の検索。完全一致と単語共有の類似検索。

    msgctxt まで見るのは、同じ原文が文脈で訳し分けられているため。コア訳の `Name` は
    `msgctxt: "Name of link anchor (TinyMCE)"` が「名称」、msgctxt 無しが「名前」で、
    msgid だけで引くと文脈無しのエントリーに「名称」が正典の顔で付いてしまう。
    """

    def __init__(self, refs: list[tuple[str, str, str, str]]):
        self.refs = refs
        self.exact: dict[tuple[str, str], int] = {}   # (msgctxt, msgid) 完全一致
        self.loose: dict[tuple[str, str], int] = {}   # (msgctxt, 大小文字・前後空白を無視した msgid)
        self.any_exact: dict[str, int] = {}           # msgctxt を問わない msgid(最後の手段)
        self.any_loose: dict[str, int] = {}
        self.words: dict[str, set[int]] = collections.defaultdict(set)
        self.ntok: list[int] = []
        for i, (mid, _mstr, _label, ctxt) in enumerate(refs):
            low = mid.strip().lower()
            self.exact.setdefault((ctxt, mid), i)     # 先勝ち(same-plugin が先に来る)
            self.loose.setdefault((ctxt, low), i)
            self.any_exact.setdefault(mid, i)
            self.any_loose.setdefault(low, i)
            toks = set(tokens(mid))
            self.ntok.append(len(toks))
            for w in toks:
                self.words[w].add(i)

    def _as_ref(self, i: int, suffix: str) -> tuple[str, str, str]:
        mid, mstr, label, _ctxt = self.refs[i]
        return (mid, mstr, label + suffix)

    def exact_lookup(self, msgid: str, msgctxt: str = "") -> tuple[str, str, str] | None:
        """同じ msgctxt の完全一致を最優先し、無ければ近似・文脈違いの順にラベル付きで返す。

        ラベルの `~case` は大小文字・前後空白違い(`Add` に対する `add`)、`~ctxt` は msgctxt 違い。
        どちらも製品ラベルの正典としては扱わない(訳者への指示でも参考扱いにする)。
        """
        i = self.exact.get((msgctxt, msgid))
        if i is not None:
            return self._as_ref(i, "")
        low = msgid.strip().lower()
        i = self.loose.get((msgctxt, low))
        if i is not None:
            return self._as_ref(i, " ~case")
        i = self.any_exact.get(msgid)
        if i is not None:
            return self._as_ref(i, " ~ctxt")
        i = self.any_loose.get(low)
        if i is not None:
            return self._as_ref(i, " ~case ~ctxt")
        return None

    def similar_lookup(self, msgid: str, msgctxt: str = "", k: int = REF_SIMILAR_K) -> list[tuple[str, str, str]]:
        toks = set(tokens(msgid))
        if len(toks) < 2:
            return []
        cnt: collections.Counter = collections.Counter()
        for w in toks:
            for i in self.words.get(w, ()):
                cnt[i] += 1
        need = max(2, len(toks) // 3)  # 共有語が少なすぎるものはノイズ
        scored = []
        for i, c in cnt.items():
            if c < need:
                continue
            score = c / ((len(toks) ** 0.5) * (max(1, self.ntok[i]) ** 0.5))
            # 同点なら先に登録された(same-plugin 側の)ものを優先するため index の負値で並べ、
            # 取り出しは正の index で行う
            scored.append((score, -abs(self.ntok[i] - len(toks)), -i, i))
        scored.sort(reverse=True)
        return [self._as_ref(i, "" if self.refs[i][3] == msgctxt else " ~ctxt")
                for _s, _d, _neg, i in scored[:k]]


def ref_msgctxts(text: str) -> dict[int, str]:
    """参照 .po の「msgid 行の行番号 -> msgctxt」。

    validate_po.py は msgctxt を扱わない(PoEntry に項目が無い)ので、見本に文脈を添えるために
    ここで拾う。PoEntry.line は msgid 行の行番号なので、それをキーにすれば取り違えない。
    解析は collect_comments() と同じ po_fields() を使う(msgctxt の扱いを 2 か所に持たない)。
    """
    out: dict[int, str] = {}
    ctxt = ""
    for lineno, kind, value in po_fields(text):
        if kind == "blank":
            ctxt = ""
        elif kind == "msgctxt":
            ctxt = value
        elif kind == "msgid":
            out[lineno] = ctxt
            ctxt = ""
    return out


def load_refs(paths: list[Path], po_path: Path, vp, quiet: bool = False) -> list[tuple[str, str, str, str]]:
    """翻訳済み .po から見本を集める。対象と同じディレクトリのものは [same-plugin]。

    次の 2 つは見本にしない。訳者への指示で `[same-plugin]` を「製品固有ラベルの正典」と
    書いている以上、確定していない訳をこのラベルで配ると下訳に伝播する。

    - `*-fuzzy.po`: GlotPress の fuzzy エクスポートには `#, fuzzy` が付かない(実ファイルで確認済み)
      ので、`e.is_fuzzy` では落とせない。中身は原文に追いついていない訳で、msgid と msgstr を
      一語ずつ突き合わせて直す対象
    - `*-changesrequested.po`: 変更要求が付いて承認されていない訳。同じくステータス別エクスポート
    - `[要確認]` 付きの msgstr: 人間の判断待ちで確定していない
    """
    refs: list[tuple[str, str, str, str]] = []
    seen_files: set[Path] = set()
    for p in paths:
        rp = p.resolve()
        if rp in seen_files:
            continue
        seen_files.add(rp)
        if UNAPPROVED_PO_RE.search(p.name):
            if not quiet:
                print("ref: %s はステータス別エクスポート(fuzzy / changesrequested)なので見本にしません" % p)
            continue
        label = "same-plugin" if rp.parent == po_path.resolve().parent else p.name
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as ex:
            # *-translated.po は自動で拾うので、1 本壊れていても止まらず WARN で続ける
            # (UnicodeDecodeError は ValueError なので OSError では拾えない)
            print("WARN: --ref を読めません: %s (%s)" % (p, ex))
            continue
        ctxts = ref_msgctxts(text)
        n = 0
        held = 0
        for e in vp.parse_po(text):
            if e.is_fuzzy or not vp._is_translated(e):
                continue
            mstr = e.msgstr or (e.msgstr_plural[0] if e.msgstr_plural else "")
            if not mstr or len(e.msgid) > REF_MAX_MSGID_LEN:
                continue
            if HOLD_MARKER in mstr:      # 確定していない訳は見本にしない
                held += 1
                continue
            refs.append((e.msgid, mstr, label, ctxts.get(e.line, "")))
            n += 1
        if not quiet:
            print("ref: %s  %d 件 [%s]%s"
                  % (p, n, label, "(うち %d 件は [要確認] 付きなので除外)" % held if held else ""))
    return refs


def assign_refs(part: list[dict], index: RefIndex, limit: int = REF_LIMIT) -> dict[int, list]:
    """チャンク内の各エントリー(1 始まりの n)に見本を割り当てる。

    完全一致を先に全件付け、残り枠で長文に類似見本を付ける。
    """
    out: dict[int, list] = {}
    budget = limit
    for n, x in enumerate(part, 1):
        r = index.exact_lookup(x["msgid"], x.get("msgctxt", ""))
        if r is not None and budget > 0:
            out[n] = [r]
            budget -= 1
    for n, x in enumerate(part, 1):
        if budget <= 0:
            break
        if len(tokens(x["msgid"])) <= SHORT_WORDS:
            continue
        have = out.get(n, [])
        for r in index.similar_lookup(x["msgid"], x.get("msgctxt", "")):
            if budget <= 0:
                break
            if r in have:
                continue
            have.append(r)
            budget -= 1
        if have:
            out[n] = have
    return out


# ---------------------------------------------------------------------------
# Project Glossary(*-glossary.csv)
# ---------------------------------------------------------------------------

def read_glossaries(po_path: Path) -> list[tuple[str, list[list[str]]]]:
    """対象 .po と同じディレクトリの *-glossary.csv を読む。(ファイル名, 行) の列を返す。

    チャンクを書くたびに読み直すのではなく**破壊的操作の前に**一度だけ読む。あとで読むと、
    UTF-8 として不正な用語集で落ちたときに、前世代を退避したあとの半端な作業ディレクトリが残る。
    UnicodeDecodeError は ValueError なので OSError では拾えない(明示的に捕まえる)。
    """
    out: list[tuple[str, list[list[str]]]] = []
    for c in sorted(po_path.parent.glob("*-glossary.csv")):
        try:
            rows = [r for r in csv.reader(io.StringIO(c.read_text(encoding="utf-8-sig"))) if r]
        except (OSError, csv.Error, UnicodeDecodeError) as ex:
            print("WARN: glossary を読めません: %s (%s)" % (c, ex))
            continue
        if len(rows) >= 2:
            out.append((c.name, rows))
    return out


def glossary_section(glossaries: list[tuple[str, list[list[str]]]], msgids: list[str]) -> str:
    """read_glossaries() の結果を、チャンクに添付する Markdown にする。"""
    parts: list[str] = []
    for name, rows in glossaries:
        header, body = rows[0], rows[1:]
        note = "全 %d 語" % len(body)
        if len(body) > GLOSSARY_FULL_LIMIT:
            text = "\n".join(msgids).lower()
            body = [r for r in body if r[0].strip() and r[0].strip().lower() in text]
            note = "%d 語のうち、このチャンクの原文に出現する %d 語" % (len(rows) - 1, len(body))
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows([header] + body)
        parts.append(
            "## Project Glossary (%s)\n\n"
            "このプラグイン専用の用語集(GlotPress の Project Glossary、%s)。共通訳語リストより優先する。\n\n"
            "```csv\n%s```\n" % (name, note, buf.getvalue())
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# チャンクの書き出し(po_collect.py の rework 生成からも使う)
# ---------------------------------------------------------------------------

def format_entry(n: int, x: dict, refs: list, previous: str | None = None, reason: str | None = None) -> str:
    kind = x.get("kind") or kind_of(x)
    block = ["### %d [%s]" % (n, kind), "<<<MSGID", x["msgid"], ">>>MSGID"]
    if x.get("msgid_plural"):
        block += ["<<<MSGID_PLURAL", x["msgid_plural"], ">>>MSGID_PLURAL"]
    if x.get("msgctxt"):
        block.append("msgctxt: " + one_line(x["msgctxt"]))
    if x.get("translators"):
        block.append("translators: " + x["translators"])
    if x.get("location"):
        block.append("location: " + x["location"])
    for mid, mstr, label in refs:
        block.append('ref [%s]: "%s" → "%s"' % (label, quoted(mid), quoted(clip(mstr, REF_MSGSTR_LEN))))
    if previous is not None:
        block.append('previous: "%s"' % quoted(previous))
    if reason:
        block.append("reason: " + one_line(reason))
    return "\n".join(block) + "\n"


def write_chunk(
    chunkdir: Path,
    name: str,
    part: list[dict],
    refs_by_n: dict[int, list] | None = None,
    glossary_md: str = "",
    extra: dict[int, tuple[str, str]] | None = None,
) -> tuple[Path, Path, int]:
    """chunk md(サブエージェント用)と json(番号 → msgid。回収用)を書く。

    extra は rework 用: {n: (前回の訳文, 機械チェックの理由)}。
    """
    chunkdir.mkdir(parents=True, exist_ok=True)
    md_path = chunkdir / (name + ".md")
    json_path = chunkdir / (name + ".json")
    body: list[str] = []
    index: list[dict] = []
    for n, x in enumerate(part, 1):
        prev, reason = (extra or {}).get(n, (None, None))
        body.append(format_entry(n, x, (refs_by_n or {}).get(n, []), prev, reason))
        index.append(
            {
                "n": n,
                "msgid": x["msgid"],
                "msgid_plural": x.get("msgid_plural") or "",
                "msgctxt": x.get("msgctxt") or "",
                "location": x.get("location") or "",
                "kind": x.get("kind") or kind_of(x),
                # entries.json 内の位置。回収側がエントリーを一意に引くのに使う
                **({"e": x["e"]} if isinstance(x.get("e"), int) else {}),
                # rework チャンクのときだけ入る。回収側がどの NG 記録への answer か特定するのに使う
                **({"rework_of": x["rework_of"]} if x.get("rework_of") else {}),
            }
        )
    chars = sum(len(x["msgid"]) + len(x.get("msgid_plural") or "") for x in part)  # split_chunks と同じ数え方
    text = "# %s (%d entries, %d chars)\n\n" % (name, len(part), chars) + "\n".join(body)
    if glossary_md:
        text += "\n" + glossary_md
    md_path.write_text(text, encoding="utf-8")
    json_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return md_path, json_path, chars


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("po_path")
    ap.add_argument("--outdir", required=True, help="中間成果物の出力先(例: .work/plugin-x)")
    ap.add_argument("--size", type=int, default=DEFAULT_SIZE, help="1チャンクあたりの最大件数(既定: %d)" % DEFAULT_SIZE)
    ap.add_argument(
        "--max-chars", type=int, default=DEFAULT_MAX_CHARS,
        help="1チャンクあたりの msgid 合計文字数の上限(既定: %d)" % DEFAULT_MAX_CHARS,
    )
    ap.add_argument("--skip-low", action="store_true", help="gp-priority: low のエントリーを除外する")
    ap.add_argument(
        "--ref", action="append", default=[], metavar="PO",
        help="既存訳の見本を引く翻訳済み .po(複数可)。同じディレクトリの *-translated.po と対象 .po 自身は自動で拾う",
    )
    ap.add_argument("--no-ref", action="store_true", help="見本を付けない")
    ap.add_argument("--ref-limit", type=int, default=REF_LIMIT, help="1チャンクあたりの ref 行の上限(既定: %d)" % REF_LIMIT)
    ap.add_argument("--no-group-by-kind", action="store_true", help="種別でまとめずに .po の出現順のまま切る")
    ap.add_argument(
        "--force", action="store_true",
        help="drafts/ にドラフトがあっても作り直す(drafts/・chunks/ と回収・適用結果は backup-<時刻>/ に退避)",
    )
    args = ap.parse_args()

    po_path = Path(args.po_path)
    if not po_path.is_file():
        sys.exit(".po ファイルが見つかりません: %s" % po_path)

    # 世代混在の防止: チャンクを作り直すと番号と msgid の対応が変わり、古いドラフトが別の msgid に付く。
    # ドラフトが残っている作業ディレクトリでは止まる(--force で退避してから作り直す)
    outdir = Path(args.outdir)
    chunkdir = outdir / "chunks"
    draftdir = outdir / "drafts"
    existing_drafts = sorted(draftdir.glob("translations_*.json")) if draftdir.is_dir() else []
    # 退避の判定は consumed/ も含める。直下のドラフトが全部 consumed に移った作業ディレクトリで
    # drafts/ を置き去りにすると、po_collect.py の draft_submitted() が consumed/ を走査して
    # 旧世代の translations_rework_00.json を見つけ、新世代の rework_00 を「投入済み」と誤判定する
    drafts_present = draftdir.is_dir() and any(q.is_file() for q in draftdir.rglob("*"))
    if existing_drafts and not args.force:
        sys.exit(
            "%s に下訳ドラフトが %d 件あります。チャンクを作り直すと番号と msgid の対応が変わり、"
            "古いドラフトが別の msgid に付きます。--force で drafts/ を退避して作り直すか、別の --outdir を使ってください。"
            % (draftdir, len(existing_drafts))
        )

    # 退避より先に、失敗しうる読み込みを全部済ませる。.po の解析で落ちたあとに
    # 前世代の chunks/ が無くなっていると、番号と msgid の対応表を失って途中から再開できない
    untranslated = at._find_untranslated(at._read_lines(po_path))
    comments = collect_comments(po_path)

    entries = []
    for e in untranslated:
        # msgctxt 違いで同じ msgid が複数あっても取り違えないよう、msgstr の行番号でコメントを引く
        meta = comments.get(e.msgstr_linenos[0][0], {}) if e.msgstr_linenos else {}
        x = {
            "msgid": e.msgid,                 # 実改行・生の " を含む形(apply に渡すのはこちら)
            "msgid_plural": e.msgid_plural,
            "msgctxt": meta.get("msgctxt", ""),
            "found": meta.get("found", ""),
            "low": meta.get("low", False),
            "high": meta.get("high", False),
            "translators": meta.get("translators", ""),
            "location": meta.get("location", e.location or ""),
        }
        x["kind"] = kind_of(x)
        entries.append(x)

    if args.skip_low:
        entries = [x for x in entries if not x["low"]]
    # entries.json 内の位置。チャンク対応表がこれを持つことで、回収側は msgid ではなく
    # エントリーそのもの(msgctxt / kind / translators / msgid_plural)を引ける
    for i, x in enumerate(entries):
        x["e"] = i

    # 既存訳の見本(参照 .po の読み込みで落ちうるので、これも退避より前に済ませる)
    index: RefIndex | None = None
    ref_paths: list[Path] = []
    if not args.no_ref:
        ref_paths = [po_path] + sorted(po_path.parent.glob("*-translated.po")) + [Path(p) for p in args.ref]
        refs = load_refs(ref_paths, po_path, vp)
        index = RefIndex(refs) if refs else None
        if index is None:
            print("ref: 翻訳済みエントリーが見つからないので見本は付きません(--ref でコア訳などを指定できる)")

    # Project Glossary も退避より前に読み切る(不正なエンコーディングで落ちても前世代を残す)
    glossaries = read_glossaries(po_path)

    # ここから破壊的操作。前世代の成果物(drafts/・chunks/ と回収・適用の結果)は backup-<時刻>/ に
    # まとめて退避する。chunks/ を削除ではなく退避にするのは、以降の書き出しで落ちても前世代の
    # 番号 → msgid 対応表が残るようにするため。
    # blocked.json も対象: po_apply_loop.py が読んで除外し続けるので、残すと新しい pool で再試行できない
    # entries.json / chunk-meta.json / wordfreq.txt も同じ世代の成果物。退避しないと、backup に
    # 入れた chunks/chunk_NN.json の e(entries.json 内の位置)が指す先を失い、前世代を復元できない
    generation_files = ("entries.json", "wordfreq.txt", "chunk-meta.json",
                        "pool.json", "hold.json", "manual.json", "missing.json", "rework.json",
                        "blocked.json", "collect-report.txt")
    stale_chunks = [p for p in chunkdir.iterdir() if p.is_file()] if chunkdir.is_dir() else []
    to_move = (
        ([draftdir] if drafts_present else [])
        + ([chunkdir] if stale_chunks else [])
        + [outdir / n for n in generation_files if (outdir / n).is_file()]
    )
    if to_move:
        labels = [p.name + ("/" if p.is_dir() else "") for p in to_move]   # rename 前に作る
        outdir.mkdir(parents=True, exist_ok=True)
        bak = unique_dir(outdir, "backup-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
        bak.mkdir()
        for p in to_move:
            p.rename(bak / p.name)
        print("%s を %s/ に退避しました" % (", ".join(labels), bak.name))

    chunkdir.mkdir(parents=True, exist_ok=True)

    (outdir / "entries.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    words: collections.Counter = collections.Counter()
    for x in entries:
        for w in re.findall(r"[A-Za-z][A-Za-z0-9_\-]+", x["msgid"]):
            words[w.lower()] += 1
    (outdir / "wordfreq.txt").write_text(
        "\n".join("%s\t%d" % (w, n) for w, n in words.most_common(150)), encoding="utf-8"
    )

    # po_collect.py が rework チャンクに同じ見本・Project Glossary を付けるための記録
    (outdir / "chunk-meta.json").write_text(
        json.dumps(
            {
                # 別のチェックアウトでも引けるよう、OS を問わない区切り かつ 可能なら cwd 相対で書く
                "po_path": portable_path(po_path),
                "refs": [portable_path(p) for p in ref_paths],
                "no_ref": bool(args.no_ref),
                "ref_limit": args.ref_limit,
                "size": args.size,
                "max_chars": args.max_chars,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    ordered = entries if args.no_group_by_kind else sorted(entries, key=lambda x: (kind_rank(x["kind"]), x["kind"]))
    parts = split_chunks(ordered, args.size, args.max_chars)

    total_refs = 0
    for i, part in enumerate(parts):
        refs_by_n = assign_refs(part, index, args.ref_limit) if index else {}
        texts = [x["msgid"] for x in part] + [x.get("msgid_plural") or "" for x in part]  # 用語は複数形にだけ出ることもある
        glossary_md = glossary_section(glossaries, texts)
        md_path, _json_path, chars = write_chunk(chunkdir, "chunk_%02d" % i, part, refs_by_n, glossary_md)
        nref = sum(len(v) for v in refs_by_n.values())
        total_refs += nref
        kinds = collections.Counter(x["kind"] for x in part)
        print(
            "%s  %d 件 / %d 字 / ref %d 件 / %s"
            % (md_path, len(part), chars, nref, ", ".join("%s %d" % kv for kv in kinds.most_common(3)))
        )

    counts = collections.Counter(x["kind"] for x in entries)
    print("\n未翻訳 %d 件 / チャンク %d 本(--size %d / --max-chars %d)/ ref 合計 %d 件"
          % (len(entries), len(parts), args.size, args.max_chars, total_refs))
    for k, v in counts.most_common():
        print("  %-28s %d" % (k, v))
    print("\n次: 訳語リストを作って %s/chunks/chunk_*.md をサブエージェントに配る"
          "(1 つの応答に全チャンク分の Agent 呼び出しをまとめる)" % outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
