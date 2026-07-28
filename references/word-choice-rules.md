# 訳語選択・文体ルール詳細

ja.wordpress.org 公式[翻訳スタイルガイド](https://ja.wordpress.org/team/handbook/translation/translation-style-guide/) 3章・6章、および[翻訳ハンドブック](https://ja.wordpress.org/team/handbook/translation/)に基づく。SKILL.mdの要点を補足する詳細資料。

## 目次

- 1. 訳語の統一の考え方
- 2. 文体の具体ルール
- 3. ブランド名・機能名
- 4. 用語集で決まっている定型表現
- 5. 用語集とConsistency Toolの使い方
- 6. 機械翻訳に関する公式の注意事項

## 1. 訳語の統一の考え方

初めて翻訳する前や訳語の選択に悩む場合は、まず `references/glossary.md`(WordPressプロジェクト共通の[用語集](https://translate.wordpress.org/locale/ja/default/glossary)の全エントリーを収録したスナップショット)を原語で検索する。用語集に載っている語は用語集の訳語に合わせる。最新の内容は公式ページで確認する。

既存の訳が存在するフレーズは統一することが望まれる。translate.wordpress.org の翻訳画面で3本線のメニューから「View original in consistency tool」を開くと、同じ原文の承認済み翻訳を一覧表示できる([Consistency Tool](https://translate.wordpress.org/consistency)へのショートカットも利用可能)。

複数の訳語候補があってどれを選んでよいか分からない場合や、既存の訳が間違っていると思われる場合は、[WordSlack](https://ja.wordpress.org/support/article/slack/) の #translate チャンネルで確認する。Skillとして訳文を出す際は、この判断を勝手に行わず `[要確認]` を付けること。

## 2. 文体の具体ルール

**2-1. 自然な日本語になるよう、受動態はなるべく避ける**

原語が受動態の場合も、可能な場合は「〜されました。」ではなく「〜しました。」などとする。

**2-2. "View XX" という表現は基本的に「〜を表示(する)」に統一する**

「〜を閲覧、〜を見る、〜を開く、〜を参照」などは使わない。動詞として使われているため「〜**の**表示」ではない点に注意。名詞の "view"(表示形式の慣用名など)は用語集で「ビュー」と決められている例外。同様に "Hide XX" は「〜を非表示」とする。

**2-3. "XX are (is) not allowed to…" は「〜する権限がありません」に統一する**

**2-4. "Sorry, …" で始まるエラーメッセージは「すみません」とは訳さず、その部分を削除する**

**2-5. 英語で "You" や "Your" とあっても、日本語にしたときに不自然な場合は「あなた」「あなたの」を入れない**

できる限り「自分の」「お使いの」「独自の」などの、より自然な言い回しを使うか、省略する。

**2-6. 表記の統一**

「下さい」は「ください」、「全て」は「すべて」、「既に」は「すでに」に統一する(「すべて」「すでに」は用語集の `all` / `already` エントリーでも指定されている)。

**2-7. メニュー項目やボタンラベルの訳語に一貫性を持たせる**

メニュー項目やボタンラベルを含む文を訳す際には、そのプロジェクト内の他の文字列でどう訳されているのか参照して、必ず統一する。

**2-8. 動詞を含む文の語尾に一貫性を持たせる**

- 見出しは体言止め、または「する」(常体)とする
- 箇条書きの項目では「する」(常体)とする
- ボタンラベルでは語尾の「します(する)」を省略した形にする
- 句読点の有無は原文に合わせる。原文内で一貫性がない場合は、サポートフォーラムやGitHubでプラグイン作者に報告することが望ましい

## 3. ブランド名・機能名

基本的に用語集(`references/glossary.md`、原典は[公式用語集](https://translate.wordpress.org/locale/ja/default/glossary))に従って一貫した名称を使用する。

- **WordPress**: 常に「WordPress」と表記し、翻訳や音訳はしない
- **機能名**: 用語集に従う。コア内の新しい用語はWordSlack #translate チャンネルで話し合って確定するものであり、Skillが独自に確定させてはいけない
- **テーマ名・プラグイン名**: 例えば "Twenty Twenty" などのテーマ名は翻訳しない。プラグイン名も同様に未翻訳のままにする
- **用語集で英語のままと決まっているもの**: `Gutenberg` `BuddyPress` `Classic Editor`(プラグイン名の場合) `Press This` `Transient` `nonce` `Cookie` `WordCamp` `Subversion` `RSS` `XML-RPC` `After the Deadline` など。カタカナに開かず原語のまま残す(全リストは `references/glossary.md`)
- **表記が指定されているもの**: `web server` は「Web サーバー」(文頭でなくても W は大文字)、`URI` は「URL」、`Two-Factor Authentication` は「2要素認証」(漢数字にしない)

## 4. 用語集で決まっている定型表現

用語集には単語だけでなく、文単位で訳し方が決まっている `expression` のエントリーがある。2章の文体ルールと重なるものは、いずれも用語集由来のルール。

| 原文 | 訳し方 |
|---|---|
| Are you sure …? | 文頭に「本当に」、文末に「してもよいですか ?」(例: `本当に設定を削除してもよいですか ?`) |
| Sorry, … | 「すみません」とは訳さず、この部分を訳文に入れない(2-4 と同じ) |
| … is/are not allowed to … | 「〜する権限がありません」(2-3 と同じ) |
| Please try again | 「もう一度お試しください」 |
| Learn More | 「さらに詳しく」 |
| Posted in | 「カテゴリー:」(テーマ内でカテゴリーリストが後に続く場合) |
| Posted on | 「投稿日:」(テーマ内で日付が後に続く場合) |
| Contributor | 「寄稿者」(権限グループのひとつ。開発への貢献者を指す `contributor` は「コントリビューター」「貢献者」) |

## 5. 用語集とConsistency Toolの使い方

- `references/glossary.md`: [公式用語集](https://translate.wordpress.org/locale/ja/default/glossary)の全エントリーを収録したスナップショット。WordPress固有の言葉に対する訳語が決められている。歴史的経緯で複数の訳語が割り当てられている場合もあり、その場合は「補足」列の文脈で選ぶ
  - 用語集は更新され続けるため、公式ページと食い違う場合は公式ページが正しい。更新するときはリポジトリで `python scripts/update_glossary.py` を実行する(表の部分だけが差し替わる)
- [Consistency Tool](https://translate.wordpress.org/consistency): 表記ゆれをチェックするツール。WordPress本体・テーマ・プラグインである単語がどのように使われているかを調べられる
- 迷ったら[コアの翻訳](https://translate.wordpress.org/locale/ja/default/wp/dev/)も参考にできる

非公式のブラウザー拡張機能も翻訳支援に利用できる(参考情報):

- [GlotDict](https://github.com/Mte90/GlotDict): 追加の警告、承認操作の簡略化など
- [WPTranslationFiller](https://github.com/vibgyj/WPTranslationFiller): 用語集との不整合の警告、機械翻訳連携など
- [WP GlotPress Tools (WPGT)](https://github.com/vlad-timotei/wpgp-tools): Consistency Toolの統合、追加警告、カスタムショートカットなど

## 6. 機械翻訳に関する公式の注意事項

[翻訳ハンドブック](https://ja.wordpress.org/team/handbook/translation/)に明記されている重要な注意:

> 機械翻訳の結果を精査せずに使った翻訳および翻訳の提案はしないでください。必ず「翻訳スタイルガイド」に合わせた修正を行ってください。精査が行われていないと承認者が判断した場合、提案を一括拒否する場合があります。

このSkillによる訳文生成もこの「機械翻訳」に該当するものとして扱う。Skillが生成した訳文は必ず人間がスタイルガイドとの整合性を精査した上で提案・インポートすること。
