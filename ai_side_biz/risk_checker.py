# -*- coding: utf-8 -*-
"""
risk_checker.py

楽天ROOM投稿文・Shopee出品下書きの両方で使う簡易リスクチェック。

【注意】
このチェックはキーワードベースの簡易判定であり、法令・規約の完全な保証ではありません。
- 薬機法(医薬品医療機器等法)に触れる可能性のある表現
- 食品・化粧品・サプリメント・電池・液体など、輸出入や配送で規制されやすいカテゴリ
- ブランド品・商標権侵害の疑いがあるもの
を機械的に洗い出し、"要確認"のフラグを立てることが目的です。
最終判断は必ず人間が行い、必要に応じて専門家(薬機法アドバイザー・弁護士・通関業者等)に確認してください。
"""

from dataclasses import dataclass

# 薬機法・景品表示法で問題になりやすい誇大表現・断定表現
NG_YAKKIHOU_WORDS = [
    "治る", "完治", "がんに効く", "がん予防", "痩せる", "確実に痩せる",
    "血圧が下がる", "血糖値が下がる", "アンチエイジング効果", "若返る",
    "美白効果", "シミが消える", "シワが消える", "医療用", "医薬品と同等",
    "副作用がない", "即効性がある", "臨床試験済み", "厚生労働省認可",
    "がんが消える", "ダイエット効果確実", "毛が生える", "発毛効果",
    "100%効果", "必ず痩せる", "病気が治る",
]

# 誇大表現・景品表示法(優良誤認・有利誤認)に注意すべき煽り表現
NG_EXAGGERATION_WORDS = [
    "絶対に儲かる", "誰でも稼げる", "月収100万円確実", "不労所得確定",
    "元本保証", "必ず儲かる", "リスクゼロ",
]

# カテゴリ別の規制・注意ワード(該当したら medium/high リスク扱い)
CATEGORY_KEYWORDS = {
    "food": ["食品", "お菓子", "健康食品", "飲料", "お茶", "調味料", "生鮮"],
    "cosmetics": ["化粧品", "コスメ", "美容液", "クリーム", "日焼け止め", "パック"],
    "supplement": ["サプリ", "サプリメント", "プロテイン", "健康補助食品"],
    "battery": ["電池", "バッテリー内蔵", "リチウム", "モバイルバッテリー"],
    "liquid": ["液体", "香水", "オイル", "ジェル", "アルコール", "スプレー"],
    "brand_risk": [
        "ブランド品", "正規品ではない", "コピー品", "レプリカ", "非正規",
        "Nike", "NIKE", "Gucci", "GUCCI", "Louis Vuitton", "LOUISVUITTON",
        "Chanel", "CHANEL", "Supreme", "Disney", "ディズニー", "サンリオ",
        "ポケモン", "任天堂", "ジブリ",
    ],
}

CATEGORY_LABEL_JA = {
    "food": "食品",
    "cosmetics": "化粧品",
    "supplement": "サプリメント",
    "battery": "電池・バッテリー",
    "liquid": "液体物",
    "brand_risk": "ブランド/商標リスク",
}


@dataclass
class RiskResult:
    risk_level: str  # "low" / "medium" / "high"
    reasons: str
    categories: list


def check_risk(product_name: str, description: str = "") -> RiskResult:
    text = f"{product_name} {description}"
    reasons = []
    categories = []

    for word in NG_YAKKIHOU_WORDS:
        if word in text:
            reasons.append(f"薬機法上の誇大・断定表現の疑い:『{word}』")

    for word in NG_EXAGGERATION_WORDS:
        if word in text:
            reasons.append(f"景品表示法上の誇大表現の疑い:『{word}』")

    for cat, words in CATEGORY_KEYWORDS.items():
        for word in words:
            if word in text:
                reasons.append(f"{CATEGORY_LABEL_JA[cat]}カテゴリに該当する可能性:『{word}』")
                categories.append(cat)
                break  # カテゴリごとに1回報告すれば十分

    categories = list(dict.fromkeys(categories))  # 重複除去(順序維持)

    if not reasons:
        risk_level = "low"
    elif len(reasons) == 1 and not categories:
        risk_level = "medium"
    else:
        risk_level = "high"

    reason_text = "; ".join(reasons) if reasons else "特記事項なし(簡易チェックのみ。最終確認は人間が行うこと)"
    return RiskResult(risk_level=risk_level, reasons=reason_text, categories=categories)


def export_customs_note(categories: list, country: str = "") -> str:
    """
    Shopee向け: カテゴリに応じた輸出入・配送時の一般的な注意喚起メモを返す。
    国ごとの正確な規制は必ず現地の通関/Shopeeの公式ポリシーで確認すること。
    """
    notes = []
    if "battery" in categories:
        notes.append("電池内蔵品は航空便で輸出規制対象になりやすい(国際郵便条件を要確認)")
    if "liquid" in categories:
        notes.append("液体物は輸送制限・破損リスクがあり、配送方法の確認が必要")
    if "food" in categories:
        notes.append("食品は輸入国の検疫・食品衛生規制の対象になりやすい")
    if "cosmetics" in categories:
        notes.append("化粧品は成分表示や輸入国の化粧品規制の対象になりやすい")
    if "supplement" in categories:
        notes.append("サプリメントは医薬品的規制の対象になる国があり要注意")
    if "brand_risk" in categories:
        notes.append("商標権・ブランド権利侵害のリスクが高いため出品非推奨")
    if country and notes:
        notes.append(f"(出荷先: {country} の最新規制をShopee公式・現地税関で必ず確認)")
    return " / ".join(notes) if notes else ""
