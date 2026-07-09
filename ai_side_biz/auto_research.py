# -*- coding: utf-8 -*-
"""
auto_research.py — Shopee越境EC 自動商品リサーチエンジン

外部APIなしで動作する日本商品データベース＋スコアリングシステム。
- 高リスクカテゴリ（食品・化粧品・医薬品など）は自動除外
- 5軸スコアリング（海外需要・日本独自性・配送しやすさ・規制リスク・利益性）
- 季節・キーワード・市場フィルタリング
- 出品下書き自動生成（DRY_RUN=True / Shopee出品は一切行わない）
"""
import csv
import datetime
import json
import random
from pathlib import Path
from typing import Optional

from config import CSV_COLUMNS, OUTPUT_DIR, DATA_DIR
from risk_checker import check_risk, export_customs_note
from shopee_research import calculate_finance, generate_shopee_copy

# ── 高リスク除外カテゴリ ───────────────────────────────────────────────
HIGH_RISK_CATEGORIES = {
    "food", "supplement", "cosmetic", "medicine", "drug", "battery",
    "liquid", "branded", "character", "fragile", "heavy", "alcohol",
    "tobacco", "weapon", "chemical", "flammable",
}

HIGH_RISK_KEYWORDS = [
    "食品", "飲料", "サプリ", "栄養", "美容液", "化粧", "薬", "電池",
    "リチウム", "液体", "ブランド", "キャラクター", "ガラス", "陶器",
    "重い", "大型", "アルコール", "香水", "ヘアカラー", "漂白",
]

