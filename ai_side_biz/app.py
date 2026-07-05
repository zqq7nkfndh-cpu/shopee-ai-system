# -*- coding: utf-8 -*-
"""
app.py
AI副業システム Streamlit Web UI
"""
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "outputs"
DATA_DIR = BASE_DIR / "data"

st.set_page_config(
    page_title="AI副業システム",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── ヘルパー ───────────────────────────────────────────────
def run_task(command: str) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "main.py", command],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def load_csv(filename: str) -> pd.DataFrame | None:
    path = OUTPUT_DIR / filename
    if not path.exists():
        return None
    return pd.read_csv(path, encoding="utf-8-sig")


def load_md(filename: str) -> str | None:
    path = OUTPUT_DIR / filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def risk_badge(level: str) -> str:
    return {"low": "🟢 低", "medium": "🟡 中", "high": "🔴 高"}.get(str(level).lower(), f"⚪ {level}")


def last_modified(filename: str) -> str:
    path = OUTPUT_DIR / filename
    if not path.exists():
        return "未生成"
    import datetime
    ts = path.stat().st_mtime
    dt = datetime.datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M")


def regen_button(label: str, command: str, filename: str):
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"最終更新: {last_modified(filename)}")
    with col2:
        if st.button(label, use_container_width=True, type="primary"):
            with st.spinner("生成中..."):
                ok, out = run_task(command)
            if ok:
                st.success("✅ 生成完了！ページを再読み込みしてください。")
            else:
                st.error("❌ エラーが発生しました")
                st.code(out)
            st.rerun()


