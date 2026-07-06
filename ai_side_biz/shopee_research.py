# -*- coding: utf-8 -*-
"""
shopee_research.py — Shopee越境EC 出品下書き生成

【運用ルール】
- 完全自動出品は行わない。出力はあくまで「出品下書きCSV」
- approved=TRUE の行だけ、人間が最終確認後に別途の出品作業に使う
- 禁止商品・規制カテゴリ・商標リスクは risk_checker で必ずチェック
"""
import csv
import datetime

from config import CSV_COLUMNS, SHOPEE_INPUT_COLUMNS, OUTPUT_DIR, DATA_DIR, DEFAULT_JPY_PER_USD
from risk_checker import check_risk, export_customs_note

TREND_INPUT_PATH = DATA_DIR / "shopee_trend_input.csv"
TREND_TEMPLATE_PATH = DATA_DIR / "shopee_trend_input_template.csv"

TRANSACTION_FEE_RATE = 0.05
SERVICE_FEE_RATE = 0.05
PAYMENT_FEE_RATE = 0.02
TOTAL_FEE_RATE = TRANSACTION_FEE_RATE + SERVICE_FEE_RATE + PAYMENT_FEE_RATE


def load_trend_input() -> list[dict]:
    path = TREND_INPUT_PATH if TREND_INPUT_PATH.exists() else TREND_TEMPLATE_PATH
    if not TREND_INPUT_PATH.exists():
        print(f"[shopee] {TREND_INPUT_PATH.name} が無いためテンプレートを使用します。")
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def calculate_finance(
    cost_price_jpy: float,
    shipping_cost_jpy: float,
    target_margin: float = 0.3,
    expected_selling_price_jpy: float = 0,
    jpy_per_usd: float = DEFAULT_JPY_PER_USD,
) -> dict:
    """
    目標利益率から推奨販売価格を逆算し、手数料・利益・損益分岐価格を計算。
    すべて概算。実際のShopee手数料・為替は最新情報に置き換えて使うこと。
    """
    cost = float(cost_price_jpy or 0)
    ship = float(shipping_cost_jpy or 0)
    base_cost = cost + ship

    denom = 1 - TOTAL_FEE_RATE - target_margin
    if denom <= 0:
        selling_price_jpy = base_cost * 2
    else:
        selling_price_jpy = base_cost / denom

    fee_estimate_jpy = selling_price_jpy * TOTAL_FEE_RATE
    profit_jpy = selling_price_jpy - base_cost - fee_estimate_jpy
    profit_margin = profit_jpy / selling_price_jpy if selling_price_jpy else 0
    selling_price_usd = selling_price_jpy / jpy_per_usd

    min_denom = 1 - TOTAL_FEE_RATE
    min_price_no_loss_jpy = base_cost / min_denom if min_denom > 0 else base_cost * 1.15

    exp = float(expected_selling_price_jpy or 0)
    if exp > 0:
        exp_fee = exp * TOTAL_FEE_RATE
        exp_profit = exp - base_cost - exp_fee
        exp_margin = exp_profit / exp if exp else 0
    else:
        exp_profit = profit_jpy
        exp_margin = profit_margin

    return {
        "selling_price_jpy": round(selling_price_jpy),
        "selling_price_usd": round(selling_price_usd, 2),
        "fee_estimate_jpy": round(fee_estimate_jpy),
        "profit_jpy": round(exp_profit if exp > 0 else profit_jpy),
        "profit_margin": round(exp_margin if exp > 0 else profit_margin, 3),
        "min_price_no_loss_jpy": round(min_price_no_loss_jpy),
    }


def _suggest_category(genre: str) -> str:
    genre_lower = genre.lower()
    mapping = {
        ("beauty", "cosmetic", "skincare", "makeup", "facial"): "Beauty & Personal Care",
        ("fashion", "clothing", "apparel", "wear", "shirt", "dress"): "Fashion",
        ("electronic", "gadget", "tech", "phone", "cable", "charger"): "Electronics",
        ("kitchen", "cooking", "cookware", "bento"): "Home & Kitchen",
        ("toy", "game", "hobby", "figure", "anime"): "Toys & Hobbies",
        ("stationery", "pen", "notebook", "office"): "Stationery & Office",
        ("health", "wellness", "fitness", "supplement"): "Health & Wellness",
        ("bag", "wallet", "accessory", "accessories"): "Bags & Accessories",
        ("home", "interior", "decor", "furniture"): "Home & Living",
        ("pet", "dog", "cat", "animal"): "Pet Care",
        ("sport", "outdoor", "exercise", "gym"): "Sports & Outdoors",
        ("food", "snack", "candy", "sweet"): "Food & Beverages",
    }
    for keys, category in mapping.items():
        if any(k in genre_lower for k in keys):
            return category
    return "Others"


