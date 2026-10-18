"""Validated domain data and deterministic, Decimal-based unit economics."""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from urllib.parse import urlsplit

MARKETS = {
    "SG": {
        "name": "シンガポール",
        "country": "Singapore",
        "currency": "SGD",
        "seller_url": "https://seller.shopee.sg/",
        "language": "en",
        "decimals": 2,
    },
    "MY": {
        "name": "マレーシア",
        "country": "Malaysia",
        "currency": "MYR",
        "seller_url": "https://seller.shopee.com.my/",
        "language": "en",
        "decimals": 2,
    },
    "TW": {
        "name": "台湾",
        "country": "Taiwan",
        "currency": "TWD",
        "seller_url": "https://seller.shopee.tw/",
        "language": "zh-TW",
        "decimals": 0,
    },
    "PH": {
        "name": "フィリピン",
        "country": "Philippines",
        "currency": "PHP",
        "seller_url": "https://seller.shopee.ph/",
        "language": "en",
        "decimals": 2,
    },
    "TH": {
        "name": "タイ",
        "country": "Thailand",
        "currency": "THB",
        "seller_url": "https://seller.shopee.co.th/",
        "language": "en",
        "decimals": 2,
    },
    "VN": {
        "name": "ベトナム",
        "country": "Vietnam",
        "currency": "VND",
        "seller_url": "https://banhang.shopee.vn/",
        "language": "vi",
        "decimals": 0,
    },
}
STATUSES = {
    "candidate": "候補",
    "researching": "調査中",
    "approved": "承認済み",
    "ready": "出品準備完了",
    "rejected": "見送り",
}
PRODUCT_DEFAULTS = {
    "name": "",
    "market": "SG",
    "sku": "",
    "category": "",
    "supplier_url": "",
    "supplier_name": "",
    "english_name": "",
    "facts_en": "",
    "notes": "",
    "title": "",
    "description": "",
    "copy_source": "",
    "cost_jpy": None,
    "domestic_shipping_jpy": None,
    "international_shipping_jpy": None,
    "packaging_jpy": None,
    "other_jpy": None,
    "customs_jpy": None,
    "shipping_rebate_jpy": 0,
    "price_local": None,
    "buyer_shipping_local": 0,
    "discount_pct": 0,
    "category_id": "",
    "image_url": "",
    "weight_kg": None,
    "length_cm": None,
    "width_cm": None,
    "height_cm": None,
    "stock": 0,
    "logistics": "",
    "brand": "",
    "condition": "New",
    "listing_language": "en",
    "demand_level": "unknown",
    "competitor_count": None,
    "competitor_price_local": None,
    "observed_sales": None,
    "research_source_url": "",
    "research_date": "",
    "research_note": "",
    "risk_reviewed": False,
    "rights_reviewed": False,
    "copy_reviewed": False,
    "market_reviewed": False,
    "status": "candidate",
}
PROFILE_DEFAULTS = {
    "jpy_per_local": None,
    "commission_pct": None,
    "transaction_pct": None,
    "service_pct": None,
    "fee_tax_pct": None,
    "payout_pct": None,
    "ad_pct": None,
    "reserve_pct": None,
    "fixed_fee_local": None,
    "commission_basis": "item",
    "transaction_basis": "order",
    "service_basis": "item",
    "target_margin_pct": 25,
    "fx_stress_pct": 10,
    "shipping_stress_pct": 20,
    "price_stress_pct": 10,
    "fee_source_url": "",
    "fx_source_url": "",
    "checked_on": "",
    "verified": False,
    "title_limit": 120,
    "description_limit": 3000,
    "template_note": "",
    "template_source_url": "",
    "template_checked_on": "",
    "template_confirmed": False,
}
COST_FIELDS = [
    "cost_jpy",
    "domestic_shipping_jpy",
    "international_shipping_jpy",
    "packaging_jpy",
    "other_jpy",
    "customs_jpy",
]
NUMERIC_PRODUCT = set(
    COST_FIELDS
    + [
        "shipping_rebate_jpy",
        "price_local",
        "buyer_shipping_local",
        "discount_pct",
        "weight_kg",
        "length_cm",
        "width_cm",
        "height_cm",
        "stock",
        "competitor_count",
        "competitor_price_local",
        "observed_sales",
    ]
)
NUMERIC_PROFILE = {
    k
    for k, v in PROFILE_DEFAULTS.items()
    if isinstance(v, (int, float)) and not isinstance(v, bool)
} | {k for k, v in PROFILE_DEFAULTS.items() if v is None}
BOOL_PRODUCT = {k for k, v in PRODUCT_DEFAULTS.items() if isinstance(v, bool)}
BOOL_PROFILE = {"verified", "template_confirmed"}


