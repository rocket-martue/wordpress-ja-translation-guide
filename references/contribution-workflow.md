# 一括翻訳ワークフローとスクリプトの使い方

[Polyglotsハンドブック / translate.wordpress.org (GlotPress)](https://make.wordpress.org/polyglots/handbook/translating/glotpress-translate-wordpress-org/)の「Importing External Files」に基づく。SKILL.mdの要点を補足する詳細資料。

## 目次

- 1. 翻訳作業の共通フロー / 1.1. apply_translations.py の使い方 / 1.2. validate_po.py の使い方 / 1.3. fix_spacing.py の使い方 / 1.4. 分担パイプライン(po_chunk.py / po_collect.py / po_apply_loop.py)
- 2. 自動化してよい範囲 / してはいけない範囲

## 1. 翻訳作業の共通フロー

1. **差分検出**: 対象プロジェクトの未翻訳・fuzzy文字列を抽出する(SVN上の最新`.pot`との比較、またはtranslate.wordpress.org上のUntranslatedフィルタを利用)
2. **既存訳の取得**: Exportリンクから、すでにCurrentになっている訳を取得し、表記統一の参考にする
3. **下訳生成**: このSkillのルールに従って訳文ドラフトを生成する
4. **`.po`ファイルへの書き込み**: 生の`.po`構文に`str_replace`で直接書き込もうとしない。`scripts/apply_translations.py`経由でバッチ書き込みする(詳細は「1.1」を参照)
5. **自動バリデーション**: プレースホルダー一致・ブランド名の未翻訳・表記ルール違反を機械的にチェックする(`scripts/validate_po.py` を使う)。**バッチ適用のたびに実行する**。ERROR が出た時点で原因バッチが特定でき、修正範囲が1バッチ分に収まる(「1.1」の運用ルールを参照)
6. **人間レビュー**: ユーザー本人が目視で確認・修正する(ここは省略不可)
7. **Import Translationsでアップロード**: `.po`をアップロードする(ステータスの選択肢は翻訳ページの表示に従う)

文字列の数が少ない場合は、Import Translationsを使わず、画面上の「Suggest」ボタンで1件ずつ提案する従来の方法でもよい。どちらの手段を使うかはユーザーの裁量に委ねる。

### 1.1. apply_translations.py の使い方(ステップ4の詳細)

> **スクリプトの場所**: このスクリプトは Skill の一部として配布されており、**SKILL.md と同じディレクトリ配下の `scripts/` にある**。
> 翻訳対象の WordPress プラグイン/テーマのディレクトリには存在しないので、Skill の場所からのフルパスで指定する。
> **動作要件: Python 3.10 以上**。
>
> ```bash
> # Claude Code にインストール済みの場合(標準の配置)
> python ~/.claude/skills/wordpress-ja-translation-guide/scripts/apply_translations.py path/to/ja.po --list
>
> # リポジトリをクローンして使う場合
> python /path/to/wordpress-ja-translation-guide/scripts/apply_translations.py path/to/ja.po --list
> ```
>
> 「このリポジトリにスクリプトは無い」と思っても、まず上記のSkillインストール先を確認すること。

生の`.po`構文に`str_replace`で書き込もうとすると、`msgstr ""`が大量に重複するため一意に特定できず、置換失敗やリトライが発生する。`scripts/apply_translations.py`経由でバッチ書き込みすることで、このコストを完全に除去できる。

```bash
# 未翻訳エントリーをインデックス付きで一覧表示(複数形エントリーは (plural) 付きで表示)
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/apply_translations.py path/to/ja.po --list
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/apply_translations.py path/to/ja.po --list --start 0 --count 20

# バッチ書き込み(JSON ファイルまたはインライン JSON)
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/apply_translations.py path/to/ja.po translations.json
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/apply_translations.py path/to/ja.po '{"0": "訳文A", "1": "訳文B"}'

# リポジトリをクローンして使う場合
python /path/to/wordpress-ja-translation-guide/scripts/apply_translations.py path/to/ja.po --list
```

JSON の値は2形式あり、**msgid 照合付きのオブジェクト形式を推奨**する:

```jsonc
// 推奨: インデックス位置の msgid と照合し、ズレていれば msgid で書き込み先を
// 自動的に再解決する(一意に決まらない場合はエラーで停止し、誤爆しない)
{"0": {"msgid": "Save changes", "msgstr": "変更を保存"}}

// 旧形式: 照合なし。インデックスがズレていても検出できないため非推奨
{"0": "変更を保存"}
```

書き込み時にはプレースホルダー照合も行われ、msgid(複数形は `msgid_plural`)と訳文でプレースホルダーの数・種類が一致しないエントリーは書き込まれずにエラー報告される。

複数形(`msgid_plural`)エントリーは、書き込むと存在するすべての `msgstr[N]` 行に同じ訳文が入る(日本語は単数/複数を区別しないため)。

出力例:

```
✅ 20件書き込みました。進捗: 20/190 (10%), 残り 170件
次: python ~/.claude/skills/wordpress-ja-translation-guide/scripts/validate_po.py path/to/ja.po で検証してから次のバッチへ
```

**運用ルール(バッチループの標準形)**:

1. **バッチを作る直前に必ず `--list` を取り直す**。インデックスは呼び出しごとに「その時点で未翻訳のエントリー」へ 0 から振り直されるため、書き込むたびにズレる。複数バッチ分の JSON を事前にまとめて作らない
2. 訳文を生成し、msgid 照合付きのオブジェクト形式 JSON を作り、スクリプトを呼び出してファイルに書き込む。書き込めたかどうかはスクリプトの出力で判断する
3. スクリプトが返す進捗と WARN / ERROR を確認する
4. **バッチ適用のたびに `validate_po.py` を実行し、ERROR が出たら次のバッチに進む前に修正する**(apply_translations.py と同じ場所にある。フルパスで呼ぶ)
5. 未翻訳が無くなるまで 1 に戻る

スクリプトが利用できない環境では、1件ずつ逐次`str_replace`で書き込む。

### 1.2. validate_po.py の使い方

> **注**: `validate_po.py` も `apply_translations.py` と同じ場所(SKILL.md と同じディレクトリ配下の `scripts/`)にあります。翻訳対象プロジェクトのディレクトリには存在しないため、Skill の場所からのフルパスで呼び出してください。
> 完了確認・整合性チェックのために自前のチェックスクリプトをその場で書かず、**必ずこのスクリプトを使うこと**。
> 即興のチェックは表記ルール違反を拾えないうえ、チェック自体のバグでプレースホルダー欠落を見逃した実例がある。

```bash
# Claude Code (Skillインストール先)
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/validate_po.py path/to/ja.po
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/validate_po.py "path/to/languages/*.po"
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/validate_po.py --errors-only path/to/ja.po  # ERROR のみ表示
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/validate_po.py --ignore NUM_SPACING_TOKEN path/to/ja.po  # 特定ルールを除外

# リポジトリをクローンして使う場合
python /path/to/wordpress-ja-translation-guide/scripts/validate_po.py path/to/ja.po
```

チェック項目と重大度:

| ルールID | 重大度 | 内容 |
|----------|--------|------|
| `PH_MISMATCH` | ERROR | プレースホルダーの数・種類の不一致 |
| `BRAND_TRANSLITERATION` | ERROR | 「WordPress」の音訳(ワードプレス等) |
| `FULLWIDTH_DIGIT` | WARN | 全角数字(０-９) |
| `FULLWIDTH_ALPHA` | WARN | 全角英字(Ａ-Ｚ、ａ-ｚ) |
| `FULLWIDTH_PUNCT` | WARN | 全角感嘆符・疑問符(！？) |
| `NUM_SPACING` | WARN | 数字・数値プレースホルダー(`%d`等)直後の不要なスペース(`%s`は対象外、notation-rules.md 6-1参照) |
| `NUM_SPACING_TOKEN` | WARN | バージョン番号・識別子トークン直後のスペース(例: `PHP 8.1 以上`、`ISO8601 の日時`。公式に規定がない係争点。notation-rules.md 1-9 の補足参照) |
| `ALPHA_SPACING` | WARN | 半角英字と全角文字の間に半角スペースがない(例: `担当者のFacebook`。notation-rules.md 1-4参照) |
| `PUNCT_SPACING` | WARN | 日本語直後の ! / ? の前にスペースがない |
| `ELLIPSIS` | WARN | 省略記号にピリオド3個を使っている(`読み込み中...` → `読み込み中…`。公式規定外の #ja-docs 合意。notation-rules.md 7 参照) |
| `WRITING_CONVENTION` | WARN | 「下さい」「全て」「既に」等の表記ゆれ |

ERROR が残った状態での Import は行わない。WARN は目視判断のうえ修正する。

`--errors-only` と `--ignore` は用途が違う:

- `--errors-only` … 表示だけを ERROR に絞る。**終了コードには影響しない**(WARN しか残っていなくても 1 で終わる)
- `--ignore RULE` … 指定したルールを表示・件数サマリー・**終了コードのすべて**から除外する。プロジェクトとして方針が決まっているルール(典型は `NUM_SPACING_TOKEN`)を黙らせ、残りの WARN に集中するために使う。複数指定・カンマ区切り可

末尾には合計に続けてルールID別の内訳が出るので、数千エントリー規模でも「どのルールが何件か」を先に把握してから仕分けに入れる。

### 1.3. fix_spacing.py の使い方

`ALPHA_SPACING`(半角英字と全角文字の間の必須スペース)は数が多くなりやすいため、機械挿入するスクリプトを用意している。`validate_po.py` と同じ検出ロジックを使う。

```bash
# dry-run(既定): 挿入候補を表示するだけでファイルは変更しない
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/fix_spacing.py path/to/ja.po

# 実際に書き換える
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/fix_spacing.py path/to/ja.po --apply
```

出力例:

```
path/to/ja.po:17  (5 箇所)
  - 拡張機能のAPIキーを取得するためには、MainWPのAPIキーが必要です。
  + 拡張機能の API キーを取得するためには、MainWP の API キーが必要です。
```

運用手順は **dry-run → 差分を目視 → `--apply` → `validate_po.py` で再検証 → 人間レビュー**。いきなり `--apply` しない。

- 挿入するのは半角スペースだけで、訳語・文体の正しさは一切保証しない(適用後の人間レビューを省略しない)
- `msgid` / コメント / obsolete(`#~`)/ ヘッダーエントリー(`Last-Translator` など)には触れない
- 書き換え後に「スペース以外の内容が不変」「プレースホルダーの数・種類が不変」「HTMLタグ数が不変」を検証し、1つでも破れた箇所は書き換えずに `[ERROR]` 報告する
- 終了コード: 0 = 対象なし / 1 = 対象あり(dry-run)・書き換え実施(`--apply`)/ 2 = エラー

### 1.4. 分担パイプライン(po_chunk.py / po_collect.py / po_apply_loop.py)

未翻訳が数百件を超えると、下訳を複数の訳者(人でも AI でも)に分担することになる。1.1 のバッチループを「準備(未翻訳の抽出と分割)」「回収(下訳の機械チェックとプール化)」「適用(`--list` → apply → validate の直列ループ)」に切り出したのが、この 3 本のスクリプト。場所は `apply_translations.py` と同じ `scripts/`(同じディレクトリのものを import・実行するので、3 本だけを別の場所へコピーしない)。

| スクリプト | 役割 | 終了コード |
|---|---|---|
| `po_chunk.py` | 未翻訳エントリーの抽出(`apply_translations.py --list` と同じ判定)、種別分類(readme の header / paragraph / list item、changelog、UI 文字列)、30 件または msgid 合計 3,000 字ごとの分割、既存訳の見本(`ref:` 行)と Project Glossary(`*-glossary.csv`)の添付、番号 → msgid の対応表 | 0 = 成功 |
| `po_collect.py` | 訳者が書いた下訳 JSON の回収、ドラフト段階の機械チェック(下表)、`pool.json`(適用対象)/ `hold.json`(`[要確認]` 付き)/ `manual.json`(msgctxt 違いで同じ msgid が複数あるもの)/ `missing.json`(未回収)/ `rework.json`(機械チェック NG)への振り分け、rework 用チャンクの生成 | 0 = 問題なし / 2 = 未回収あり / 3 = rework あり / 4 = ドラフトの形式エラー |
| `po_apply_loop.py` | `pool.json` を 20 件ずつ、未翻訳一覧の取り直し(`--list` と同じ判定)→ msgid 照合付き JSON → apply → `validate_po.py --errors-only` で直列適用。msgctxt 違いで同じ msgid が複数あるエントリーとプールに訳の無いエントリーは飛ばして先へ進む。書き込めなかったエントリーは `blocked.json` に落として次バッチから外す | 0 = 完了 / 2 = `.po` が読めない・apply が 1 件も書けない・validate が ERROR で中断 |

```bash
# ① 準備: 未翻訳を抽出してチャンクに分割(--ref は見本を引く翻訳済み .po。コア訳などを渡す)
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/po_chunk.py path/to/ja.po --outdir .work/plugin-x --ref path/to/core-ja-translated.po
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/po_chunk.py path/to/ja.po --outdir .work/plugin-x --skip-low   # gp-priority: low(changelog 等)を除外

# ② 回収: 訳者が .work/plugin-x/drafts/translations_NN.json に書いた下訳を検証してプールにまとめる
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/po_collect.py --outdir .work/plugin-x

# ③ 適用: プールを .po に直列で流し込む(.po への書き込みは apply_translations.py 経由)
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/po_apply_loop.py path/to/ja.po --outdir .work/plugin-x
```

訳者に渡すのは `chunks/chunk_NN.md`(1 エントリーが `### N [種別]` と `<<<MSGID` … `>>>MSGID` の形。`translators:` / `location:` / `ref:` 行と、末尾に Project Glossary が付く)と、プロジェクト共通の訳語リスト(`glossary-template.md` の型)だけ。訳者が Claude Code のサブエージェントなら、配り方・回収・仕上げの手順は `parallel-translation-workflow.md` にある。**訳者に `.po` を触らせず、`apply_translations.py` のインデックスも渡さない**(インデックスは適用のたびに振り直されるので、生成と適用の間に時間差があると必ずズレる。チャンク内の番号 `N` は別物で、`po_collect.py` が `chunks/chunk_NN.json` で msgid に戻す)。

訳者が書く下訳 JSON は、指定されたパスへ次の配列だけ:

```json
[
  {"n": 1, "id": "Save changes", "msgstr": "変更を保存"},
  {"n": 3, "id": "Active", "ctx": "Name for the CSS pseudo-class selector", "msgstr": "アクティブ"}
]
```

`n` はチャンクの `### N` の番号、`id` は msgid の先頭 30 文字(番号ズレ検出用)、`ctx` はそのエントリーに `msgctxt:` 行があるときだけ。訳せなかったものも `[要確認: …]` 付きで出す(欠落させない。欠落は `missing.json` に残り exit 2 になる)。

`po_collect.py` のドラフト段階の機械チェック(`validate_po.py` が apply 後にしか見ないものを、`.po` に入る前に弾く):

| チェック | 内容 | 根拠 |
|---|---|---|
| `PH_MISMATCH` | プレースホルダーの数・種類(`validate_po.py` と同じ判定。番号付きへの並べ替えは通る) | SKILL.md「プレースホルダー」 |
| `PH_NUM_SPACE` | `translators:` コメントから数値に置き換わると分かる `%s` 系プレースホルダーと日本語の間の半角スペース(`%2$s件中 %1$s件` → `%2$s件中%1$s件`)。`validate_po.py` の `NUM_SPACING` は `%d` 系しか見ない | notation-rules.md 6-1 |
| `FULLWIDTH` | 全角記号 `！？（）：；` | notation-rules.md 1-2 |
| `TERMINAL` | 終端記号は原文にあるものだけを写す。原文の `.` は「。」、`!` `?` は半角のまま直前に半角スペース、`:` は半角のまま、原文に無ければ付けない | word-choice-rules.md 2-8、notation-rules.md 1-2 / 1-4 |
| `HTML_TAG` | HTML タグの種類・数・入れ子(翻訳対象の属性 `title` `alt` などは除いて比較) | SKILL.md「翻訳しないもの」 |
| `ID_MISMATCH` / `CTX_MISMATCH` | `id` / `ctx` が対応表の msgid / msgctxt と食い違う(番号ズレ) | — |

NG は `rework.json` に落ちて `chunks/rework_NN.md`(前回の下訳と NG の理由付き)が生成されるので、通常のチャンクと同じ手順で訳者に戻し、`po_collect.py` を再実行する。`hold.json` / `manual.json` / `blocked.json` に残ったものは人間が個別に判断する(`manual.json` は `apply_translations.py --list` の個別インデックスで 1 件ずつ適用する)。

運用上の注意:

- `drafts/` にドラフトが残っている作業ディレクトリでは `po_chunk.py` は止まる(作り直すと番号と msgid の対応が変わり、古いドラフトが別の msgid に付く)。作り直すなら `--force`(前世代を `backup-<時刻>/` に退避)か別の `--outdir`
- 原文に `100% free` のような裸の `%` があると `% f` がプレースホルダーとして誤検出され、構造上書き込めない。`pool.json` には残るが apply で `blocked.json` に落ちるので、訳案を添えて人間に渡す
- 3 本とも `.po` への書き込みは `apply_translations.py` をサブプロセスで呼ぶだけで、自前では書き戻さない
- `po_apply_loop.py` が完走しても「人間レビュー → 手動 Import」は残る(2 節)。スクリプトの末尾もそう案内する

## 2. 自動化してよい範囲 / してはいけない範囲

- 自動化してよい: 差分検出、下訳生成、バリデーションスクリプトの実行、アップロード用`.po`ファイルの組み立て(1.4 の分担パイプラインもここに含まれる)
- 自動化してはいけない: 人間レビューの省略、Import操作そのものを無人で実行すること(ファイルの内容を毎回ユーザー本人が確認した上で、手動でアップロードする)
- **Importでどのステータスを選べる場合であっても**、人間レビューを経ずに即時反映してはいけない。「どうせ承認待ちだから精査しなくていい」という考え方もしない。未精査の機械翻訳を大量に投入すると、承認者の負担になり、提案が一括拒否される原因になる(ハンドブックに明記された機械翻訳の精査義務)