def generate_shopee_copy(
    product_name_ja: str, genre: str, country: str, trend_reason: str
) -> dict:
    category = _suggest_category(genre)
    title = f"{product_name_ja} | Japan {genre} | Fast Ship"
    title = title[:60]

    description = (
        f"Authentic {genre} direct from Japan: {product_name_ja}. "
        f"Trending now — {trend_reason}. "
        f"Carefully packed and shipped from Japan. "
        f"Please check size/specs in photos before ordering. "
        f"Feel free to contact us with any questions!"
    )

    bullets = [
        f"✓ 100% authentic {genre} sourced directly from Japan",
        f"✓ Trending pick for {country} buyers — {trend_reason[:40]}",
        f"✓ Carefully packed to prevent damage during transit",
        f"✓ Fast international shipping with tracking number",
        f"✓ Satisfaction guaranteed — contact us if any issues",
    ]

    keywords = (
        f"japan, {genre.lower()}, japanese {genre.lower()}, "
        f"made in japan, {country.lower()} trending"
    )

    selling_points = [
        f"Direct Japan source — genuine quality",
        f"Popular trend item in {country} market",
        f"Reliable international shipping with tracking",
    ]

    caution = (
        "Please check product dimensions/specs carefully before purchasing. "
        "Colors may vary slightly due to monitor settings. "
        "Estimated delivery: 7–14 business days (international). "
        "Contact us before ordering if you have any concerns."
    )

    return {
        "shopee_title": title,
        "shopee_description": description,
        "bullet_points": " | ".join(bullets),
        "keywords": keywords,
        "category_suggestion": category,
        "selling_points": " | ".join(selling_points),
        "caution_notes": caution,
    }


def build_candidates(target_margin: float = 0.3) -> list[dict]:
    trend_rows = load_trend_input()
    today = datetime.date.today().isoformat()
    out_rows = []

    for t in trend_rows:
        product_name = t.get("product_name", "").strip()
        if not product_name:
            continue
        country = t.get("country", "")
        genre = t.get("genre", "")
        trend_reason = t.get("trend_reason", "")
        source_url = t.get("source_url", "")
        cost_price = t.get("cost_price_jpy", 0)
        shipping_cost = t.get("shipping_cost_jpy", 0)
        expected_price = t.get("expected_selling_price_jpy", 0)

        finance = calculate_finance(
            cost_price, shipping_cost,
            target_margin=target_margin,
            expected_selling_price_jpy=expected_price,
        )
        risk = check_risk(product_name, trend_reason)
        customs_note = export_customs_note(risk.categories, country)
        copy = generate_shopee_copy(product_name, genre, country, trend_reason)

        row: dict = {col: "" for col in CSV_COLUMNS}
        row.update({
            "date": today,
            "country": country,
            "genre": genre,
            "product_name": product_name,
            "source_url": source_url,
            "trend_reason": trend_reason,
            "target_customer": f"{country}のShopeeユーザー",
            "cost_price_jpy": cost_price,
            "shipping_cost_jpy": shipping_cost,
            "expected_selling_price_jpy": expected_price,
            "selling_price_jpy": finance["selling_price_jpy"],
            "selling_price_usd": finance["selling_price_usd"],
            "fee_estimate_jpy": finance["fee_estimate_jpy"],
            "profit_jpy": finance["profit_jpy"],
            "profit_margin": finance["profit_margin"],
            "min_price_no_loss_jpy": finance["min_price_no_loss_jpy"],
            "risk_level": risk.risk_level,
            "risk_reason": risk.reasons + (f" / 通関メモ: {customs_note}" if customs_note else ""),
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
        out_rows.append(row)

    return out_rows


def run(target_margin: float = 0.3) -> str:
    rows = build_candidates(target_margin=target_margin)
    out_path = OUTPUT_DIR / "shopee_listing_drafts.csv"
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    high_risk = [r for r in rows if r["risk_level"] == "high"]
    print(f"[shopee] {len(rows)}件の出品下書きを書き出しました → {out_path}")
    if high_risk:
        print(f"[shopee] 警告: {len(high_risk)}件が risk_level=high です。内容を必ず確認してください。")
    print("[shopee] 重要: approved列は全てFALSEで出力。人間が確認・承認したものだけ次の工程へ。")
    return str(out_path)


if __name__ == "__main__":
    run()
