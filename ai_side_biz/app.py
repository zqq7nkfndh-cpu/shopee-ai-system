# -*- coding: utf-8 -*-
"""
app.py — AI副業システム (Shopee専用) Streamlit Web UI
"""
import io
import json as _json
import datetime as _dt
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
DRAFTS_FILE = OUTPUT_DIR / "shopee_listing_drafts.csv"

SHOPEE_INPUT_COLUMNS = [
    "country", "genre", "product_name", "trend_reason",
    "source_url", "cost_price_jpy", "shipping_cost_jpy",
    "expected_selling_price_jpy",
]

TRANSACTION_FEE = 0.05
SERVICE_FEE = 0.05
PAYMENT_FEE = 0.02
TOTAL_FEE_RATE = TRANSACTION_FEE + SERVICE_FEE + PAYMENT_FEE

st.set_page_config(
    page_title="Shopee AI副業システム",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── ヘルパー ──────────────────────────────────────────────────────────────────

def run_task(command: str) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "main.py", command],
        cwd=str(BASE_DIR),
        capture_output=True, text=True, timeout=120,
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
        df = pd.DataFrame(columns=SHOPEE_INPUT_COLUMNS)
    for col in SHOPEE_INPUT_COLUMNS:
        if col not in df.columns:
            df[col] = 0 if col.endswith("_jpy") else ""
    for num_col in ["cost_price_jpy", "shipping_cost_jpy", "expected_selling_price_jpy"]:
        df[num_col] = pd.to_numeric(df[num_col], errors="coerce").fillna(0).astype(int)
    return df[SHOPEE_INPUT_COLUMNS].reset_index(drop=True)


def save_shopee_input(df: pd.DataFrame) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(SHOPEE_INPUT_FILE, index=False, encoding="utf-8-sig")


def risk_badge(level: str) -> str:
    return {"low": "🟢 低リスク", "medium": "🟡 要確認", "high": "🔴 高リスク"}.get(
        str(level).lower(), f"⚪ {level}"
    )


def last_modified(filename: str) -> str:
    path = OUTPUT_DIR / filename
    if not path.exists():
        return "未生成"
    dt = _dt.datetime.fromtimestamp(path.stat().st_mtime)
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
                st.success("✅ 完了！")
            else:
                st.error("❌ エラーが発生しました")
                st.code(out)
            st.rerun()


def calc_profit(cost: float, ship: float, selling: float) -> dict:
    base = cost + ship
    fee = selling * TOTAL_FEE_RATE
    profit = selling - base - fee
    margin = profit / selling if selling > 0 else 0
    min_price = base / (1 - TOTAL_FEE_RATE) if (1 - TOTAL_FEE_RATE) > 0 else base * 1.15
    return {
        "fee": round(fee),
        "profit": round(profit),
        "margin": margin,
        "min_price": round(min_price),
    }


