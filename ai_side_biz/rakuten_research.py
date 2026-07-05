# -*- coding: utf-8 -*-
"""
rakuten_research.py

楽天市場のランキングAPIを使って商品をリサーチし、スコアリングした上で
楽天ROOM用の「投稿文候補」と「ハッシュタグ」を作成する。

【厳守事項】
- このモジュールは楽天ROOMへの自動投稿を一切行わない(投稿文の"下書き"生成まで)
- 楽天ROOMへのコメント自動送信も行わない
- 楽天市場の商品画像を保存・加工して再アップロードする処理は実装しない
- 生成される投稿文は必ず人間が内容を確認し、手動で楽天ROOMに投稿すること
"""
import csv
import datetime
import requests

from config import RAKUTEN_APP_ID, SEASON_EVENTS, CSV_COLUMNS, OUTPUT_DIR
from risk_checker import check_risk

RANKING_ENDPOINT = "https://app.rakuten.co.jp/services/api/IchibaItem/Ranking/20220601"

# ジャンルID: 0=総合。運用したいジャンルに合わせて変更してください。
# (例: レディースファッション=100371, インテリア=100804, コスメ=100939 など)
DEFAULT_GENRE_IDS = [0]


def get_season_keywords(date: datetime.date = None) -> list:
    date = date or datetime.date.today()
    return SEASON_EVENTS.get(date.month, [])


def fetch_ranking(genre_id: int = 0, page: int = 1) -> list:
    """楽天ランキングAPIを叩く。APP_ID未設定時はサンプルデータで動作確認できる。"""
    if not RAKUTEN_APP_ID:
        print("[rakuten] RAKUTEN_APP_ID未設定のため、サンプルデータで動作します。")
        return _sample_ranking_data()

    params = {
        "format": "json",
        "genreId": genre_id,
        "page": page,
        "applicationId": RAKUTEN_APP_ID,
    }
    try:
        resp = requests.get(RANKING_ENDPOINT, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("Items", [])
    except Exception as e:
        print(f"[rakuten] APIエラー: {e} → サンプルデータにフォールバックします。")
        return _sample_ranking_data()


def _sample_ranking_data() -> list:
    """オフライン動作確認用のダミーデータ(実運用ではAPIの実データに置き換わる)"""
    sample_items = [
        {"itemName": "冷感敷きパッド 接触冷感 洗える 夏用", "rank": 1, "reviewCount": 320,
         "itemPrice": 2980, "itemUrl": "https://item.rakuten.co.jp/sample/001/", "genreName": "寝具"},
        {"itemName": "折りたたみ日傘 UVカット 遮光100% 軽量", "rank": 2, "reviewCount": 210,
         "itemPrice": 1980, "itemUrl": "https://item.rakuten.co.jp/sample/002/", "genreName": "雨具"},
        {"itemName": "ネッククーラー 冷却 首掛け扇風機", "rank": 5, "reviewCount": 540,
         "itemPrice": 3480, "itemUrl": "https://item.rakuten.co.jp/sample/003/", "genreName": "季節家電"},
    ]
    return [{"Item": item} for item in sample_items]


def score_item(item: dict, season_keywords: list) -> float:
    score = 0.0
    rank = item.get("rank", 999)
    score += max(0, 100 - rank)  # 上位ランクほど加点
    review_count = item.get("reviewCount", 0) or 0
    score += min(review_count, 500) / 10
    name = item.get("itemName", "")
    for kw in season_keywords:
        if kw in name:
            score += 20
    return round(score, 1)


def generate_room_texts(item_name: str, season_keywords: list, target_customer: str) -> list:
    """
    楽天ROOM投稿文の下書きを3パターン生成する。
    ・薬機法/景品表示法に触れやすい断定表現は使わない
    ・「個人の感想です」等、誤認を避ける一文を添える
    ※これはあくまで下書き。最終的な投稿文の確認・編集・投稿は人間が行う。
    """
    kw = season_keywords[0] if season_keywords else "この時期"
    patterns = [
        (
            f"【今気になってるアイテム】\n{item_name}\n"
            f"{kw}に良さそうだなと思ってチェックしています。\n"
            f"気になる方は商品ページも見てみてください♪\n"
            f"※個人の感想であり、効果・効能を保証するものではありません。"
        ),
        (
            f"{kw}のシーズンにぴったりかもと思ったアイテムです。\n"
            f"{item_name}\n"
            f"{target_customer}に人気があるようなので、リサーチがてらROOMに置いてみました。"
        ),
        (
            f"最近リサーチしていて見つけた商品です。\n"
            f"{item_name}\n"
            f"{kw}のギフト候補や自分用にも良さそうだと感じました。詳細は商品ページでご確認ください。"
        ),
    ]
    return patterns


def generate_hashtags(genre_name: str, season_keywords: list) -> str:
    tags = [f"#{genre_name}".replace(" ", ""), "#楽天ROOM", "#楽天ROOM初心者"]
    tags += [f"#{kw}" for kw in season_keywords[:3]]
    return " ".join(dict.fromkeys(tags))  # 重複除去


def build_candidates(genre_ids: list = None, target_customer: str = "20代-30代女性", top_n: int = 10) -> list:
    genre_ids = genre_ids or DEFAULT_GENRE_IDS
    season_keywords = get_season_keywords()
    today = datetime.date.today().isoformat()

    rows = []
    for genre_id in genre_ids:
        items = fetch_ranking(genre_id=genre_id)
        for raw in items:
            item = raw.get("Item", raw)
            name = item.get("itemName", "")
            price = item.get("itemPrice", 0)
            url = item.get("itemUrl", "")
            genre_name = item.get("genreName", "楽天市場")

            score = score_item(item, season_keywords)
            risk = check_risk(name)
            room_texts = generate_room_texts(name, season_keywords, target_customer)
            hashtags = generate_hashtags(genre_name, season_keywords)

            row = {col: "" for col in CSV_COLUMNS}
            row.update({
                "date": today,
                "platform": "rakuten_room",
                "country": "JP",
                "genre": genre_name,
                "product_name": name,
                "source_url": url,
                "trend_reason": f"楽天ランキング {item.get('rank', '?')}位 / レビュー{item.get('reviewCount', 0)}件 / スコア{score}",
                "season_reason": "、".join(season_keywords) if season_keywords else "",
                "target_customer": target_customer,
                "cost_price": "",
                "selling_price": price,
                "shipping_cost": "",
                "fee_estimate": "",
                "profit": "",
                "profit_margin": "",
                "risk_level": risk.risk_level,
                "risk_reason": risk.reasons,
                "room_text": " ||| ".join(room_texts) + f" ||| ハッシュタグ: {hashtags}",
                "shopee_title": "",
                "shopee_description": "",
                "note_angle": "",
                "status": "draft_only_human_review_required",
                "approved": "FALSE",
            })
            rows.append(row)

    rows.sort(key=lambda r: r["trend_reason"], reverse=True)
    return rows[:top_n]


def run(genre_ids: list = None, target_customer: str = "20代-30代女性", top_n: int = 10) -> str:
    rows = build_candidates(genre_ids=genre_ids, target_customer=target_customer, top_n=top_n)
    out_path = OUTPUT_DIR / "rakuten_room_candidates.csv"
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[rakuten] {len(rows)}件の候補を書き出しました → {out_path}")
    print("[rakuten] 重要: このCSVの投稿文は下書きです。楽天ROOMへの投稿は必ず手動で行ってください。")
    return str(out_path)


if __name__ == "__main__":
    run()
