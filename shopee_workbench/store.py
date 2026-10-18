"""SQLite repository. Every write is atomic and updates have optimistic concurrency checks."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from .domain import (
    MARKETS,
    PRODUCT_DEFAULTS,
    PROFILE_DEFAULTS,
    DomainError,
    approval_errors,
    identity,
    now,
    readiness_errors,
    validate_product,
    validate_profile,
)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError(
                    "Unsupported database version; restore with a compatible app."
                )
            con.executescript("""
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY, market TEXT NOT NULL, identity_key TEXT NOT NULL,
                    data TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(market,identity_key));
                CREATE TABLE IF NOT EXISTS profiles (market TEXT PRIMARY KEY, data TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, product_id TEXT, action TEXT NOT NULL, snapshot TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (client TEXT PRIMARY KEY, count INTEGER NOT NULL, since REAL NOT NULL);
                PRAGMA user_version=1;
            """)
            for market in MARKETS:
                con.execute(
                    "INSERT OR IGNORE INTO profiles(market,data) VALUES (?,?)",
                    (market, json.dumps(PROFILE_DEFAULTS)),
                )
        self.path.chmod(0o600)

    @contextmanager
    def connect(self, write=False):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except sqlite3.IntegrityError as exc:
            con.rollback()
            raise DomainError(
                "同じSKU（未指定時は同じ商品名）がこの国に存在します。既存商品を編集してください。",
                409,
            ) from exc
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def unpack(row):
        if not row:
            raise DomainError("商品が見つかりません。", 404)
        return {
            **json.loads(row["data"]),
            "id": row["id"],
            "version": row["version"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def products(self):
        with self.connect() as con:
            return [
                self.unpack(r)
                for r in con.execute(
                    "SELECT * FROM products ORDER BY updated_at DESC,id"
                )
            ]

    def get(self, pid):
        with self.connect() as con:
            return self.unpack(
                con.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            )

    def profiles(self):
        with self.connect() as con:
            return {
                r["market"]: {**json.loads(r["data"]), "version": r["version"]}
                for r in con.execute("SELECT * FROM profiles")
            }

    @staticmethod
    def event(con, pid, action, snapshot):
        con.execute(
            "INSERT INTO events(product_id,action,snapshot,created_at) VALUES (?,?,?,?)",
            (pid, action, json.dumps(snapshot, ensure_ascii=False), now()),
        )

    def create(self, data):
        p = validate_product(data)
        if p["status"] not in {"candidate", "researching"}:
            raise DomainError("新規商品は候補または調査中で登録してください。")
        p.update(
            risk_reviewed=False,
            rights_reviewed=False,
            copy_reviewed=False,
            market_reviewed=False,
        )
        pid = str(uuid.uuid4())
        timestamp = now()
        with self.connect(True) as con:
            con.execute(
                "INSERT INTO products(id,market,identity_key,data,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                (
                    pid,
                    p["market"],
                    identity(p),
                    json.dumps(p, ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
            self.event(con, pid, "created", p)
        return self.get(pid)

    def update(self, pid, data, version):
        p = validate_product(data)
        with self.connect(True) as con:
            old = self.unpack(
                con.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            )
            if old["version"] != version:
                raise DomainError(
                    "別の画面で更新されています。再読込して変更内容を確認してください。",
                    409,
                )
            if p["market"] != old["market"]:
                raise DomainError(
                    "販売国は変更できません。別の国には新規商品として登録してください。"
                )
            if p["status"] != old["status"]:
                raise DomainError("状態は専用の承認・状態変更操作で更新してください。")
            changed = {k for k in p if p[k] != old[k]}
            if not changed:
                return old
            meaningful = changed - {
                "notes",
                "research_note",
                "research_source_url",
                "research_date",
                "demand_level",
                "competitor_count",
                "competitor_price_local",
                "observed_sales",
            }
            if meaningful and old["status"] in {"approved", "ready"}:
                p["status"] = "researching"
            if changed & {
                "name",
                "category",
                "english_name",
                "facts_en",
                "title",
                "description",
                "brand",
                "supplier_url",
            }:
                p["risk_reviewed"] = False
                p["rights_reviewed"] = False
            if changed & {
                "title",
                "description",
                "english_name",
                "facts_en",
                "listing_language",
            }:
                p["copy_reviewed"] = False
            con.execute(
                "UPDATE products SET identity_key=?,data=?,version=version+1,updated_at=? WHERE id=?",
                (identity(p), json.dumps(p, ensure_ascii=False), now(), pid),
            )
            self.event(
                con, pid, "updated", {"before": {k: old[k] for k in p}, "after": p}
            )
        return self.get(pid)

    def transition(self, pid, status, version):
        if not isinstance(status, str) or status not in {
            "candidate",
            "researching",
            "approved",
            "ready",
            "rejected",
        }:
            raise DomainError("状態を選択してください。")
        with self.connect(True) as con:
            old = self.unpack(
                con.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            )
            if old["version"] != version:
                raise DomainError("更新が競合しました。再読込してください。", 409)
            profile = json.loads(
                con.execute(
                    "SELECT data FROM profiles WHERE market=?", (old["market"],)
                ).fetchone()[0]
            )
            if status == "approved":
                errors = approval_errors(old, profile)
                if errors:
                    raise DomainError("\n".join(errors), 422)
            elif status == "ready":
                errors = readiness_errors(old, profile)
                if errors:
                    raise DomainError("\n".join(errors), 422)
            p = {k: old[k] for k in PRODUCT_DEFAULTS}
            p["status"] = status
            con.execute(
                "UPDATE products SET data=?,version=version+1,updated_at=? WHERE id=?",
                (json.dumps(p, ensure_ascii=False), now(), pid),
            )
            self.event(con, pid, "status:" + status, p)
        return self.get(pid)

    def update_profile(self, market, data, version):
        if market not in MARKETS:
            raise DomainError("販売国が不正です。")
        s = validate_profile(data)
        with self.connect(True) as con:
            current = con.execute(
                "SELECT * FROM profiles WHERE market=?", (market,)
            ).fetchone()
            if current["version"] != version:
                raise DomainError(
                    "設定が別の画面で更新されています。再読込してください。", 409
                )
            if json.loads(current["data"]) == s:
                return
            con.execute(
                "UPDATE profiles SET data=?,version=version+1 WHERE market=?",
                (json.dumps(s, ensure_ascii=False), market),
            )
            self.event(con, None, "profile:" + market, s)
            for row in con.execute(
                "SELECT * FROM products WHERE market=?", (market,)
            ).fetchall():
                p = json.loads(row["data"])
                if p["status"] in {"approved", "ready"}:
                    p["status"] = "researching"
                    con.execute(
                        "UPDATE products SET data=?,version=version+1,updated_at=? WHERE id=?",
                        (json.dumps(p, ensure_ascii=False), now(), row["id"]),
                    )
                    self.event(
                        con, row["id"], "settings_changed:reapproval_required", p
                    )

    def history(self, pid):
        self.get(pid)
        with self.connect() as con:
            return [
                {
                    "action": r["action"],
                    "created_at": r["created_at"],
                    "snapshot": json.loads(r["snapshot"]),
                }
                for r in con.execute(
                    "SELECT * FROM events WHERE product_id=? ORDER BY id DESC LIMIT 30",
                    (pid,),
                )
            ]

    def workspace(self):
        # Read related records from one consistent WAL snapshot.
        with self.connect() as con:
            con.execute("BEGIN")
            return {
                "products": [
                    self.unpack(r)
                    for r in con.execute(
                        "SELECT * FROM products ORDER BY updated_at DESC,id"
                    )
                ],
                "profiles": {
                    r["market"]: {**json.loads(r["data"]), "version": r["version"]}
                    for r in con.execute("SELECT * FROM profiles")
                },
            }

    def backup(self):
        # One read transaction: products and profiles represent the same database snapshot.
        with self.connect() as con:
            con.execute("BEGIN")
            return {
                "format": "shopee-research-desk",
                "schema_version": 1,
                "exported_at": now(),
                "products": [
                    self.unpack(r) for r in con.execute("SELECT * FROM products")
                ],
                "profiles": {
                    r["market"]: json.loads(r["data"])
                    for r in con.execute("SELECT * FROM profiles")
                },
            }

    def restore(self, backup):
        if (
            not isinstance(backup, dict)
            or backup.get("format") != "shopee-research-desk"
            or backup.get("schema_version") != 1
        ):
            raise DomainError("対応するバックアップJSONを選んでください。")
        if (
            not isinstance(backup.get("products"), list)
            or len(backup["products"]) > 2000
            or not isinstance(backup.get("profiles"), dict)
        ):
            raise DomainError("バックアップ構造または件数が不正です。")
        products = []
        keys = set()
        for row in backup["products"]:
            if not isinstance(row, dict):
                raise DomainError("商品データが不正です。")
            p = validate_product(
                {k: v for k, v in row.items() if k in PRODUCT_DEFAULTS}
            )
            key = (p["market"], identity(p))
            if key in keys:
                raise DomainError("バックアップ内に商品重複があります。")
            keys.add(key)
            # Restored approvals must be reviewed against current market conditions.
            if p["status"] in {"approved", "ready"}:
                p["status"] = "researching"
            p.update(
                risk_reviewed=False,
                rights_reviewed=False,
                copy_reviewed=False,
                market_reviewed=False,
            )
            products.append(p)
        profiles = {}
        if set(backup["profiles"]) != set(MARKETS):
            raise DomainError("販売国の設定が不足しています。")
        for market, data in backup["profiles"].items():
            if not isinstance(data, dict):
                raise DomainError("販売国設定の形式が不正です。")
            data = dict(data)
            data.update(verified=False, template_confirmed=False)
            profiles[market] = validate_profile(data)
        with self.connect(True) as con:
            if con.execute("SELECT COUNT(*) FROM products").fetchone()[0]:
                raise DomainError(
                    "復元は商品が空の環境で行ってください。現在のデータは上書きしません。",
                    409,
                )
            for market, data in profiles.items():
                con.execute(
                    "UPDATE profiles SET data=?,version=version+1 WHERE market=?",
                    (json.dumps(data), market),
                )
            for p in products:
                pid = str(uuid.uuid4())
                stamp = now()
                con.execute(
                    "INSERT INTO products(id,market,identity_key,data,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                    (
                        pid,
                        p["market"],
                        identity(p),
                        json.dumps(p, ensure_ascii=False),
                        stamp,
                        stamp,
                    ),
                )
                self.event(con, pid, "restored:reapproval_required", p)
        return len(products)

    def import_candidates(self, rows):
        rows = [validate_product(p) for p in rows]
        added = skipped = 0
        with self.connect(True) as con:
            for p in rows:
                if con.execute(
                    "SELECT 1 FROM products WHERE market=? AND identity_key=?",
                    (p["market"], identity(p)),
                ).fetchone():
                    skipped += 1
                    continue
                if p["status"] not in {"candidate", "researching"}:
                    p["status"] = "researching"
                p.update(
                    risk_reviewed=False,
                    rights_reviewed=False,
                    copy_reviewed=False,
                    market_reviewed=False,
                )
                pid = str(uuid.uuid4())
                stamp = now()
                con.execute(
                    "INSERT INTO products(id,market,identity_key,data,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                    (
                        pid,
                        p["market"],
                        identity(p),
                        json.dumps(p, ensure_ascii=False),
                        stamp,
                        stamp,
                    ),
                )
                self.event(con, pid, "imported", p)
                added += 1
        return {"added": added, "skipped": skipped}

    def backup_to(self, output):
        import os

        output = Path(output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if output == self.path.resolve():
            raise DomainError("バックアップ先は別のファイルにしてください。")
        # Refuse replacement and create with restricted permissions before writing data.
        try:
            descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise DomainError(
                "バックアップ先がすでに存在します。別名を指定してください。"
            ) from exc
        os.close(descriptor)
        try:
            with self.connect() as source:
                target = sqlite3.connect(output)
                try:
                    source.backup(target)
                finally:
                    target.close()
        except Exception:
            output.unlink(missing_ok=True)
            raise
        return output
