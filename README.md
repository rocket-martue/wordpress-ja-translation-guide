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
- 公式用語集の全エントリー(取得日時点のスナップショット)の収録と、Consistency Toolへの参照
- 用語選択に確信が持てない箇所は `[要確認]` として明示し、断定しない
- `.po`形式での出力フォーマットを維持
- **一括翻訳ワークフロー**: `scripts/apply_translations.py` によるバッチ書き込みと、`scripts/validate_po.py` による機械チェックを組み合わせた大量翻訳の手順

詳細なルールと例は以下を参照してください:

- [`references/notation-rules.md`](./references/notation-rules.md) — 全角半角・句読点・括弧・カタカナ語の長音記号・日付・プレースホルダー
- [`references/word-choice-rules.md`](./references/word-choice-rules.md) — 訳語統一・文体ルール・ブランド名・用語集の使い方
- [`references/glossary.md`](./references/glossary.md) — [公式用語集](https://translate.wordpress.org/locale/ja/default/glossary/)全エントリーのスナップショット(英語・品詞・日本語訳・補足。取得日と収録件数はファイル冒頭に記載)
- [`references/contribution-workflow.md`](./references/contribution-workflow.md) — 一括翻訳ワークフローとスクリプトの使い方、自動化してよい範囲・してはいけない範囲

## 使い方

### .po ファイルのダウンロード

1. [translate.wordpress.org](https://translate.wordpress.org/) で翻訳対象のプロジェクトを開く
2. 「Japanese」を選択
3. Stable または Stable Readme のいずれかを選択
4. Untranslated をクリックして未翻訳のものだけを表示する
5. ページ最下部までスクロールし、「all current」を「only matching the filter」に変更してから「Export」をクリックして .po ファイルをダウンロードする
6. ダウンロードした .po ファイルの翻訳をAIに依頼する
7. 翻訳結果を確認し、必要に応じて修正する
8. `python scripts/validate_po.py path/to/ja.po` で機械的に検出できるルール違反がないかチェックする(詳細は[後述](#翻訳品質チェック-validate_popy))
9. 翻訳後の .po ファイルは translate.wordpress.org のページ最下部にある「Import Translations」からアップロードする

### Claude Code / Claude.ai (Desktop, Cowork)

1. このリポジトリをダウンロードまたは `git clone` する
2. `wordpress-ja-translation-guide/` フォルダを Skills ディレクトリに配置する、または `.skill` ファイルとしてインストールする
3. WordPress翻訳に関する依頼をすると、自動的にこのSkillが参照されます

### .skillファイルとして直接共有する場合

このリポジトリの [Releases](../../releases) (または直接配布されたファイル)から `wordpress-ja-translation-guide.skill` を入手し、Claude にインストールしてください。

## 注意事項

- [`references/glossary.md`](./references/glossary.md) に収録している公式用語集は、**取得日時点のスナップショット**です。用語集は更新され続けるため、[公式ページ](https://translate.wordpress.org/locale/ja/default/glossary/)と食い違う場合は公式ページが正しい内容になります。用語集に無い語や判断に迷う訳語は `[要確認]` として明示される設計です
- このSkillが生成する訳文は**ドラフト**です。`translate.wordpress.org` への反映(提案・インポートいずれも)は、必ず人間によるレビューを経てから行ってください

## 開発者向け: .skillファイルの生成方法

`.skill`ファイルはビルド成果物のため、このリポジトリにはコミットされていません(`.gitignore`で除外)。配布用の`.skill`は、`vX.Y.Z` 形式のタグをpushすると GitHub Actions(`.github/workflows/release.yml`)がタグの内容からビルドし、[Releases](../../releases)に自動で添付します。以下のスクリプトは、手元で内容を確認したいときに使ってください。

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
- `.git` / `.github` / `dist` / `__pycache__` / `CLAUDE.md` / `package_skill.py` / `update_glossary.py` など配布に不要なファイルを除外しつつ、リポジトリ全体を `wordpress-ja-translation-guide/` フォルダごとzip化(`scripts/` 内の `apply_translations.py`・`validate_po.py`・`fix_spacing.py` はSKILL.mdが参照するランタイムツールのため同梱)

### 用語集の更新: update_glossary.py

[公式用語集](https://translate.wordpress.org/locale/ja/default/glossary/)を取得し、[`references/glossary.md`](./references/glossary.md) の表を最新の内容に差し替えます(前書き・使い方などの手書き部分は変更されません)。

```bash
python scripts/update_glossary.py          # 取得して references/glossary.md を更新
python scripts/update_glossary.py --check  # 差分があれば終了コード1(更新漏れの確認用)
```

用語集は不定期に更新されるため、リリース前に `--check` を実行して差分の有無を確認することを推奨します。リリースワークフローからは自動実行していません(タグを打った時点で外部サイトの内容が黙って配布物に混入するのを避けるためです)。

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
| `FULLWIDTH_PUNCT` | WARN | 全角感嘆符・疑問符(!?) |
| `NUM_SPACING` | WARN | 数字・数値プレースホルダー(`%d`等)直後の不要なスペース |
| `ALPHA_SPACING` | WARN | 半角英字と全角文字の間に半角スペースがない(例: `担当者のFacebook`) |
| `PUNCT_SPACING` | WARN | 日本語直後の `!` / `?` にスペースがない |
| `WRITING_CONVENTION` | WARN | 「下さい」「全て」「既に」等の表記ゆれ |

終了コードが `0` なら違反なし。`1` なら1件以上の違反あり(`--errors-only` と組み合わせてCI等に組み込む用途にも使えます)。

### スペースの自動挿入: fix_spacing.py

`ALPHA_SPACING` は件数が多くなりやすいため、`validate_po.py` と同じ検出ロジックで半角スペースを機械挿入するスクリプトを用意しています。

```bash
python scripts/fix_spacing.py path/to/ja.po           # dry-run(既定): 候補を表示するだけ
python scripts/fix_spacing.py path/to/ja.po --apply   # 実際に書き換える
```

```
path/to/ja.po:17  (5 箇所)
  - 拡張機能のAPIキーを取得するためには、MainWPのAPIキーが必要です。
  + 拡張機能の API キーを取得するためには、MainWP の API キーが必要です。
```

挿入するのは半角スペースだけで、訳語・文体の正しさは保証しません。`--apply` の後は必ず `validate_po.py` で再検証し、人間が目視レビューしてください。`msgid`・コメント・obsolete(`#~`)・ヘッダーエントリーには触れず、書き換え後に「スペース以外の内容が不変」「プレースホルダーの数・種類が不変」「HTMLタグ数が不変」を検証します。

## 貢献

表記ルールの誤りや追加してほしいルールがあれば、Issue・Pull Requestを歓迎します。

## ライセンス

[GPL-2.0-or-later](./LICENSE)