# ── 商品データベース（60+件）─────────────────────────────────────────
PRODUCT_DATABASE = [
    # ── 文具・雑貨 ────────────────────────────────────────────────────
    {
        "product_name_ja": "マスキングテープセット",
        "genre": "Stationery", "category": "stationery",
        "typical_cost_jpy": 400, "typical_shipping_jpy": 300,
        "typical_weight_g": 80,
        "overseas_demand": 5, "japan_uniqueness": 5,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines", "Thailand"],
        "seasons": ["all"],
        "keywords": ["washi tape", "masking tape", "stationery", "craft"],
        "trend_reason": "Japanese washi tape is globally popular for journaling and crafts",
        "target_customer": "Craft lovers, students, journal keepers",
    },
    {
        "product_name_ja": "ゲルインクボールペンセット",
        "genre": "Stationery", "category": "stationery",
        "typical_cost_jpy": 500, "typical_shipping_jpy": 300,
        "typical_weight_g": 100,
        "overseas_demand": 4, "japan_uniqueness": 4,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines"],
        "seasons": ["all"],
        "keywords": ["gel pen", "japanese pen", "stationery", "writing"],
        "trend_reason": "Japanese pens (Pilot, Zebra, Uni) have worldwide cult following",
        "target_customer": "Students, office workers, stationery collectors",
    },
    {
        "product_name_ja": "手帳・システム手帳",
        "genre": "Stationery", "category": "stationery",
        "typical_cost_jpy": 1200, "typical_shipping_jpy": 400,
        "typical_weight_g": 200,
        "overseas_demand": 4, "japan_uniqueness": 5,
        "shipping_ease": 4, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Taiwan", "Singapore", "Malaysia"],
        "seasons": ["autumn", "winter"],
        "keywords": ["japanese planner", "techo", "hobonichi", "diary"],
        "trend_reason": "Hobonichi-style planners are trending in Asia",
        "target_customer": "Productivity enthusiasts, stationery fans",
    },
    {
        "product_name_ja": "スタンプセット（はんこ）",
        "genre": "Stationery", "category": "stationery",
        "typical_cost_jpy": 600, "typical_shipping_jpy": 300,
        "typical_weight_g": 120,
        "overseas_demand": 4, "japan_uniqueness": 5,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Taiwan", "Singapore", "Malaysia", "Thailand"],
        "seasons": ["all"],
        "keywords": ["japanese stamp", "hanko", "craft stamp", "scrapbooking"],
        "trend_reason": "Japanese rubber stamps popular in scrapbooking community",
        "target_customer": "Craft lovers, journal keepers",
    },
    {
        "product_name_ja": "ふせん・付箋紙セット",
        "genre": "Stationery", "category": "stationery",
        "typical_cost_jpy": 350, "typical_shipping_jpy": 250,
        "typical_weight_g": 60,
        "overseas_demand": 4, "japan_uniqueness": 4,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines"],
        "seasons": ["all"],
        "keywords": ["sticky notes", "memo pad", "japanese stationery", "kawaii"],
        "trend_reason": "Cute Japanese sticky notes popular for office and study",
        "target_customer": "Students, office workers, stationery fans",
    },
    # ── キッチン・日用品 ───────────────────────────────────────────────
    {
        "product_name_ja": "弁当箱・ランチボックス",
        "genre": "Kitchen", "category": "kitchen",
        "typical_cost_jpy": 800, "typical_shipping_jpy": 400,
        "typical_weight_g": 250,
        "overseas_demand": 5, "japan_uniqueness": 5,
        "shipping_ease": 4, "regulation_risk": 1, "profit_potential": 5,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines", "Thailand"],
        "seasons": ["all"],
        "keywords": ["bento box", "lunch box", "japanese bento", "food container"],
        "trend_reason": "Japanese bento culture is globally trending via social media",
        "target_customer": "Health-conscious adults, parents, students",
    },
    {
        "product_name_ja": "竹製箸セット",
        "genre": "Kitchen", "category": "kitchen",
        "typical_cost_jpy": 400, "typical_shipping_jpy": 250,
        "typical_weight_g": 80,
        "overseas_demand": 4, "japan_uniqueness": 4,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Thailand", "Vietnam"],
        "seasons": ["all"],
        "keywords": ["japanese chopsticks", "bamboo chopsticks", "reusable chopsticks"],
        "trend_reason": "Eco-friendly bamboo chopsticks in demand globally",
        "target_customer": "Eco-conscious consumers, Asian cuisine lovers",
    },
    {
        "product_name_ja": "台所スポンジ・クリーニングクロス",
        "genre": "Household", "category": "household",
        "typical_cost_jpy": 300, "typical_shipping_jpy": 200,
        "typical_weight_g": 50,
        "overseas_demand": 4, "japan_uniqueness": 4,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan"],
        "seasons": ["all"],
        "keywords": ["japanese sponge", "kitchen sponge", "cleaning cloth", "microfiber"],
        "trend_reason": "Japanese cleaning products known for quality and durability",
        "target_customer": "Homemakers, housewives, cleaning enthusiasts",
    },
    {
        "product_name_ja": "シリコン調理用品セット",
        "genre": "Kitchen", "category": "kitchen",
        "typical_cost_jpy": 900, "typical_shipping_jpy": 350,
        "typical_weight_g": 180,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines"],
        "seasons": ["all"],
        "keywords": ["silicone kitchen tools", "cooking utensils", "japanese kitchen"],
        "trend_reason": "Silicone kitchen tools trending for safety and durability",
        "target_customer": "Home cooks, parents with young children",
    },
    {
        "product_name_ja": "折りたたみ式水切りラック",
        "genre": "Kitchen", "category": "kitchen",
        "typical_cost_jpy": 1200, "typical_shipping_jpy": 500,
        "typical_weight_g": 400,
        "overseas_demand": 4, "japan_uniqueness": 4,
        "shipping_ease": 3, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Taiwan", "Malaysia"],
        "seasons": ["all"],
        "keywords": ["dish drying rack", "foldable rack", "japanese kitchen", "space saving"],
        "trend_reason": "Space-saving Japanese kitchen tools popular in small apartments",
        "target_customer": "Urban dwellers, apartment renters",
    },
    # ── ヘアケア・美容用品（化粧品除く） ─────────────────────────────
    {
        "product_name_ja": "ヘアゴム・ヘアアクセサリーセット",
        "genre": "Fashion Accessories", "category": "accessories",
        "typical_cost_jpy": 400, "typical_shipping_jpy": 200,
        "typical_weight_g": 60,
        "overseas_demand": 5, "japan_uniqueness": 4,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 5,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines", "Thailand", "Vietnam"],
        "seasons": ["all"],
        "keywords": ["hair accessories", "hair ties", "japanese hair", "scrunchie"],
        "trend_reason": "Japanese kawaii hair accessories trending across Southeast Asia",
        "target_customer": "Women aged 15-35, fashion-conscious shoppers",
    },
    {
        "product_name_ja": "ヘアブラシ・クシセット",
        "genre": "Personal Care", "category": "personal_care",
        "typical_cost_jpy": 700, "typical_shipping_jpy": 300,
        "typical_weight_g": 150,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Thailand"],
        "seasons": ["all"],
        "keywords": ["hair brush", "japanese comb", "detangling brush", "wide tooth comb"],
        "trend_reason": "Japanese hair tools known for quality bristles and ergonomic design",
        "target_customer": "Women, hair care enthusiasts",
    },
    # ── ファッション・アクセサリー ─────────────────────────────────────
    {
        "product_name_ja": "手袋（手芸・防寒用）",
        "genre": "Fashion", "category": "fashion",
        "typical_cost_jpy": 500, "typical_shipping_jpy": 250,
        "typical_weight_g": 80,
        "overseas_demand": 3, "japan_uniqueness": 3,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 3,
        "countries": ["Taiwan", "Singapore"],
        "seasons": ["autumn", "winter"],
        "keywords": ["gloves", "winter gloves", "japanese fashion", "cold weather"],
        "trend_reason": "Winter accessories from Japan valued for quality",
        "target_customer": "Fashion-conscious adults in cooler climates",
    },
    {
        "product_name_ja": "エコバッグ・折りたたみバッグ",
        "genre": "Bags", "category": "bags",
        "typical_cost_jpy": 600, "typical_shipping_jpy": 300,
        "typical_weight_g": 100,
        "overseas_demand": 4, "japan_uniqueness": 4,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines", "Thailand"],
        "seasons": ["all"],
        "keywords": ["eco bag", "reusable bag", "foldable bag", "japanese bag"],
        "trend_reason": "Eco-friendly foldable bags trending with environmentally conscious consumers",
        "target_customer": "Eco-conscious shoppers, working adults",
    },
    {
        "product_name_ja": "がま口財布・小物入れ",
        "genre": "Bags & Accessories", "category": "bags",
        "typical_cost_jpy": 800, "typical_shipping_jpy": 300,
        "typical_weight_g": 100,
        "overseas_demand": 4, "japan_uniqueness": 5,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Taiwan", "Singapore", "Malaysia", "Thailand"],
        "seasons": ["all"],
        "keywords": ["gamaguchi", "coin purse", "japanese purse", "traditional japanese"],
        "trend_reason": "Traditional Japanese clasp purses popular for their unique style",
        "target_customer": "Women who appreciate Japanese traditional design",
    },
    {
        "product_name_ja": "コンパクト折りたたみ傘",
        "genre": "Fashion Accessories", "category": "accessories",
        "typical_cost_jpy": 1500, "typical_shipping_jpy": 400,
        "typical_weight_g": 250,
        "overseas_demand": 4, "japan_uniqueness": 4,
        "shipping_ease": 4, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines"],
        "seasons": ["spring", "summer"],
        "keywords": ["compact umbrella", "japanese umbrella", "foldable umbrella", "UV umbrella"],
        "trend_reason": "Japanese UV-protective umbrellas in demand in tropical countries",
        "target_customer": "Working adults, outdoor enthusiasts",
    },
    # ── ホーム・インテリア ─────────────────────────────────────────────
    {
        "product_name_ja": "収納ボックス・整理グッズ",
        "genre": "Home & Living", "category": "home",
        "typical_cost_jpy": 800, "typical_shipping_jpy": 400,
        "typical_weight_g": 200,
        "overseas_demand": 4, "japan_uniqueness": 4,
        "shipping_ease": 4, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan"],
        "seasons": ["all"],
        "keywords": ["storage box", "organizer", "japanese organization", "muji style"],
        "trend_reason": "Japanese minimalist home organization products trending globally",
        "target_customer": "Home organization enthusiasts, minimalism fans",
    },
    {
        "product_name_ja": "アロマディフューザー（電池/USB式）",
        "genre": "Home & Living", "category": "home",
        "typical_cost_jpy": 1200, "typical_shipping_jpy": 400,
        "typical_weight_g": 200,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 4, "regulation_risk": 2, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Thailand"],
        "seasons": ["all"],
        "keywords": ["aroma diffuser", "essential oil diffuser", "japanese aroma", "home fragrance"],
        "trend_reason": "Aromatherapy home products trending for wellness lifestyle",
        "target_customer": "Wellness-focused adults, work-from-home workers",
    },
    {
        "product_name_ja": "風呂敷（マルチクロス）",
        "genre": "Home & Living", "category": "home",
        "typical_cost_jpy": 700, "typical_shipping_jpy": 250,
        "typical_weight_g": 100,
        "overseas_demand": 4, "japan_uniqueness": 5,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Thailand"],
        "seasons": ["all"],
        "keywords": ["furoshiki", "japanese wrapping cloth", "eco wrap", "traditional japanese"],
        "trend_reason": "Traditional furoshiki cloth gaining popularity as eco-friendly gift wrap",
        "target_customer": "Eco-conscious consumers, Japanese culture enthusiasts",
    },
    {
        "product_name_ja": "木製インテリア雑貨",
        "genre": "Home Decor", "category": "home",
        "typical_cost_jpy": 900, "typical_shipping_jpy": 400,
        "typical_weight_g": 200,
        "overseas_demand": 4, "japan_uniqueness": 4,
        "shipping_ease": 4, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan"],
        "seasons": ["all"],
        "keywords": ["wood decor", "japanese home decor", "wooden ornament", "natural wood"],
        "trend_reason": "Natural wood home decor trending in minimalist interior design",
        "target_customer": "Home decor enthusiasts, interior design fans",
    },
    {
        "product_name_ja": "珪藻土バスマット",
        "genre": "Home & Living", "category": "home",
        "typical_cost_jpy": 1500, "typical_shipping_jpy": 500,
        "typical_weight_g": 500,
        "overseas_demand": 5, "japan_uniqueness": 5,
        "shipping_ease": 3, "regulation_risk": 1, "profit_potential": 5,
        "countries": ["Taiwan", "Singapore", "Malaysia"],
        "seasons": ["all"],
        "keywords": ["diatomite bath mat", "japanese bath mat", "stone bath mat", "quick dry"],
        "trend_reason": "Japanese diatomite bath mats are viral on social media for quick-drying properties",
        "target_customer": "Homeowners, bathroom upgrade enthusiasts",
    },
    # ── ペットケア ────────────────────────────────────────────────────
    {
        "product_name_ja": "ペット用おもちゃ",
        "genre": "Pet Care", "category": "pet",
        "typical_cost_jpy": 500, "typical_shipping_jpy": 300,
        "typical_weight_g": 80,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Thailand"],
        "seasons": ["all"],
        "keywords": ["pet toy", "cat toy", "dog toy", "japanese pet"],
        "trend_reason": "Pet humanization trend driving premium pet product demand",
        "target_customer": "Pet owners, dog and cat lovers",
    },
    {
        "product_name_ja": "ペット用食器・フードボウル",
        "genre": "Pet Care", "category": "pet",
        "typical_cost_jpy": 800, "typical_shipping_jpy": 350,
        "typical_weight_g": 200,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 4, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan"],
        "seasons": ["all"],
        "keywords": ["pet bowl", "cat bowl", "dog bowl", "japanese pet accessories"],
        "trend_reason": "Premium pet bowls trending with pet humanization movement",
        "target_customer": "Pet owners who treat pets like family",
    },
    # ── スポーツ・アウトドア ────────────────────────────────────────────
    {
        "product_name_ja": "スポーツタオル・マイクロファイバータオル",
        "genre": "Sports & Outdoors", "category": "sports",
        "typical_cost_jpy": 500, "typical_shipping_jpy": 250,
        "typical_weight_g": 100,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines", "Thailand"],
        "seasons": ["summer", "all"],
        "keywords": ["microfiber towel", "sports towel", "japanese towel", "gym towel"],
        "trend_reason": "Japanese quality microfiber towels popular for sports and outdoor activities",
        "target_customer": "Sports enthusiasts, gym goers, outdoor lovers",
    },
    {
        "product_name_ja": "アウトドア折りたたみグッズ",
        "genre": "Sports & Outdoors", "category": "sports",
        "typical_cost_jpy": 1000, "typical_shipping_jpy": 400,
        "typical_weight_g": 300,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 4, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Thailand"],
        "seasons": ["spring", "summer", "autumn"],
        "keywords": ["outdoor gear", "foldable", "camping", "japanese outdoor"],
        "trend_reason": "Outdoor camping culture growing in Southeast Asia",
        "target_customer": "Outdoor enthusiasts, campers, hikers",
    },
    # ── テクノロジー・ガジェット（電池不使用） ─────────────────────────
    {
        "product_name_ja": "スマホリング・スタンド",
        "genre": "Electronics Accessories", "category": "tech_accessories",
        "typical_cost_jpy": 500, "typical_shipping_jpy": 250,
        "typical_weight_g": 50,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines", "Thailand"],
        "seasons": ["all"],
        "keywords": ["phone ring holder", "smartphone stand", "pop socket", "japanese"],
        "trend_reason": "Smartphone accessories always in demand with phone-dependent lifestyle",
        "target_customer": "Smartphone users aged 15-40",
    },
    {
        "product_name_ja": "ケーブルオーガナイザー",
        "genre": "Electronics Accessories", "category": "tech_accessories",
        "typical_cost_jpy": 400, "typical_shipping_jpy": 200,
        "typical_weight_g": 50,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines"],
        "seasons": ["all"],
        "keywords": ["cable organizer", "cable management", "desk organization", "tech accessories"],
        "trend_reason": "Work-from-home trend driving demand for desk organization products",
        "target_customer": "Work-from-home workers, tech enthusiasts",
    },
    {
        "product_name_ja": "ノートPCスタンド（折りたたみ）",
        "genre": "Electronics Accessories", "category": "tech_accessories",
        "typical_cost_jpy": 1500, "typical_shipping_jpy": 500,
        "typical_weight_g": 350,
        "overseas_demand": 5, "japan_uniqueness": 3,
        "shipping_ease": 4, "regulation_risk": 1, "profit_potential": 5,
        "countries": ["Singapore", "Malaysia", "Taiwan"],
        "seasons": ["all"],
        "keywords": ["laptop stand", "notebook stand", "ergonomic stand", "work from home"],
        "trend_reason": "Remote work driving laptop stand demand globally",
        "target_customer": "Remote workers, students, office workers",
    },
    # ── 美容用品（化粧品除く） ─────────────────────────────────────────
    {
        "product_name_ja": "フェイスローラー（ステンレス製）",
        "genre": "Beauty Tools", "category": "beauty_tools",
        "typical_cost_jpy": 800, "typical_shipping_jpy": 300,
        "typical_weight_g": 120,
        "overseas_demand": 5, "japan_uniqueness": 4,
        "shipping_ease": 5, "regulation_risk": 2, "profit_potential": 5,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Thailand", "Philippines"],
        "seasons": ["all"],
        "keywords": ["face roller", "facial massager", "beauty tool", "skincare tool"],
        "trend_reason": "Face rolling tools viral on social media for skin massage",
        "target_customer": "Women aged 20-40, beauty enthusiasts",
    },
    {
        "product_name_ja": "頭皮マッサージャー",
        "genre": "Beauty Tools", "category": "beauty_tools",
        "typical_cost_jpy": 700, "typical_shipping_jpy": 300,
        "typical_weight_g": 100,
        "overseas_demand": 5, "japan_uniqueness": 4,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 5,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Thailand", "Philippines"],
        "seasons": ["all"],
        "keywords": ["scalp massager", "hair massager", "head massager", "japanese beauty"],
        "trend_reason": "Scalp care trend growing with focus on hair health",
        "target_customer": "Women and men interested in hair health",
    },
    {
        "product_name_ja": "アイマスク（睡眠用・遮光）",
        "genre": "Personal Care", "category": "personal_care",
        "typical_cost_jpy": 600, "typical_shipping_jpy": 200,
        "typical_weight_g": 50,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Thailand"],
        "seasons": ["all"],
        "keywords": ["sleep mask", "eye mask", "blackout mask", "japanese sleep"],
        "trend_reason": "Sleep quality focus driving demand for sleep accessories",
        "target_customer": "Adults with sleep concerns, frequent travelers",
    },
    {
        "product_name_ja": "シルクヘアバンド・ナイトキャップ",
        "genre": "Beauty Tools", "category": "beauty_tools",
        "typical_cost_jpy": 700, "typical_shipping_jpy": 250,
        "typical_weight_g": 80,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines"],
        "seasons": ["all"],
        "keywords": ["silk hair band", "night cap", "hair care", "beauty accessories"],
        "trend_reason": "Silk hair accessories trending for hair health maintenance",
        "target_customer": "Women interested in hair protection",
    },
    # ── 趣味・ホビー ──────────────────────────────────────────────────
    {
        "product_name_ja": "色鉛筆セット（高品質）",
        "genre": "Art & Craft", "category": "art_craft",
        "typical_cost_jpy": 1200, "typical_shipping_jpy": 400,
        "typical_weight_g": 300,
        "overseas_demand": 4, "japan_uniqueness": 4,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Taiwan", "Singapore", "Malaysia", "Thailand"],
        "seasons": ["all"],
        "keywords": ["colored pencils", "japanese art supplies", "drawing pencils", "artist pencils"],
        "trend_reason": "Japanese art supplies (Faber-Castell, Tombow) trusted by artists worldwide",
        "target_customer": "Artists, art students, hobbyists",
    },
    {
        "product_name_ja": "水彩絵の具セット",
        "genre": "Art & Craft", "category": "art_craft",
        "typical_cost_jpy": 900, "typical_shipping_jpy": 350,
        "typical_weight_g": 200,
        "overseas_demand": 4, "japan_uniqueness": 4,
        "shipping_ease": 4, "regulation_risk": 2, "profit_potential": 4,
        "countries": ["Taiwan", "Singapore", "Malaysia"],
        "seasons": ["all"],
        "keywords": ["watercolor", "watercolor set", "japanese art", "painting supplies"],
        "trend_reason": "Watercolor painting trending as relaxation hobby",
        "target_customer": "Hobbyist painters, art students",
    },
    {
        "product_name_ja": "刺繍キット・手芸セット",
        "genre": "Art & Craft", "category": "art_craft",
        "typical_cost_jpy": 1000, "typical_shipping_jpy": 350,
        "typical_weight_g": 150,
        "overseas_demand": 4, "japan_uniqueness": 5,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Taiwan", "Singapore", "Malaysia", "Thailand"],
        "seasons": ["winter"],
        "keywords": ["embroidery kit", "japanese embroidery", "sewing kit", "cross stitch"],
        "trend_reason": "Handcraft revival trending during stay-at-home lifestyle",
        "target_customer": "Craft hobbyists, women aged 25-50",
    },
    # ── 健康・ウェルネス（医薬品除く） ────────────────────────────────
    {
        "product_name_ja": "ヨガマット（薄型・折りたたみ）",
        "genre": "Sports & Fitness", "category": "sports",
        "typical_cost_jpy": 1500, "typical_shipping_jpy": 600,
        "typical_weight_g": 700,
        "overseas_demand": 5, "japan_uniqueness": 3,
        "shipping_ease": 3, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Thailand"],
        "seasons": ["all"],
        "keywords": ["yoga mat", "travel yoga mat", "foldable yoga mat", "fitness mat"],
        "trend_reason": "Home fitness trend driving yoga mat demand globally",
        "target_customer": "Yoga practitioners, fitness enthusiasts",
    },
    {
        "product_name_ja": "ストレッチポール・フォームローラー",
        "genre": "Sports & Fitness", "category": "sports",
        "typical_cost_jpy": 2000, "typical_shipping_jpy": 600,
        "typical_weight_g": 500,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 3, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Taiwan", "Malaysia"],
        "seasons": ["all"],
        "keywords": ["foam roller", "muscle roller", "stretching", "recovery tool"],
        "trend_reason": "Muscle recovery tools trending with fitness lifestyle",
        "target_customer": "Athletes, office workers with muscle tension",
    },
    {
        "product_name_ja": "指圧グッズ・ツボ押し",
        "genre": "Health & Wellness", "category": "personal_care",
        "typical_cost_jpy": 600, "typical_shipping_jpy": 300,
        "typical_weight_g": 100,
        "overseas_demand": 4, "japan_uniqueness": 5,
        "shipping_ease": 5, "regulation_risk": 2, "profit_potential": 4,
        "countries": ["Taiwan", "Singapore", "Malaysia", "Thailand"],
        "seasons": ["all"],
        "keywords": ["acupressure tool", "shiatsu", "pressure point", "japanese wellness"],
        "trend_reason": "Traditional Japanese wellness tools gaining global attention",
        "target_customer": "Health-conscious adults, office workers",
    },
    # ── 季節商品 ──────────────────────────────────────────────────────
    {
        "product_name_ja": "ハンディファン・携帯扇風機（USB充電式）",
        "genre": "Electronics Accessories", "category": "tech_accessories",
        "typical_cost_jpy": 1200, "typical_shipping_jpy": 400,
        "typical_weight_g": 150,
        "overseas_demand": 5, "japan_uniqueness": 3,
        "shipping_ease": 4, "regulation_risk": 2, "profit_potential": 5,
        "countries": ["Singapore", "Malaysia", "Philippines", "Thailand", "Vietnam"],
        "seasons": ["summer"],
        "keywords": ["handheld fan", "portable fan", "USB fan", "cooling fan"],
        "trend_reason": "Portable fans essential in tropical Southeast Asian climate",
        "target_customer": "Outdoor workers, commuters in hot climates",
    },
    {
        "product_name_ja": "カイロ・ホッカイロ（使い捨て）",
        "genre": "Seasonal", "category": "seasonal",
        "typical_cost_jpy": 300, "typical_shipping_jpy": 250,
        "typical_weight_g": 100,
        "overseas_demand": 4, "japan_uniqueness": 5,
        "shipping_ease": 5, "regulation_risk": 2, "profit_potential": 4,
        "countries": ["Taiwan", "Singapore"],
        "seasons": ["winter"],
        "keywords": ["hand warmer", "heat pack", "japanese warmer", "pocket warmer"],
        "trend_reason": "Japanese disposable hand warmers loved globally for quality",
        "target_customer": "Outdoor workers, winter sports enthusiasts",
    },
    {
        "product_name_ja": "虫除けグッズ（非スプレー）",
        "genre": "Seasonal", "category": "seasonal",
        "typical_cost_jpy": 500, "typical_shipping_jpy": 250,
        "typical_weight_g": 100,
        "overseas_demand": 4, "japan_uniqueness": 4,
        "shipping_ease": 5, "regulation_risk": 2, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Philippines", "Thailand", "Vietnam"],
        "seasons": ["summer"],
        "keywords": ["mosquito repellent", "insect repellent patch", "bug patch", "japanese"],
        "trend_reason": "Mosquito repellent patches popular in tropical regions",
        "target_customer": "Parents, outdoor workers, travelers",
    },
    # ── キッズ・育児 ───────────────────────────────────────────────────
    {
        "product_name_ja": "知育おもちゃ（木製）",
        "genre": "Toys & Kids", "category": "toys",
        "typical_cost_jpy": 1200, "typical_shipping_jpy": 400,
        "typical_weight_g": 250,
        "overseas_demand": 5, "japan_uniqueness": 4,
        "shipping_ease": 4, "regulation_risk": 1, "profit_potential": 5,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Thailand"],
        "seasons": ["all"],
        "keywords": ["wooden toy", "educational toy", "japanese toy", "kids toy"],
        "trend_reason": "Wooden educational toys trending for screen-free child development",
        "target_customer": "Parents of young children aged 1-6",
    },
    {
        "product_name_ja": "ベビー用品（食器・スプーン）",
        "genre": "Baby & Kids", "category": "baby",
        "typical_cost_jpy": 800, "typical_shipping_jpy": 300,
        "typical_weight_g": 150,
        "overseas_demand": 4, "japan_uniqueness": 4,
        "shipping_ease": 5, "regulation_risk": 2, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines"],
        "seasons": ["all"],
        "keywords": ["baby spoon", "baby bowl", "japanese baby", "infant feeding"],
        "trend_reason": "Japanese baby products trusted for safety and BPA-free materials",
        "target_customer": "New parents, expecting mothers",
    },
    # ── 旅行・トラベル ─────────────────────────────────────────────────
    {
        "product_name_ja": "トラベルポーチ・旅行用整理袋",
        "genre": "Travel", "category": "travel",
        "typical_cost_jpy": 700, "typical_shipping_jpy": 300,
        "typical_weight_g": 120,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines"],
        "seasons": ["all"],
        "keywords": ["travel pouch", "packing organizer", "travel bag", "luggage organizer"],
        "trend_reason": "Post-pandemic travel revival driving demand for travel organizers",
        "target_customer": "Frequent travelers, business travelers",
    },
    {
        "product_name_ja": "圧縮袋（旅行用）",
        "genre": "Travel", "category": "travel",
        "typical_cost_jpy": 600, "typical_shipping_jpy": 250,
        "typical_weight_g": 80,
        "overseas_demand": 4, "japan_uniqueness": 3,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Philippines", "Thailand"],
        "seasons": ["all"],
        "keywords": ["compression bag", "space saver bag", "travel bag", "vacuum bag"],
        "trend_reason": "Travel compression bags popular for maximizing luggage space",
        "target_customer": "Travelers, backpackers",
    },
    # ── ギフト・ラッピング ─────────────────────────────────────────────
    {
        "product_name_ja": "和柄ラッピングペーパー・包装紙",
        "genre": "Gift & Packaging", "category": "gift",
        "typical_cost_jpy": 400, "typical_shipping_jpy": 200,
        "typical_weight_g": 80,
        "overseas_demand": 4, "japan_uniqueness": 5,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 4,
        "countries": ["Singapore", "Malaysia", "Taiwan", "Thailand"],
        "seasons": ["winter"],
        "keywords": ["japanese wrapping paper", "washi paper", "gift wrap", "japanese pattern"],
        "trend_reason": "Japanese traditional patterns popular for unique gift presentation",
        "target_customer": "Gift givers, event planners, Japan enthusiasts",
    },
    {
        "product_name_ja": "ポチ袋・和柄封筒セット",
        "genre": "Stationery", "category": "stationery",
        "typical_cost_jpy": 300, "typical_shipping_jpy": 150,
        "typical_weight_g": 50,
        "overseas_demand": 3, "japan_uniqueness": 5,
        "shipping_ease": 5, "regulation_risk": 1, "profit_potential": 3,
        "countries": ["Taiwan", "Singapore", "Malaysia"],
        "seasons": ["winter", "spring"],
        "keywords": ["pochi bag", "money envelope", "japanese envelope", "gift envelope"],
        "trend_reason": "Japanese money envelopes popular for gifts and special occasions",
        "target_customer": "People celebrating special occasions, Japan enthusiasts",
    },
]