class DomainError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def valid_url(value, allow_empty=True):
    if not value:
        return allow_empty
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and not any(c.isspace() for c in value)
        )
    except ValueError:
        return False


def recent_date(value, days=30):
    try:
        age = (date.today() - date.fromisoformat(value)).days
        return 0 <= age <= days
    except (ValueError, TypeError):
        return False


def _validate(data, defaults, numeric, boolean):
    if not isinstance(data, dict):
        raise DomainError("オブジェクト形式で入力してください。")
    extra = set(data) - set(defaults)
    if extra:
        raise DomainError("未対応の項目: " + ", ".join(sorted(extra)))
    out = dict(defaults)
    for key, value in data.items():
        if key in boolean:
            if type(value) is not bool:
                raise DomainError(f"{key}: 真偽値を指定してください。")
        elif key in numeric:
            if value is None and defaults[key] is not None:
                raise DomainError(f"{key}: 数値を入力してください。")
            if value is not None:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not 0 <= value <= 1_000_000_000
                ):
                    raise DomainError(f"{key}: 0以上の有限の数値を入力してください。")
                if key.endswith("_pct") and value >= 100:
                    raise DomainError(f"{key}: 100%未満で入力してください。")
                if (
                    key
                    in {
                        "stock",
                        "competitor_count",
                        "observed_sales",
                        "title_limit",
                        "description_limit",
                    }
                    and int(value) != value
                ):
                    raise DomainError(f"{key}: 整数を入力してください。")
        else:
            if not isinstance(value, str) or len(value) > (
                10000
                if key in {"description", "facts_en", "notes", "research_note"}
                else 1000
            ):
                raise DomainError(f"{key}: 文字列が長すぎるか、形式が違います。")
            value = value.strip()
            if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
                raise DomainError(f"{key}: 制御文字は使えません。")
            if key.endswith("_url") and not valid_url(value):
                raise DomainError(f"{key}: http(s)のURLを入力してください。")
            if key in {"checked_on", "research_date", "template_checked_on"} and value:
                try:
                    parsed = date.fromisoformat(value)
                    if parsed > date.today():
                        raise ValueError()
                except ValueError:
                    raise DomainError(
                        f"{key}: 今日以前の日付（YYYY-MM-DD）を入力してください。"
                    )
        out[key] = value
    return out


def validate_product(data):
    p = _validate(data, PRODUCT_DEFAULTS, NUMERIC_PRODUCT, BOOL_PRODUCT)
    if not p["name"] or len(p["name"]) > 200 or p["market"] not in MARKETS:
        raise DomainError("商品名（200文字以内）と対応する販売国が必要です。")
    if (
        p["status"] not in STATUSES
        or p["demand_level"] not in {"unknown", "low", "medium", "high"}
        or p["condition"] not in {"New", "Used"}
    ):
        raise DomainError("状態または需要の値が不正です。")
    if p["listing_language"] not in {"en", "zh-TW", "th", "vi", "ms"}:
        raise DomainError("出品言語を選んでください。")
    if p["category_id"] and not re.fullmatch(r"[1-9][0-9]{0,14}", p["category_id"]):
        raise DomainError("カテゴリIDは正の整数で入力してください。")
    if (
        any(
            p[k] is not None
            for k in ["competitor_count", "competitor_price_local", "observed_sales"]
        )
        or p["demand_level"] != "unknown"
    ):
        if (
            not p["research_source_url"]
            or not p["research_date"]
            or not p["research_note"]
        ):
            raise DomainError(
                "需要・競合の情報には出典URL、観測日、観測条件メモが必要です。"
            )
    return p


