# 共通訳語リストのテンプレート

分担翻訳のフェーズ①(`parallel-translation-workflow.md` 3 節)でプロジェクトごとに作るファイルの型。作業ディレクトリに `translation-glossary.md` として置き、訳者(サブエージェント)にはこのファイルのパスを渡す。

**中身より構成が本体**。訳語表だけ渡しても、固有名詞と文体が揃わないと訳者間でバラける。以下の 6 ブロックは削らない。

---

```markdown
# {プロジェクト名} {ui|readme} 共通訳語リスト

対象: `path/to/ja.po`(未翻訳 N 件 / うち `gp-priority: low` M 件)

正典は `wordpress-ja-translation-guide` Skill(SKILL.md / references/notation-rules.md /
references/word-choice-rules.md)。以下はこのファイル固有の上乗せ。

## 翻訳しない固有名詞

プラグイン名・製品名・サービス名・機能名を**列挙する**。ここに書き漏らすと必ず誤訳される。
`wordfreq.txt` の上位語と、原文中の大文字始まりの語を突き合わせて拾う。

関数名・フック名・オプション名・ファイル名はコードとして保持することも明記する。

## 一般訳語

| 原語 | 訳語 | 備考 |
|---|---|---|
| ... | ... | 判断が割れる語には「〜は使わない」と否定形で書く |

- 公式用語集(`references/glossary.md`)にある語は用語集どおり
- 同じ原語に複数訳がある語(`default`、`term` など)は、このファイルで文脈を固定する
- 決められない語は `[要確認]` にして確定させない

## 文体

エントリー種別ごとに語尾を決める。`po_chunk.py` が付ける種別タグと対応させること。

- 本文(`description paragraph` / `faq paragraph` / `installation paragraph`): 敬体
- 見出し(`description header` / `faq header` / `installation header`): 体言止め。疑問文は半角 `?`(直前に半角スペース)
- 箇条書き(`description list item`): 体言止め・常体
- 手順の箇条書き(`installation list item`): 「〜します」
- changelog(`gp-priority: low`): 体言止め。原文に句点があれば付け、なければ付けない
  - `improved X` →「X を改善」/ `fixed X` →「X を修正」/ `added X` →「X を追加」
  - 名詞句のみの項目は動詞化せず体言止めのまま受ける

## プロジェクト固有の例外(あれば)

このプロジェクトで方針として決めたことだけを書く。例: `validate_po.py` の `NUM_SPACING_TOKEN`
(バージョン番号直後のスペース)は WARN のまま受け入れ、`--ignore NUM_SPACING_TOKEN` で抑制する。
Skill のルールを上書きする内容は書かない。

## 既存訳の見本

同じプロジェクトの別 `.po`(UI ↔ readme)に翻訳済みエントリーがあれば、文体・語尾の見本として
2〜3 件そのまま引用する。ゼロから始めるより揃う。

## [要確認]

確定させなかった語を列挙し、フェーズ④で用語集・Consistency Tool・翻訳コミュニティへの相談に回す。
```

---

## 作り方の手順

1. `po_chunk.py` が出す `wordfreq.txt` の上位 50 語を見る
2. 原文中の大文字始まりの語・製品名を「翻訳しない固有名詞」に集める
3. 頻出動詞・名詞を `references/glossary.md` で原語から引いて「一般訳語」表を作る
4. 同じプロジェクトの別 `.po` から既存訳を引用する
5. **ユーザーに提示して確認を取る**(フェーズ①の最後。ここを飛ばすと数百件を訳し直すことになる)
