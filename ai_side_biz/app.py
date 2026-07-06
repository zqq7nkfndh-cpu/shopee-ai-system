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

SHOPEE_COUNTRIES = ["Singapore", "Malaysia", "Taiwan", "Philippines", "Thailand", "Vietnam"]
SHOPEE_INPUT_FILE = DATA_DIR / "shopee_trend_input.csv"
SHOPEE_TEMPLATE_FILE = DATA_DIR / "shopee_trend_input_template.csv"
SHOPEE_COLUMNS = [
    "country", "genre", "product_name", "trend_reason",
    "source_url", "cost_price_jpy", "shipping_cost_jpy",
]

st.set_page_config(
    page_title="AI副業システム",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── ヘルパー ──────────────────────────────────────────────────────────────────

def run_task(command: str) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "main.py", command],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode == 0, result.stdout + result.stderr


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


def load_shopee_input() -> pd.DataFrame:
    if SHOPEE_INPUT_FILE.exists():
        df = pd.read_csv(SHOPEE_INPUT_FILE, encoding="utf-8-sig")
    elif SHOPEE_TEMPLATE_FILE.exists():
        df = pd.read_csv(SHOPEE_TEMPLATE_FILE, encoding="utf-8-sig")
    else:
        df = pd.DataFrame(columns=SHOPEE_COLUMNS)
    for col in SHOPEE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    for num_col in ["cost_price_jpy", "shipping_cost_jpy"]:
        df[num_col] = pd.to_numeric(df[num_col], errors="coerce").fillna(0).astype(int)
    return df[SHOPEE_COLUMNS].reset_index(drop=True)


def save_shopee_input(df: pd.DataFrame) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(SHOPEE_INPUT_FILE, index=False, encoding="utf-8-sig")


def risk_badge(level: str) -> str:
    return {"low": "🟢 低", "medium": "🟡 中", "high": "🔴 高"}.get(
        str(level).lower(), f"⚪ {level}"
    )


def last_modified(filename: str) -> str:
    path = OUTPUT_DIR / filename
    if not path.exists():
        return "未生成"
    import datetime
    dt = datetime.datetime.fromtimestamp(path.stat().st_mtime)
    return dt.strftime("%Y-%m-%d %H:%M")


def regen_button(label: str, command: str, filename: str) -> None:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"最終更新: {last_modified(filename)}")
    with col2:
        if st.button(label, use_container_width=True, type="primary"):
            with st.spinner("生成中..."):
                ok, out = run_task(command)
            if ok:
                st.success("✅ 生成完了！")
            else:
                st.error("❌ エラーが発生しました")
                st.code(out)
            st.rerun()


