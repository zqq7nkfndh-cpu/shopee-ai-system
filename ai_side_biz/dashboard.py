# -*- coding: utf-8 -*-
"""
dashboard.py

rakuten_room_candidates.csv と shopee_listing_drafts.csv を統合して
dashboard.csv (収益・ステータス管理用の一覧)を作る。

- 既存の dashboard.csv があれば読み込み、同じ(date, platform, product_name)の
  行は「承認状況(approved/status)」を維持しつつ、新しいリサーチ結果で更新する。
- これにより「一度人間が承認した行が再実行で消えてしまう」事故を防ぐ。
"""
import csv
from config import CSV_COLUMNS, OUTPUT_DIR


def _load_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _row_key(row):
    return (row.get("date", ""), row.get("platform", ""), row.get("product_name", ""))


def build_dashboard() -> list:
    existing = _load_csv(OUTPUT_DIR / "dashboard.csv")
    existing_map = {_row_key(r): r for r in existing}

    new_rows = []
    new_rows += _load_csv(OUTPUT_DIR / "rakuten_room_candidates.csv")
    new_rows += _load_csv(OUTPUT_DIR / "shopee_listing_drafts.csv")

    merged = dict(existing_map)  # 既存を土台にする
    for row in new_rows:
        key = _row_key(row)
        if key in existing_map:
            # 人間が編集したかもしれない approved / status は保持し、それ以外の
            # リサーチ情報(価格・リスク等)は最新の値に更新する。
            kept_status = existing_map[key].get("status", row.get("status", ""))
            kept_approved = existing_map[key].get("approved", row.get("approved", "FALSE"))
            row["status"] = kept_status
            row["approved"] = kept_approved
        merged[key] = row

    rows = list(merged.values())
    rows.sort(key=lambda r: (r.get("platform", ""), r.get("date", "")), reverse=True)
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
