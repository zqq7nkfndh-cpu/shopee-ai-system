# -*- coding: utf-8 -*-
"""
shopee_research.py

Shopee越境ECの出品「下書き」を作るモジュール。

【なぜスクレイピングではなく手動入力CSVなのか】
Shopeeは一般公開のトレンド取得APIを提供しておらず、無断スクレイピングは
Shopeeの利用規約に抵触するおそれがあります。そのため本システムでは、
`data/shopee_trend_input_template.csv` をコピーして
`data/shopee_trend_input.csv` を作り、そこに人間がShopeeアプリ/サイトを
見て気づいた「国別の売れ筋・急上昇っぽい商品」を手入力する運用にしています。
このファイルを入力として、利益計算・英語コピー生成・リスクチェックを自動化します。

【厳守事項】
- 完全自動出品は行わない。出力はあくまで「出品下書きCSV」
- approved列がTRUEの行だけを、人間の最終確認後に別途の出品作業に使う設計
- 禁止商品・規制カテゴリ・商標リスクは risk_checker で必ずチェックする
"""
import csv
import datetime
from pathlib import Path

from config import CSV_COLUMNS, OUTPUT_DIR, DATA_DIR, DEFAULT_JPY_PER_USD
from risk_checker import check_risk, export_customs_note

TREND_INPUT_PATH = DATA_DIR / "shopee_trend_input.csv"
TREND_TEMPLATE_PATH = DATA_DIR / "shopee_trend_input_template.csv"

# Shopeeの手数料は変動するため、実際の最新情報をSeller Centerで確認して調整すること
TRANSACTION_FEE_RATE = 0.05   # 取引手数料の目安
SERVICE_FEE_RATE = 0.05       # サービス手数料の目安(上限ありのプログラムが多い点に注意)
PAYMENT_FEE_RATE = 0.02       # 決済手数料の目安


def load_trend_input() -> list:
    path = TREND_INPUT_PATH if TREND_INPUT_PATH.exists() else TREND_TEMPLATE_PATH
    if not TREND_INPUT_PATH.exists():
        print(f"[shopee] {TREND_INPUT_PATH.name} が無いためテンプレートを使用します。")
        print(f"[shopee] 本番運用では {TREND_INPUT_PATH} を作成し、実際のリサーチ結果を入力してください。")
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def calculate_finance(cost_price_jpy: float, shipping_cost_jpy: float,
                       target_margin: float = 0.3, jpy_per_usd: float = DEFAULT_JPY_PER_USD):
    """
    目標利益率から想定販売価格を逆算し、手数料・利益を計算する。
    すべて概算。実際のShopee手数料・為替は最新情報に置き換えて使うこと。
    """
    cost_price_jpy = float(cost_price_jpy or 0)
    shipping_cost_jpy = float(shipping_cost_jpy or 0)
    base_cost = cost_price_jpy + shipping_cost_jpy

    total_fee_rate = TRANSACTION_FEE_RATE + SERVICE_FEE_RATE + PAYMENT_FEE_RATE
    # selling_price * (1 - fee_rate) - base_cost = selling_price * target_margin
    # selling_price * (1 - fee_rate - target_margin) = base_cost
    denom = (1 - total_fee_rate - target_margin)
    if denom <= 0:
        selling_price_jpy = base_cost * 2  # フォールバック(目標利益率が過大な場合)
    else:
        selling_price_jpy = base_cost / denom

    fee_estimate_jpy = selling_price_jpy * total_fee_rate
    profit_jpy = selling_price_jpy - base_cost - fee_estimate_jpy
    profit_margin = profit_jpy / selling_price_jpy if selling_price_jpy else 0
    selling_price_usd = selling_price_jpy / jpy_per_usd

    return {
        "selling_price_jpy": round(selling_price_jpy),
        "selling_price_usd": round(selling_price_usd, 2),
        "fee_estimate_jpy": round(fee_estimate_jpy),
        "profit_jpy": round(profit_jpy),
        "profit_margin": round(profit_margin, 3),
    }


def generate_shopee_copy(product_name_ja: str, genre: str, country: str, trend_reason: str) -> dict:
    """
    英語タイトル・説明文・検索キーワードの下書きを生成する(テンプレートベース)。
    ANTHROPIC_API_KEY が設定されていれば、より自然な英語コピーの生成に
    差し替え可能(main.py内でオプション拡張する想定。ここではオフラインでも
    動く安全なテンプレート実装にしている)。
    """
    title = f"{product_name_ja} - Japan Quality {genre} (Fast Shipping from Japan)"
    description = (
        f"Direct from Japan: {product_name_ja}.\n"
        f"Category: {genre}.\n"
        f"Why it's trending: {trend_reason}.\n"
        f"Carefully packed and shipped from Japan. "
        f"Please check size/spec details in the photos before ordering."
    )
    keywords = f"japan, {genre.lower()}, japan quality, {country.lower()}, trending"
    return {"title": title, "description": description, "keywords": keywords}


def build_candidates(target_margin: float = 0.3) -> list:
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

        finance = calculate_finance(cost_price, shipping_cost, target_margin=target_margin)
        risk = check_risk(product_name, trend_reason)
        customs_note = export_customs_note(risk.categories, country)
        copy = generate_shopee_copy(product_name, genre, country, trend_reason)

        row = {col: "" for col in CSV_COLUMNS}
        row.update({
            "date": today,
            "platform": "shopee",
            "country": country,
            "genre": genre,
            "product_name": product_name,
            "source_url": source_url,
            "trend_reason": trend_reason,
            "season_reason": "",
            "target_customer": f"{country}のShopeeユーザー",
            "cost_price": cost_price,
            "selling_price": finance["selling_price_jpy"],
            "shipping_cost": shipping_cost,
            "fee_estimate": finance["fee_estimate_jpy"],
            "profit": finance["profit_jpy"],
            "profit_margin": finance["profit_margin"],
            "risk_level": risk.risk_level,
            "risk_reason": (risk.reasons + (f" / 通関メモ: {customs_note}" if customs_note else "")),
            "room_text": "",
            "shopee_title": copy["title"],
            "shopee_description": copy["description"] + f" | Keywords: {copy['keywords']}",
            "note_angle": "",
            "status": "draft_pending_human_approval",
            # 危険度highのものは自動でFALSEに固定。人間が精査した上で個別にTRUEへ変更する運用。
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
    print("[shopee] 重要: approved列は全てFALSEで出力されます。出品前に必ず人間が内容を確認し、")
    print("[shopee]        承認したものだけ手動でapprovedをTRUEに変更してから次の工程に進めてください。")
    return str(out_path)


if __name__ == "__main__":
    run()
