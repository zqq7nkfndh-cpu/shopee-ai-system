# -*- coding: utf-8 -*-
"""
note_generator.py

Shopee運用向けの週次note下書きを生成する。
"""
import csv
import json
import datetime

from config import OUTPUT_DIR, DATA_DIR

WEEKLY_RESULTS_PATH = DATA_DIR / "weekly_results.json"
WEEKLY_RESULTS_TEMPLATE = DATA_DIR / "weekly_results_template.json"


def _load_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _load_weekly_results():
    path = WEEKLY_RESULTS_PATH if WEEKLY_RESULTS_PATH.exists() else WEEKLY_RESULTS_TEMPLATE
    if not WEEKLY_RESULTS_PATH.exists():
        print(f"[note] {WEEKLY_RESULTS_PATH.name} が無いためテンプレート値を使用します。")
        print(f"[note] 実際の週次収益・失敗・改善点は {WEEKLY_RESULTS_PATH} に記入してください。")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _format_table(rows, columns, headers=None):
    headers = headers or columns
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in columns) + " |")
    return "\n".join(lines)


def build_report_markdown() -> str:
    today = datetime.date.today().isoformat()
    shopee_rows = _load_csv(OUTPUT_DIR / "shopee_listing_drafts.csv")[:5]
    wk = _load_weekly_results()

    shopee_table = _format_table(
        shopee_rows,
        ["country", "product_name", "selling_price_jpy", "profit_jpy", "profit_margin", "risk_level"],
        ["国", "商品名", "想定販売価格(円)", "想定利益(円)", "利益率", "リスク判定"],
    )

    shorts_scripts = "\n".join(f"- {s}" for s in wk.get("shorts_script_ideas", []))
    failures = "\n".join(f"- {f}" for f in wk.get("failures", []))
    improvements = "\n".join(f"- {i}" for i in wk.get("improvements", []))
    shopee = wk.get("shopee", {})

    report = f"""# Shopee副業実験ログ - {wk.get('week_label', today)}

> このログはAIで自動生成した下書きを元に、実際に自分で試した結果をまとめています。
> 誇大な収益アピールを目的とせず、良かった点と改善点を記録します。

## 1. 今週のShopee出品候補

{shopee_table}

※ 利益額・利益率はShopee手数料と為替の概算です。出品前に最新条件を確認してください。
※ 出品は下書き止まりで、実際に出品したのは人間が内容確認・承認したものだけです。

## 2. ショート動画台本アイデア

{shorts_scripts if shorts_scripts else '- (今週は特になし)'}

## 3. 今週の実績（概算・自己申告）

| 項目 | Shopee |
|---|---|
| 出品数 | {shopee.get('listings_approved', 0)} |
| 注文数 | {shopee.get('orders', 0)} |
| 売上(円) | {shopee.get('revenue_jpy', 0)} |
| 利益(円) | {shopee.get('profit_jpy', 0)} |

## 4. うまくいかなかったこと

{failures if failures else '- (今週は特になし)'}

## 5. 来週への改善点

{improvements if improvements else '- (今週は特になし)'}

## 6. 使ったプロンプト（要旨）

**Shopee英語コピー生成プロンプト:**
```
日本語の商品名・カテゴリ・トレンド理由を渡し、
英語タイトル(60文字以内)、説明文(3文程度)、検索キーワードを作る。
誇大な効果効能の記述は避け、事実ベースで記述する。
```

---
※本記事はAI下書きをベースに、実体験と実数値を加筆して公開する前提です。
"""
    return report


def run() -> str:
    report = build_report_markdown()
    out_path = OUTPUT_DIR / "note_weekly_report.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[note] 週次レポート下書きを書き出しました → {out_path}")
    print("[note] 公開前に必ず自分の言葉・実際の数値で加筆修正してください。")
    return str(out_path)


if __name__ == "__main__":
    run()