# ── 季節カレンダー ────────────────────────────────────────────────────
def get_current_season() -> str:
    month = datetime.date.today().month
    if month in (3, 4, 5):
        return "spring"
    elif month in (6, 7, 8):
        return "summer"
    elif month in (9, 10, 11):
        return "autumn"
    else:
        return "winter"


def get_seasonal_events() -> list[str]:
    month = datetime.date.today().month
    events = {
        1: ["New Year (oshogatsu)", "Valentine prep"],
        2: ["Valentine's Day", "Spring Festival (CNY)"],
        3: ["Spring equinox", "Graduation season", "Sakura season start"],
        4: ["Hanami (cherry blossom viewing)", "New school/work year"],
        5: ["Golden Week", "Mother's Day", "Children's Day"],
        6: ["Rainy season (tsuyu) start", "Father's Day"],
        7: ["Summer vacation", "Tanabata", "Matsuri season"],
        8: ["Obon holiday", "Summer festivals", "Back to school prep"],
        9: ["Autumn start", "Tsukimi (moon viewing)", "Sports festivals"],
        10: ["Halloween", "Autumn foliage season"],
        11: ["Shichi-go-san", "Early Christmas prep"],
        12: ["Christmas", "Year-end gifts (oseibo)", "New Year prep"],
    }
    return events.get(month, [])