# ── サイドバー ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🛒 Shopee AI副業")
    st.caption("越境EC リサーチ・下書き生成ツール")
    st.divider()
    page = st.radio(
        "ページを選択",
        options=[
            "🏠 ダッシュボード",
            "📥 商品入力エディタ",
            "📝 出品下書き確認",
            "💰 利益計算シミュレーター",
            "📤 承認済みエクスポート",
            "📰 noteレポート",
            "ℹ️ 使い方",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(
        "⚠️ 下書き生成専用ツールです。\n"
        "実際の出品は必ず人間が\n手動で確認・承認してください。"
    )


# ══════════════════════════════════════════════════════════
# 🏠 ダッシュボード
# ══════════════════════════════════════════════════════════
if page == "🏠 ダッシュボード":
    st.title("🏠 Shopee リサーチ ダッシュボード")
    regen_button("🔄 全データを再生成", "shopee", "shopee_listing_drafts.csv")
    st.divider()

    df = load_csv("shopee_listing_drafts.csv")
    if df is None:
        st.warning("まだデータがありません。「📥 商品入力エディタ」で商品を追加してから「🔄 再生成」を押してください。")
        st.stop()

    total = len(df)
    approved = len(df[df["approved"].astype(str).str.upper() == "TRUE"])
    high_risk = len(df[df["risk_level"].astype(str).str.lower() == "high"])
    low_risk = len(df[df["risk_level"].astype(str).str.lower() == "low"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("総商品数", total)
    c2.metric("承認済み", approved)
    c3.metric("🟢 低リスク", low_risk)
    c4.metric("🔴 高リスク", high_risk)

    st.divider()

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("📊 リスク分布")
        if "risk_level" in df.columns:
            risk_counts = df["risk_level"].value_counts().reset_index()
            risk_counts.columns = ["リスク", "件数"]
            risk_counts["リスク"] = risk_counts["リスク"].map(
                {"low": "🟢 低", "medium": "🟡 中", "high": "🔴 高"}
            ).fillna(risk_counts["リスク"])
            st.dataframe(risk_counts, use_container_width=True, hide_index=True)

    with col_r:
        st.subheader("🌍 国別内訳")
        if "country" in df.columns:
            country_counts = df["country"].value_counts().reset_index()
            country_counts.columns = ["国", "件数"]
            st.dataframe(country_counts, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📋 全商品一覧")
    display_cols = [c for c in [
        "country", "genre", "product_name",
        "selling_price_jpy", "profit_jpy", "profit_margin",
        "risk_level", "approved",
    ] if c in df.columns]

    def fmt_margin(val):
        try:
            return f"{float(val)*100:.0f}%"
        except Exception:
            return val

    display_df = df[display_cols].copy()
    if "profit_margin" in display_df.columns:
        display_df["profit_margin"] = display_df["profit_margin"].apply(fmt_margin)
    if "risk_level" in display_df.columns:
        display_df["risk_level"] = display_df["risk_level"].map(
            {"low": "🟢 低", "medium": "🟡 中", "high": "🔴 高"}
        ).fillna(display_df["risk_level"])

    st.dataframe(display_df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════
# 📥 商品入力エディタ
# ══════════════════════════════════════════════════════════
elif page == "📥 商品入力エディタ":
    st.title("📥 Shopee 商品データ入力")
    st.info(
        "ここで入力したデータをもとに出品下書きが生成されます。"
        "実際の出品はこのツールでは行いません。"
    )

    st.subheader("➕ 新しい商品を追加")
    with st.form("add_shopee_item", clear_on_submit=True):
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            new_country = st.selectbox("対象国 ＊", SHOPEE_COUNTRIES)
            new_genre = st.text_input("ジャンル（英語）＊", placeholder="例: Beauty Tools")
        with r1c2:
            new_product = st.text_input("商品名（日本語）＊", placeholder="例: ミニ美顔ローラー")
            new_url = st.text_input("Shopee URL", placeholder="https://shopee.sg/...")

        new_trend = st.text_area(
            "トレンド理由 ＊",
            placeholder="例: Shopeeビューティーカテゴリで上位表示されていた",
            height=90,
        )

        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            new_cost = st.number_input("仕入れ価格（円）＊", min_value=0, value=500, step=100)
        with pc2:
            new_ship = st.number_input("送料見込み（円）", min_value=0, value=300, step=50)
        with pc3:
            new_expected = st.number_input(
                "目標販売価格（円）",
                min_value=0, value=0, step=100,
                help="0の場合は自動計算（目標利益率30%ベース）",
            )

        submitted = st.form_submit_button("＋ リストに追加する", use_container_width=True, type="primary")

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
                "expected_selling_price_jpy": int(new_expected),
            }])
            updated = pd.concat([current_df, new_row], ignore_index=True)
            save_shopee_input(updated)
            st.success(f"✅ 「{new_product.strip()}」を追加しました！")
            st.rerun()

    st.divider()
    st.subheader("📋 登録済みリスト（タップして編集可）")
    st.caption("行を選択して「-」ボタンで削除。編集後は「💾 保存」を押してください。")

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
                "country": st.column_config.SelectboxColumn("対象国", options=SHOPEE_COUNTRIES, required=True),
                "genre": st.column_config.TextColumn("ジャンル（英語）", required=True),
                "product_name": st.column_config.TextColumn("商品名", required=True),
                "trend_reason": st.column_config.TextColumn("トレンド理由", width="large"),
                "source_url": st.column_config.LinkColumn("Shopee URL", display_text="リンク"),
                "cost_price_jpy": st.column_config.NumberColumn("仕入れ価格（円）", min_value=0, format="¥%d", required=True),
                "shipping_cost_jpy": st.column_config.NumberColumn("送料（円）", min_value=0, format="¥%d"),
                "expected_selling_price_jpy": st.column_config.NumberColumn(
                    "目標販売価格（円）",
                    min_value=0, format="¥%d",
                    help="0=自動計算（目標利益率30%）",
                ),
            },
            hide_index=True,
            key="shopee_editor",
        )

    st.write("")
    btn_c1, btn_c2 = st.columns(2)
    with btn_c1:
        if st.button("💾 変更を保存", use_container_width=True, type="primary"):
            if edited_df is not None and not edited_df.empty:
                clean = edited_df.dropna(subset=["product_name"]).reset_index(drop=True)
                save_shopee_input(clean)
                st.success(f"✅ {len(clean)} 件を保存しました。")
            else:
                save_shopee_input(pd.DataFrame(columns=SHOPEE_INPUT_COLUMNS))
                st.success("✅ データをクリアしました。")
    with btn_c2:
        if st.button("🔄 出品下書きを再生成", use_container_width=True):
            with st.spinner("生成中..."):
                ok, out = run_task("shopee")
            if ok:
                st.success("✅ 完了！「📝 出品下書き確認」で確認してください。")
            else:
                st.error("❌ エラーが発生しました")
                st.code(out)


# ══════════════════════════════════════════════════════════
# 📝 出品下書き確認
# ══════════════════════════════════════════════════════════
elif page == "📝 出品下書き確認":
    st.title("📝 Shopee 出品下書き確認")
    st.warning(
        "⚠️ **下書き確認専用です。** "
        "Shopeeへの出品は必ず人間が内容を確認・承認してから手動で行ってください。"
    )
    regen_button("🔄 下書きを再生成", "shopee", "shopee_listing_drafts.csv")
    st.divider()

    df = load_csv("shopee_listing_drafts.csv")
    if df is None:
        st.warning("まだ下書きがありません。「📥 商品入力エディタ」でデータを追加してください。")
        st.stop()

    risk_filter = st.multiselect(
        "リスクフィルター",
        options=["🟢 低リスク", "🟡 要確認", "🔴 高リスク"],
        default=["🟢 低リスク", "🟡 要確認", "🔴 高リスク"],
    )
    risk_map = {"🟢 低リスク": "low", "🟡 要確認": "medium", "🔴 高リスク": "high"}
    selected_risks = [risk_map[r] for r in risk_filter]
    df = df[df["risk_level"].astype(str).str.lower().isin(selected_risks)]

    st.caption(f"表示件数: {len(df)} 件")
    st.divider()

    for _, row in df.iterrows():
        product_name = str(row.get("product_name", ""))
        country = row.get("country", "")
        genre = row.get("genre", "")
        cost = row.get("cost_price_jpy", "")
        selling = row.get("selling_price_jpy", "")
        selling_usd = row.get("selling_price_usd", "")
        profit = row.get("profit_jpy", "")
        margin = row.get("profit_margin", "")
        min_price = row.get("min_price_no_loss_jpy", "")
        fee = row.get("fee_estimate_jpy", "")
        risk = str(row.get("risk_level", ""))
        risk_reason = str(row.get("risk_reason", ""))
        category_sug = str(row.get("category_suggestion", ""))
        target_cust = str(row.get("target_customer", ""))
        shopee_title = str(row.get("shopee_title", ""))
        shopee_desc = str(row.get("shopee_description", ""))
        bullets_raw = str(row.get("bullet_points", ""))
        keywords = str(row.get("keywords", ""))
        selling_pts_raw = str(row.get("selling_points", ""))
        caution = str(row.get("caution_notes", ""))
        source_url = str(row.get("source_url", ""))
        approved = str(row.get("approved", "FALSE"))

        border_color = {"low": "#28a745", "medium": "#ffc107", "high": "#dc3545"}.get(risk.lower(), "#888")

        with st.container(border=True):
            h_col, r_col = st.columns([4, 1])
            with h_col:
                st.subheader(product_name)
                st.caption(f"🌍 {country}  ｜  ジャンル: {genre}  ｜  カテゴリ候補: {category_sug}")
                if source_url and source_url != "nan":
                    st.markdown(f"[🔗 商品ページを開く]({source_url})")
            with r_col:
                st.markdown(f"**リスク**\n\n{risk_badge(risk)}")
                st.caption(f"承認: {'✅ 済' if approved.upper() == 'TRUE' else '🔲 未'}")

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("仕入れ", f"¥{cost}")
            m2.metric("推奨販売価格", f"¥{selling}")
            m3.metric("USD換算", f"${selling_usd}")
            m4.metric("想定利益", f"¥{profit}")
            try:
                m5.metric("利益率", f"{float(margin)*100:.0f}%")
            except Exception:
                m5.metric("利益率", "-")

            m6, m7 = st.columns(2)
            m6.metric("手数料概算", f"¥{fee}", help="取引5%+サービス5%+決済2%の合計概算")
            m7.metric("損益分岐価格", f"¥{min_price}", help="この価格を下回ると赤字になる最低ライン")

            if risk_reason and risk_reason not in ("nan", "特記事項なし（簡易チェックのみ。最終確認は人間が行うこと）"):
                with st.expander("⚠️ リスク詳細を見る"):
                    st.warning(risk_reason)

            st.markdown("---")

            tab1, tab2, tab3 = st.tabs(["📋 出品コピー", "🎯 販売戦略", "⚠️ 注意事項"])

            with tab1:
                st.markdown("**英語タイトル（60文字以内）**")
                st.text_area(
                    "title",
                    value=shopee_title if shopee_title != "nan" else "",
                    height=60,
                    label_visibility="collapsed",
                    key=f"title_{product_name}_{country}",
                )

                if shopee_desc and shopee_desc != "nan":
                    st.markdown("**商品説明文**")
                    st.text_area(
                        "desc",
                        value=shopee_desc,
                        height=110,
                        label_visibility="collapsed",
                        key=f"desc_{product_name}_{country}",
                    )

                if bullets_raw and bullets_raw != "nan":
                    st.markdown("**箇条書きポイント**")
                    bullets = [b.strip() for b in bullets_raw.split("|") if b.strip()]
                    bullet_text = "\n".join(bullets)
                    st.text_area(
                        "bullets",
                        value=bullet_text,
                        height=130,
                        label_visibility="collapsed",
                        key=f"bullets_{product_name}_{country}",
                    )

                if keywords and keywords != "nan":
                    st.markdown("**検索キーワード**")
                    st.text_area(
                        "keywords",
                        value=keywords,
                        height=60,
                        label_visibility="collapsed",
                        key=f"kw_{product_name}_{country}",
                    )

            with tab2:
                if target_cust and target_cust != "nan":
                    st.markdown(f"**ターゲット顧客:** {target_cust}")
                if selling_pts_raw and selling_pts_raw != "nan":
                    st.markdown("**セリングポイント**")
                    for pt in selling_pts_raw.split("|"):
                        pt = pt.strip()
                        if pt:
                            st.markdown(f"- {pt}")

            with tab3:
                if caution and caution != "nan":
                    st.info(caution)

            status_text = (
                "✅ 承認済み — エクスポート対象"
                if approved.upper() == "TRUE"
                else "🔲 未承認 — 承認するには drafts CSVの approved 列を TRUE に変更"
            )
            st.caption(f"ステータス: {status_text}")

        st.write("")


# ══════════════════════════════════════════════════════════
# 💰 利益計算シミュレーター
# ══════════════════════════════════════════════════════════
elif page == "💰 利益計算シミュレーター":
    st.title("💰 利益計算シミュレーター")
    st.info(
        "Shopee手数料は変動します。実際の出品前にShopee Seller Centerで"
        "最新の手数料率を必ず確認してください。"
    )

    st.subheader("📊 コスト入力")
    col1, col2 = st.columns(2)
    with col1:
        sim_cost = st.number_input("仕入れ価格（円）", min_value=0, value=800, step=50)
        sim_ship_domestic = st.number_input("国内送料（円）", min_value=0, value=0, step=50)
    with col2:
        sim_ship_intl = st.number_input("国際送料見込み（円）", min_value=0, value=300, step=50)
        sim_target_price = st.number_input(
            "販売希望価格（円）", min_value=0, value=2000, step=100,
            help="設定した価格での利益を計算します"
        )

    st.divider()
    st.subheader("⚙️ 手数料設定（概算）")
    fee_col1, fee_col2, fee_col3 = st.columns(3)
    with fee_col1:
        txn_fee = st.slider("取引手数料 (%)", 0.0, 15.0, 5.0, 0.5) / 100
    with fee_col2:
        svc_fee = st.slider("サービス手数料 (%)", 0.0, 15.0, 5.0, 0.5) / 100
    with fee_col3:
        pay_fee = st.slider("決済手数料 (%)", 0.0, 5.0, 2.0, 0.5) / 100

    total_fee_rate_sim = txn_fee + svc_fee + pay_fee
    base_cost_sim = sim_cost + sim_ship_domestic + sim_ship_intl

    if sim_target_price > 0:
        fee_amount = sim_target_price * total_fee_rate_sim
        profit_sim = sim_target_price - base_cost_sim - fee_amount
        margin_sim = profit_sim / sim_target_price
        denom = 1 - total_fee_rate_sim
        min_price_sim = base_cost_sim / denom if denom > 0 else base_cost_sim * 1.15
        jpy_per_usd = 150.0
        price_usd = sim_target_price / jpy_per_usd

        st.divider()
        st.subheader("📈 計算結果")

        res_cols = st.columns(4)
        res_cols[0].metric("総コスト", f"¥{base_cost_sim:,.0f}")
        res_cols[1].metric("手数料合計", f"¥{fee_amount:,.0f}", f"({total_fee_rate_sim*100:.0f}%)")
        res_cols[2].metric(
            "想定利益",
            f"¥{profit_sim:,.0f}",
            delta=f"{'黒字' if profit_sim > 0 else '赤字'}",
            delta_color="normal" if profit_sim > 0 else "inverse",
        )
        res_cols[3].metric("利益率", f"{margin_sim*100:.1f}%")

        st.info(
            f"**損益分岐価格（最低販売価格）:** ¥{min_price_sim:,.0f}  "
            f"｜  **USD換算:** ${price_usd:.2f}（¥150/$1 概算）"
        )

        if profit_sim <= 0:
            st.error(f"⚠️ この価格設定では赤字です。最低 ¥{min_price_sim:,.0f} 以上に設定してください。")
        elif margin_sim < 0.2:
            st.warning(f"💡 利益率が {margin_sim*100:.0f}% と低めです。20〜30%以上を目標にしましょう。")
        else:
            st.success(f"✅ 利益率 {margin_sim*100:.0f}% — 健全な利益が見込めます。")

        st.divider()
        st.subheader("📊 価格別シミュレーション")
        sim_prices = range(int(base_cost_sim * 1.1), int(base_cost_sim * 3), max(50, int(base_cost_sim * 0.1)))
        rows = []
        for p in sim_prices:
            f_amt = p * total_fee_rate_sim
            pr = p - base_cost_sim - f_amt
            rows.append({
                "販売価格（円）": f"¥{p:,.0f}",
                "USD換算": f"${p/150:.2f}",
                "手数料": f"¥{f_amt:,.0f}",
                "利益": f"¥{pr:,.0f}",
                "利益率": f"{(pr/p*100):.0f}%" if p > 0 else "-",
                "判定": "✅ 黒字" if pr > 0 else "🔴 赤字",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════
# 📤 承認済みエクスポート
# ══════════════════════════════════════════════════════════
elif page == "📤 承認済みエクスポート":
    st.title("📤 承認済みリストのエクスポート")
    st.warning(
        "⚠️ **エクスポートは下書きの出力のみです。**\n"
        "Shopeeへの実際の出品は、このファイルをもとに人間が手動で行ってください。\n"
        "高リスク商品は自動的に除外されます。"
    )

    df = load_csv("shopee_listing_drafts.csv")
    if df is None:
        st.info("まだデータがありません。「📥 商品入力エディタ」でデータを追加して下書きを生成してください。")
        st.stop()

    approved_df = df[
        (df["approved"].astype(str).str.upper() == "TRUE") &
        (df["risk_level"].astype(str).str.lower() != "high")
    ].copy().reset_index(drop=True)

    rejected_df = df[
        (df["approved"].astype(str).str.upper() == "TRUE") &
        (df["risk_level"].astype(str).str.lower() == "high")
    ]

    total = len(df)
    exportable = len(approved_df)
    excluded = len(rejected_df)
    not_approved = len(df) - len(df[df["approved"].astype(str).str.upper() == "TRUE"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("総商品数", total)
    c2.metric("✅ エクスポート対象", exportable)
    c3.metric("🔴 高リスクで除外", excluded)
    c4.metric("🔲 未承認", not_approved)

    st.divider()

    if exportable == 0:
        st.info(
            "エクスポート可能な商品がありません。\n\n"
            "👉 `shopee_listing_drafts.csv` の **approved 列を TRUE** に変更すると承認されます。\n"
            "高リスク商品は承認してもエクスポートされません。"
        )
    else:
        st.subheader(f"📋 エクスポート対象商品（{exportable}件）")

        display_cols = [c for c in [
            "country", "genre", "product_name", "shopee_title",
            "selling_price_jpy", "selling_price_usd",
            "profit_jpy", "profit_margin", "risk_level",
        ] if c in approved_df.columns]
        st.dataframe(approved_df[display_cols], use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("⬇️ ダウンロード")

        dl_col1, dl_col2 = st.columns(2)

        with dl_col1:
            csv_buffer = io.StringIO()
            approved_df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
            st.download_button(
                label="📄 承認済みCSVをダウンロード",
                data=csv_buffer.getvalue().encode("utf-8-sig"),
                file_name=f"shopee_approved_{_dt.date.today().isoformat()}.csv",
                mime="text/csv",
                use_container_width=True,
                type="primary",
            )
            st.caption("このCSVをもとにShopee Seller Centerで手動出品してください")

        with dl_col2:
            api_items = []
            for _, r in approved_df.iterrows():
                bullets = [b.strip() for b in str(r.get("bullet_points", "")).split("|") if b.strip()]
                api_items.append({
                    "product_name_ja": r.get("product_name", ""),
                    "shopee_title": r.get("shopee_title", ""),
                    "shopee_description": r.get("shopee_description", ""),
                    "bullet_points": bullets,
                    "keywords": r.get("keywords", ""),
                    "category_suggestion": r.get("category_suggestion", ""),
                    "selling_price_jpy": r.get("selling_price_jpy", 0),
                    "selling_price_usd": r.get("selling_price_usd", 0),
                    "country": r.get("country", ""),
                    "risk_level": r.get("risk_level", ""),
                    "_api_ready": False,
                    "_note": "API連携前に必ず人間が内容を確認してください",
                })
            json_str = _json.dumps(api_items, ensure_ascii=False, indent=2)
            st.download_button(
                label="🔧 API連携用JSONをダウンロード",
                data=json_str.encode("utf-8"),
                file_name=f"shopee_api_draft_{_dt.date.today().isoformat()}.json",
                mime="application/json",
                use_container_width=True,
            )
            st.caption("将来のShopee Open Platform API連携用（現在はドライランのみ）")

    if excluded > 0:
        st.divider()
        with st.expander(f"🔴 除外された高リスク商品 ({excluded}件)"):
            st.error("以下の商品は approved=TRUE ですが、高リスクのためエクスポートから除外しました。")
            excl_cols = [c for c in ["product_name", "risk_level", "risk_reason"] if c in rejected_df.columns]
            st.dataframe(rejected_df[excl_cols], use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════
# 📰 noteレポート
# ══════════════════════════════════════════════════════════
elif page == "📰 noteレポート":
    import json as _json2
    import datetime as _dt2

    WEEKLY_RESULTS_FILE = DATA_DIR / "weekly_results.json"
    WEEKLY_RESULTS_TEMPLATE = DATA_DIR / "weekly_results_template.json"

    def load_weekly_results() -> dict:
        src = WEEKLY_RESULTS_FILE if WEEKLY_RESULTS_FILE.exists() else WEEKLY_RESULTS_TEMPLATE
        if src.exists():
            with open(src, encoding="utf-8") as f:
                return _json2.load(f)
        today = _dt2.date.today()
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
            _json2.dump(data, f, ensure_ascii=False, indent=2)

    st.title("📰 note 週次レポート下書き")
    st.info("⚠️ 下書きです。自分の言葉・実際の数値を加筆修正してから公開してください。")

    with st.expander("📊 今週の実績データを入力する", expanded=not (OUTPUT_DIR / "note_weekly_report.md").exists()):
        wk = load_weekly_results()
        shopee_wk = wk.get("shopee", {})

        with st.form("weekly_results_form"):
            st.markdown("### 📅 週ラベル")
            week_label = st.text_input(
                "週ラベル",
                value=wk.get("week_label", ""),
                placeholder="例: 2026年7月 第2週",
                label_visibility="collapsed",
            )

            st.markdown("### 🌏 Shopee 実績")
            s1, s2, s3, s4 = st.columns(4)
            with s1:
                s_listings = st.number_input("出品数", min_value=0, value=int(shopee_wk.get("listings_approved", 0)), step=1)
            with s2:
                s_orders = st.number_input("注文数", min_value=0, value=int(shopee_wk.get("orders", 0)), step=1)
            with s3:
                s_revenue = st.number_input("売上（円）", min_value=0, value=int(shopee_wk.get("revenue_jpy", 0)), step=100)
            with s4:
                s_profit = st.number_input("利益（円）", min_value=0, value=int(shopee_wk.get("profit_jpy", 0)), step=100)

            st.markdown("### ❌ うまくいかなかったこと（1行1件）")
            failures_raw = st.text_area(
                "失敗・課題",
                value="\n".join(wk.get("failures", [])),
                height=100,
                placeholder="例: 出品タイトルが60文字を超えて表示が切れた",
                label_visibility="collapsed",
            )

            st.markdown("### ✅ 来週への改善点（1行1件）")
            improvements_raw = st.text_area(
                "改善点",
                value="\n".join(wk.get("improvements", [])),
                height=100,
                placeholder="例: 次週はタイトルを60文字以内に修正する",
                label_visibility="collapsed",
            )

            st.markdown("### 🎬 ショート動画アイデア（任意）")
            shorts_raw = st.text_area(
                "ショートアイデア",
                value="\n".join(wk.get("shorts_script_ideas", [])),
                height=70,
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
                "rakuten_room": {"posts_made": 0, "clicks": 0, "estimated_reward_jpy": 0},
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
    regen_button("🔄 下書きのみ再生成", "note", "note_weekly_report.md")
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

    st.subheader("🛒 このアプリでできること")
    st.markdown("""
| 機能 | 説明 |
|---|---|
| 商品入力エディタ | Shopeeリサーチ結果をフォームで入力・編集・削除 |
| 出品下書き確認 | 英語コピー・利益計算・リスクチェック結果を確認 |
| 利益計算シミュレーター | 価格・手数料を変えて利益を試算 |
| 承認済みエクスポート | 承認済み・低/中リスク商品のCSV/JSONをダウンロード |
| noteレポート | 週次の実績をまとめたnote記事の下書きを生成 |
| ダッシュボード | 全商品のリスク・承認状況を一覧表示 |
    """)

    st.divider()

    st.subheader("📋 基本的な使い方（ステップ順）")
    st.markdown("""
**ステップ 1 — 商品リサーチ（手動）**
- Shopeeアプリで各国のカテゴリを見て、売れそうな日本製品を探す
- 商品名・カテゴリ・URL・仕入れ価格・送料・目標価格をメモする

**ステップ 2 — データ入力**
- 「📥 商品入力エディタ」ページのフォームから商品情報を入力
- 「💾 変更を保存」ボタンで保存
- 「🔄 出品下書きを再生成」ボタンを押す

**ステップ 3 — 下書き確認**
- 「📝 出品下書き確認」ページで英語コピー・利益・リスクを確認
- 問題なければ `shopee_listing_drafts.csv` を開いて **approved 列を TRUE** に変更

**ステップ 4 — エクスポート**
- 「📤 承認済みエクスポート」ページでCSVをダウンロード
- このCSVをもとに Shopee Seller Center で**手動で**出品する

⚠️ **高リスク商品は自動的にエクスポートから除外されます**
    """)

    st.divider()

    st.subheader("🔴 出品NGカテゴリ（リスクチェッカーが自動検出）")
    st.markdown("""
以下のカテゴリは高リスクフラグが立ちます。必ず人間が個別に確認してください：

| カテゴリ | 理由 |
|---|---|
| 食品・飲料 | 輸入国の食品衛生規制・検疫 |
| サプリメント | 医薬品として扱われる国あり |
| 化粧品 | 各国の化粧品規制・成分表示義務 |
| 医薬品・医療機器 | 輸出入許可が必要 |
| 電池内蔵製品 | 航空便輸出規制（IATA） |
| 液体物 | 輸送制限・破損リスク |
| ブランド品・キャラクター商品 | 商標権・著作権侵害リスク |
| 禁止品 | Shopee規約・法令で禁止 |
    """)

    st.divider()

    st.subheader("🔧 将来のShopee API連携について")
    st.markdown("""
`shopee_api.py` に API連携用のプレースホルダーが実装されています。

現時点では **DRY_RUN = True** で動作しており、実際の出品は行いません。
本番連携するには:

1. [Shopee Open Platform](https://open.shopee.com/) でアプリ申請
2. `SHOPEE_PARTNER_ID` / `SHOPEE_PARTNER_KEY` / `SHOPEE_SHOP_ID` / `SHOPEE_ACCESS_TOKEN` を設定
3. `shopee_api.py` の `DRY_RUN = False` に変更（十分なテスト後）
4. `create_item()` に承認済みデータを渡す実装を追加

⚠️ **本番連携前に必ず Shopee Open Platform の利用規約と出品ポリシーを確認してください。**
    """)
