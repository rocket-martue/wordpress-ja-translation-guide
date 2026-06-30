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
5. **自動バリデーション**: プレースホルダー一致・ブランド名の未翻訳・表記ルール違反を機械的にチェックする(`scripts/validate_po.py` を使う)
6. **人間レビュー**: ユーザー本人が目視で確認・修正する(ここは省略不可)
7. **Import Translationsでアップロード**: `.po`をアップロードする
   - PTE/GTEの場合: Current(即時反映)かWaiting(承認待ち)かを選べる
   - 一般コントリビューターの場合: Waitingとしてアップロードされる(GTE/PTEの承認を待つ)

文字列の数が少ない場合は、Import Translationsを使わず、画面上の「Suggest」ボタンで1件ずつ提案する従来の方法でもよい。どちらの手段を使うかはユーザーの裁量に委ねる。

### 3.5. apply_translations.py の使い方（ステップ4の詳細）

生の`.po`構文に`str_replace`で書き込もうとすると、`msgstr ""`が大量に重複するため一意に特定できず、置換失敗やリトライが発生する。`scripts/apply_translations.py`経由でバッチ書き込みすることで、このコストを完全に除去できる。

```bash
# 未翻訳エントリーをインデックス付きで一覧表示
python scripts/apply_translations.py path/to/ja.po --list
python scripts/apply_translations.py path/to/ja.po --list --start 0 --count 20

# インデックス→訳文ペアをバッチ書き込み（JSON ファイル）
python scripts/apply_translations.py path/to/ja.po translations.json

# インライン JSON 文字列でも可
python scripts/apply_translations.py path/to/ja.po '{"0": "訳文A", "1": "訳文B"}'
```

出力例:

```
✅ 20件書き込みました。進捗: 40/190 (21%), 残り 150件
```

**運用ルール**:

- 訳文を生成したら、ナレーションで「書いた」ことにしない——必ずスクリプトを呼び出してファイルに書き込む
- スクリプトが返す進捗を確認してから次のバッチへ進む
- スクリプトが利用できない環境では、1件ずつ逐次`str_replace`で書き込む

### validate_po.py の使い方

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
| `NUM_SPACING` | WARN | 数字・プレースホルダー直後の不要なスペース |
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
