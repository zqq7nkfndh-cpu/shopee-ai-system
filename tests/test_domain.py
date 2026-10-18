import unittest
from datetime import date, timedelta
from shopee_workbench.domain import *


def product(**kw):
    return validate_product(
        {
            **PRODUCT_DEFAULTS,
            "name": "ノート",
            "market": "SG",
            "cost_jpy": 800,
            "domestic_shipping_jpy": 200,
            "international_shipping_jpy": 700,
            "packaging_jpy": 80,
            "customs_jpy": 0,
            "other_jpy": 50,
            "price_local": 35,
            **kw,
        }
    )


def profile(**kw):
    return validate_profile(
        {
            **PROFILE_DEFAULTS,
            "jpy_per_local": 100,
            "commission_pct": 8,
            "transaction_pct": 3,
            "service_pct": 0,
            "fee_tax_pct": 0,
            "payout_pct": 2,
            "ad_pct": 2,
            "reserve_pct": 3,
            "fixed_fee_local": 0,
            **kw,
        }
    )


def verified_profile(**kw):
    return profile(
        **{
            "verified": True,
            "fee_source_url": "https://shopee.jp/service/",
            "fx_source_url": "https://example.com/fx",
            "checked_on": date.today().isoformat(),
            **kw,
        }
    )


class FinanceTests(unittest.TestCase):
    def test_hand_calculated_full_costs(self):
        f = finance(product(), profile())
        # 3500 sales -385 fees -62.3 payout -70 ads -105 reserve -1830 fixed
        self.assertEqual(f["profit_jpy"], 1047.7)
        self.assertEqual(f["cost_total_jpy"], 1830)
        self.assertEqual(f["margin_pct"], 29.93)
        self.assertFalse(f["verified"])
        self.assertLess(f["stress_profit_jpy"], f["profit_jpy"])

    def test_fee_bases_fee_tax_and_buyer_shipping(self):
        p = product(price_local=100, buyer_shipping_local=10, discount_pct=10)
        s = profile(
            commission_pct=10,
            transaction_pct=2,
            service_pct=3,
            fee_tax_pct=10,
            payout_pct=0,
            ad_pct=0,
            reserve_pct=0,
            fixed_fee_local=1,
        )
        # Item90 + buyer10. fees=(9+2+2.7+1)*1.1 =16.17
        self.assertEqual(finance(p, s)["marketplace_fees_jpy"], 1617)
        s["commission_basis"] = "order"
        self.assertEqual(finance(p, s)["marketplace_fees_jpy"], 1727)

    def test_break_even_ceiling_is_safe_in_all_markets(self):
        for code in MARKETS:
            p = product(market=code)
            f = finance(p, profile())
            boundary = f["break_even_local"]
            self.assertIsNotNone(boundary)
            p["price_local"] = boundary
            self.assertGreaterEqual(finance(p, profile())["profit_jpy"], 0)
            p["price_local"] = boundary - 10 ** (-MARKETS[code]["decimals"])
            self.assertLessEqual(finance(p, profile())["profit_jpy"], 0)

    def test_no_fake_profit_for_missing_or_zero_price(self):
        self.assertFalse(finance(product(), PROFILE_DEFAULTS)["available"])
        self.assertFalse(finance(product(price_local=None), profile())["available"])
        self.assertFalse(finance(product(price_local=0), profile())["available"])
        self.assertFalse(finance(product(cost_jpy=None), profile())["available"])

    def test_impossible_rates_do_not_invent_a_target(self):
        f = finance(product(), profile(commission_pct=90, transaction_pct=80))
        self.assertIsNone(f["break_even_local"])
        self.assertIsNone(f["target_price_local"])
        self.assertLess(f["profit_jpy"], 0)

    def test_zero_cost_and_return_reserve(self):
        p = product(**dict.fromkeys(COST_FIELDS, 0))
        f = finance(p, profile())
        self.assertEqual(f["break_even_local"], 0)
        self.assertEqual(f["reserve_jpy"], 105)

    def test_adverse_conditions_are_exact(self):
        f = finance(product(), profile())
        # 31.5*100*.9 revenue, proportional charges, 20% more on700 international shipping
        self.assertEqual(f["stress_profit_jpy"], 360.94)


class ValidationTests(unittest.TestCase):
    def test_reject_nonfinite_negative_boolean_and_bad_types(self):
        for value in [float("nan"), float("inf"), -1, True, "50"]:
            with self.subTest(value=value), self.assertRaises(DomainError):
                product(cost_jpy=value)
        with self.assertRaises(DomainError):
            product(buyer_shipping_local=None)
        with self.assertRaises(DomainError):
            product(stock=1.5)
        with self.assertRaises(DomainError):
            product(market="XX")
        with self.assertRaises(DomainError):
            product(category_id="nan")
        with self.assertRaises(DomainError):
            product(risk_reviewed="true")

    def test_url_schemes_and_credentials(self):
        for url in [
            "javascript:alert(1)",
            "file:///etc/passwd",
            "https://a:b@example.com",
            "https://exa mple.com",
        ]:
            with self.subTest(url=url), self.assertRaises(DomainError):
                product(supplier_url=url)

    def test_observations_need_provenance(self):
        with self.assertRaises(DomainError):
            product(observed_sales=0)
        with self.assertRaises(DomainError):
            product(demand_level="high")
        p = product(
            demand_level="high",
            observed_sales=10,
            research_date=date.today().isoformat(),
            research_source_url="https://example.com/item",
            research_note="検索語note、期間不明、表示数を転記",
        )
        self.assertEqual(p["observed_sales"], 10)

    def test_profile_verification_requires_fresh_sources(self):
        self.assertTrue(profile_verified(verified_profile()))
        with self.assertRaises(DomainError):
            profile(verified=True)
        with self.assertRaises(DomainError):
            verified_profile(checked_on=(date.today() - timedelta(days=31)).isoformat())

    def test_casefold_risks_and_no_safe_verdict(self):
        self.assertEqual(risks(product(name="NIKE SHOES"))["level"], "review")
        self.assertEqual(risks(product(name="Lithium BATTERY"))["level"], "review")
        self.assertEqual(risks(product(name="counterfeit replica"))["level"], "high")
        self.assertNotEqual(
            risks(product(supplier_url="https://example.com"))["level"], "safe"
        )

    def test_readiness_blocks_language_and_missing_fields(self):
        errors = readiness_errors(product(), verified_profile())
        self.assertTrue(any("承認" in e for e in errors))
        self.assertTrue(any("カテゴリ" in e for e in errors))
        p = product(
            market="TW", price_local=35, title="日本のノート", description="説明"
        )
        errors = readiness_errors(p, verified_profile())
        self.assertTrue(any("言語" in e for e in errors))
        self.assertTrue(any("日本語" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
