# CLAUDE.md

このファイルは、このリポジトリ(`wordpress-ja-translation-guide`)で Claude Code を使って作業する際のプロジェクト固有の指示です。

## このリポジトリについて

[ja.wordpress.org 公式の翻訳ハンドブック](https://ja.wordpress.org/team/handbook/translation/)・[翻訳スタイルガイド](https://ja.wordpress.org/team/handbook/translation/translation-style-guide/)を反映した Claude Skill (`wordpress-ja-translation-guide`) のソースリポジトリです。

SKILL.md と references/ 一式を `.skill`(zip)としてパッケージ化し、Claude.ai または Claude Code にインストールして、WordPressプラグイン/テーマ/コアの日本語翻訳作業を支援するために使います。

## ディレクトリ構成と各ファイルの役割

```
wordpress-ja-translation-guide/
├── CLAUDE.md                          このファイル(配布物には含めない)
├── SKILL.md                           トリガー条件 + 要点のみ
├── README.md                          利用者向け説明(インストール・ビルド手順)
├── LICENSE                            GPL-2.0-or-later
├── .gitattributes                     GitHubのSource zipからCLAUDE.md等を除外(export-ignore)
├── .github/
│   └── workflows/
│       └── release.yml                タグpush時に.skillをビルドしReleaseへ自動添付
├── scripts/
│   ├── package_skill.py               .skill生成スクリプト(標準ライブラリのみ。.skillには同梱しない)
│   ├── apply_translations.py          翻訳結果を.poへ反映するランタイムツール(.skillに同梱)
│   └── validate_po.py                 .poの規約違反チェックツール(.skillに同梱)
└── references/
    ├── notation-rules.md              全角半角・句読点・括弧・カギ括弧・カタカナ語・日付・プレースホルダー
    ├── word-choice-rules.md           訳語統一・文体・ブランド名・用語集の使い方
    └── contribution-workflow.md       一括翻訳ワークフローとスクリプトの使い方
```

## 編集時の方針

- **一次情報は常に公式ページ**: ルールを追加・変更する際は、必ず ja.wordpress.org の公式ハンドブック・スタイルガイドの該当ページを確認してから反映する。記憶や推測で書き足さない
- **SKILL.mdは要点のみ**: 本体は500行程度を目安に収め、詳細・例文は `references/` に逃がす(progressive disclosure)。SKILL.mdに新しい詳細ルールを書きたくなったら、まず references/ のどのファイルに属すか考える
- **references/ が300行を超えたら目次を付ける**: 現状はまだ収まっているが、増えてきたら冒頭に目次を追加する
- **核となる安全装置は絶対に弱めない**:
  - 「機械翻訳の精査義務」(SKILL.mdの最重要セクション)
  - 自信のない訳語を `[要確認]` として明示し、断定しない運用
  - PTE保有・非保有を問わず、最終的な人間レビューを省略しない原則
  - PTE非保有プロジェクトでのSuggest操作の自動化を禁止する記述
  これらを「簡潔にするため」「使いやすくするため」といった理由で削ったり弱めたりしない
- **個人情報・案件固有の情報を埋め込まない**: このリポジトリは公開・共有を前提にしている。まーちゅう個人のPTE保有プロジェクト一覧や、特定クライアント案件の情報などはSKILL.md/references/に書かない。「対象プロジェクトでPTEを持っているか確認する」という汎用ロジックを維持する

## リリース手順

1. `SKILL.md` または `references/*.md` を編集し、コミットして `git push origin main` する
2. (任意)内容を手元で確認したい場合は `python scripts/package_skill.py` で `dist/wordpress-ja-translation-guide.skill` を生成する(`dist/` と `*.skill` は `.gitignore` 対象なのでコミット不要。これはあくまで確認用で、リリースには使わない)
3. `git tag vX.Y.Z` でバージョンを切り、`git push origin vX.Y.Z`
4. タグの push をトリガーに GitHub Actions(`.github/workflows/release.yml`)が**タグの内容から** `.skill` をビルドし、Release を自動作成・添付する。手動で `.skill` を添付しない(作業ツリーの状態に依存した成果物を配布しないため)
5. Actions の実行結果と、Releases に `.skill` が添付されたことを確認する

## やってはいけないこと

- `dist/` や `*.skill` をリポジトリにコミットする(ビルド成果物のため `.gitignore` で除外している)
- 公式ページの裏取りなしに、翻訳ルールを推測で追加・変更する
- `CLAUDE.md` を配布物に含める(`.skill` は `scripts/package_skill.py` の除外リスト、GitHub の Source code (zip/tar.gz) は `.gitattributes` の `export-ignore` で対応済み。どちらを編集する際もこの方針を維持する)