# ── スコア計算 ────────────────────────────────────────────────────────
def score_product(product: dict, target_margin: float = 0.30) -> dict:
    """5軸スコアを計算してスコアつき商品辞書を返す"""
    od = product.get("overseas_demand", 3)
    ju = product.get("japan_uniqueness", 3)
    se = product.get("shipping_ease", 3)
    rr = product.get("regulation_risk", 3)
    pp = product.get("profit_potential", 3)

    # 規制リスクは逆算（低いほど良い）
    reg_score = 6 - rr  # 1→5, 2→4, 3→3, 4→2, 5→1

    total = (od * 2 + ju * 2 + se + reg_score + pp) / 9 * 100
    score = min(100, round(total))

    # 利益計算
    cost = float(product.get("typical_cost_jpy", 500))
    ship = float(product.get("typical_shipping_jpy", 300))
    from shopee_research import calculate_finance
    finance = calculate_finance(cost, ship, target_margin=target_margin)

    return {
        **product,
        "score": score,
        "score_overseas_demand": od,
        "score_japan_uniqueness": ju,
        "score_shipping_ease": se,
        "score_regulation_risk": rr,
        "score_profit_potential": pp,
        "selling_price_jpy": finance["selling_price_jpy"],
        "profit_jpy": finance["profit_jpy"],
        "profit_margin_pct": round(finance["profit_margin"] * 100, 1),
    }


