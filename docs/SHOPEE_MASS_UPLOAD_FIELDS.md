# 出品準備CSVについて（旧説明の訂正）

旧版は独自ヘッダーのCSVを「Shopee公式Mass Upload形式」と説明していましたが、国・カテゴリごとの最新テンプレートとの互換性を確認できていません。新アプリの出力は**出品準備・転記用CSV**です。

公式一括アップロードテンプレートをSeller Centerから入手し、このCSVから必要情報を転記してください。シート構造・必須属性・画像・物流・言語・価格の詳細は対象国とカテゴリの最新仕様で確認します。自動アップロード・出品はありません。

| 列 | 内容 |
|---|---|
| market / currency | 販売国コードと現地通貨 |
| sku / title / description | 人間が確認したSKU・タイトル・本文 |
| category_id / brand / condition | 対象国で確認したカテゴリ等 |
| price_local / stock | 現地売価・確認済みの在庫 |
| image_url | 利用権と公開可否を人間が確認する画像URL |
| weight_kg / length_cm / width_cm / height_cm | 梱包後の重量・寸法 |
| logistics / listing_language | 対象国で確認した物流・言語 |
| supplier_url | 内部参照用。Shopeeへ転記する項目ではない |
| template_note / format_notice | 確認メモと転記用であることの注意 |

「出品準備完了」状態を全件再検証します。期限切れ設定・未承認・高リスク・赤字・必須情報不足があれば国単位の出力を止めます。不備商品を黙って除外しません。文字列の数式注入を防ぐため、`=` / `+` / `-` / `@` などで始まる値には先頭にアポストロフィを付けます。

設定・根拠の詳細は [OFFICIAL_SOURCES.md](OFFICIAL_SOURCES.md) を参照してください。