def validate_profile(data):
    p = _validate(data, PROFILE_DEFAULTS, NUMERIC_PROFILE, BOOL_PROFILE)
    if p["jpy_per_local"] is not None and p["jpy_per_local"] <= 0:
        raise DomainError("為替は0より大きい値を入力してください。")
    for key in ["commission_basis", "transaction_basis", "service_basis"]:
        if p[key] not in {"item", "order"}:
            raise DomainError("手数料の基準は商品代金または注文合計です。")
    for key in ["title_limit", "description_limit"]:
        if p[key] is None or not 1 <= p[key] <= 10000:
            raise DomainError("文字数上限は1〜10000で指定してください。")
    for key in [
        "target_margin_pct",
        "fx_stress_pct",
        "shipping_stress_pct",
        "price_stress_pct",
    ]:
        if p[key] is None:
            raise DomainError(f"{key}: 入力してください。")
    if p["verified"] and not profile_verified(p):
        raise DomainError(
            "確認済みにするには費用・為替の全数値、出典URL、30日以内の確認日が必要です。"
        )
    if p["template_confirmed"] and (
        not p["template_source_url"]
        or not recent_date(p["template_checked_on"])
        or not p["template_note"]
    ):
        raise DomainError(
            "テンプレート確認には出典URL、30日以内の日付と、カテゴリ・属性・物流の確認メモが必要です。"
        )
    return p


def identity(p):
    return unicodedata.normalize("NFKC", p["sku"] or p["name"]).strip().casefold()


def profile_verified(p):
    return bool(
        p["verified"]
        and p["fee_source_url"]
        and p["fx_source_url"]
        and recent_date(p["checked_on"])
        and all(
            p[k] is not None
            for k in [
                "jpy_per_local",
                "commission_pct",
                "transaction_pct",
                "service_pct",
                "fee_tax_pct",
                "payout_pct",
                "ad_pct",
                "reserve_pct",
                "fixed_fee_local",
            ]
        )
    )


def D(v):
    return Decimal(str(v))


def rounded(v, places=2, up=False):
    return float(
        v.quantize(
            Decimal(1).scaleb(-places), rounding=ROUND_CEILING if up else ROUND_HALF_UP
        )
    )


