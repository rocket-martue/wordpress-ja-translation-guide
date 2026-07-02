# PTE権限の有無で変わる作業フロー

[Polyglotsハンドブック / translate.wordpress.org (GlotPress)](https://make.wordpress.org/polyglots/handbook/translating/glotpress-translate-wordpress-org/)の「User Roles and Permissions」「Importing External Files」、および[日本語翻訳ハンドブック](https://ja.wordpress.org/team/handbook/translation/)の「承認者について」に基づく。SKILL.mdの要点を補足する詳細資料。

## 目次

- 1. 承認者の種類(GTE / PTE)
- 2. Import Translations機能の権限差(重要な訂正)
- 3. 共通の作業フロー(PTE有無に関わらず一括処理が可能) / 3.5. apply_translations.py の使い方
- 4. 自動化してよい範囲 / してはいけない範囲
- 5. PTE権限のリクエスト

## 1. 承認者の種類(GTE / PTE)

translate.wordpress.org上のユーザーロールは3種類: Guest(未ログイン)、Contributor(ログイン済み一般ユーザー)、Translation Editor。

Translation Editorはさらに2種類に分かれる。

- **GTE (General/Global Translation Editor)**: コア、およびすべてのプラグインとテーマを承認可能。コア以外のプロジェクトへのインポートもCurrentとして反映できる
- **PTE (Project Translation Editor)**: 自分が権限を持つ個別のプラグイン・テーマのみ承認可能

PTE権限はプロジェクトごとに付与されるため、「あるプラグインではPTEだが、別のプラグインでは権限なし」という状態もふつうにあり得る。

**作業前に必ず確認すること**: 翻訳作業の依頼を受けたら、対象プロジェクトについてユーザーがPTE権限を持っているかどうかを確認する(すでに会話内で明言されていれば再確認は不要)。確認方法の例:

- 自分の[WordPress.orgプロフィールページ](https://profiles.wordpress.org/)の「Translations」セクションに、PTEを持つプロジェクト一覧が表示される
- 対象プロジェクトの翻訳ページでImport Translationsを開いた際、アップロード時のステータス選択肢に「Current」が出るかどうかでも判断できる(出ればPTE/GTE、出なければ一般コントリビューター)

## 2. Import Translations機能の権限差(重要な訂正)

**「PTEでなければSuggestで一件ずつ提案するしかない」というのは誤り。** 公式ハンドブックには次のように明記されている:

> Any WordPress.org user can import plugin and theme translation files using the "Import Translations" feature of GlotPress (Note: only GTEs can import into projects other than plugins and themes).
>
> GTEs and PTEs can upload translations as "Current" or "Waiting" status. Others can only upload as "Waiting".

つまりプラグイン・テーマの翻訳ファイルインポート自体は、**ログイン済みのWordPress.orgユーザーなら誰でも使える**。PTE権限の有無で変わるのは、反映される**ステータス**だけ。

| ユーザーの立場 | Importでアップロードできるステータス | 備考 |
|---|---|---|
| 対象プロジェクトのPTE | Current または Waiting | Currentを選べば即時反映 |
| GTE | Current または Waiting(コア・他種別プロジェクトも対象) | 全プロジェクトに反映可能 |
| 一般コントリビューター(PTE/GTEでない) | Waiting のみ | Suggestと同じ「承認待ち」状態になるが、1件ずつでなく**一括で**アップロードできる |

一般コントリビューターであっても、`.po`/`.mo`形式のファイルをImport Translations機能で一括アップロードできる。これは「Suggest」ボタンで1文字列ずつ提案するのと比べて効率的な手段であり、Skillによる一括下訳生成のワークフローは**PTEの有無に関わらず成立する**。

なお、インポート時に「未翻訳の文字列」と「既存訳と異なる文字列」が保存され、translate.wordpress.org側に存在しない原文を含むファイルは無視される。

## 3. 共通の作業フロー(PTE有無に関わらず一括処理が可能)

1. **差分検出**: 対象プロジェクトの未翻訳・fuzzy文字列を抽出する(SVN上の最新`.pot`との比較、またはtranslate.wordpress.org上のUntranslatedフィルタを利用)
2. **既存訳の取得**: Exportリンクから、すでにCurrentになっている訳を取得し、表記統一の参考にする
3. **下訳生成**: このSkillのルールに従って訳文ドラフトを生成する
4. **`.po`ファイルへの書き込み**: 生の`.po`構文に`str_replace`で直接書き込もうとしない。`scripts/apply_translations.py`経由でバッチ書き込みする(詳細は「3.5」を参照)
5. **自動バリデーション**: プレースホルダー一致・ブランド名の未翻訳・表記ルール違反を機械的にチェックする(`scripts/validate_po.py` を使う)。全件完了後にまとめて1回ではなく、**バッチ適用のたびに実行する**(「3.5」の運用ルールを参照)
6. **人間レビュー**: ユーザー本人が目視で確認・修正する(ここは省略不可)
7. **Import Translationsでアップロード**: `.po`をアップロードする
   - PTE/GTEの場合: Current(即時反映)かWaiting(承認待ち)かを選べる
   - 一般コントリビューターの場合: Waitingとしてアップロードされる(GTE/PTEの承認を待つ)

文字列の数が少ない場合は、Import Translationsを使わず、画面上の「Suggest」ボタンで1件ずつ提案する従来の方法でもよい。どちらの手段を使うかはユーザーの裁量に委ねる。

### 3.5. apply_translations.py の使い方（ステップ4の詳細）

> **スクリプトの場所**: このスクリプトは Skill の一部として配布されており、**Skill をインストールした時点で利用可能**。
> 翻訳対象の WordPress プラグイン/テーマのディレクトリには存在しないので、フルパスで指定する。
>
> ```bash
> # Claude Code にインストール済みの場合(標準の配置)
> python ~/.claude/skills/wordpress-ja-translation-guide/scripts/apply_translations.py path/to/ja.po --list
>
> # リポジトリをクローンして使う場合
> python /path/to/wordpress-ja-translation-guide/scripts/apply_translations.py path/to/ja.po --list
> ```
>
> 「このリポジトリにスクリプトは無い」と思っても、まず上記のSkillインストール先を確認すること(自前の代替スクリプトを書かない)。

生の`.po`構文に`str_replace`で書き込もうとすると、`msgstr ""`が大量に重複するため一意に特定できず、置換失敗やリトライが発生する。`scripts/apply_translations.py`経由でバッチ書き込みすることで、このコストを完全に除去できる。

```bash
# 未翻訳エントリーをインデックス付きで一覧表示(複数形エントリーは (plural) 付きで表示)
python scripts/apply_translations.py path/to/ja.po --list
python scripts/apply_translations.py path/to/ja.po --list --start 0 --count 20

# バッチ書き込み(JSON ファイルまたはインライン JSON)
python scripts/apply_translations.py path/to/ja.po translations.json
python scripts/apply_translations.py path/to/ja.po '{"0": "訳文A", "1": "訳文B"}'
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
次: python scripts/validate_po.py path/to/ja.po で検証してから次のバッチへ
```

**運用ルール(バッチループの標準形)**:

1. **バッチを作る直前に必ず `--list` を取り直す**。インデックスは呼び出しごとに「その時点で未翻訳のエントリー」へ 0 から振り直されるため、書き込むたびにズレる。複数バッチ分の JSON を事前にまとめて作らない
2. 訳文を生成し、msgid 照合付きのオブジェクト形式 JSON を作る。ナレーションで「書いた」ことにしない——必ずスクリプトを呼び出してファイルに書き込む
3. スクリプトが返す進捗と WARN / ERROR を確認する
4. **バッチ適用のたびに `scripts/validate_po.py` を実行し、ERROR が出たら次のバッチに進む前に修正する**(バッチごとに検証すれば、問題がどのバッチで混入したかすぐ特定できる)
5. 未翻訳が無くなるまで 1 に戻る

スクリプトが利用できない環境では、1件ずつ逐次`str_replace`で書き込む。

### validate_po.py の使い方

> **注**: `validate_po.py` も `apply_translations.py` と同じ場所(Skillインストール先の `scripts/`)にあります。
> 完了確認・整合性チェックのために自前のチェックスクリプトをその場で書かず、**必ずこのスクリプトを使うこと**。
> 即興のチェックは表記ルール違反を拾えないうえ、チェック自体のバグでプレースホルダー欠落を見逃した実例がある。

```bash
python scripts/validate_po.py path/to/ja.po
python scripts/validate_po.py "path/to/languages/*.po"
python scripts/validate_po.py --errors-only path/to/ja.po  # ERROR のみ表示
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
| `PUNCT_SPACING` | WARN | 日本語直後の ! / ? の前にスペースがない |
| `WRITING_CONVENTION` | WARN | 「下さい」「全て」「既に」等の表記ゆれ |

ERROR が残った状態での Import は行わない。WARN は目視判断のうえ修正する。

## 4. 自動化してよい範囲 / してはいけない範囲

- 自動化してよい: 差分検出、下訳生成、バリデーションスクリプトの実行、アップロード用`.po`ファイルの組み立て
- 自動化してはいけない: 人間レビューの省略、Import操作そのものを無人で実行すること(ファイルの内容を毎回ユーザー本人が確認した上で、手動でアップロードする)
- **PTE/GTEでCurrentを選べる場合でも**、人間レビューを経ずに即時反映してはいけない。一般コントリビューターとしてWaitingでアップロードする場合も同様で、「どうせ承認待ちだから精査しなくていい」という考え方はしない。未精査の機械翻訳を大量に投入すると、承認者の負担になり、提案が一括拒否される原因になる(ハンドブックに明記された機械翻訳の精査義務)

## 5. PTE権限のリクエスト

自作のプラグイン・テーマを自分で翻訳したい場合や、継続して特定のプラグイン・テーマを翻訳したい場合は、翻訳ガイドラインに沿った翻訳の実績があればPTE権限をリクエストできる([翻訳承認・レビューのリクエスト手順](https://ja.wordpress.org/team/handbook/translation/wordpress-translation-steps/#%e7%bf%bb%e8%a8%b3%e6%89%bf%e8%aa%8d-%e3%83%ac%e3%83%93%e3%83%a5%e3%83%bc-%e3%81%ae%e3%83%aa%e3%82%af%e3%82%a8%e3%82%b9%e3%83%88))。

ユーザーが「このプロジェクトをよく翻訳しているがPTEは持っていない」と話している場合、状況に応じてPTEリクエストの選択肢があることを伝えてよい。ただし、リクエストするかどうかの判断はユーザーに委ねること。PTEを持たなくても一括Import(Waiting)自体は可能なので、PTE取得は「即時反映したいか」「承認プロセスを背負いたいか」という判断軸で勧めるとよい。
