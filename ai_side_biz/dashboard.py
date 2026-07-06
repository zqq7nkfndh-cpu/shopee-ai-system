# -*- coding: utf-8 -*-
"""
dashboard.py — Shopee出品下書きを統合したダッシュボードCSVを作る

既存のdashboard.csvがあれば承認状況(approved/status)を維持しつつ最新データで更新する。
"""
import csv
from config import CSV_COLUMNS, OUTPUT_DIR


def _load_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _row_key(row):
    return (row.get("date", ""), row.get("country", ""), row.get("product_name", ""))


def build_dashboard() -> list:
    existing = _load_csv(OUTPUT_DIR / "dashboard.csv")
    existing_map = {_row_key(r): r for r in existing}

    new_rows = _load_csv(OUTPUT_DIR / "shopee_listing_drafts.csv")

    merged = dict(existing_map)
    for row in new_rows:
        key = _row_key(row)
        if key in existing_map:
            row["status"] = existing_map[key].get("status", row.get("status", ""))
            row["approved"] = existing_map[key].get("approved", row.get("approved", "FALSE"))
        merged[key] = row

    rows = list(merged.values())
    rows.sort(key=lambda r: r.get("date", ""), reverse=True)
    return rows


def run() -> str:
    rows = build_dashboard()
    out_path = OUTPUT_DIR / "dashboard.csv"
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    approved_count = sum(1 for r in rows if str(r.get("approved", "")).upper() == "TRUE")
    print(f"[dashboard] 合計{len(rows)}件 (うち承認済み{approved_count}件) → {out_path}")
    return str(out_path)


if __name__ == "__main__":
    run()
