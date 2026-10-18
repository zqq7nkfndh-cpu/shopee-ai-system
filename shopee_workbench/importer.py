"""Explicit, idempotent importers. They never execute files or overwrite saved products."""

import csv
import io
import json
from pathlib import Path

from .domain import (
    MARKETS,
    NUMERIC_PRODUCT,
    PRODUCT_DEFAULTS,
    DomainError,
    valid_url,
    validate_product,
)

IMPORT_FIELDS = set(PRODUCT_DEFAULTS) - {
    "status",
    "copy_source",
    "risk_reviewed",
    "rights_reviewed",
    "copy_reviewed",
    "market_reviewed",
}


def parse_csv(text):
    if not isinstance(text, str) or len(text) > 2 * 1024 * 1024:
        raise DomainError("CSVはUTF-8・2MB以下で入力してください。")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames or not {"name", "market"}.issubset(reader.fieldnames):
        raise DomainError("CSVにnameとmarketの列が必要です。")
    if (
        len(reader.fieldnames) != len(set(reader.fieldnames))
        or set(reader.fieldnames) - IMPORT_FIELDS
    ):
        raise DomainError(
            "CSVの列が重複しているか、未対応の列があります。入力テンプレートを使ってください。"
        )
    result = []
    for i, row in enumerate(reader, start=2):
        if i > 501:
            raise DomainError("CSVは1回500商品までです。")
        if None in row or any(v is None for v in row.values()):
            raise DomainError(f"{i}行目の列数を確認してください。")
        if not any(row.values()):
            continue
        p = {}
        try:
            for k, v in row.items():
                v = v.strip()
                if not v:
                    continue
                p[k] = float(v) if k in NUMERIC_PRODUCT else v
            result.append(validate_product(p))
        except (DomainError, ValueError) as exc:
            raise DomainError(f"{i}行目: {exc}") from exc
    if not result:
        raise DomainError("CSVに商品行がありません。")
    return result


def load_legacy(directory):
    directory = Path(directory)
    rows = {}
    country_to_code = {v["country"]: k for k, v in MARKETS.items()}

    def read_csv(path):
        if not path.exists():
            return []
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    # Latest drafts supersede dashboard copies. Input is supplemental only.
    for relative in [
        "data/shopee_trend_input.csv",
        "outputs/dashboard.csv",
        "outputs/shopee_listing_drafts.csv",
    ]:
        for row in read_csv(directory / relative):
            key = (row.get("country", ""), row.get("product_name", "").strip())
            if key[1]:
                rows[key] = {**rows.get(key, {}), **row}
    tracker = {
        (r.get("country", ""), r.get("product_name", "").strip()): r
        for r in read_csv(directory / "data/product_cost_tracker.csv")
    }
    extras_path = directory / "data/mass_upload_extra_data.json"
    extras = json.loads(extras_path.read_text()) if extras_path.exists() else {}
    products = []
    warnings = []

    def number(row, key):
        value = row.get(key, "")
        if str(value).lower() in {"", "nan", "none"}:
            return None
        try:
            result = float(value)
            if not 0 <= result <= 1_000_000_000:
                raise ValueError()
            return result
        except (ValueError, TypeError):
            return None

    for (country, name), r in rows.items():
        if country not in country_to_code:
            warnings.append(name + ": 対応国でないため除外")
            continue
        t = tracker.get((country, name), {})
        p = {
            **PRODUCT_DEFAULTS,
            "name": name,
            "market": country_to_code[country],
            "category": r.get("genre", ""),
            "status": "researching",
        }
        p["cost_jpy"] = (
            number(t, "actual_purchase_price_jpy") if t else number(r, "cost_price_jpy")
        )
        for target, key in [
            ("domestic_shipping_jpy", "domestic_shipping_jpy"),
            ("international_shipping_jpy", "international_shipping_estimate_jpy"),
            ("packaging_jpy", "packaging_cost_jpy"),
        ]:
            p[target] = number(t, key)
        if valid_url(t.get("supplier_url", "")):
            p["supplier_url"] = t.get("supplier_url", "")
        p["supplier_name"] = t.get("supplier_name", "")
        for target, source in [
            ("title", "shopee_title"),
            ("description", "shopee_description"),
        ]:
            value = r.get(source, "")
            if str(value).lower() != "nan":
                p[target] = value
        p["copy_source"] = "legacy:unverified"
        p["notes"] = (
            "旧版から移行。旧承認状態: "
            + str(r.get("approved", ""))
            + " / "
            + str(r.get("status", ""))
            + "\n旧source_url（仕入れ先か観測元か要確認）: "
            + str(r.get("source_url", ""))
            + "\n旧JPY売価: "
            + str(r.get("selling_price_jpy", ""))
            + "\n旧送料（国内/国際の区別を要確認）: "
            + str(r.get("shipping_cost_jpy", ""))
            + "\n"
            + str(r.get("trend_reason", ""))
            + "\n"
            + str(t.get("notes", ""))
        )[:10000]
        extra = extras.get(country + "|" + name, {})
        for target, source in [
            ("category_id", "category_id"),
            ("image_url", "main_image_url"),
            ("weight_kg", "weight_kg"),
            ("length_cm", "length_cm"),
            ("width_cm", "width_cm"),
            ("height_cm", "height_cm"),
            ("stock", "stock_qty"),
            ("logistics", "logistic_channel"),
            ("brand", "brand"),
            ("price_local", "price_local"),
        ]:
            value = (
                number(extra, source)
                if target in NUMERIC_PRODUCT
                else extra.get(source, "")
            )
            if value is not None and value != "":
                p[target] = value
        # Pre-validate all rows before the database transaction; report invalid rows explicitly.
        try:
            products.append(validate_product(p))
        except DomainError as exc:
            warnings.append(name + ": " + str(exc))
    return products, warnings
