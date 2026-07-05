# -*- coding: utf-8 -*-
"""
config.py
共通設定。.env からAPIキー等を読み込み、各モジュールで使う定数を定義する。

【重要ルール(このシステム全体で守ること)】
- 楽天ROOMへの自動投稿・自動コメントは絶対に行わない(このリポジトリにその機能は実装しない)
- 楽天ROOMの商品画像を保存・加工して再アップロードしない
- Shopeeは完全自動出品しない。出品下書きCSVを作るところまで。
- CSVの approved 列が TRUE のものだけ、人間が最終確認の上で手動 or 別途承認済み処理に回す
- 価格決定・最終投稿・最終出品は必ず人間が行う
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# --- APIキー類(.envに設定。無くてもサンプルデータで動作する) ---
RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID", "")
RAKUTEN_AFFILIATE_ID = os.getenv("RAKUTEN_AFFILIATE_ID", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # 任意: 文章生成の質を上げたい場合
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")        # 任意: 代替LLMを使いたい場合

# --- 為替(Shopee利益計算用の簡易レート。運用時は都度最新レートに更新すること) ---
DEFAULT_JPY_PER_USD = float(os.getenv("JPY_PER_USD", "150"))

# --- dashboard.csv / 各種CSVの統一スキーマ ---
CSV_COLUMNS = [
    "date", "platform", "country", "genre", "product_name", "source_url",
    "trend_reason", "season_reason", "target_customer",
    "cost_price", "selling_price", "shipping_cost", "fee_estimate",
    "profit", "profit_margin",
    "risk_level", "risk_reason",
    "room_text", "shopee_title", "shopee_description",
    "note_angle", "status", "approved",
]

# --- 月ごとの季節・イベントキーワード(日本市場向け。適宜追記・修正してください) ---
SEASON_EVENTS = {
    1:  ["正月", "福袋", "成人式", "防寒", "寒さ対策"],
    2:  ["バレンタイン", "節分", "花粉症対策"],
    3:  ["卒業式", "花見", "春の新生活", "花粉症"],
    4:  ["入学式", "新生活", "花粉症", "GW準備"],
    5:  ["GW", "母の日", "衣替え", "紫外線対策"],
    6:  ["梅雨", "父の日", "紫外線対策", "湿気対策"],
    7:  ["夏休み", "七夕", "猛暑対策", "熱中症対策"],
    8:  ["お盆", "夏休み", "熱中症対策", "台風対策"],
    9:  ["防災の日", "敬老の日", "運動会", "台風対策"],
    10: ["ハロウィン", "衣替え", "運動会", "秋の行楽"],
    11: ["七五三", "ブラックフライデー", "紅葉", "冬支度"],
    12: ["クリスマス", "年末年始", "大掃除", "帰省"],
}

# Shopeeの主要ターゲット国(必要に応じて増減してください)
SHOPEE_TARGET_COUNTRIES = ["Singapore", "Malaysia", "Taiwan", "Philippines", "Thailand", "Vietnam"]
