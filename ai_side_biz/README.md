# Shopee AI副業システム

Shopee専用のリサーチ・利益計算・出品下書き管理を行うローカルPythonツールです。  
最終的な出品可否の判断と実行は必ず人間が行います。

## できること

- Shopee向け商品候補の入力・管理（CSV）
- 出品下書きCSVの生成（英語タイトル/説明、利益計算、リスク判定）
- 承認/却下フロー（Streamlit UIから更新）
- 承認済み商品のCSV/JSONエクスポート
- DRY_RUN前提のShopee APIプレースホルダー
- 週次レポート（note下書き）生成

## セットアップ

```bash
cd ai_side_biz
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 起動

```bash
streamlit run app.py
```

## 補助コマンド

```bash
python main.py shopee
python main.py dashboard
python main.py note
python main.py all
```

## 主要ファイル

- 入力: `data/shopee_trend_input.csv`（なければテンプレート利用）
- 出品下書き: `outputs/shopee_listing_drafts.csv`
- ダッシュボードCSV: `outputs/dashboard.csv`
- 週次レポート: `outputs/note_weekly_report.md`

## 運用上の注意

- `approved=TRUE` は「承認済み記録」のみで、出品実行ではありません
- 高リスク商品は必ず人間が再確認してください
- `shopee_api.py` は初期状態 `DRY_RUN=True` のまま運用してください
