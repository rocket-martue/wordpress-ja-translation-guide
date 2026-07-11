# 一括翻訳ワークフローとスクリプトの使い方

[Polyglotsハンドブック / translate.wordpress.org (GlotPress)](https://make.wordpress.org/polyglots/handbook/translating/glotpress-translate-wordpress-org/)の「Importing External Files」に基づく。SKILL.mdの要点を補足する詳細資料。

## 目次

- 1. 翻訳作業の共通フロー / 1.1. apply_translations.py の使い方 / 1.2. validate_po.py の使い方
- 2. 自動化してよい範囲 / してはいけない範囲

## 1. 翻訳作業の共通フロー

1. **差分検出**: 対象プロジェクトの未翻訳・fuzzy文字列を抽出する(SVN上の最新`.pot`との比較、またはtranslate.wordpress.org上のUntranslatedフィルタを利用)
2. **既存訳の取得**: Exportリンクから、すでにCurrentになっている訳を取得し、表記統一の参考にする
3. **下訳生成**: このSkillのルールに従って訳文ドラフトを生成する
4. **`.po`ファイルへの書き込み**: 生の`.po`構文に`str_replace`で直接書き込もうとしない。`scripts/apply_translations.py`経由でバッチ書き込みする(詳細は「1.1」を参照)
5. **自動バリデーション**: プレースホルダー一致・ブランド名の未翻訳・表記ルール違反を機械的にチェックする(`scripts/validate_po.py` を使う)。全件完了後にまとめて1回ではなく、**バッチ適用のたびに実行する**(「1.1」の運用ルールを参照)
6. **人間レビュー**: ユーザー本人が目視で確認・修正する(ここは省略不可)
7. **Import Translationsでアップロード**: `.po`をアップロードする(ステータスの選択肢は翻訳ページの表示に従う)

文字列の数が少ない場合は、Import Translationsを使わず、画面上の「Suggest」ボタンで1件ずつ提案する従来の方法でもよい。どちらの手段を使うかはユーザーの裁量に委ねる。

### 1.1. apply_translations.py の使い方(ステップ4の詳細)

> **スクリプトの場所**: このスクリプトは Skill の一部として配布されており、**Skill をインストールした時点で利用可能**。
> 翻訳対象の WordPress プラグイン/テーマのディレクトリには存在しないので、フルパスで指定する。
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
> 「このリポジトリにスクリプトは無い」と思っても、まず上記のSkillインストール先を確認すること(自前の代替スクリプトを書かない)。

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
2. 訳文を生成し、msgid 照合付きのオブジェクト形式 JSON を作る。ナレーションで「書いた」ことにしない——必ずスクリプトを呼び出してファイルに書き込む
3. スクリプトが返す進捗と WARN / ERROR を確認する
4. **バッチ適用のたびに `validate_po.py` を実行し、ERROR が出たら次のバッチに進む前に修正する**(apply_translations.py と同じ場所にある。フルパスで呼ぶ)
5. 未翻訳が無くなるまで 1 に戻る

スクリプトが利用できない環境では、1件ずつ逐次`str_replace`で書き込む。

### 1.2. validate_po.py の使い方

> **注**: `validate_po.py` も `apply_translations.py` と同じ場所(Skillインストール先の `scripts/`)にあります。翻訳対象プロジェクトのディレクトリには存在しないため、フルパスで呼び出してください。
> 完了確認・整合性チェックのために自前のチェックスクリプトをその場で書かず、**必ずこのスクリプトを使うこと**。
> 即興のチェックは表記ルール違反を拾えないうえ、チェック自体のバグでプレースホルダー欠落を見逃した実例がある。

```bash
# Claude Code (Skillインストール先)
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/validate_po.py path/to/ja.po
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/validate_po.py "path/to/languages/*.po"
python ~/.claude/skills/wordpress-ja-translation-guide/scripts/validate_po.py --errors-only path/to/ja.po  # ERROR のみ表示

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
| `PUNCT_SPACING` | WARN | 日本語直後の ! / ? の前にスペースがない |
| `WRITING_CONVENTION` | WARN | 「下さい」「全て」「既に」等の表記ゆれ |

ERROR が残った状態での Import は行わない。WARN は目視判断のうえ修正する。

## 2. 自動化してよい範囲 / してはいけない範囲

- 自動化してよい: 差分検出、下訳生成、バリデーションスクリプトの実行、アップロード用`.po`ファイルの組み立て
- 自動化してはいけない: 人間レビューの省略、Import操作そのものを無人で実行すること(ファイルの内容を毎回ユーザー本人が確認した上で、手動でアップロードする)
- **Importでどのステータスを選べる場合であっても**、人間レビューを経ずに即時反映してはいけない。「どうせ承認待ちだから精査しなくていい」という考え方もしない。未精査の機械翻訳を大量に投入すると、承認者の負担になり、提案が一括拒否される原因になる(ハンドブックに明記された機械翻訳の精査義務)
