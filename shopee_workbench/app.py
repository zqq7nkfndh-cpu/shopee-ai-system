"""Authenticated same-origin Flask API and buildless responsive UI."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

from flask import Flask, Response, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from . import ai
from .domain import (
    MARKETS,
    PRODUCT_DEFAULTS,
    PROFILE_DEFAULTS,
    STATUSES,
    DomainError,
    finance,
    readiness_errors,
    risks,
    validate_product,
    validate_profile,
)
from .exports import preparation_csv
from .importer import parse_csv
from .store import Store

STATIC = Path(__file__).parent / "static"


def create_app(config=None):
    app = Flask(__name__, static_folder=str(STATIC), static_url_path="/assets")
    production = os.environ.get("APP_ENV") == "production"
    app.config.update(
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
        DATABASE=os.environ.get("DATABASE_PATH", "var/workbench.sqlite3"),
        PASSWORD_HASH=os.environ.get("APP_PASSWORD_HASH", ""),
        PASSWORD=os.environ.get("APP_PASSWORD", ""),
        COOKIE_SECURE=production,
        APP_ORIGIN=os.environ.get("APP_ORIGIN", "").rstrip("/"),
        TESTING=False,
        PRODUCTION=production,
    )
    if config:
        app.config.update(config)
    if not app.config["PASSWORD_HASH"]:
        password = app.config["PASSWORD"]
        if len(password) < 12:
            raise RuntimeError(
                "APP_PASSWORD（12文字以上）またはAPP_PASSWORD_HASHを設定してください。"
            )
        app.config["PASSWORD_HASH"] = generate_password_hash(password)
    app.config["PASSWORD"] = ""
    if app.config["PRODUCTION"] and not app.config["APP_ORIGIN"].startswith("https://"):
        raise RuntimeError("公開環境はHTTPSのAPP_ORIGINが必要です。")
    db = Store(app.config["DATABASE"])
    app.extensions["store"] = db

    def json_body():
        if not request.is_json:
            raise DomainError("JSON形式で送信してください。", 415)
        value = request.get_json()
        if not isinstance(value, dict):
            raise DomainError("JSONオブジェクトが必要です。")
        return value

    @app.before_request
    def protect():
        if not request.path.startswith("/api/"):
            return
        g.auth = None
        token = request.cookies.get("workbench_session", "")
        if token:
            with db.connect() as con:
                row = con.execute(
                    "SELECT * FROM sessions WHERE token=? AND expires>?",
                    (hashlib.sha256(token.encode()).hexdigest(), time.time()),
                ).fetchone()
                if row:
                    g.auth = dict(row)
        public = request.path in {"/api/session", "/api/login", "/api/health"}
        if not public and not g.auth:
            raise DomainError("ログインしてください。", 401)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("Origin")
            expected = app.config["APP_ORIGIN"] or request.host_url.rstrip("/")
            if origin and origin != expected:
                raise DomainError("別のサイトからの操作は受け付けません。", 403)
            if request.path == "/api/login":
                expected_csrf = request.cookies.get("workbench_login_csrf", "")
            else:
                expected_csrf = g.auth["csrf"] if g.auth else ""
            if not expected_csrf or not secrets.compare_digest(
                expected_csrf, request.headers.get("X-CSRF-Token", "")
            ):
                raise DomainError(
                    "操作用トークンが切れました。再読込してください。", 403
                )

    @app.after_request
    def headers(response):
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            }
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if app.config["COOKIE_SECURE"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.errorhandler(DomainError)
    def domain_error(error):
        return jsonify(error=str(error)), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        return (
            jsonify(
                error="リクエストを処理できません。形式・サイズ・URLを確認してください。"
            ),
            error.code,
        )

    @app.errorhandler(sqlite3.OperationalError)
    def database_error(error):
        app.logger.error("Database operation failed (%s)", type(error).__name__)
        return (
            jsonify(
                error="保存先を利用できません。空き容量・権限を確認して再試行してください。"
            ),
            503,
        )

    @app.errorhandler(Exception)
    def unexpected(error):
        app.logger.error("Unhandled error (%s)", type(error).__name__)
        return (
            jsonify(error="処理に失敗しました。入力を保持して再試行してください。"),
            500,
        )

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/api/health")
    def health():
        with db.connect() as con:
            con.execute("SELECT 1").fetchone()
        return jsonify(status="ok", version="2.0.0")

    @app.get("/api/session")
    def session():
        if g.auth:
            return jsonify(authenticated=True, csrf=g.auth["csrf"])
        csrf = secrets.token_urlsafe(32)
        response = jsonify(authenticated=False, csrf=csrf)
        response.set_cookie(
            "workbench_login_csrf",
            csrf,
            httponly=True,
            secure=app.config["COOKIE_SECURE"],
            samesite="Strict",
            max_age=600,
        )
        return response

    @app.post("/api/login")
    def login():
        data = json_body()
        password = data.get("password", "")
        if not isinstance(password, str) or len(password) > 1024:
            raise DomainError("パスワードの形式を確認してください。")
        client = request.remote_addr or "local"
        stamp = time.time()
        with db.connect(True) as con:
            con.execute("DELETE FROM attempts WHERE since<?", (stamp - 900,))
            row = con.execute(
                "SELECT count FROM attempts WHERE client=?", (client,)
            ).fetchone()
            if row and row[0] >= 10:
                raise DomainError(
                    "ログイン試行が多すぎます。15分後に再試行してください。", 429
                )
            con.execute(
                "INSERT INTO attempts VALUES (?,1,?) ON CONFLICT(client) DO UPDATE SET count=count+1",
                (client, stamp),
            )
        if not check_password_hash(app.config["PASSWORD_HASH"], password):
            raise DomainError("パスワードが違います。", 401)
        token = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        with db.connect(True) as con:
            con.execute("DELETE FROM attempts WHERE client=?", (client,))
            con.execute("DELETE FROM sessions WHERE expires<?", (stamp,))
            con.execute(
                "INSERT INTO sessions VALUES (?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), csrf, stamp + 8 * 3600),
            )
        response = jsonify(authenticated=True, csrf=csrf)
        response.set_cookie(
            "workbench_session",
            token,
            httponly=True,
            secure=app.config["COOKIE_SECURE"],
            samesite="Strict",
            max_age=8 * 3600,
        )
        response.delete_cookie("workbench_login_csrf")
        return response

    @app.post("/api/logout")
    def logout():
        with db.connect(True) as con:
            con.execute("DELETE FROM sessions WHERE token=?", (g.auth["token"],))
        response = jsonify(ok=True)
        response.delete_cookie("workbench_session")
        return response

    def enriched(p, profiles):
        s = profiles[p["market"]]
        return {
            **p,
            "finance": finance(p, s),
            "risk": risks(p),
            "readiness_errors": readiness_errors(p, s),
        }

    @app.get("/api/bootstrap")
    def bootstrap():
        snapshot = db.workspace()
        profiles = snapshot["profiles"]
        return jsonify(
            markets=MARKETS,
            statuses=STATUSES,
            product_defaults=PRODUCT_DEFAULTS,
            profile_defaults=PROFILE_DEFAULTS,
            profiles=profiles,
            products=[enriched(p, profiles) for p in snapshot["products"]],
            ai_available=bool(os.environ.get("OPENAI_API_KEY")),
            manual_only=True,
        )

    @app.post("/api/products")
    def create_product():
        return jsonify(db.create(json_body())), 201

    @app.put("/api/products/<pid>")
    def update_product(pid):
        body = json_body()
        if set(body) != {"data", "version"} or type(body["version"]) is not int:
            raise DomainError("データと更新番号が必要です。")
        return jsonify(db.update(pid, body["data"], body["version"]))

    @app.post("/api/products/<pid>/status")
    def status(pid):
        body = json_body()
        if set(body) != {"status", "version"} or type(body["version"]) is not int:
            raise DomainError("状態と更新番号が必要です。")
        return jsonify(db.transition(pid, body["status"], body["version"]))

    @app.get("/api/products/<pid>/history")
    def history(pid):
        return jsonify(db.history(pid))

    @app.post("/api/products/<pid>/copy")
    def copy(pid):
        # Explicit button is the only operation that sends these product facts to OpenAI.
        return jsonify(ai.suggest(db.get(pid)))

    @app.put("/api/profiles/<market>")
    def profile(market):
        body = json_body()
        if set(body) != {"data", "version"} or type(body["version"]) is not int:
            raise DomainError("設定と更新番号が必要です。")
        db.update_profile(market, body["data"], body["version"])
        return jsonify(ok=True)

    @app.post("/api/finance")
    def simulate():
        body = json_body()
        return jsonify(
            finance(
                validate_product(body.get("product", {})),
                validate_profile(body.get("profile", {})),
            )
        )

    @app.get("/api/ideas")
    def ideas():
        return Response(
            (Path(__file__).parent / "catalogue.json").read_text(),
            mimetype="application/json",
        )

    @app.post("/api/compare")
    def compare():
        ids = json_body().get("ids", [])
        if (
            not isinstance(ids, list)
            or not 2 <= len(ids) <= 6
            or not all(isinstance(i, str) for i in ids)
            or len(set(ids)) < 2
        ):
            raise DomainError("比較する商品を2〜6件選んでください。")
        profiles = db.profiles()
        return jsonify(
            ai.compare([enriched(db.get(pid), profiles) for pid in dict.fromkeys(ids)])
        )

    @app.get("/api/export/<market>")
    def export(market):
        if market not in MARKETS:
            raise DomainError("販売国が不正です。")
        snapshot = db.workspace()
        profile = snapshot["profiles"][market]
        rows = [
            p
            for p in snapshot["products"]
            if p["market"] == market and p["status"] == "ready"
        ]
        if not rows:
            raise DomainError("この国には出品準備完了の商品がありません。", 422)
        blocked = [
            p["name"] + ": " + "; ".join(readiness_errors(p, profile))
            for p in rows
            if readiness_errors(p, profile)
        ]
        if blocked:
            raise DomainError("再確認が必要です。\n" + "\n".join(blocked), 422)
        content = preparation_csv(rows, profile)
        return Response(
            content,
            mimetype="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="listing_preparation_{market}.csv"'
            },
        )

    @app.post("/api/import")
    def import_csv():
        return jsonify(db.import_candidates(parse_csv(json_body().get("csv", ""))))

    @app.get("/api/backup")
    def backup():
        return Response(
            json.dumps(db.backup(), ensure_ascii=False, allow_nan=False),
            mimetype="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="shopee_backup.json"'
            },
        )

    @app.post("/api/restore")
    def restore():
        return jsonify(restored=db.restore(json_body()))

    return app