def finance(p, s):
    required = [
        "jpy_per_local",
        "commission_pct",
        "transaction_pct",
        "service_pct",
        "fee_tax_pct",
        "payout_pct",
        "ad_pct",
        "reserve_pct",
        "fixed_fee_local",
    ]
    missing = [k for k in required if s[k] is None] + [
        k for k in COST_FIELDS + ["price_local"] if p[k] is None
    ]
    if missing or not p.get("price_local"):
        return {
            "available": False,
            "missing": missing or ["price_local"],
            "warnings": ["費用・価格・為替を入力すると計算できます。"],
        }
    fx = D(s["jpy_per_local"])

    def calc(price, rate=fx, shipping_multiplier=Decimal(1)):
        item = price * (1 - D(p["discount_pct"]) / 100)
        buyer = D(p["buyer_shipping_local"])
        revenue = item + buyer
        fees = D(s["fixed_fee_local"])
        for kind in ["commission", "transaction", "service"]:
            fees += (
                (revenue if s[kind + "_basis"] == "order" else item)
                * D(s[kind + "_pct"])
                / 100
            )
        fees *= 1 + D(s["fee_tax_pct"]) / 100
        payout = max(Decimal(0), revenue - fees) * D(s["payout_pct"]) / 100
        ad = item * D(s["ad_pct"]) / 100
        reserve = item * D(s["reserve_pct"]) / 100
        fixed_cost = sum(D(p[k]) for k in COST_FIELDS) - D(p["shipping_rebate_jpy"])
        fixed_cost += D(p["international_shipping_jpy"]) * (shipping_multiplier - 1)
        profit = (revenue - fees - payout - ad - reserve) * rate - fixed_cost
        return {
            "revenue_jpy": revenue * rate,
            "marketplace_fees_jpy": fees * rate,
            "payout_fee_jpy": payout * rate,
            "advertising_jpy": ad * rate,
            "reserve_jpy": reserve * rate,
            "cost_total_jpy": fixed_cost,
            "profit_jpy": profit,
            "margin_pct": profit / (revenue * rate) * 100 if revenue else Decimal(0),
        }

    result = calc(D(p["price_local"]))

    # Price is monotonic for realistic rates; infeasible rates yield no target rather than a fake fallback.
    def solve(target):
        def residual(x):
            r = calc(x)
            return r["profit_jpy"] - r["revenue_jpy"] * target / 100

        low, high = Decimal(0), Decimal("1000000000")
        if residual(high) < 0:
            return None
        if residual(low) >= 0:
            return 0.0
        for _ in range(100):
            mid = (low + high) / 2
            if residual(mid) >= 0:
                high = mid
            else:
                low = mid
        return rounded(high, MARKETS[p["market"]]["decimals"], up=True)

    stress = calc(
        D(p["price_local"]) * (1 - D(s["price_stress_pct"]) / 100),
        fx * (1 - D(s["fx_stress_pct"]) / 100),
        1 + D(s["shipping_stress_pct"]) / 100,
    )
    scenarios = []
    for factor in ["0.8", "0.9", "1", "1.1", "1.2"]:
        price = D(p["price_local"]) * D(factor)
        scenarios.append(
            {
                "price_local": rounded(price, MARKETS[p["market"]]["decimals"]),
                "profit_jpy": rounded(calc(price)["profit_jpy"]),
            }
        )
    warnings = []
    if not profile_verified(s):
        warnings.append(
            "試算条件は未確認または期限切れです。手数料・為替を確認してください。"
        )
    if result["profit_jpy"] <= 0:
        warnings.append("現在の価格では利益が残りません。")
    if stress["profit_jpy"] < 0:
        warnings.append("ストレス条件で赤字になります。")
    return {
        "available": True,
        **{k: rounded(v) for k, v in result.items()},
        "break_even_local": solve(Decimal(0)),
        "target_price_local": solve(D(s["target_margin_pct"])),
        "stress_profit_jpy": rounded(stress["profit_jpy"]),
        "verified": profile_verified(s),
        "scenarios": scenarios,
        "warnings": warnings,
    }


RISK_RULES = [
    (
        "high",
        "医薬品・危険物の可能性。販売可否と輸送可否を確認",
        r"医薬|処方|麻薬|武器|爆発|毒物|medicine|pharmaceutical|weapon|explosive|tobacco|vape|電子たばこ",
    ),
    (
        "high",
        "模倣品・権利侵害を疑う表現。正規性を確認",
        r"偽物|非公式|コピー品|レプリカ|counterfeit|replica|knock.?off",
    ),
    (
        "high",
        "効能や保証の断定表現。根拠と表示ルールを確認",
        r"必ず痩せ|治る|がんに効|100%効果|cure[sd]?\b|guaranteed results|100% authentic",
    ),
    (
        "review",
        "食品・サプリの輸入条件、成分・期限を確認",
        r"食品|お菓子|飲料|サプリ|お茶|snack|food|supplement|vitamin|tea\b",
    ),
    (
        "review",
        "化粧品・液体の成分、登録と配送条件を確認",
        r"化粧|コスメ|美容液|香水|液体|スプレー|cosmetic|serum|perfume|liquid|spray|cream",
    ),
    (
        "review",
        "電池・充電式製品の航空輸送条件を確認",
        r"電池|バッテリ|充電|リチウム|battery|lithium|rechargeable",
    ),
    (
        "review",
        "商標・著作権、正規仕入れと画像利用権を確認",
        r"ポケモン|サンリオ|ディズニ|任天堂|nike|adidas|disney|pokemon|sanrio|apple|sony|ブランド|キャラクター",
    ),
    (
        "review",
        "破損・材料・安全規格と梱包を確認",
        r"ガラス|陶器|ベビー|玩具|木製|glass|ceramic|baby|toy|bamboo",
    ),
]


