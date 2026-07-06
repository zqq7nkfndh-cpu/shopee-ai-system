# -*- coding: utf-8 -*-
"""
config.py
共通設定 — Shopee越境EC専用システム
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

# --- APIキー類 ---
SHOPEE_PARTNER_ID = os.getenv("SHOPEE_PARTNER_ID", "")
SHOPEE_PARTNER_KEY = os.getenv("SHOPEE_PARTNER_KEY", "")
SHOPEE_SHOP_ID = os.getenv("SHOPEE_SHOP_ID", "")
SHOPEE_ACCESS_TOKEN = os.getenv("SHOPEE_ACCESS_TOKEN", "")

# 旧互換 (Rakuten — 参照のみ)
RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- 為替レート (Shopee利益計算用概算。運用時は最新レートに更新) ---
DEFAULT_JPY_PER_USD = float(os.getenv("JPY_PER_USD", "150"))

# --- 出品下書きCSVスキーマ ---
CSV_COLUMNS = [
    "date", "country", "genre", "product_name", "source_url",
    "trend_reason", "target_customer",
    "cost_price_jpy", "shipping_cost_jpy",
    "expected_selling_price_jpy",
    "selling_price_jpy", "selling_price_usd",
    "fee_estimate_jpy", "profit_jpy", "profit_margin",
    "min_price_no_loss_jpy",
    "risk_level", "risk_reason",
    "shopee_title", "shopee_description",
    "bullet_points", "keywords",
    "category_suggestion", "selling_points", "caution_notes",
    "status", "approved",
]

# --- 商品入力CSVスキーマ ---
SHOPEE_INPUT_COLUMNS = [
    "country", "genre", "product_name", "trend_reason",
    "source_url", "cost_price_jpy", "shipping_cost_jpy",
    "expected_selling_price_jpy",
]

# Shopeeの主要ターゲット国
SHOPEE_TARGET_COUNTRIES = [
    "Singapore", "Malaysia", "Taiwan",
    "Philippines", "Thailand", "Vietnam",
]
