# -*- coding: utf-8 -*-
"""
shopee_mass_upload.py — Shopee公式 Mass Upload CSV 形式エクスポート

このモジュールは内部の出品下書きCSVを Shopee Mass Upload テンプレート形式に変換します。

【重要な制限・ルール】
- カテゴリID・商品画像URL・重量・物流チャンネル・在庫数・現地通貨価格は
  システム内に存在しないため、エクスポート前にユーザーが各商品に対して入力する必要があります。
- システムが生成するデータ（タイトル・説明文・キーワード等）はそのままマッピングします。
- 価格の現地通貨換算は参考値のみ。実際の出品前に最新レートで確認してください。
- このモジュールはCSVファイルを生成するのみで、Shopeeへの出品は一切行いません。

【Shopee Mass Upload テンプレートについて】
各国の正式テンプレートは Shopee Seller Center の「一括アップロード」から
最新版をダウンロードして確認してください。本モジュールの列構成は
Shopee共通の一括アップロード仕様（2024年版）を参考に実装しています。
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

# ── Shopee Mass Upload テンプレート列定義 ─────────────────────────────────────
# Shopee Seller Center の一括アップロード形式（共通必須フィールド）
# ＊付きは Shopee が必須と定めているフィールド
MASS_UPLOAD_COLUMNS: list[str] = [
    "Product Name*",         # shopee_title から取得
    "Category ID*",          # ユーザー入力必須（Shopee公式IDを使用すること）
    "Description*",          # shopee_description から取得
    "Price*",                # ユーザーが現地通貨で確認・入力（参考値あり）
    "Stock*",                # ユーザー入力（在庫数）
    "Seller SKU",            # product_name から自動生成（任意）
    "Main Image URL*",       # ユーザー入力必須（画像はシステム外で用意すること）
    "Image URL 2",           # ユーザー入力（任意）
    "Image URL 3",           # ユーザー入力（任意）
    "Image URL 4",           # ユーザー入力（任意）
    "Image URL 5",           # ユーザー入力（任意）
    "Weight (kg)*",          # ユーザー入力必須（梱包後の重量）
    "Package Length (cm)",   # ユーザー入力（任意）
    "Package Width (cm)",    # ユーザー入力（任意）
    "Package Height (cm)",   # ユーザー入力（任意）
    "Logistic Channel*",     # ユーザー入力必須（利用可能な配送チャンネル名）
    "Pre-order (days)",      # ユーザー入力（任意、0の場合は空欄）
    "Condition",             # デフォルト "New"
    "Brand",                 # ユーザー入力（任意）
    "Supplier URL",          # 参考用：source_url から取得（Shopee出品には不要）
]

# ── 必須フィールドチェック定義 ────────────────────────────────────────────────
# キー: バリデーションエラー時に使う識別子
# "source": "draft" → 内部CSVから取得 / "extra" → ユーザー追加入力
REQUIRED_FIELD_CHECKS = [
    {
        "key":     "supplier_url",
        "source":  "draft",
        "label":   "仕入れ先URL（source_url）",
        "message": (
            "仕入れ先URL が未入力です。\n"
            "「📥 商品入力エディタ」で Shopee URL を設定してください。"
        ),
    },
    {
        "key":     "selling_price",
        "source":  "draft",
        "label":   "販売価格（selling_price_jpy）",
        "message": (
            "販売価格（selling_price_jpy）が 0 または未設定です。\n"
            "商品を再生成して価格を設定してください。"
        ),
    },
    {
        "key":     "stock_qty",
        "source":  "extra",
        "label":   "在庫数（Stock）",
        "message": (
            "在庫数が 0 または未入力です。\n"
            "在庫数を 1 以上に設定してください。"
        ),
    },
    {
        "key":     "main_image_url",
        "source":  "extra",
        "label":   "メイン商品画像URL（Main Image URL）",
        "message": (
            "メイン商品画像URLが未入力です。\n"
            "Shopee Mass Upload には最低1枚の画像URLが必須です。\n"
            "商品画像をアップロードして URL を入力してください。"
        ),
    },
    {
        "key":     "category_id",
        "source":  "extra",
        "label":   "Shopee カテゴリID（Category ID）",
        "message": (
            "Shopee カテゴリID が未入力です。\n"
            "Shopee Seller Center の「カテゴリ管理」または "
            "公式APIドキュメントでカテゴリIDを確認して入力してください。\n"
            "カテゴリ候補（参考）はシステムが提案しますが、正式IDは人間が確認すること。"
        ),
    },
    {
        "key":     "weight_kg",
        "source":  "extra",
        "label":   "重量・kg（Weight）",
        "message": (
            "梱包後の重量（kg）が未入力です。\n"
            "商品＋梱包材の重量を kg 単位で入力してください。"
        ),
    },
    {
        "key":     "logistic_channel",
        "source":  "extra",
        "label":   "物流チャンネル（Logistic Channel）",
        "message": (
            "物流チャンネルが未入力です。\n"
            "Shopee Seller Center で有効化した配送チャンネル名を入力してください。\n"
            "例: 「Shopee Express」「Standard Express」「J&T Express」など"
        ),
    },
    {
        "key":     "price_local",
        "source":  "extra",
        "label":   "現地通貨販売価格（Price）",
        "message": (
            "現地通貨での販売価格が 0 または未入力です。\n"
            "参考価格を元に現地通貨で確認・入力してください。\n"
            "※ システムの換算価格はあくまで参考値です。最新為替レートで確認してください。"
        ),
    },
]

# ── 国別設定 ──────────────────────────────────────────────────────────────────
COUNTRY_CURRENCY: dict[str, str] = {
    "Singapore":   "SGD",
    "Malaysia":    "MYR",
    "Taiwan":      "TWD",
    "Philippines": "PHP",
    "Thailand":    "THB",
    "Vietnam":     "VND",
}

# 参考為替レート（JPY → 各通貨 1単位あたりのJPY）。
# これらは市場の概算値であり、実際の出品前に必ず最新レートで確認すること。
APPROX_JPY_PER_LOCAL: dict[str, float] = {
    "SGD": 112.0,   # 1 SGD ≈ 112 JPY（概算）
    "MYR":  33.0,   # 1 MYR ≈  33 JPY（概算）
    "TWD":   4.8,   # 1 TWD ≈  4.8 JPY（概算）
    "PHP":   2.7,   # 1 PHP ≈  2.7 JPY（概算）
    "THB":   4.2,   # 1 THB ≈  4.2 JPY（概算）
    "VND":   0.006, # 1 VND ≈  0.006 JPY（概算）
}

# ── データクラス ──────────────────────────────────────────────────────────────

@dataclass
class MassUploadExtra:
    """ユーザーが各商品に対して追加入力する必須・任意フィールド"""
    category_id:      str   = ""
    price_local:      float = 0.0   # 現地通貨価格（ユーザーが確認・入力）
    stock_qty:        int   = 0
    main_image_url:   str   = ""
    image_url_2:      str   = ""
    image_url_3:      str   = ""
    image_url_4:      str   = ""
    image_url_5:      str   = ""
    weight_kg:        float = 0.0
    length_cm:        float = 0.0
    width_cm:         float = 0.0
    height_cm:        float = 0.0
    logistic_channel: str   = ""
    preorder_days:    int   = 0
    condition:        str   = "New"
    brand:            str   = ""

    def to_dict(self) -> dict:
        return {
            "category_id":      self.category_id,
            "price_local":      self.price_local,
            "stock_qty":        self.stock_qty,
            "main_image_url":   self.main_image_url,
            "image_url_2":      self.image_url_2,
            "image_url_3":      self.image_url_3,
            "image_url_4":      self.image_url_4,
            "image_url_5":      self.image_url_5,
            "weight_kg":        self.weight_kg,
            "length_cm":        self.length_cm,
            "width_cm":         self.width_cm,
            "height_cm":        self.height_cm,
            "logistic_channel": self.logistic_channel,
            "preorder_days":    self.preorder_days,
            "condition":        self.condition,
            "brand":            self.brand,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MassUploadExtra":
        return cls(
            category_id=str(d.get("category_id", "")),
            price_local=float(d.get("price_local") or 0),
            stock_qty=int(d.get("stock_qty") or 0),
            main_image_url=str(d.get("main_image_url", "")),
            image_url_2=str(d.get("image_url_2", "")),
            image_url_3=str(d.get("image_url_3", "")),
            image_url_4=str(d.get("image_url_4", "")),
            image_url_5=str(d.get("image_url_5", "")),
            weight_kg=float(d.get("weight_kg") or 0),
            length_cm=float(d.get("length_cm") or 0),
            width_cm=float(d.get("width_cm") or 0),
            height_cm=float(d.get("height_cm") or 0),
            logistic_channel=str(d.get("logistic_channel", "")),
            preorder_days=int(d.get("preorder_days") or 0),
            condition=str(d.get("condition") or "New"),
            brand=str(d.get("brand", "")),
        )


@dataclass
class ValidationResult:
    """1商品のバリデーション結果"""
    product_name: str
    country: str
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


# ── バリデーション ────────────────────────────────────────────────────────────

def validate_product(
    draft_row: dict,
    extra: MassUploadExtra,
) -> ValidationResult:
    """
    Shopee Mass Upload に必要なフィールドを検証する。
    エラーがない場合 result.is_valid == True。

    Args:
        draft_row: shopee_listing_drafts.csv の1行（dict）
        extra: ユーザーが追加入力したフィールド

    Returns:
        ValidationResult（errors が空なら OK）
    """
    product_name = str(draft_row.get("product_name", ""))
    country = str(draft_row.get("country", ""))
    errors: list[str] = []

    # 1. 仕入れ先URL
    source_url = str(draft_row.get("source_url", "")).strip()
    if not source_url or source_url in ("nan", ""):
        errors.append(REQUIRED_FIELD_CHECKS[0]["message"])

    # 2. 販売価格 > 0
    try:
        price_jpy = float(draft_row.get("selling_price_jpy") or 0)
    except (ValueError, TypeError):
        price_jpy = 0.0
    if price_jpy <= 0:
        errors.append(REQUIRED_FIELD_CHECKS[1]["message"])

    # 3. 在庫数 > 0
    if extra.stock_qty <= 0:
        errors.append(REQUIRED_FIELD_CHECKS[2]["message"])

    # 4. メイン画像URL
    if not extra.main_image_url.strip():
        errors.append(REQUIRED_FIELD_CHECKS[3]["message"])

    # 5. カテゴリID
    if not extra.category_id.strip():
        errors.append(REQUIRED_FIELD_CHECKS[4]["message"])

    # 6. 重量
    if extra.weight_kg <= 0:
        errors.append(REQUIRED_FIELD_CHECKS[5]["message"])

    # 7. 物流チャンネル
    if not extra.logistic_channel.strip():
        errors.append(REQUIRED_FIELD_CHECKS[6]["message"])

    # 8. 現地通貨価格
    if extra.price_local <= 0:
        errors.append(REQUIRED_FIELD_CHECKS[7]["message"])

    return ValidationResult(
        product_name=product_name,
        country=country,
        errors=errors,
    )


# ── 価格参考値計算 ────────────────────────────────────────────────────────────

def suggest_local_price(selling_price_jpy: float, country: str) -> float:
    """
    JPY価格から現地通貨の概算参考価格を計算する。
    あくまで参考値。実際の出品前に必ず最新為替レートで確認・調整すること。

    Args:
        selling_price_jpy: 円建て販売価格
        country: 出品先国名

    Returns:
        現地通貨概算価格（小数第2位まで）
    """
    currency = COUNTRY_CURRENCY.get(country, "")
    rate = APPROX_JPY_PER_LOCAL.get(currency, 0.0)
    if rate <= 0 or selling_price_jpy <= 0:
        return 0.0
    return round(selling_price_jpy / rate, 2)


# ── 行ビルド ─────────────────────────────────────────────────────────────────

def build_mass_upload_row(
    draft_row: dict,
    extra: MassUploadExtra,
) -> dict:
    """
    バリデーション済みの内部データとユーザー入力を
    Shopee Mass Upload テンプレート形式の1行に変換する。

    バリデーション済みの行にのみ呼び出すこと（validate_product() を先に実行）。

    Args:
        draft_row: shopee_listing_drafts.csv の1行（dict）
        extra: ユーザーが追加入力したフィールド（validate 済み）

    Returns:
        MASS_UPLOAD_COLUMNS に対応した dict
    """
    # Seller SKU: product_name を短縮して使用（任意フィールド）
    raw_sku = str(draft_row.get("product_name", ""))[:40]
    sku = raw_sku.replace(",", "_").replace("\n", " ").strip()

    row = {
        "Product Name*":      str(draft_row.get("shopee_title", ""))[:120].strip(),
        "Category ID*":       extra.category_id.strip(),
        "Description*":       str(draft_row.get("shopee_description", ""))[:3000].strip(),
        "Price*":             extra.price_local,
        "Stock*":             extra.stock_qty,
        "Seller SKU":         sku,
        "Main Image URL*":    extra.main_image_url.strip(),
        "Image URL 2":        extra.image_url_2.strip(),
        "Image URL 3":        extra.image_url_3.strip(),
        "Image URL 4":        extra.image_url_4.strip(),
        "Image URL 5":        extra.image_url_5.strip(),
        "Weight (kg)*":       extra.weight_kg,
        "Package Length (cm)": extra.length_cm if extra.length_cm > 0 else "",
        "Package Width (cm)":  extra.width_cm if extra.width_cm > 0 else "",
        "Package Height (cm)": extra.height_cm if extra.height_cm > 0 else "",
        "Logistic Channel*":  extra.logistic_channel.strip(),
        "Pre-order (days)":   extra.preorder_days if extra.preorder_days > 0 else "",
        "Condition":          (extra.condition or "New").strip(),
        "Brand":              extra.brand.strip(),
        "Supplier URL":       str(draft_row.get("source_url", "")).strip(),
    }
    return row


# ── CSV 生成 ──────────────────────────────────────────────────────────────────

def generate_mass_upload_csv(rows: list[dict]) -> bytes:
    """
    Shopee Mass Upload 形式の CSV バイト列を生成する。

    Args:
        rows: build_mass_upload_row() の出力リスト

    Returns:
        UTF-8 BOM 付き CSV バイト列
    """
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=MASS_UPLOAD_COLUMNS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")
