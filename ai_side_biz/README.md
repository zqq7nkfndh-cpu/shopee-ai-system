# Shopee AI副業システム

Shopee専用のStreamlit運用ツールです。  
AIで出品候補を作成し、**人間の承認後にのみ**出品へ進める運用を前提にしています。

## できること

- Shopee向け商品候補の入力・管理（CSV）
- 利益計算（手数料・送料・利益率・最低価格）
- 英語タイトル/説明文の下書き生成
- リスクチェック（高リスク商品の警告）
- 承認/却下フロー
- 承認済みCSV/JSONエクスポート
- note週次レポート下書き生成（Shopee実績ベース）
- DRY_RUN前提のShopee APIプレースホルダー

## セットアップ

```bash
cd ai_side_biz
python -m venv venv
source venv/bin/activate   # Windowsは venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

## 起動

```bash
cd ai_side_biz
streamlit run app.py
```

## 主なファイル

- `data/shopee_trend_input.csv` : 入力データ
- `outputs/shopee_listing_drafts.csv` : 出品下書き
- `outputs/dashboard.csv` : 統合管理CSV
- `outputs/note_weekly_report.md` : note下書き

## 運用フロー

1. 商品入力エディタで候補を登録
2. 出品下書きを生成
3. 下書き確認ページで利益・リスク・説明文を確認
4. 承認/却下を実行
5. 承認済みのみエクスポートしてShopee Seller Centerで手動出品

## 安全運用

- 高リスク商品は承認前に必ず人間が確認
- `shopee_api.py` は `DRY_RUN=True`（初期値）を維持
- 本番API連携は準備完了後に段階的に実施
