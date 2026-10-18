import concurrent.futures
import csv
import io
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from werkzeug.security import generate_password_hash
from shopee_workbench.app import create_app
from shopee_workbench.domain import (
    PRODUCT_DEFAULTS,
    PROFILE_DEFAULTS,
    DomainError,
    readiness_errors,
)
from shopee_workbench.store import Store
from shopee_workbench.importer import parse_csv, load_legacy
from shopee_workbench import ai
from shopee_workbench.exports import safe_cell
from test_domain import product, profile, verified_profile

PASSWORD = "test-password-only-123"
PASSWORD_HASH = generate_password_hash(PASSWORD)


def data_only(p):
    return {k: p[k] for k in PRODUCT_DEFAULTS}


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": str(Path(self.temp.name) / "test.sqlite3"),
                "PASSWORD_HASH": PASSWORD_HASH,
            }
        )
        self.client = self.app.test_client()
        self.db = self.app.extensions["store"]
        session = self.client.get("/api/session").get_json()
        login = self.client.post(
            "/api/login",
            json={"password": PASSWORD},
            headers={"X-CSRF-Token": session["csrf"]},
        )
        self.assertEqual(login.status_code, 200)
        self.csrf = login.get_json()["csrf"]
        self.headers = {"X-CSRF-Token": self.csrf}

    def tearDown(self):
        self.temp.cleanup()

    def create(self, **kw):
        return self.client.post(
            "/api/products", json=product(**kw), headers=self.headers
        ).get_json()

    def put(self, p, **kw):
        return self.client.put(
            "/api/products/" + p["id"],
            json={"data": {**data_only(p), **kw}, "version": p["version"]},
            headers=self.headers,
        )

    def transition(self, p, status):
        return self.client.post(
            "/api/products/" + p["id"] + "/status",
            json={"status": status, "version": p["version"]},
            headers=self.headers,
        )

    def make_ready(self):
        self.db.update_profile(
            "SG",
            verified_profile(
                template_confirmed=True,
                template_source_url="https://seller.shopee.sg/",
                template_checked_on=date.today().isoformat(),
                template_note="test only: notebook attributes verified",
            ),
            1,
        )
        p = self.create(
            name="ノート",
            sku="NOTE-01",
            supplier_url="https://example.com/notebook",
            title="Plain Notebook",
            description="Notebook. Size: A5.",
            category_id="123",
            image_url="https://example.com/note.jpg",
            weight_kg=0.2,
            length_cm=25,
            width_cm=20,
            height_cm=3,
            stock=1,
            logistics="Confirmed test channel",
        )
        p = self.put(
            p,
            risk_reviewed=True,
            rights_reviewed=True,
            copy_reviewed=True,
            market_reviewed=True,
        ).get_json()
        response = self.transition(p, "approved")
        self.assertEqual(response.status_code, 200, response.get_json())
        p = response.get_json()
        response = self.transition(p, "ready")
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_auth_csrf_and_no_public_data(self):
        anon = self.app.test_client()
        self.assertEqual(anon.get("/api/bootstrap").status_code, 401)
        self.assertEqual(anon.get("/api/backup").status_code, 401)
        self.assertEqual(
            self.client.post("/api/products", json=product()).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                "/api/products",
                json=product(),
                headers={**self.headers, "Origin": "https://attacker.example"},
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/health").status_code, 200)

    def test_login_rate_limited(self):
        other = self.app.test_client()
        token = other.get("/api/session").get_json()["csrf"]
        for _ in range(10):
            self.assertEqual(
                other.post(
                    "/api/login",
                    json={"password": "bad"},
                    headers={"X-CSRF-Token": token},
                ).status_code,
                401,
            )
        self.assertEqual(
            other.post(
                "/api/login",
                json={"password": PASSWORD},
                headers={"X-CSRF-Token": token},
            ).status_code,
            429,
        )

    def test_headers_and_cookie_flags(self):
        res = self.client.get("/")
        self.assertIn("Research Desk", res.text)
        self.assertIn("script-src 'self'", res.headers["Content-Security-Policy"])
        self.assertEqual(res.headers["X-Frame-Options"], "DENY")
        for url in ["/assets/app.js", "/assets/styles.css", "/assets/mark.svg"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            response.close()
        res.close()
        self.assertEqual(
            self.client.get("/api/bootstrap").headers["Cache-Control"], "no-store"
        )

    def test_create_edit_duplicate_and_persistence(self):
        p = self.create(name="Notebook", sku="NOTE-1")
        self.assertIn("id", p)
        response = self.client.post(
            "/api/products",
            json=product(name="Other", sku="note-1"),
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.put(p, notes="saved").status_code, 200)
        self.assertEqual(self.put(p, notes="stale write").status_code, 409)
        reopened = Store(Path(self.temp.name) / "test.sqlite3")
        self.assertEqual(reopened.get(p["id"])["notes"], "saved")
        self.assertEqual(
            len(self.client.get("/api/products/" + p["id"] + "/history").get_json()), 2
        )

    def test_approval_export_and_reapproval(self):
        p = self.make_ready()
        response = self.client.get("/api/export/SG")
        self.assertEqual(response.status_code, 200, response.text)
        rows = list(csv.DictReader(io.StringIO(response.data.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["currency"], "SGD")
        self.assertIn("INTERNAL_PREPARATION_ONLY", rows[0]["format_notice"])
        updated = self.put(p, price_local=30).get_json()
        self.assertEqual(updated["status"], "researching")
        self.assertEqual(self.client.get("/api/export/SG").status_code, 422)

    def test_settings_changes_invalidate_and_do_not_erase(self):
        p = self.make_ready()
        s = verified_profile(commission_pct=9)
        self.db.update_profile("SG", s, 2)
        updated = self.db.get(p["id"])
        self.assertEqual(updated["status"], "researching")
        self.assertEqual(updated["title"], p["title"])
        self.assertGreater(updated["version"], p["version"])
        self.assertEqual(self.put(p, notes="stale").status_code, 409)

    def test_no_approval_without_review(self):
        p = self.create()
        self.assertEqual(self.transition(p, "approved").status_code, 422)
        self.assertEqual(self.transition(p, "ready").status_code, 422)
        self.assertEqual(self.put(p, status="ready").status_code, 400)

    def test_copy_is_optional_and_non_destructive(self):
        p = self.create(
            english_name="Plain Notebook",
            facts_en="Size: A5.",
            title="Edited title",
            description="Keep my description.",
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            r = self.client.post(
                "/api/products/" + p["id"] + "/copy", headers=self.headers
            ).get_json()
        self.assertEqual(r["source"], "template")
        self.assertEqual(r["title"], "Plain Notebook")
        saved = self.db.get(p["id"])
        self.assertEqual(saved["title"], "Edited title")
        self.assertEqual(saved["version"], 1)
        self.assertNotIn("authentic", r["description"])

    def test_backup_restore_and_secret_exclusion(self):
        p = self.make_ready()
        backup = self.client.get("/api/backup").get_json()
        text = json.dumps(backup)
        self.assertNotIn(PASSWORD, text)
        self.assertNotIn("sessions", text)
        self.assertNotIn("OPENAI_API_KEY", text)
        self.assertEqual(
            self.client.post(
                "/api/restore", json=backup, headers=self.headers
            ).status_code,
            409,
        )
        other = Store(Path(self.temp.name) / "other.sqlite3")
        self.assertEqual(other.restore(backup), 1)
        restored = other.products()[0]
        self.assertEqual(restored["title"], p["title"])
        self.assertEqual(restored["status"], "researching")
        self.assertFalse(restored["copy_reviewed"])
        self.assertFalse(other.profiles()["SG"]["verified"])

    def test_restore_invalid_is_atomic(self):
        backup = self.db.backup()
        backup["products"] = [product(), {**product(name="Bad"), "price_local": -5}]
        with self.assertRaises(DomainError):
            self.db.restore(backup)
        self.assertEqual(len(self.db.products()), 0)

    def test_csv_import_duplicates_and_invalid_batch(self):
        text = "name,market,sku,cost_jpy\nNotebook,SG,N1,800\nNotebook,SG,N1,800\n"
        r = self.client.post("/api/import", json={"csv": text}, headers=self.headers)
        self.assertEqual(r.get_json(), {"added": 1, "skipped": 1})
        p = self.db.products()[0]
        self.put(p, notes="keep")
        r = self.client.post("/api/import", json={"csv": text}, headers=self.headers)
        self.assertEqual(r.get_json(), {"added": 0, "skipped": 2})
        self.assertEqual(self.db.get(p["id"])["notes"], "keep")
        bad = "name,market,cost_jpy\nOkay,SG,100\nBad,SG,NaN\n"
        self.assertEqual(
            self.client.post(
                "/api/import", json={"csv": bad}, headers=self.headers
            ).status_code,
            400,
        )
        self.assertEqual(len(self.db.products()), 1)

    def test_all_api_input_failures_are_json(self):
        for value in [None, [], 42, "bad"]:
            r = self.client.post("/api/products", json=value, headers=self.headers)
            self.assertIn(r.status_code, [400, 415])
            self.assertIn("error", r.get_json())
        self.assertEqual(
            self.client.get("/api/products/missing/history").status_code, 404
        )
        self.assertEqual(self.client.get("/assets/../../.env").status_code, 404)

    def test_compare_and_numeric_rejection(self):
        a = self.create(name="A")
        b = self.create(name="B", market="MY")
        r = self.client.post(
            "/api/compare", json={"ids": [a["id"], b["id"]]}, headers=self.headers
        ).get_json()
        self.assertEqual(r["source"], "calculated")
        self.assertEqual(len(r["items"]), 2)
        self.assertIn("需要", r["explanation"])
        r = self.client.post(
            "/api/finance",
            json={"product": product(), "profile": {**profile(), "jpy_per_local": 0}},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 400)

    def test_parallel_writes_have_one_winner(self):
        p = self.create()

        def update(value):
            try:
                return self.db.update(p["id"], {**data_only(p), "notes": value}, 1)[
                    "notes"
                ]
            except DomainError as exc:
                return exc.status

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, ["one", "two"]))
        self.assertEqual(results.count(409), 1)
        self.assertEqual(self.db.get(p["id"])["version"], 2)

    def test_online_backup_keeps_history_and_refuses_overwrite(self):
        p = self.create()
        output = Path(self.temp.name) / "snapshot.sqlite3"
        self.db.backup_to(output)
        snapshot = Store(output)
        self.assertEqual(snapshot.get(p["id"])["name"], p["name"])
        self.assertEqual(len(snapshot.history(p["id"])), 1)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(DomainError):
            self.db.backup_to(output)

    def test_invalid_status_and_restore_profile_types_are_rejected(self):
        p = self.create()
        self.assertEqual(self.transition(p, []).status_code, 400)
        empty = Store(Path(self.temp.name) / "empty.sqlite3")
        backup = empty.backup()
        backup["profiles"]["SG"] = []
        with self.assertRaises(DomainError):
            empty.restore(backup)

    def test_no_shopee_mutation_endpoints(self):
        for endpoint in ["/api/publish", "/api/buy", "/api/payment"]:
            self.assertEqual(
                self.client.post(endpoint, headers=self.headers).status_code, 404
            )


class UtilityTests(unittest.TestCase):
    def test_formula_injection(self):
        for value in ["=1+2", "+SUM(1)", "-formula", "@SUM(1)", "  =cmd", "\t=1"]:
            self.assertTrue(str(safe_cell(value)).startswith("'"))
        self.assertEqual(safe_cell(12.5), 12.5)

    def test_ai_failures_and_malformed_json_fall_back(self):
        def failure(*args, **kwargs):
            raise TimeoutError()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder-not-a-key"}):
            result = ai.suggest(product(english_name="Notebook"), opener=failure)
        self.assertEqual(result["source"], "template")
        self.assertIn("利用できなかった", result["review_notes"])
        self.assertEqual(ai.fallback(product())["title"], "")

    def test_ai_success_schema_and_minimal_payload(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, *args):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "title": "Notebook",
                                            "description": "Size: A5.",
                                            "review_notes": "要確認",
                                        }
                                    )
                                }
                            }
                        ]
                    }
                ).encode()

        captured = {}

        def opener(req, timeout):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data)
            return Response()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "placeholder-test-key"}):
            result = ai.suggest(
                product(
                    supplier_url="https://private.example/supplier",
                    english_name="Notebook",
                ),
                opener=opener,
            )
        self.assertEqual(result["source"], "openai")
        self.assertEqual(captured["url"], "https://api.openai.com/v1/chat/completions")
        self.assertFalse(captured["body"]["store"])
        sent = captured["body"]["messages"][1]["content"]
        self.assertNotIn("private.example", sent)
        self.assertNotIn("cost_jpy", sent)

        def malformed(req, timeout):
            response = Response()
            response.read = lambda *args: b'{"choices": []}'
            return response

        with patch.dict(os.environ, {"OPENAI_API_KEY": "placeholder-test-key"}):
            result = ai.suggest(product(english_name="Notebook"), opener=malformed)
        self.assertEqual(result["source"], "template")

    def test_old_csv_import_is_idempotent(self):
        rows, warnings = load_legacy(
            Path(__file__).resolve().parents[1] / "ai_side_biz"
        )
        self.assertGreater(len(rows), 0)
        self.assertTrue(all(p["price_local"] is None for p in rows))
        self.assertTrue(all(p["supplier_url"] == "" for p in rows))
        with tempfile.TemporaryDirectory() as d:
            db = Store(Path(d) / "legacy.db")
            self.assertGreater(db.import_candidates(rows)["added"], 0)
            self.assertEqual(db.import_candidates(rows)["added"], 0)

    def test_production_requires_secure_configuration(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                create_app(
                    {
                        "PRODUCTION": True,
                        "APP_ORIGIN": "http://example.com",
                        "DATABASE": d + "/prod.db",
                        "PASSWORD_HASH": PASSWORD_HASH,
                    }
                )


if __name__ == "__main__":
    unittest.main()