# ── フィルタリング ────────────────────────────────────────────────────
def filter_products(
    products: list[dict],
    keywords: list[str],
    countries: list[str],
    seasons_filter: list[str],
    min_score: int = 0,
) -> list[dict]:
    result = []
    for p in products:
        # 季節フィルタ
        p_seasons = p.get("seasons", ["all"])
        if "all" not in p_seasons:
            if not any(s in p_seasons for s in seasons_filter):
                continue

        # 国フィルタ
        p_countries = p.get("countries", [])
        if countries and not any(c in p_countries for c in countries):
            continue

        # キーワードフィルタ
        if keywords:
            p_text = (
                p.get("product_name_ja", "") +
                " ".join(p.get("keywords", [])) +
                p.get("genre", "") +
                p.get("trend_reason", "")
            ).lower()
            if not any(kw.lower() in p_text for kw in keywords):
                continue

        # スコアフィルタ
        if p.get("score", 0) < min_score:
            continue

        result.append(p)
    return result


def is_high_risk(product: dict) -> bool:
    """高リスク商品かどうかを判定（自動除外対象）"""
    cat = product.get("category", "").lower()
    name = product.get("product_name_ja", "").lower()
    genre = product.get("genre", "").lower()

    for hr in HIGH_RISK_CATEGORIES:
        if hr in cat or hr in genre:
            return True
    for kw in HIGH_RISK_KEYWORDS:
        if kw in name:
            return True
    return False


