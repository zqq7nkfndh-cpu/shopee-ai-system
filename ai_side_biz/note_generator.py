# -*- coding: utf-8 -*-
"""
note_generator.py

note メンバーシップ向け「AI副業実験ログ」の週次記事下書きを生成する。

方針(ユーザー指定ルールに準拠):
- AI量産記事ではなく、本人の副業実験ログとして使うための"素材"を作る位置づけ
- 数字は正直に書く(誇張・煽りをしない)。うまくいかなかった点も必ず載せる
- 読者が真似できるように、実際に使ったプロンプトやテンプレートを載せる
- 生成後は必ず人間が自分の言葉で加筆・修正してから公開すること
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
    rakuten_rows = _load_csv(OUTPUT_DIR / "rakuten_room_candidates.csv")[:5]
    shopee_rows = _load_csv(OUTPUT_DIR / "shopee_listing_drafts.csv")[:5]
    wk = _load_weekly_results()

    room_table = _format_table(
        rakuten_rows,
        ["product_name", "trend_reason", "season_reason", "risk_level"],
        ["商品名", "選定理由(トレンド)", "季節理由", "リスク判定"],
    )
    shopee_table = _format_table(
        shopee_rows,
        ["country", "product_name", "selling_price", "profit", "profit_margin", "risk_level"],
        ["国", "商品名", "想定販売価格(円)", "想定利益(円)", "利益率", "リスク判定"],
    )

    shorts_scripts = "\n".join(f"- {s}" for s in wk.get("shorts_script_ideas", []))
    failures = "\n".join(f"- {f}" for f in wk.get("failures", []))
    improvements = "\n".join(f"- {i}" for i in wk.get("improvements", []))

    room = wk.get("rakuten_room", {})
    shopee = wk.get("shopee", {})

    report = f"""# AI副業実験ログ - {wk.get('week_label', today)}

> このログはAIで自動生成した"下書き"を元に、実際に自分で試した結果をまとめています。
> 誇大な収益アピールを目的としたものではなく、良かった点も悪かった点も正直に記録しています。

## 1. 今週リサーチした楽天ROOM候補商品

{room_table}

※ 上記はAIが下書きした投稿候補です。実際に投稿したのはこの中から自分で選んだものだけです。
※ 楽天ROOMへの投稿・画像の扱いはすべて手動で行っています(自動投稿ツールは使っていません)。

## 2. 今週のShopee出品候補

{shopee_table}

※ 利益額・利益率はShopee手数料と為替を概算したものです。実際の手数料は変動するため、
　出品前にShopee Seller Centerで最新の手数料を確認しています。
※ 出品は下書き止まりで、実際に出品したのは自分で内容を確認し承認したものだけです。

## 3. ショート動画台本アイデア

{shorts_scripts if shorts_scripts else "- (今週は特になし)"}

## 4. 今週の収益(概算・自己申告ベース)

| 項目 | 楽天ROOM | Shopee |
|---|---|---|
| 投稿/出品数 | {room.get('posts_made', 0)} | {shopee.get('listings_approved', 0)} |
| クリック/注文数 | {room.get('clicks', 0)} | {shopee.get('orders', 0)} |
| 想定報酬/売上(円) | {room.get('estimated_reward_jpy', 0)} | {shopee.get('revenue_jpy', 0)} |
| 想定利益(円) | - | {shopee.get('profit_jpy', 0)} |

## 5. うまくいかなかったこと

{failures if failures else "- (今週は特になし)"}

## 6. 来週への改善点

{improvements if improvements else "- (今週は特になし)"}

## 7. 実際に使ったプロンプト・テンプレート(読者が真似できるように公開)

**楽天ROOM投稿文生成プロンプト(要旨):**
```
商品名と季節キーワードを渡し、以下の条件で3パターンの投稿文を作る。
・薬機法や景品表示法に触れる断定表現は使わない
・「個人の感想」であることが伝わる一文を入れる
・80〜120文字程度で3パターン作る
```

**Shopee英語コピー生成プロンプト(要旨):**
```
日本語の商品名・カテゴリ・トレンド理由を渡し、
英語タイトル(60文字以内)、説明文(3文程度)、検索キーワード(5個程度)を作る。
誇大な効果効能の記述は避け、事実ベースの説明にする。
```

---
※本記事はAI副業運用システムで生成した下書きに、自分の実体験・数値を加えて作成しています。
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
