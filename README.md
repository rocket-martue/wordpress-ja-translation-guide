# wordpress-ja-translation-guide

WordPress コア・プラグイン・テーマの文字列を日本語に翻訳する際に、[ja.wordpress.org 公式の翻訳スタイルガイド](https://ja.wordpress.org/team/handbook/translation/) に沿った表記を保つための [Claude Skill](https://www.anthropic.com/news/skills) です。

`.po` / `.pot` ファイルの翻訳、既存の日本語訳のレビュー、[translate.wordpress.org](https://translate.wordpress.org/) への提案やPTE(Project Translation Editor)としてのインポート前チェックなど、WordPress日本語ローカライズ作業全般で利用できます。

## このSkillが反映しているルール

ja.wordpress.org 公式の[翻訳ハンドブック](https://ja.wordpress.org/team/handbook/translation/)・[翻訳スタイルガイド](https://ja.wordpress.org/team/handbook/translation/translation-style-guide/)の内容を反映しています。

- 機械翻訳は精査せずに提案・インポートしない(公式ハンドブックの明記事項。提案が一括拒否される原因になる)
- 「分かりやすさ・独自性・現代的であること」という翻訳方針
- 全角半角・句読点・括弧・カギ括弧の使い方
- カタカナ語の長音記号ルール、中点「・」の扱い
- 受動態を避ける、"View XX"→「〜を表示」など訳語統一ルール
- プレースホルダー(`%s` `%d` `%1$s` など)の数・種類を原文と完全一致させる
- テーマ名・プラグイン名・「WordPress」表記・確定済みの機能名は翻訳しない
- 公式用語集・Consistency Toolへの参照
- 用語選択に確信が持てない箇所は `[要確認]` として明示し、断定しない
- `.po`形式での出力フォーマットを維持
- **PTE(Project Translation Editor)権限の有無に応じた作業フローの案内**(Import Translationsはログイン済みユーザーなら誰でも使える。PTE権限の有無で変わるのは「Current / Waiting どちらのステータスでアップロードできるか」だけ)

詳細なルールと例は以下を参照してください:

- [`references/notation-rules.md`](./references/notation-rules.md) — 全角半角・句読点・括弧・カタカナ語の長音記号・日付・プレースホルダー
- [`references/word-choice-rules.md`](./references/word-choice-rules.md) — 訳語統一・文体ルール・ブランド名・用語集の使い方
- [`references/contribution-workflow.md`](./references/contribution-workflow.md) — Import Translationsの権限差(Current / Waiting)、共通の作業フロー、自動化してよい範囲・してはいけない範囲

## 使い方

### Claude Code / Claude.ai (Desktop, Cowork)

1. このリポジトリをダウンロードまたは `git clone` する
2. `wordpress-ja-translation-guide/` フォルダを Skills ディレクトリに配置する、または `.skill` ファイルとしてインストールする
3. WordPress翻訳に関する依頼をすると、自動的にこのSkillが参照されます

### .skillファイルとして直接共有する場合

このリポジトリの [Releases](../../releases) (または直接配布されたファイル)から `wordpress-ja-translation-guide.skill` を入手し、Claude にインストールしてください。

## 注意事項

- このSkillは ja.wordpress.org 公式の用語集(glossary)を全件収録しているわけではありません。判断に迷う訳語は `[要確認]` として明示される設計です
- このSkillが生成する訳文は**ドラフト**です。`translate.wordpress.org` への反映(提案・インポートいずれも)は、必ず人間によるレビューを経てから行ってください

## 開発者向け: .skillファイルの生成方法

`.skill`ファイルはビルド成果物のため、このリポジトリにはコミットされていません(`.gitignore`で除外)。配布用の`.skill`は、リリースを作るたびに以下のスクリプトで手元生成し、[Releases](../../releases)に添付してください。

### 必要なもの

- Python 3.8以降(標準ライブラリのみで動作、追加インストール不要)

### 生成コマンド

```bash
python scripts/package_skill.py
```

`dist/wordpress-ja-translation-guide.skill` が生成されます。出力先を変えたい場合は `-o` オプションで指定できます。

```bash
python scripts/package_skill.py -o dist
```

### スクリプトがやっていること

- `SKILL.md` の存在と、frontmatter(`name` / `description`)が正しく書かれているかを検証
- `.git` / `scripts` / `dist` / `__pycache__` などビルドに不要なファイルを除外しつつ、リポジトリ全体を `wordpress-ja-translation-guide/` フォルダごとzip化

### 翻訳品質チェック: validate_po.py

`.po` ファイルを Import する前に、機械的に検出できるルール違反を確認できます。

```bash
python scripts/validate_po.py path/to/ja.po
python scripts/validate_po.py "path/to/languages/*.po"
python scripts/validate_po.py --errors-only path/to/ja.po
```

| ルールID | 重大度 | 内容 |
|---|---|---|
| `PH_MISMATCH` | ERROR | プレースホルダーの数・種類の不一致 |
| `BRAND_TRANSLITERATION` | ERROR | 「WordPress」の音訳(ワードプレス等) |
| `FULLWIDTH_DIGIT` | WARN | 全角数字(０-９) |
| `FULLWIDTH_ALPHA` | WARN | 全角英字(Ａ-Ｚ、ａ-ｚ) |
| `NUM_SPACING` | WARN | 数字・プレースホルダー直後の不要なスペース |
| `WRITING_CONVENTION` | WARN | 「下さい」「全て」「既に」等の表記ゆれ |

終了コードが `0` なら違反なし。`1` なら1件以上の違反あり(`--errors-only` と組み合わせてCI等に組み込む用途にも使えます)。

## 貢献

表記ルールの誤りや追加してほしいルールがあれば、Issue・Pull Requestを歓迎します。

## ライセンス

[GPL-2.0-or-later](./LICENSE)
