# Shopee Mass Upload — Required Fields Reference

This document describes the fields required by the Shopee Mass Upload template,
how they map to this system's internal data, and what must be provided manually.

## Overview

The **Shopee Mass Upload CSV** (`🗂️ Shopee一括アップロード形式` page) is a
**separate export** from the internal approved CSV (`📤 承認済みエクスポート` page).
It follows Shopee's official bulk-upload template format and is intended for upload
to **Shopee Seller Center → Product Management → Batch Upload**.

> ⚠️ Uploading this CSV does **not** automatically publish products on Shopee.
> Shopee's Seller Center still requires human review before listings go live.

---

## Column Definitions

| Column | Required? | Source | Notes |
|---|---|---|---|
| `Product Name*` | ✅ Required | `shopee_title` (auto-generated) | Max 120 characters |
| `Category ID*` | ✅ Required | **Must be entered manually** | Shopee numeric ID — find in Seller Center or Open Platform API |
| `Description*` | ✅ Required | `shopee_description` (auto-generated) | Max 3,000 characters |
| `Price*` | ✅ Required | **Must be entered manually** (reference value provided) | In local currency; system provides approximate conversion from JPY |
| `Stock*` | ✅ Required | **Must be entered manually** | Integer ≥ 1; verify actual inventory before entering |
| `Seller SKU` | Optional | `product_name` (truncated, auto-generated) | Used for your own tracking; not visible to buyers |
| `Main Image URL*` | ✅ Required | **Must be entered manually** | At least 1 product image URL is mandatory |
| `Image URL 2–5` | Optional | **Can be entered manually** | Up to 4 additional image URLs |
| `Weight (kg)*` | ✅ Required | **Must be entered manually** | Total packed weight including packaging material |
| `Package Length (cm)` | Optional | **Can be entered manually** | |
| `Package Width (cm)` | Optional | **Can be entered manually** | |
| `Package Height (cm)` | Optional | **Can be entered manually** | |
| `Logistic Channel*` | ✅ Required | **Must be entered manually** | Enter the exact channel name enabled in your Seller Center |
| `Pre-order (days)` | Optional | **Can be entered manually** | Leave blank for regular (non-pre-order) listings |
| `Condition` | Optional | Default `New` | `New` or `Used` |
| `Brand` | Optional | **Can be entered manually** | |
| `Supplier URL` | Reference only | `source_url` (from input) | Included for traceability; Shopee does not use this field |

---

## Export Blocking Rules

A product is **excluded from the Mass Upload CSV** if any of the following
required fields are missing or invalid:

| # | Field | Blocking Condition |
|---|---|---|
| 1 | Supplier URL | `source_url` is blank or "nan" |
| 2 | Selling price | `selling_price_jpy` ≤ 0 |
| 3 | Stock quantity | User-entered stock qty ≤ 0 |
| 4 | Main Image URL | User-entered image URL is blank |
| 5 | Category ID | User-entered Shopee category ID is blank |
| 6 | Weight | User-entered weight ≤ 0 kg |
| 7 | Logistic Channel | User-entered channel name is blank |
| 8 | Local currency price | User-confirmed local price ≤ 0 |

Validation errors are shown **before** the download button appears, per product.
Products that fail validation are shown in a collapsible error summary and are
excluded from the CSV.

---

## Country & Currency Mapping

| Country | Currency | Approximate Rate (JPY per 1 local unit) |
|---|---|---|
| Singapore | SGD | ¥112 / SGD (approx.) |
| Malaysia | MYR | ¥33 / MYR (approx.) |
| Taiwan | TWD | ¥4.8 / TWD (approx.) |
| Philippines | PHP | ¥2.7 / PHP (approx.) |
| Thailand | THB | ¥4.2 / THB (approx.) |
| Vietnam | VND | ¥0.006 / VND (approx.) |

> ⚠️ These rates are **approximations** for reference only.
> Always verify with a current exchange rate before setting your final price.

---

## How to Find Your Shopee Category ID

1. Log in to [Shopee Seller Center](https://seller.shopee.sg/) for your target country.
2. Go to **Product Management → Add Product**.
3. Browse or search for the appropriate product category.
4. The numeric Category ID can also be retrieved via the
   [Shopee Open Platform API](https://open.shopee.com/) using the
   `product.get_category` endpoint.

> ❌ Do **not** invent or guess category IDs — using an incorrect ID will cause
> the batch upload to fail or list the product in the wrong category.

---

## How to Get Product Image URLs

Shopee's Mass Upload format requires publicly accessible image URLs.
You can use any of the following approaches:

- Upload images to Shopee's own image hosting via Seller Center and copy the URL.
- Host images on a CDN (e.g., Cloudinary, AWS S3) and use the direct URL.
- Use existing product listing image URLs from your supplier (with permission).

> ❌ Do **not** use temporary or login-protected URLs — Shopee must be able to
> download the image during processing.

---

## Logistic Channel Names

Enter the **exact channel name** as it appears in your Shopee Seller Center
(Shipping → Shipping Settings → Active Channels). Examples:

- `Standard Express`
- `Shopee Express`
- `J&T Express`
- `Ninja Van`
- `Flash Express`

Channel availability and names vary by country. Check your Seller Center for
the exact names enabled for your shop.

---

## File Saved by This System

User-entered extra data (category ID, images, weight, etc.) is persisted to:

```
ai_side_biz/data/mass_upload_extra_data.json
```

This file is keyed by `"{country}|{product_name}"` so you can resume
input across sessions without re-entering data.

---

## Relationship to Internal CSV Export

| | Internal CSV (`📤 承認済みエクスポート`) | Mass Upload CSV (`🗂️ Shopee一括アップロード形式`) |
|---|---|---|
| Purpose | Internal records, reference | Direct Shopee batch upload |
| Format | System-internal columns | Shopee official template |
| Images | Not included | Required (must be added) |
| Category | Text suggestion | Official numeric ID required |
| Price | JPY | Local currency (per country) |
| Weight | Not included | Required (must be added) |
| Logistics | Not included | Required (must be added) |
| Publishes to Shopee? | No | No (requires Seller Center upload + review) |

Both exports are available as separate downloads. The internal CSV is **not**
directly uploadable to Shopee and must not be treated as such.