# ── サイドバー ───────────────────────────────────────────────
with st.sidebar:
    st.title("🤖 AI副業システム")
    st.caption("リサーチ・下書き生成ツール")
    st.divider()
    page = st.radio(
        "ページを選択",
        options=[
            "🏠 ダッシュボード",
            "🛍️ 楽天ROOM候補",
            "🌏 Shopee出品下書き",
            "📝 noteレポート",
            "ℹ️ 使い方",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("⚠️ このツールは下書き生成のみ行います。投稿・出品は必ず人間が手動で行ってください。")


# ══════════════════════════════════════════════════════════
# 🏠 ダッシュボード
# ══════════════════════════════════════════════════════════
if page == "🏠 ダッシュボード":
    st.title("🏠 ダッシュボード")
    regen_button("🔄 全データを再生成", "all", "dashboard.csv")
    st.divider()

    df = load_csv("dashboard.csv")
    if df is None:
        st.warning("dashboard.csv が見つかりません。右上の「再生成」ボタンを押してください。")
        st.stop()

    # サマリー
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("総アイテム数", len(df))
    c2.metric("楽天ROOM候補", len(df[df["platform"] == "rakuten_room"]))
    c3.metric("Shopee候補", len(df[df["platform"] == "shopee"]))
    approved = len(df[df["approved"].astype(str).str.upper() == "TRUE"])
    c4.metric("承認済み", approved)

    st.divider()

    # リスク別集計
    if "risk_level" in df.columns:
        st.subheader("リスク分布")
        risk_counts = df["risk_level"].value_counts().reset_index()
        risk_counts.columns = ["リスク", "件数"]
        st.dataframe(risk_counts, use_container_width=True, hide_index=True)

    st.divider()

    # テーブル
    st.subheader("全アイテム一覧")
    display_cols = [
        col for col in
        ["date", "platform", "country", "genre", "product_name",
         "selling_price", "profit", "profit_margin",
         "risk_level", "status", "approved"]
        if col in df.columns
    ]
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════
# 🛍️ 楽天ROOM候補
# ══════════════════════════════════════════════════════════
elif page == "🛍️ 楽天ROOM候補":
    st.title("🛍️ 楽天ROOM 投稿候補")
    st.info("⚠️ 下書き確認専用です。楽天ROOMへの投稿は必ず手動で行ってください。")
    regen_button("🔄 楽天リサーチを再実行", "rakuten", "rakuten_room_candidates.csv")
    st.divider()

    df = load_csv("rakuten_room_candidates.csv")
    if df is None:
        st.warning("rakuten_room_candidates.csv が見つかりません。再生成ボタンを押してください。")
        st.stop()

    for _, row in df.iterrows():
        product_name = row.get("product_name", "")
        genre = row.get("genre", "")
        price = row.get("selling_price", "")
        risk = row.get("risk_level", "")
        trend = row.get("trend_reason", "")
        season = row.get("season_reason", "")
        source_url = row.get("source_url", "")
        room_text_raw = str(row.get("room_text", ""))

        with st.container(border=True):
            h_col, r_col = st.columns([4, 1])
            with h_col:
                st.subheader(product_name)
                st.caption(f"ジャンル: {genre}　｜　価格: ¥{price}")
            with r_col:
                st.markdown(f"**リスク**\n{risk_badge(risk)}")

            if trend:
                st.markdown(f"**トレンド理由:** {trend}")
            if season:
                st.markdown(f"**季節キーワード:** {season}")
            if source_url and source_url != "nan":
                st.markdown(f"[🔗 商品ページを開く]({source_url})")

            # 投稿文の解析・表示
            if room_text_raw and room_text_raw != "nan":
                parts = [p.strip() for p in room_text_raw.split("|||")]
                hashtags = ""
                text_parts = []
                for p in parts:
                    if p.startswith("ハッシュタグ:"):
                        hashtags = p.replace("ハッシュタグ:", "").strip()
                    else:
                        text_parts.append(p)

                st.markdown("**📋 投稿文（下書き）**")
                for i, text in enumerate(text_parts, 1):
                    if text:
                        with st.expander(f"パターン {i}"):
                            st.text_area(
                                f"投稿文パターン{i}",
                                value=text,
                                height=150,
                                label_visibility="collapsed",
                                key=f"room_{product_name}_{i}",
                            )

                if hashtags:
                    with st.expander("# ハッシュタグ"):
                        st.text_area(
                            "ハッシュタグ",
                            value=hashtags,
                            height=80,
                            label_visibility="collapsed",
                            key=f"hash_{product_name}",
                        )

        st.write("")  # spacing


# ══════════════════════════════════════════════════════════
# 🌏 Shopee出品下書き
# ══════════════════════════════════════════════════════════
elif page == "🌏 Shopee出品下書き":
    st.title("🌏 Shopee 出品下書き")
    st.info("⚠️ 下書き確認専用です。Shopeeへの出品は必ず人間が手動で行ってください。approved列のTRUE変更もCSVファイルを直接編集してください。")

    regen_button("🔄 Shopeeリサーチを再実行", "shopee", "shopee_listing_drafts.csv")

    # トレンド入力の案内
    with st.expander("📥 Shopeeトレンドデータを手動入力するには"):
        st.markdown("""
`ai_side_biz/data/shopee_trend_input.csv` を作成し、リサーチした商品情報を入力してください。

テンプレートファイル: `data/shopee_trend_input_template.csv`

| 列名 | 説明 |
|---|---|
| country | 対象国（Singapore, Taiwan など） |
| genre | カテゴリ名（英語） |
| product_name | 商品名（日本語） |
| source_url | Shopeeの商品URL |
| trend_reason | なぜ売れているか |
| cost_price | 仕入れ価格（円） |
| shipping_cost | 送料見込み（円） |
        """)

    st.divider()

    df = load_csv("shopee_listing_drafts.csv")
    if df is None:
        st.warning("shopee_listing_drafts.csv が見つかりません。再生成ボタンを押してください。")
        st.stop()

    for _, row in df.iterrows():
        product_name = row.get("product_name", "")
        country = row.get("country", "")
        genre = row.get("genre", "")
        cost = row.get("cost_price", "")
        sell = row.get("selling_price", "")
        ship = row.get("shipping_cost", "")
        profit = row.get("profit", "")
        margin = row.get("profit_margin", "")
        risk = row.get("risk_level", "")
        risk_reason = row.get("risk_reason", "")
        shopee_title = str(row.get("shopee_title", ""))
        shopee_desc = str(row.get("shopee_description", ""))
        approved = str(row.get("approved", "FALSE"))

        with st.container(border=True):
            h_col, r_col = st.columns([4, 1])
            with h_col:
                st.subheader(product_name)
                st.caption(f"🌍 {country}　｜　ジャンル: {genre}")
            with r_col:
                st.markdown(f"**リスク**\n{risk_badge(risk)}")

            # 利益計算
            p_col1, p_col2, p_col3, p_col4 = st.columns(4)
            p_col1.metric("仕入れ", f"¥{cost}")
            p_col2.metric("販売価格", f"¥{sell}")
            p_col3.metric("想定利益", f"¥{profit}")
            p_col4.metric("利益率", f"{float(margin)*100:.0f}%" if str(margin) != "nan" else "-")

            if risk_reason and str(risk_reason) != "nan":
                st.caption(f"⚠️ リスクメモ: {risk_reason}")

            # 英語コピー
            if shopee_title and shopee_title != "nan":
                with st.expander("📝 英語タイトル・説明文"):
                    st.markdown("**タイトル（コピーして使用）**")
                    st.text_area(
                        "タイトル",
                        value=shopee_title,
                        height=70,
                        label_visibility="collapsed",
                        key=f"stitle_{product_name}_{country}",
                    )
                    if shopee_desc and shopee_desc != "nan":
                        st.markdown("**説明文**")
                        st.text_area(
                            "説明文",
                            value=shopee_desc,
                            height=150,
                            label_visibility="collapsed",
                            key=f"sdesc_{product_name}_{country}",
                        )

            st.caption(f"承認状態: {'✅ 承認済み' if approved.upper() == 'TRUE' else '🔲 未承認（CSVのapproved列をTRUEに変更すると承認）'}")

        st.write("")


# ══════════════════════════════════════════════════════════
# 📝 noteレポート
# ══════════════════════════════════════════════════════════
elif page == "📝 noteレポート":
    st.title("📝 note 週次レポート下書き")
    st.info("⚠️ 下書きです。自分の言葉・実際の数値を加筆修正してから公開してください。")
    regen_button("🔄 レポートを再生成", "note", "note_weekly_report.md")

    # weekly_results.json 入力案内
    with st.expander("📥 実際の収益データを入力するには"):
        st.markdown("""
`ai_side_biz/data/weekly_results.json` を作成し、実際の結果を入力してください。

テンプレート: `data/weekly_results_template.json`

```json
{
  "week_label": "2026年7月 第1週",
  "rakuten_posts": 3,
  "rakuten_clicks": 12,
  "rakuten_estimated_reward": 500,
  "shopee_listings": 1,
  "shopee_orders": 0,
  "shopee_revenue": 0,
  "shopee_profit": 0,
  "failures": ["出品タイトルが長すぎた"],
  "improvements": ["次週は60文字以内に修正する"]
}
```
        """)

    st.divider()

    md = load_md("note_weekly_report.md")
    if md is None:
        st.warning("note_weekly_report.md が見つかりません。再生成ボタンを押してください。")
        st.stop()

    tab1, tab2 = st.tabs(["👁️ プレビュー", "📋 テキストコピー用"])
    with tab1:
        st.markdown(md)
    with tab2:
        st.text_area(
            "全文コピー用",
            value=md,
            height=600,
            label_visibility="collapsed",
        )


# ══════════════════════════════════════════════════════════
# ℹ️ 使い方
# ══════════════════════════════════════════════════════════
elif page == "ℹ️ 使い方":
    st.title("ℹ️ 使い方ガイド")

    st.subheader("📱 このアプリでできること")
    st.markdown("""
| 機能 | 説明 |
|---|---|
| 楽天ROOMリサーチ | 楽天ランキングAPIから商品を取得し、投稿文の下書きを生成 |
| Shopee出品下書き | 仕入れ価格・利益計算・英語コピーの下書きを生成 |
| note週次レポート | 週次の実績をまとめたnote記事の下書きを生成 |
| ダッシュボード | 全データを一覧表示 |
    """)

    st.divider()

    st.subheader("🔄 データを更新するには")
    st.markdown("""
各ページの右上にある **「再生成」ボタン** を押すと、最新データで再実行されます。

- **楽天ROOM候補** → 楽天ランキングAPIを再取得
- **Shopee出品下書き** → `data/shopee_trend_input.csv` の内容で再計算
- **noteレポート** → `data/weekly_results.json` の内容で再生成
- **ダッシュボード（全再生成）** → 上記をすべて一括実行
    """)

    st.divider()

    st.subheader("🌏 Shopeeリサーチの手順")
    st.markdown("""
1. Shopeeアプリ/サイトで売れ筋商品を見つける
2. `ai_side_biz/data/shopee_trend_input.csv` を作成して手入力する
   （テンプレート: `data/shopee_trend_input_template.csv`）
3. Shopeeページの「再生成」ボタンを押す
4. 生成された英語タイトル・説明文をコピーして Shopee Seller Center で出品
5. 出品OKと判断したら CSV の `approved` 列を `TRUE` に変更する
    """)

    st.divider()

    st.subheader("🛍️ 楽天ROOMの手順")
    st.markdown("""
1. 楽天ROOMページで投稿候補を確認する
2. 気に入った投稿文パターンをコピーする
3. 楽天ROOMアプリ/サイトから**手動で**投稿する
4. 商品画像は楽天の公式投稿機能を使う（画像の保存・加工・再アップは禁止）
    """)

    st.divider()

    st.subheader("🔑 APIキー設定")
    st.markdown("""
| キー | 用途 | 設定場所 |
|---|---|---|
| `RAKUTEN_APP_ID` | 楽天ランキングAPI | Replit Secrets |
| `RAKUTEN_AFFILIATE_ID` | 楽天アフィリエイトリンク（任意） | Replit Secrets |
| `JPY_PER_USD` | Shopee利益計算の為替レート | Replit Secrets |

👉 楽天アプリID取得: https://webservice.rakuten.co.jp/
    """)

    st.divider()

    st.subheader("⚠️ 重要な注意事項")
    st.error("""
このツールは「下書き・候補の生成」のみを行います。

- 楽天ROOMへの自動投稿は行いません
- Shopeeへの自動出品は行いません
- 投稿文・出品文・リスク判定はあくまで目安です
- 最終的な投稿・出品・価格設定は必ずご自身で確認してください
    """)
