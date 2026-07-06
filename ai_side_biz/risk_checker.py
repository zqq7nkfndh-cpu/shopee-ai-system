# -*- coding: utf-8 -*-
"""
risk_checker.py — Shopee越境EC向け総合リスクチェッカー

キーワードベースの簡易判定です。法令・規約の完全な保証ではありません。
最終判断は必ず人間が行い、必要に応じて専門家に確認してください。
"""
from dataclasses import dataclass, field

# --- 薬機法・景品表示法上の禁止表現 ---
NG_YAKKIHOU_WORDS = [
    "治る", "完治", "がんに効く", "がん予防", "痩せる", "確実に痩せる",
    "血圧が下がる", "血糖値が下がる", "アンチエイジング効果", "若返る",
    "美白効果", "シミが消える", "シワが消える", "医療用", "医薬品と同等",
    "副作用がない", "即効性がある", "臨床試験済み", "厚生労働省認可",
    "がんが消える", "ダイエット効果確実", "毛が生える", "発毛効果",
    "100%効果", "必ず痩せる", "病気が治る",
]

# --- カテゴリ別リスクキーワード ---
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "food": [
        "食品", "お菓子", "健康食品", "飲料", "お茶", "調味料", "生鮮",
        "乾物", "レトルト", "缶詰", "インスタント", "スナック", "グミ",
    ],
    "supplement": [
        "サプリ", "サプリメント", "プロテイン", "健康補助食品",
        "ビタミン", "コラーゲン", "ミネラル", "栄養補助",
    ],
    "cosmetics": [
        "化粧品", "コスメ", "美容液", "クリーム", "日焼け止め", "パック",
        "ファンデーション", "口紅", "リップ", "アイシャドウ", "マスカラ",
        "スキンケア", "化粧水", "乳液", "アイライナー",
    ],
    "medicine": [
        "医薬品", "処方薬", "薬品", "医療機器", "医療", "診断",
        "治療", "薬剤", "市販薬", "OTC", "第一類", "第二類",
    ],
    "battery": [
        "電池", "バッテリー内蔵", "リチウム", "モバイルバッテリー",
        "充電池", "リチウムイオン", "蓄電", "充電器",
    ],
    "liquid": [
        "液体", "香水", "オイル", "ジェル", "アルコール", "スプレー",
        "ローション", "シャンプー", "洗剤", "塗料", "接着剤",
    ],
    "fragile": [
        "割れ物", "ガラス製品", "陶磁器", "陶器", "壊れやすい",
        "繊細", "精密機器", "ガラス", "磁器",
    ],
    "heavy": [
        "重量物", "大型", "重い商品", "家電", "家具", "工具",
        "鉄製", "石製", "重量",
    ],
    "brand_risk": [
        "ブランド品", "正規品ではない", "コピー品", "レプリカ", "非正規",
        "Nike", "NIKE", "Adidas", "ADIDAS", "Gucci", "GUCCI",
        "Louis Vuitton", "Chanel", "CHANEL", "Supreme",
        "Rolex", "Apple", "Sony", "Dyson",
    ],
    "character_goods": [
        "Disney", "ディズニー", "サンリオ", "Hello Kitty",
        "ポケモン", "任天堂", "ジブリ", "ドラえもん", "キティ",
        "ピカチュウ", "ミッキー", "スヌーピー", "マーベル", "DC",
        "ワンピース", "鬼滅", "呪術", "ナルト", "キャラクター",
    ],
    "trademark_risk": [
        "商標", "ライセンス品", "公式ではない", "非公式",
        "パチモン", "類似品", "そっくり", "偽物",
    ],
    "unclear_source": [
        "個人輸入", "仕入れ先不明", "メーカー不明", "出所不明",
        "正規ルート不明", "転売品",
    ],
    "prohibited": [
        "危険物", "爆発物", "武器", "刃物", "毒物", "劇物",
        "麻薬", "覚醒剤", "違法", "規制品",
    ],
}

CATEGORY_LABEL_JA: dict[str, str] = {
    "food": "食品",
    "supplement": "サプリメント",
    "cosmetics": "化粧品",
    "medicine": "医薬品・医療機器",
    "battery": "電池・バッテリー",
    "liquid": "液体物",
    "fragile": "割れ物・精密品",
    "heavy": "重量物・大型",
    "brand_risk": "ブランド品リスク",
    "character_goods": "キャラクター商品",
    "trademark_risk": "商標・著作権リスク",
    "unclear_source": "仕入れ先不明",
    "prohibited": "禁止・規制品",
}

# 高リスクカテゴリ（1つでも該当すれば high）
HIGH_RISK_CATEGORIES = {
    "medicine", "brand_risk", "character_goods",
    "trademark_risk", "prohibited",
}

# 中リスクカテゴリ（該当すれば medium 以上）
MEDIUM_RISK_CATEGORIES = {
    "food", "supplement", "cosmetics",
    "battery", "liquid", "unclear_source",
}


@dataclass
class RiskResult:
    risk_level: str        # "low" / "medium" / "high"
    reasons: str
    categories: list = field(default_factory=list)


def check_risk(product_name: str, description: str = "") -> RiskResult:
    text = f"{product_name} {description}"
    reasons: list[str] = []
    categories: list[str] = []

    for word in NG_YAKKIHOU_WORDS:
        if word in text:
            reasons.append(f"薬機法上の誇大・断定表現の疑い:『{word}』")

    for cat, words in CATEGORY_KEYWORDS.items():
        for word in words:
            if word in text:
                label = CATEGORY_LABEL_JA[cat]
                reasons.append(f"{label}カテゴリに該当:『{word}』")
                if cat not in categories:
                    categories.append(cat)
                break

    if any(c in HIGH_RISK_CATEGORIES for c in categories):
        risk_level = "high"
    elif any(c in MEDIUM_RISK_CATEGORIES for c in categories) or reasons:
        risk_level = "medium"
    else:
        risk_level = "low"

    reason_text = (
        "; ".join(reasons)
        if reasons
        else "特記事項なし（簡易チェックのみ。最終確認は人間が行うこと）"
    )
    return RiskResult(risk_level=risk_level, reasons=reason_text, categories=categories)


def export_customs_note(categories: list, country: str = "") -> str:
    notes: list[str] = []
    if "battery" in categories:
        notes.append("電池内蔵品は航空便輸出規制対象（国際郵便条件を要確認）")
    if "liquid" in categories:
        notes.append("液体物は輸送制限・破損リスクあり")
    if "food" in categories:
        notes.append("食品は輸入国の検疫・食品衛生規制の対象")
    if "cosmetics" in categories:
        notes.append("化粧品は輸入国の化粧品規制の対象")
    if "supplement" in categories:
        notes.append("サプリは医薬品規制対象になる国あり")
    if "medicine" in categories:
        notes.append("医薬品・医療機器は輸出入許可が必要な場合あり")
    if "brand_risk" in categories or "character_goods" in categories:
        notes.append("商標権・著作権侵害リスク大：出品非推奨")
    if "prohibited" in categories:
        notes.append("禁止品の可能性あり：絶対に出品しないこと")
    if country and notes:
        notes.append(f"（{country}の最新規制をShopee公式・現地税関で確認）")
    return " / ".join(notes)


def get_risk_flags(categories: list) -> dict[str, bool]:
    """UI表示用：カテゴリごとのフラグ辞書を返す"""
    return {cat: cat in categories for cat in CATEGORY_LABEL_JA}