# ── リサーチ実行 ──────────────────────────────────────────────────────
def run_research(
    keywords: list[str] = None,
    countries: list[str] = None,
    min_score: int = 60,
    season_override: str = None,
    target_margin: float = 0.30,
    n_results: int = 20,
) -> list[dict]:
    """
    商品データベースから条件に合う商品をスコアリングして返す。
    高リスク商品は自動除外する。
    """
    keywords = keywords or []
    countries = countries or []
    season = season_override or get_current_season()

    # 全商品をスコアリング
    scored = [
        score_product(p, target_margin=target_margin)
        for p in PRODUCT_DATABASE
        if not is_high_risk(p)
    ]

    # フィルタリング
    filtered = filter_products(
        scored,
        keywords=keywords,
        countries=countries,
        seasons_filter=[season, "all"],
        min_score=min_score,
    )

    # スコア降順でソート
    filtered.sort(key=lambda x: x["score"], reverse=True)

    return filtered[:n_results]


# ── 出品下書き生成 ────────────────────────────────────────────────────
def generate_drafts_from_research(
    selected_products: list[dict],
    countries: list[str],
    target_margin: float = 0.30,
) -> list[dict]:
    """
    リサーチ結果から出品下書き行を生成する。
    既存の shopee_research.py の関数を再利用。
    Shopeeへの出品は行わない（DRY_RUN=True）。
    """
    today = datetime.date.today().isoformat()
    drafts = []

    for product in selected_products:
        target_countries = countries if countries else product.get("countries", ["Singapore"])

        for country in target_countries:
            cost = float(product.get("typical_cost_jpy", 500))
            ship = float(product.get("typical_shipping_jpy", 300))
            finance = calculate_finance(cost, ship, target_margin=target_margin)
            risk = check_risk(
                product.get("product_name_ja", ""),
                product.get("trend_reason", ""),
            )
            customs = export_customs_note(risk.categories, country)
            copy = generate_shopee_copy(
                product.get("product_name_ja", ""),
                product.get("genre", ""),
                country,
                product.get("trend_reason", ""),
            )

            row = {col: "" for col in CSV_COLUMNS}
            row.update({
                "date": today,
                "country": country,
                "genre": product.get("genre", ""),
                "product_name": product.get("product_name_ja", ""),
                "source_url": "",
                "trend_reason": product.get("trend_reason", ""),
                "target_customer": product.get("target_customer", ""),
                "cost_price_jpy": cost,
                "shipping_cost_jpy": ship,
                "expected_selling_price_jpy": finance["selling_price_jpy"],
                "selling_price_jpy": finance["selling_price_jpy"],
                "selling_price_usd": finance["selling_price_usd"],
                "fee_estimate_jpy": finance["fee_estimate_jpy"],
                "profit_jpy": finance["profit_jpy"],
                "profit_margin": finance["profit_margin"],
                "min_price_no_loss_jpy": finance["min_price_no_loss_jpy"],
                "risk_level": risk.risk_level,
                "risk_reason": risk.reasons + (f" / 通関: {customs}" if customs else ""),
                "shopee_title": copy["shopee_title"],
                "shopee_description": copy["shopee_description"],
                "bullet_points": copy["bullet_points"],
                "keywords": copy["keywords"],
                "category_suggestion": copy["category_suggestion"],
                "selling_points": copy["selling_points"],
                "caution_notes": copy["caution_notes"],
                "status": "draft_pending_human_approval",
                "approved": "FALSE",
            })
            drafts.append(row)

    return drafts


def append_drafts_to_csv(drafts: list[dict]) -> tuple[int, int]:
    """
    生成した下書きを shopee_listing_drafts.csv に追記する。
    重複（product_name + country）はスキップ。
    追加件数と重複スキップ件数を返す。
    """
    out_path = OUTPUT_DIR / "shopee_listing_drafts.csv"

    existing = {}
    if out_path.exists():
        with open(out_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                key = (row.get("product_name", ""), row.get("country", ""))
                existing[key] = row

    added = 0
    skipped = 0
    for draft in drafts:
        key = (draft.get("product_name", ""), draft.get("country", ""))
        if key in existing:
            skipped += 1
        else:
            existing[key] = draft
            added += 1

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(existing.values())

    return added, skipped


def save_research_results(results: list[dict]) -> Path:
    """リサーチ結果をJSONに保存（セッション間の参照用）"""
    out_path = DATA_DIR / "auto_research_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return out_path


def load_research_results() -> list[dict]:
    """保存済みリサーチ結果を読み込む"""
    path = DATA_DIR / "auto_research_results.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []
