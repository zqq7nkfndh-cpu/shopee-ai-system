"""CSV is an internal preparation sheet, never advertised as a verified upload template."""

import csv
import io
from .domain import MARKETS

COLUMNS = [
    "market",
    "currency",
    "sku",
    "title",
    "description",
    "category_id",
    "price_local",
    "stock",
    "image_url",
    "weight_kg",
    "length_cm",
    "width_cm",
    "height_cm",
    "logistics",
    "brand",
    "condition",
    "listing_language",
    "supplier_url",
    "template_note",
    "format_notice",
]


def safe_cell(value):
    if value is None:
        return ""
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + text
    return value


def preparation_csv(products, profile):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    for p in products:
        row = {k: p.get(k, "") for k in COLUMNS}
        row.update(
            currency=MARKETS[p["market"]]["currency"],
            template_note=profile["template_note"],
            format_notice="INTERNAL_PREPARATION_ONLY: transfer into your current Seller Center template; review before upload",
        )
        writer.writerow({k: safe_cell(v) for k, v in row.items()})
    return out.getvalue().encode("utf-8-sig")
