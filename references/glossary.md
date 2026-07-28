# WordPress 日本語用語集(公式 glossary のスナップショット)

出典: [translate.wordpress.org の日本語ロケール用語集](https://translate.wordpress.org/locale/ja/default/glossary/)(WordPress 日本語ローカライズチームが管理)。下の表はその全エントリーを取得日時点でそのまま転記したもので、訳語・補足の文言はこちらで足したり言い換えたりしていない。

**原文ママで転記しているため、公式用語集側の誤字もそのまま含まれる**。原語で見つからないときは綴り違いも試す。誤字を見つけたら、このファイルを直すのではなく[公式用語集](https://translate.wordpress.org/locale/ja/default/glossary/)側の修正を Making WordPress の #ja-docs チャンネルで提案する(このファイルの表は自動生成のため、手で直しても次回の更新で元に戻る)。

## 目次

- 1. 使い方
- 2. 特に間違いやすい項目
- 3. 用語集(全エントリー)

## 1. 使い方

1. **訳語に迷ったら、まずこの表を原語で検索する**。用語集にある語は、この表の訳語に合わせる
2. **同じ原語に複数の訳語があるものは、「補足」列の文脈で選ぶ**。例: `default` は「初期設定 / 初期値 / デフォルト」、`term` は検索文脈なら「キーワード」・タクソノミー文脈なら「ターム」、`page` は「ページ / 固定ページ」。文脈から決められないときは確定させず `[要確認]` とする
3. **この表に無い語は、用語集で決まっていない**。SKILL.md の表記ルール・訳語ルールに従いつつ、確信が持てなければ `[要確認]` を付けて人間の判断に委ねる
4. 用語集は更新され続けるため、この表は**取得日時点のスナップショット**。公式ページと食い違っていたら公式ページが正しい。更新するときは `python scripts/update_glossary.py` を実行する(表の部分だけが差し替わる)

## 2. 特に間違いやすい項目

用語集の補足欄で明示的に注意されているもの:

| 原語 | 訳語 | 注意点 |
|---|---|---|
| all | すべて | 「全て」と漢字書きにしない |
| already | すでに | 「既に」としない |
| outdent | インデントを戻す | 「アウトデント」としない |
| override | 上書き | 「オーバーライドする」としない |
| hide | 非表示 | "Hide XX" は「〜を非表示」 |
| URI | URL | 「URI」のままにしない |
| web server | Web サーバー | 文頭でなくても W は大文字。単に「サーバー」でよい場合もある |
| Two-Factor Authentication | 2要素認証 | 漢数字の「二」ではなく数字の「2」 |
| Are you sure | 本当に〜してもよいですか ? | 文頭に「本当に」、文末に「してもよいですか ?」 |
| Sorry, | (訳さない) | この部分は訳文に入れない |
| poetry | 詩 | ただし "Code is Poetry" というフレーズは訳さない |
| category / gallery / taxonomy | カテゴリー / ギャラリー / タクソノミー | 長音記号の 4 文字ルールの例外として長音を付ける(notation-rules.md の 3 章) |

## 3. 用語集(全エントリー)

<!-- glossary:begin -->
<!-- ここから下は scripts/update_glossary.py が自動生成します。手で編集しないでください。 -->
<!-- 取得日: 2026-07-28 / 収録件数: 278件 -->

| 英語 | 品詞 | 日本語訳 | 補足 |
|---|---|---|---|
| ability | noun | アビリティ | Abilities API は英語ママ |
| action hook | noun | アクションフック |  |
| activate | verb | 有効化 | ボタンなどに使う場合 |
| activate | verb | 有効化する | 文章内で使う場合 |
| activated | adjective | 有効化した |  |
| activated | adjective | 有効化済み |  |
| admin bar | noun | 管理バー |  |
| admin panel | noun | 管理画面 |  |
| administrator | noun | 管理者 |  |
| advanced settings | noun | 高度な設定 |  |
| After the Deadline | noun | After the Deadline | Automattic のサービス名。参照: http://www.afterthedeadline.com/ |
| all | adjective | すべて | ※「全て」ではなく、ひらがな書きにする。 |
| already | adverb | すでに | 「既に」としない。 |
| Appearance | noun | 外観 | 管理画面メニュー項目 |
| archive | noun | アーカイブ |  |
| archive | verb | アーカイブ化 |  |
| Are you sure | expression | 本当に〜してもよいですか ? | 文頭に「本当に」、文末に「してもよいですか ?」<br>Are you sure you want to delete the settings? → 本当に設定を削除してもよいですか ? |
| area | noun | エリア | 「ウィジェットエリア」など。 |
| argument | noun | 引数 |  |
| array | noun | 配列 |  |
| attachment | noun | 添付ファイル |  |
| audio | noun | 音声ファイル |  |
| author | noun | 作成者 | テーマ・プラグインの作者 |
| Author | noun | 投稿者 | ブログ投稿またはコメントを作成したユーザー |
| Authorization header | noun | Authorization ヘッダー |  |
| binary | noun | バイナリ |  |
| block | noun | ブロック | Gutenberg のコンテンツユニット |
| block type | noun | ブロックタイプ | Gutenberg 用語 |
| bookmarklet | noun | ブックマークレット |  |
| border | noun | 枠線 |  |
| browser | noun | ブラウザー |  |
| BuddyPress | noun | BuddyPress |  |
| Bulk Actions | noun | 一括操作 |  |
| bullet list | noun | 箇条書きリスト | HTML 要素 |
| capability | noun | 権限 | 参照: https://ja.wordpress.org/support/article/roles-and-capabilities/ |
| cart | noun | お買い物カゴ |  |
| cart | noun | カート |  |
| category | noun | カテゴリー | 例外で長音付き |
| CDN | noun | CDN | Content Delivery Network の略語 |
| character code | noun | 文字コード |  |
| character entity reference | noun | 文字実体参照 |  |
| character set | noun | 文字セット |  |
| checkout | noun | 購入手続き | eコマースサイトでお買い物カゴに入っている商品を実際に購入する操作。 |
| citation | noun | 引用元 | blockquote 要素の属性 |
| Classic | adjective | クラシック | Gutenberg のブロックタイプ |
| Classic Editor | noun | Classic Editor | プラグイン名 |
| Classic Editor | noun | 旧エディター | エディターの種類 |
| Code Editor | noun | コードエディター | HTML を編集するタイプのエディターツール |
| color scheme | noun | 配色 |  |
| comment | noun | コメント |  |
| comment | verb | コメントする |  |
| computer | noun | コンピューター |  |
| conditional tag | noun | 条件分岐タグ |  |
| constant | noun | 定数 |  |
| contact form | noun | お問い合わせフォーム |  |
| container | noun | コンテナ |  |
| content | noun | コンテンツ |  |
| Content Delivery Network | noun | コンテンツデリバリーネットワーク |  |
| Contributor | expression | 寄稿者 | 権限グループのひとつ。参照: https://wpdocs.osdn.jp/Roles_and_Capabilities |
| contributor | noun | コントリビューター |  |
| contributor | noun | 貢献者 |  |
| Cookie | noun | Cookie | ブラウザの Cookie |
| credentials | noun | ログイン情報 | ユーザー名とパスワードのセットなどアクセスに必要な一連の情報。コンテキストによっては「認証情報」を指すこともある |
| credentials | noun | 認証情報 | "API Credentials" などのような場合。 |
| Custom Post Type | noun | カスタム投稿タイプ |  |
| customize | verb | カスタマイズ |  |
| customizer | noun | カスタマイザー |  |
| Dashboard | noun | ダッシュボード |  |
| Data Erasure Request | noun | データ消去リクエスト |  |
| deactivate | verb | 停止する |  |
| deactivate | verb | 無効化 |  |
| default | noun | デフォルト |  |
| default | noun | 初期値 |  |
| default | noun | 初期設定 |  |
| default theme | noun | デフォルトテーマ |  |
| deprecated | adjective | 非推奨 |  |
| description | noun | 説明 |  |
| developer | noun | 開発者 |  |
| device | noun | 端末 |  |
| directories | noun | ディレクトリ |  |
| directory | noun | ディレクトリ |  |
| disable | verb | 無効化 |  |
| Distraction Free Writing | noun | 集中執筆モード |  |
| divider | noun | 区切り | Gutenberg 以外で汎用的に使う場合。 |
| divider | noun | 罫線 | Gutenberg ブロックの検索キーワードとして使う場合。 |
| domain mapping | noun | ドメインマッピング | WordPress.com paid upgrade product name |
| domain registrar | noun | ドメイン登録業者 |  |
| draft | noun | 下書き |  |
| drop | verb | ドロップ | ドラッグ & ドロップ操作の一部 |
| Drop Cap | noun | ドロップキャップ | https://ejje.weblio.jp/content/drop+cap |
| e-mail | noun | メール |  |
| e-mail | noun | メールアドレス |  |
| eCommerce | noun | eコマース |  |
| editor | noun | エディター | 編集ツール (例: ビジュアルエディター、テーマエディター、プラグインエディター) |
| Editor | noun | 編集者 | 権限グループのひとつ。参照: https://wpdocs.osdn.jp/Roles_and_Capabilities |
| email | noun | メール |  |
| email | noun | メールアドレス |  |
| embed block | noun | 埋め込みブロック |  |
| enable | verb | 有効化 |  |
| error | noun | エラー |  |
| excerpt | noun | 抜粋 |  |
| Facebook | noun | Facebook |  |
| featured image | noun | アイキャッチ画像 |  |
| featured post | noun | おすすめ投稿 |  |
| feed | noun | フィード |  |
| filter | noun | フィルター |  |
| filter | noun | 絞り込み |  |
| filter | verb | 絞り込む |  |
| filter hook | noun | フィルターフック |  |
| folder | noun | フォルダー |  |
| front end | adjective | フロントエンド |  |
| front-end | noun | フロントエンド |  |
| Full Site Editing | noun | フルサイト編集 |  |
| gallery | noun | ギャラリー | 例外で長音付き |
| Gutenberg | noun | Gutenberg |  |
| Happiness Engineers | noun | サポートスタッフ |  |
| hide | verb | 非表示 | "Hide XX" → "〜を非表示" |
| horizontal-line | noun | 水平線 |  |
| host | noun | ホスティングサービス |  |
| host | noun | ホスト | 「ホスティングサービス」と訳すのが適切でない場合。 |
| hosting provider | noun | ホスティングサービス |  |
| indent | verb | インデント |  |
| inserter | noun | インサーター | ブロックインサーター。 |
| Inserter Tool | noun | 挿入ツール | Gutenberg 用語 |
| installer | noun | インストーラ |  |
| interface | noun | インターフェース |  |
| interface | noun | 管理画面 |  |
| invalid | adjective | 不正な |  |
| invalid | adjective | 無効 |  |
| invalid | adjective | 間違った |  |
| IP address | noun | IP アドレス |  |
| is required | verb | 必要 |  |
| item | noun | 項目 | 一般的な事項の呼称 |
| Learn More | expression | さらに詳しく |  |
| log in | noun | ログイン |  |
| log out | noun | ログアウト |  |
| logged in | adjective | ログイン中 |  |
| logged out | adjective | ログアウト中 |  |
| login | verb | ログイン |  |
| logout | verb | ログアウト |  |
| match | verb | 一致 |  |
| media library | noun | メディアライブラリ |  |
| Media Uploader | noun | メディアアップローダー |  |
| memory | noun | メモリ |  |
| meta | noun | メタ |  |
| meta | noun | メタ情報 |  |
| multisite | noun | マルチサイト |  |
| My Upgrades | noun | アップグレード状況 |  |
| name server | noun | ネームサーバー |  |
| nameserver | noun | ネームサーバー |  |
| navigation | noun | ナビゲーション |  |
| network | verb | サイトネットワーク | https://goo.gl/pXLGEj 参照 |
| next post | noun | 次の投稿 |  |
| nonce | noun | nonce |  |
| not allowed to | expression | する権限がありません |  |
| not sticky | adjective | 通常通り表示 | 投稿を先頭固定表示にしないステータス。 |
| numbered list | noun | 番号付きリスト |  |
| object | noun | オブジェクト |  |
| older post | noun | 過去の投稿 |  |
| option | noun | オプション |  |
| option | noun | 設定 |  |
| outdent | verb | インデントを戻す | ※「アウトデント」ではなく。 |
| override | verb | 上書き | ※「オーバーライドする」ではなく。 |
| page | noun | ページ |  |
| page | noun | 固定ページ |  |
| pagination | noun | ページ送り |  |
| parameter | noun | パラメータ |  |
| permalink | noun | パーマリンク |  |
| permission | noun | パーミッション |  |
| permission | noun | 権限 |  |
| ping | noun | ping |  |
| ping | noun | ピンバック |  |
| pingback | noun | ピンバック |  |
| placeholder | noun | プレースホルダー |  |
| please try again | expression | もう一度お試しください |  |
| plugin | noun | プラグイン |  |
| poetry | noun | 詩 | ただし、"Code is Poetry" というフレーズの場合は訳さない |
| poll | noun | 投票 |  |
| Polldaddy | noun | Polldaddy |  |
| post | noun | 投稿 |  |
| post | verb | 投稿する |  |
| post format | noun | 投稿フォーマット |  |
| post status | noun | 投稿ステータス |  |
| post thumbnail | noun | 投稿サムネイル |  |
| post type | noun | 投稿タイプ |  |
| Posted in | expression | カテゴリー: | テーマ内でカテゴリーリストが後に続いて使われた場合。 |
| Posted on | expression | 投稿日: | テーマ内で日付が後に続いて使われた場合。 |
| Poster Image | noun | ポスター画像 | Gutenberg 用語 |
| preformatted | adjective | 整形済み |  |
| Press This | noun | Press This |  |
| previous post | noun | 過去の投稿 |  |
| profile | noun | プロフィール | ユーザーの情報を表示するプロフィール画面などを指す場合。 |
| publish | verb | 公開する |  |
| query | noun | クエリー |  |
| Quick Post | noun | クイックポスト |  |
| reader | noun | 読者 |  |
| referrer | noun | リファラー | リンク元、参照元 |
| registrar | noun | 登録業者 |  |
| repository | noun | リポジトリ |  |
| required | adjective | 必要 |  |
| required | adjective | 必須 |  |
| resolve | noun | 問題を解決する | (Gutenberg の場合) ブロックに発生した問題を解決すること |
| responsive | adjective | レスポンシブ |  |
| return value | noun | 戻り値 |  |
| Reusable Block | verb | 再利用ブロック |  |
| Reusable Template | noun | 再利用テンプレート | Gutenberg で保存したブロック |
| Revision | noun | リビジョン | 投稿、固定ページなどの履歴管理機能。参照: https://ja.wordpress.org/support/article/revisions/ |
| role | noun | 権限グループ |  |
| RSS | noun | RSS |  |
| screen | noun | 画面 | ※Screen Options は例外的に表示と訳出しています。 |
| Screen Options | noun | 表示オプション |  |
| self-hosted | adjective | インストール型の |  |
| separator | noun | 区切り | Gutenberg で保存したテンプレート (ブロックの組み合わせ) |
| server | noun | サーバー |  |
| sidebar | noun | サイドバー |  |
| single | noun | 個別 | 個別投稿、個別商品など |
| single post | noun | 個別投稿 |  |
| site | noun | サイト |  |
| slug | noun | スラッグ |  |
| Sorry, | expression |  | ※この部分は翻訳しません。 |
| spam | noun | スパム |  |
| spam filtering | noun | スパムフィルター機能 |  |
| Spotlight mode | noun | スポットライトモード | Gutenberg でのエディター表示モードの一つ |
| status | noun | ステータス |  |
| status | noun | 状態 |  |
| stick | verb | 先頭に固定表示する |  |
| sticky | adjective | 先頭固定表示 |  |
| strikethrough | noun | 打ち消し線 |  |
| string | noun | 文字列 |  |
| subpanel | noun | サブパネル |  |
| Subscriber | noun | 購読者 | 権限グループのひとつ。参照: https://wpdocs.osdn.jp/Roles_and_Capabilities |
| subtitle | noun | サブタイトル | 副次的な見出し |
| subtitle | noun | 字幕 | 動画などの字幕 |
| Subversion | noun | Subversion |  |
| Super admin | noun | 特権管理者 | マルチサイト全体の管理者。参照: http://bit.ly/2LXrzdb |
| survey | noun | アンケート |  |
| tag | noun | タグ |  |
| tagline | noun | キャッチフレーズ |  |
| taxonomy | noun | タクソノミー | 例外で長音付き |
| template hierarchy | noun | テンプレート階層 |  |
| term | noun | キーワード | 検索のコンテキストの場合 (= search term) |
| term | noun | ターム | タクソノミーのコンテキストの場合。 |
| term | noun | 単語 |  |
| term | noun | 語句 |  |
| term | noun | 項目 |  |
| text block | noun | テキストブロック | Gutenberg のブロックタイプ |
| text editor | noun | テキストエディター |  |
| theme | noun | テーマ |  |
| thought | noun | フィードバック | "%1$s thought on “%2$s”" などの場合、コメントだけではなくピンバックを含むこともあるので「コメント」とは訳さない。Consistency Tool に同じフレーズが存在する可能性があります。 |
| Toolbar | noun | ツールバー |  |
| trackback | noun | トラックバック |  |
| Transient | noun | Transient |  |
| trash | noun | ゴミ箱 |  |
| trashed | adjective | ゴミ箱内の |  |
| troubleshooting | noun | トラブルシューティング |  |
| Twitter | noun | Twitter |  |
| two factor authentication | noun | 2要素認証 |  |
| Two-Factor Authentication | noun | 2要素認証 | 漢字ではなく数字の2で統一する。 |
| Unified toolbar | noun | 統合ツールバー | Gutenberg でのツールバー表示モードの一つ |
| update | noun | 更新 |  |
| update | verb | 更新する |  |
| upgrade | noun | アップグレード |  |
| uploader | noun | アップローダー |  |
| URI | noun | URL |  |
| user | noun | ユーザー |  |
| valid | adjective | 有効 |  |
| valid | adjective | 正しい |  |
| verse | noun | 詩 |  |
| video | noun | 動画 |  |
| view | noun | ビュー | ほとんどの場合は「表示」と訳すが、タブビューやリストビューなどの表示形式の慣用名などの例外ではこちらでも可。 |
| view | verb | 表示 |  |
| web server | noun | Web サーバー | 文頭でなくても W は大文字に統一する。単に「サーバー」としてもいい場合もある。 |
| website | noun | サイト |  |
| WordCamp | noun | WordCamp |  |
| WordPress | noun | WordPress |  |
| WordPress Dashboard | noun | WordPress ダッシュボード |  |
| WordPress.com | noun | WordPress.com |  |
| XML-RPC | noun | XML-RPC |  |

<!-- glossary:end -->