# ── サイドバー ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🤖 AI副業システム")
    st.caption("リサーチ・下書き生成ツール")
    st.divider()
    page = st.radio(
        "ページを選択",
        options=[
            "🏠 ダッシュボード",
            "🛍️ 楽天ROOM候補",
            "📥 Shopeeデータ入力",
            "🌏 Shopee出品下書き",
            "📝 noteレポート",
            "ℹ️ 使い方",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(
        "⚠️ 下書き生成専用ツールです。\n投稿・出品は必ず人間が手動で行ってください。"
    )


# ══════════════════════════════════════════════════════════
# 🏠 ダッシュボード
# ══════════════════════════════════════════════════════════
if page == "🏠 ダッシュボード":
    st.title("🏠 ダッシュボード")
    regen_button("🔄 全データを再生成", "all", "dashboard.csv")
    st.divider()

    df = load_csv("dashboard.csv")
    if df is None:
        st.warning("dashboard.csv が見つかりません。上の「再生成」ボタンを押してください。")
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("総アイテム数", len(df))
    c2.metric("楽天ROOM候補", len(df[df["platform"] == "rakuten_room"]))
    c3.metric("Shopee候補", len(df[df["platform"] == "shopee"]))
    approved = len(df[df["approved"].astype(str).str.upper() == "TRUE"])
    c4.metric("承認済み", approved)

    st.divider()

    if "risk_level" in df.columns:
        st.subheader("リスク分布")
        risk_counts = df["risk_level"].value_counts().reset_index()
        risk_counts.columns = ["リスク", "件数"]
        st.dataframe(risk_counts, use_container_width=True, hide_index=True)
        st.divider()

    st.subheader("全アイテム一覧")
    display_cols = [
        c for c in
        ["date", "platform", "country", "genre", "product_name",
         "selling_price", "profit", "profit_margin",
         "risk_level", "status", "approved"]
        if c in df.columns
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
        product_name = str(row.get("product_name", ""))
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
                st.markdown(f"**リスク**\n\n{risk_badge(risk)}")

            if trend:
                st.markdown(f"**トレンド理由:** {trend}")
            if season:
                st.markdown(f"**季節キーワード:** {season}")
            if source_url and str(source_url) != "nan":
                st.markdown(f"[🔗 商品ページを開く]({source_url})")

            if room_text_raw and room_text_raw != "nan":
                parts = [p.strip() for p in room_text_raw.split("|||")]
                hashtags = ""
                text_parts = []
                for p in parts:
                    if p.startswith("ハッシュタグ:"):
                        hashtags = p.replace("ハッシュタグ:", "").strip()
                    elif p:
                        text_parts.append(p)

                st.markdown("**📋 投稿文（下書き）**")
                for i, text in enumerate(text_parts, 1):
                    with st.expander(f"パターン {i}"):
                        st.text_area(
                            f"パターン{i}",
                            value=text,
                            height=160,
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
        st.write("")


# ══════════════════════════════════════════════════════════
# 📥 Shopeeデータ入力
# ══════════════════════════════════════════════════════════
elif page == "📥 Shopeeデータ入力":
    st.title("📥 Shopeeリサーチデータ入力")
    st.info(
        "ここで入力したデータをもとに Shopee 出品下書きが生成されます。"
        "実際の出品はこのツールでは行いません。"
    )

    # ── 新規追加フォーム ────────────────────────────────────────
    st.subheader("➕ 新しい商品を追加")
    with st.form("add_shopee_item", clear_on_submit=True):
        row1_c1, row1_c2 = st.columns(2)
        with row1_c1:
            new_country = st.selectbox("対象国 ＊", SHOPEE_COUNTRIES)
            new_genre = st.text_input(
                "ジャンル（英語）＊",
                placeholder="例: Beauty Tools",
            )
        with row1_c2:
            new_product = st.text_input(
                "商品名（日本語）＊",
                placeholder="例: ミニ美顔ローラー",
            )
            new_url = st.text_input(
                "Shopee URL",
                placeholder="https://shopee.sg/...",
            )

        new_trend = st.text_area(
            "トレンド理由 ＊",
            placeholder="例: Shopee Singaporeのビューティーツールカテゴリで上位表示されていた",
            height=90,
        )

        price_c1, price_c2 = st.columns(2)
        with price_c1:
            new_cost = st.number_input(
                "仕入れ価格（円）＊", min_value=0, value=500, step=100
            )
        with price_c2:
            new_ship = st.number_input(
                "送料見込み（円）", min_value=0, value=300, step=50
            )

        submitted = st.form_submit_button(
            "＋ リストに追加する", use_container_width=True, type="primary"
        )

    if submitted:
        if not new_genre.strip() or not new_product.strip() or not new_trend.strip():
            st.error("❌ ジャンル・商品名・トレンド理由は必須です。")
        else:
            current_df = load_shopee_input()
            new_row = pd.DataFrame([{
                "country": new_country,
                "genre": new_genre.strip(),
                "product_name": new_product.strip(),
                "trend_reason": new_trend.strip(),
                "source_url": new_url.strip(),
                "cost_price_jpy": int(new_cost),
                "shipping_cost_jpy": int(new_ship),
            }])
            updated = pd.concat([current_df, new_row], ignore_index=True)
            save_shopee_input(updated)
            st.success(f"✅ 「{new_product.strip()}」を追加しました！")
            st.rerun()

    st.divider()

    # ── 編集テーブル ────────────────────────────────────────────
    st.subheader("📋 登録済みリスト（タップして編集・行削除可）")
    st.caption("行を選択して「Delete」または「-」ボタンで削除できます。編集後は「💾 保存」を押してください。")

    current_df = load_shopee_input()

    if current_df.empty:
        st.info("まだデータがありません。上のフォームから追加してください。")
        edited_df = current_df
    else:
        edited_df = st.data_editor(
            current_df,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "country": st.column_config.SelectboxColumn(
                    "対象国",
                    options=SHOPEE_COUNTRIES,
                    required=True,
                ),
                "genre": st.column_config.TextColumn(
                    "ジャンル（英語）",
                    required=True,
                ),
                "product_name": st.column_config.TextColumn(
                    "商品名",
                    required=True,
                ),
                "trend_reason": st.column_config.TextColumn(
                    "トレンド理由",
                    width="large",
                ),
                "source_url": st.column_config.LinkColumn(
                    "Shopee URL",
                    display_text="リンク",
                ),
                "cost_price_jpy": st.column_config.NumberColumn(
                    "仕入れ価格（円）",
                    min_value=0,
                    format="¥%d",
                    required=True,
                ),
                "shipping_cost_jpy": st.column_config.NumberColumn(
                    "送料（円）",
                    min_value=0,
                    format="¥%d",
                ),
            },
            hide_index=True,
            key="shopee_editor",
        )

    st.write("")

    # ── 保存 & 再生成ボタン ──────────────────────────────────────
    btn_c1, btn_c2 = st.columns(2)
    with btn_c1:
        if st.button("💾 変更を保存", use_container_width=True, type="primary"):
            if edited_df is not None and not edited_df.empty:
                clean = edited_df.dropna(subset=["product_name"]).reset_index(drop=True)
                save_shopee_input(clean)
                st.success(f"✅ {len(clean)} 件を保存しました。")
            else:
                save_shopee_input(pd.DataFrame(columns=SHOPEE_COLUMNS))
                st.success("✅ データをクリアしました。")

    with btn_c2:
        if st.button("🔄 Shopee下書きを再生成", use_container_width=True):
            with st.spinner("Shopeeリサーチを実行中..."):
                ok, out = run_task("shopee")
            if ok:
                st.success("✅ 完了！「Shopee出品下書き」ページで確認してください。")
            else:
                st.error("❌ エラーが発生しました")
                st.code(out)


# ══════════════════════════════════════════════════════════
# 🌏 Shopee出品下書き
# ══════════════════════════════════════════════════════════
elif page == "🌏 Shopee出品下書き":
    st.title("🌏 Shopee 出品下書き")
    st.info(
        "⚠️ 下書き確認専用です。Shopeeへの出品は必ず人間が手動で行ってください。"
        "approved列のTRUE変更も手動で行ってください。"
    )
    regen_button("🔄 Shopeeリサーチを再実行", "shopee", "shopee_listing_drafts.csv")
    st.divider()

    df = load_csv("shopee_listing_drafts.csv")
    if df is None:
        st.warning("shopee_listing_drafts.csv が見つかりません。再生成ボタンを押してください。")
        st.stop()

    for _, row in df.iterrows():
        product_name = str(row.get("product_name", ""))
        country = row.get("country", "")
        genre = row.get("genre", "")
        cost = row.get("cost_price", "")
        sell = row.get("selling_price", "")
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
                st.markdown(f"**リスク**\n\n{risk_badge(risk)}")

            p1, p2, p3, p4 = st.columns(4)
            p1.metric("仕入れ", f"¥{cost}")
            p2.metric("販売価格", f"¥{sell}")
            p3.metric("想定利益", f"¥{profit}")
            try:
                p4.metric("利益率", f"{float(margin)*100:.0f}%")
            except Exception:
                p4.metric("利益率", "-")

            if risk_reason and str(risk_reason) != "nan":
                st.caption(f"⚠️ リスクメモ: {risk_reason}")

            if shopee_title and shopee_title != "nan":
                with st.expander("📝 英語タイトル・説明文を見る"):
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

            status_text = (
                "✅ 承認済み"
                if approved.upper() == "TRUE"
                else "🔲 未承認（CSVのapproved列を TRUE に変更すると承認）"
            )
            st.caption(f"承認状態: {status_text}")

        st.write("")


# ══════════════════════════════════════════════════════════
# 📝 noteレポート
# ══════════════════════════════════════════════════════════
elif page == "📝 noteレポート":
    import json as _json
    import datetime as _dt

    WEEKLY_RESULTS_FILE = DATA_DIR / "weekly_results.json"
    WEEKLY_RESULTS_TEMPLATE = DATA_DIR / "weekly_results_template.json"

    def load_weekly_results() -> dict:
        src = WEEKLY_RESULTS_FILE if WEEKLY_RESULTS_FILE.exists() else WEEKLY_RESULTS_TEMPLATE
        if src.exists():
            with open(src, encoding="utf-8") as f:
                return _json.load(f)
        today = _dt.date.today()
        week_num = (today.day - 1) // 7 + 1
        return {
            "week_label": f"{today.year}年{today.month}月 第{week_num}週",
            "rakuten_room": {"posts_made": 0, "clicks": 0, "estimated_reward_jpy": 0},
            "shopee": {"listings_approved": 0, "orders": 0, "revenue_jpy": 0, "profit_jpy": 0},
            "shorts_script_ideas": [],
            "failures": [],
            "improvements": [],
        }

    def save_weekly_results(data: dict) -> None:
        DATA_DIR.mkdir(exist_ok=True)
        with open(WEEKLY_RESULTS_FILE, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)

    st.title("📝 note 週次レポート下書き")
    st.info("⚠️ 下書きです。自分の言葉・実際の数値を加筆修正してから公開してください。")

    # ── 週次データ入力フォーム ────────────────────────────────────
    with st.expander("📊 今週の実績データを入力する", expanded=not (OUTPUT_DIR / "note_weekly_report.md").exists()):
        wk = load_weekly_results()
        room = wk.get("rakuten_room", {})
        shopee = wk.get("shopee", {})

        with st.form("weekly_results_form"):
            st.markdown("### 📅 週ラベル")
            week_label = st.text_input(
                "週ラベル",
                value=wk.get("week_label", ""),
                placeholder="例: 2026年7月 第1週",
                label_visibility="collapsed",
            )

            st.markdown("### 🛍️ 楽天ROOM 実績")
            r1, r2, r3 = st.columns(3)
            with r1:
                r_posts = st.number_input("投稿数", min_value=0, value=int(room.get("posts_made", 0)), step=1)
            with r2:
                r_clicks = st.number_input("クリック数", min_value=0, value=int(room.get("clicks", 0)), step=1)
            with r3:
                r_reward = st.number_input("想定報酬（円）", min_value=0, value=int(room.get("estimated_reward_jpy", 0)), step=10)

            st.markdown("### 🌏 Shopee 実績")
            s1, s2, s3, s4 = st.columns(4)
            with s1:
                s_listings = st.number_input("出品数", min_value=0, value=int(shopee.get("listings_approved", 0)), step=1)
            with s2:
                s_orders = st.number_input("注文数", min_value=0, value=int(shopee.get("orders", 0)), step=1)
            with s3:
                s_revenue = st.number_input("売上（円）", min_value=0, value=int(shopee.get("revenue_jpy", 0)), step=100)
            with s4:
                s_profit = st.number_input("利益（円）", min_value=0, value=int(shopee.get("profit_jpy", 0)), step=100)

            st.markdown("### ❌ うまくいかなかったこと")
            st.caption("1行につき1件。空行は無視されます。")
            failures_raw = st.text_area(
                "失敗・課題",
                value="\n".join(wk.get("failures", [])),
                height=110,
                placeholder="例: 出品タイトルが長すぎて表示が切れた",
                label_visibility="collapsed",
            )

            st.markdown("### ✅ 来週への改善点")
            improvements_raw = st.text_area(
                "改善点",
                value="\n".join(wk.get("improvements", [])),
                height=110,
                placeholder="例: 次週はタイトルを60文字以内に修正する",
                label_visibility="collapsed",
            )

            st.markdown("### 🎬 ショート動画アイデア（任意）")
            shorts_raw = st.text_area(
                "ショートアイデア",
                value="\n".join(wk.get("shorts_script_ideas", [])),
                height=80,
                placeholder="例: 開封15秒レビュー動画",
                label_visibility="collapsed",
            )

            save_and_regen = st.form_submit_button(
                "💾 保存して下書きを再生成",
                use_container_width=True,
                type="primary",
            )

        if save_and_regen:
            new_data = {
                "week_label": week_label.strip() or wk.get("week_label", ""),
                "rakuten_room": {
                    "posts_made": int(r_posts),
                    "clicks": int(r_clicks),
                    "estimated_reward_jpy": int(r_reward),
                },
                "shopee": {
                    "listings_approved": int(s_listings),
                    "orders": int(s_orders),
                    "revenue_jpy": int(s_revenue),
                    "profit_jpy": int(s_profit),
                },
                "failures": [l.strip() for l in failures_raw.splitlines() if l.strip()],
                "improvements": [l.strip() for l in improvements_raw.splitlines() if l.strip()],
                "shorts_script_ideas": [l.strip() for l in shorts_raw.splitlines() if l.strip()],
            }
            save_weekly_results(new_data)
            with st.spinner("下書きを生成中..."):
                ok, out = run_task("note")
            if ok:
                st.success("✅ 保存して下書きを再生成しました！")
            else:
                st.error("❌ 生成に失敗しました")
                st.code(out)
            st.rerun()

    st.divider()

    regen_button("🔄 下書きのみ再生成（データ変更なし）", "note", "note_weekly_report.md")
    st.divider()

    md = load_md("note_weekly_report.md")
    if md is None:
        st.warning("まだ下書きがありません。上のフォームでデータを入力して「保存して再生成」してください。")
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
| Shopeeデータ入力 | リサーチ結果をフォームで入力・編集・削除 |
| Shopee出品下書き | 仕入れ価格・利益計算・英語コピーの下書きを確認 |
| note週次レポート | 週次の実績をまとめたnote記事の下書きを生成 |
| ダッシュボード | 全データを一覧表示 |
    """)

    st.divider()

    st.subheader("🌏 Shopeeリサーチの手順")
    st.markdown("""
1. **「📥 Shopeeデータ入力」ページ**でフォームから商品情報を追加
2. 「💾 変更を保存」ボタンで保存
3. 「🔄 Shopee下書きを再生成」ボタンを押す
4. **「🌏 Shopee出品下書き」ページ**で英語タイトル・説明文をコピー
5. Shopee Seller Center で**手動で**出品する
6. 出品OKと判断したら `shopee_listing_drafts.csv` の `approved` 列を `TRUE` に変更
    """)

    st.divider()

    st.subheader("🛍️ 楽天ROOMの手順")
    st.markdown("""
1. **「🛍️ 楽天ROOM候補」ページ**で投稿候補を確認
2. 気に入った投稿文パターンをコピー
3. 楽天ROOMアプリ/サイトから**手動で**投稿
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

・楽天ROOMへの自動投稿は行いません
・Shopeeへの自動出品は行いません
・投稿文・出品文・リスク判定はあくまで目安です
・最終的な投稿・出品・価格設定は必ずご自身で確認してください
    """)