def risks(p):
    text = " ".join(
        str(p[k])
        for k in [
            "name",
            "category",
            "english_name",
            "facts_en",
            "title",
            "description",
            "brand",
        ]
    )
    reasons = [
        {"level": level, "reason": reason}
        for level, reason, pattern in RISK_RULES
        if re.search(pattern, text, re.I)
    ]
    if not p["supplier_url"]:
        reasons.append(
            {
                "level": "review",
                "reason": "仕入れ先URLが未入力です。供給元と在庫を確認してください。",
            }
        )
    if p["weight_kg"] is not None and p["weight_kg"] > 2:
        reasons.append(
            {
                "level": "review",
                "reason": "梱包重量が2kg超です。配送見積とサイズ条件を再確認してください。",
            }
        )
    return {
        "level": (
            "high"
            if any(r["level"] == "high" for r in reasons)
            else "review" if reasons else "unchecked"
        ),
        "reasons": reasons,
        "note": "キーワードによる確認支援です。未検出でも販売可とは判定しません。",
    }


def approval_errors(p, s):
    errors = []
    f = finance(p, s)
    if not f["available"]:
        errors.append("利益計算に必要な費用・価格・為替を入力してください。")
    elif f["profit_jpy"] <= 0:
        errors.append("現在の価格が赤字または利益ゼロです。")
    if not profile_verified(s):
        errors.append(
            "販売国の手数料・為替を出典付きで確認してください（確認から30日以内）。"
        )
    for k, label in [
        ("risk_reviewed", "販売規制・配送条件"),
        ("rights_reviewed", "正規仕入れ・知的財産権"),
        ("market_reviewed", "対象国での販売資格・出店状況"),
    ]:
        if not p[k]:
            errors.append(label + "の確認が必要です。")
    if risks(p)["level"] == "high":
        errors.append(
            "高リスクの表現・商品に該当します。内容を修正・再調査してください。"
        )
    return errors


def readiness_errors(p, s):
    errors = approval_errors(p, s)
    if p["status"] not in {"approved", "ready"}:
        errors.append("人間による承認が必要です。")
    for k, label in [
        ("supplier_url", "仕入れ先URL"),
        ("sku", "SKU"),
        ("title", "タイトル"),
        ("description", "説明文"),
        ("category_id", "カテゴリID"),
        ("image_url", "メイン画像URL"),
        ("logistics", "物流チャンネル"),
    ]:
        if not p[k]:
            errors.append(label + "が未入力です。")
    for k, label in [
        ("weight_kg", "梱包重量"),
        ("length_cm", "長さ"),
        ("width_cm", "幅"),
        ("height_cm", "高さ"),
        ("stock", "確認済み在庫"),
    ]:
        if p[k] is None or p[k] <= 0:
            errors.append(label + "を0より大きい値で入力してください。")
    if not p["copy_reviewed"]:
        errors.append("タイトル・説明文の最終確認が必要です。")
    if (
        len(p["title"]) > s["title_limit"]
        or len(p["description"]) > s["description_limit"]
    ):
        errors.append("対象国の設定文字数上限を超えています。")
    if not s["template_confirmed"] or not recent_date(s["template_checked_on"]):
        errors.append(
            "対象国・カテゴリの最新テンプレートと必須属性を確認してください（30日以内）。"
        )
    language = MARKETS[p["market"]]["language"]
    if p["listing_language"] != language and not (
        p["market"] == "TH" and p["listing_language"] == "th"
    ):
        errors.append(
            "対象国の出品言語を確認してください。台湾は繁体字、ベトナムはベトナム語の確認が必要です。"
        )
    if re.search(r"[\u3040-\u30ff]", p["title"] + p["description"]):
        errors.append(
            "出品本文に日本語が残っています。対象国の言語へ修正してください。"
        )
    decimals = MARKETS[p["market"]]["decimals"]
    if p["price_local"] is not None and D(p["price_local"]) != D(
        p["price_local"]
    ).quantize(Decimal(1).scaleb(-decimals)):
        errors.append("現地価格の小数桁を通貨設定に合わせてください。")
    return list(dict.fromkeys(errors))
