# -*- coding: utf-8 -*-
"""
shopee_api.py — Shopee Open Platform API 連携モジュール（プレースホルダー）

【重要】
このモジュールは将来のShopee Open Platform API連携のための構造を準備したものです。
現時点では実際のAPIリクエストは送信しません。すべての関数はドライランモードで
ログ出力のみ行います。

本番連携を有効にするには:
1. Shopee Open Platformでアプリ申請を行う
2. SHOPEE_PARTNER_ID, SHOPEE_PARTNER_KEY, SHOPEE_SHOP_ID, SHOPEE_ACCESS_TOKENを設定
3. DRY_RUN = False に変更（必ず十分なテスト後に行うこと）

参考: https://open.shopee.com/documents
"""
import hashlib
import hmac
import time
import json
from pathlib import Path

from config import (
    SHOPEE_PARTNER_ID, SHOPEE_PARTNER_KEY,
    SHOPEE_SHOP_ID, SHOPEE_ACCESS_TOKEN,
)

DRY_RUN = True  # 本番連携するまで必ずTrueのまま

SHOPEE_API_BASE = "https://partner.shopeemobile.com/api/v2"


def _generate_signature(path: str, timestamp: int) -> str:
    """Shopee Open Platform の HMAC-SHA256 署名を生成する"""
    base_string = f"{SHOPEE_PARTNER_ID}{path}{timestamp}{SHOPEE_ACCESS_TOKEN}{SHOPEE_SHOP_ID}"
    return hmac.new(
        SHOPEE_PARTNER_KEY.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def authenticate() -> dict:
    """
    Shopee Open Platform の認証情報を確認する。
    ドライランモードではクレデンシャルの設定状況のみ返す。
    """
    if DRY_RUN:
        creds_ok = all([SHOPEE_PARTNER_ID, SHOPEE_PARTNER_KEY, SHOPEE_SHOP_ID, SHOPEE_ACCESS_TOKEN])
        print("[shopee_api][DRY-RUN] authenticate() — クレデンシャル確認")
        print(f"[shopee_api][DRY-RUN] 設定済み: {creds_ok}")
        return {
            "dry_run": True,
            "credentials_configured": creds_ok,
            "message": "ドライランモード: 実際のAPI認証は行いません",
        }
    timestamp = int(time.time())
    path = "/auth/token/get"
    sign = _generate_signature(path, timestamp)
    return {
        "partner_id": SHOPEE_PARTNER_ID,
        "timestamp": timestamp,
        "sign": sign,
        "note": "本番連携時はここでrequests.postを呼び出す",
    }


def create_item(product_data: dict) -> dict:
    """
    Shopeeに新しい商品を出品する。

    product_dataの必須キー:
        name: str — 商品タイトル（英語、60文字以内）
        description: str — 商品説明
        price: float — 販売価格（現地通貨）
        stock: int — 在庫数
        category_id: int — ShopeeカテゴリID
        images: list[str] — 画像URL or ローカルパスのリスト
        logistics: list[dict] — 配送方法設定

    ドライランモードでは出品せず、送信予定データをログ出力します。
    """
    if DRY_RUN:
        print("[shopee_api][DRY-RUN] create_item() — 以下のデータを出品予定:")
        print(json.dumps(product_data, ensure_ascii=False, indent=2))
        return {
            "dry_run": True,
            "item_id": None,
            "message": "ドライランモード: 実際の出品は行いません",
            "data_preview": product_data,
        }
    raise NotImplementedError(
        "本番出品はDRY_RUN=Falseに設定し、Shopee Open Platform APIの"
        "item.add エンドポイントを呼び出すように実装してください。"
    )


def upload_images(image_paths: list[str]) -> list[str]:
    """
    商品画像をShopeeにアップロードし、image_idのリストを返す。

    ドライランモードでは指定されたパスのリストをそのまま返します。
    """
    if DRY_RUN:
        print(f"[shopee_api][DRY-RUN] upload_images() — {len(image_paths)}枚の画像アップロード予定")
        for p in image_paths:
            print(f"  - {p}")
        return [f"[DRY-RUN] {p}" for p in image_paths]
    raise NotImplementedError(
        "本番連携時はShopee media.upload_imageエンドポイントを呼び出してください。"
    )


def update_stock(item_id: int, model_id: int, stock: int) -> dict:
    """
    商品の在庫数を更新する。

    ドライランモードでは更新せず、変更内容をログ出力します。
    """
    if DRY_RUN:
        print(f"[shopee_api][DRY-RUN] update_stock() — item_id={item_id}, stock→{stock}")
        return {
            "dry_run": True,
            "item_id": item_id,
            "model_id": model_id,
            "new_stock": stock,
            "message": "ドライランモード: 実際の在庫更新は行いません",
        }
    raise NotImplementedError(
        "本番連携時はShopee product.update_stock エンドポイントを呼び出してください。"
    )


def get_orders(time_from: int | None = None, time_to: int | None = None) -> list[dict]:
    """
    注文一覧を取得する。

    time_from/time_to: Unixタイムスタンプ（省略時は直近15分）
    ドライランモードではサンプルデータを返します。
    """
    if DRY_RUN:
        print("[shopee_api][DRY-RUN] get_orders() — サンプル注文データを返します")
        return [
            {
                "dry_run": True,
                "order_sn": "DRY-RUN-000001",
                "order_status": "READY_TO_SHIP",
                "total_amount": 0,
                "message": "ドライランモード: 実際の注文データは取得しません",
            }
        ]
    raise NotImplementedError(
        "本番連携時はShopee order.get_order_list エンドポイントを呼び出してください。"
    )


def export_approved_to_draft_json(approved_rows: list[dict], out_path: Path | None = None) -> Path:
    """
    承認済み商品データをShopee API用のJSONドラフトとして書き出す。
    実際の出品前に人間がこのファイルを確認・編集できるようにする。
    """
    from config import OUTPUT_DIR
    out_path = out_path or OUTPUT_DIR / "shopee_api_draft.json"

    safe_rows = [
        r for r in approved_rows
        if str(r.get("approved", "")).upper() == "TRUE"
        and str(r.get("risk_level", "")).lower() != "high"
    ]

    drafts = []
    for r in safe_rows:
        drafts.append({
            "product_name_ja": r.get("product_name", ""),
            "shopee_title": r.get("shopee_title", ""),
            "shopee_description": r.get("shopee_description", ""),
            "bullet_points": r.get("bullet_points", "").split(" | "),
            "keywords": r.get("keywords", ""),
            "category_suggestion": r.get("category_suggestion", ""),
            "selling_price_jpy": r.get("selling_price_jpy", 0),
            "selling_price_usd": r.get("selling_price_usd", 0),
            "country": r.get("country", ""),
            "risk_level": r.get("risk_level", ""),
            "_api_ready": False,
            "_note": "このファイルを確認・編集後、create_item()に渡してください",
        })

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(drafts, f, ensure_ascii=False, indent=2)

    print(f"[shopee_api] APIドラフトを書き出しました ({len(drafts)}件) → {out_path}")
    return out_path
