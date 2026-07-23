# -*- coding: utf-8 -*-
"""
app.py — AI副業システム (Shopee専用) Streamlit Web UI
"""
import io
import csv
import json as _json
import datetime as _dt
import contextlib
import traceback
from pathlib import Path

import pandas as pd
import streamlit as st
import shopee_research
import dashboard
import shopee_mass_upload as _smu

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "outputs"
DATA_DIR = BASE_DIR / "data"

SHOPEE_COUNTRIES = ["Singapore", "Malaysia", "Taiwan", "Philippines", "Thailand", "Vietnam"]
SHOPEE_INPUT_FILE = DATA_DIR / "shopee_trend_input.csv"
SHOPEE_TEMPLATE_FILE = DATA_DIR / "shopee_trend_input_template.csv"
DRAFTS_FILE = OUTPUT_DIR / "shopee_listing_drafts.csv"

MASS_UPLOAD_EXTRA_FILE = DATA_DIR / "mass_upload_extra_data.json"

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
    task_map = {
        "shopee": shopee_research.run,
        "dashboard": dashboard.run,
    }
    runner = task_map.get(command)
    if runner is None:
        return False, f"unsupported command: {command}"
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            runner()
        return True, buf.getvalue()
    except Exception:
        traceback.print_exc(file=buf)
        return False, buf.getvalue()


def load_csv(filename: str) -> pd.DataFrame | None:
    path = OUTPUT_DIR / filename
    if not path.exists():
        return None
    df = pd.read_csv(path, encoding="utf-8-sig")
    return normalize_for_streamlit(df)


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


def _normalize_approved_column(df: pd.DataFrame) -> pd.DataFrame:
    if "approved" in df.columns:
        df["approved"] = (
            df["approved"]
            .fillna(False)
            .map(lambda x: str(x).strip().lower() in ("true", "1", "yes"))
            .astype(bool)
        )
    return df


def _normalize_object_value(value):
    """Convert object-like/nullable cell values into Streamlit/PyArrow-safe scalars."""
    if isinstance(value, (list, tuple, set, dict)):
        return _json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            return bytes(value).decode("utf-8")
        except Exception:
            return str(value)
    if pd.isna(value):
        return ""
    return value


def normalize_for_streamlit(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize bool/object columns before Streamlit render/export to avoid Arrow crashes."""
    safe_df = _normalize_approved_column(df.copy())

    for col in safe_df.columns:
        series = safe_df[col]
        if str(series.dtype) == "boolean":
            safe_df[col] = series.fillna(False).astype(bool)
        elif pd.api.types.is_object_dtype(series):
            safe_df[col] = series.map(_normalize_object_value)

    return safe_df


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
        if st.button(label, width="stretch", type="primary"):
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


def update_draft_csv(product_name: str, country: str, updates: dict) -> bool:
    """出品下書きCSVの特定行を更新する（承認/却下の書き込みに使用）"""
    if not DRAFTS_FILE.exists():
        return False
    df = pd.read_csv(DRAFTS_FILE, encoding="utf-8-sig")
    mask = (
        (df["product_name"].astype(str) == str(product_name)) &
        (df["country"].astype(str) == str(country))
    )
    if not mask.any():
        return False
    for col, val in updates.items():
        if col not in df.columns:
            df[col] = False if col == "approved" else ""
        if col == "approved":
            df = _normalize_approved_column(df)
            df.loc[mask, col] = bool(val)
        else:
            # Direct string assignment — no dtype coercion needed.
            df.loc[mask, col] = str(val)
    df.to_csv(DRAFTS_FILE, index=False, encoding="utf-8-sig")
    # Keep dashboard.csv in sync so the dashboard page reflects approvals immediately.
    _sync_dashboard_csv(product_name, updates)
    return True


def _sync_dashboard_csv(product_name: str, updates: dict) -> None:
    """dashboard.csv の対応行を shopee_listing_drafts.csv の変更に合わせて更新する"""
    dashboard_file = OUTPUT_DIR / "dashboard.csv"
    if not dashboard_file.exists():
        return
    rows: list[dict] = []
    fieldnames: list[str] = []
    with open(dashboard_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            if row.get("product_name", "") == str(product_name):
                for col, val in updates.items():
                    if col in row:
                        if col == "approved":
                            row[col] = "True" if val else "False"
                        else:
                            row[col] = str(val)
            rows.append(row)
    with open(dashboard_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def make_approved_csv_bytes(df: pd.DataFrame) -> bytes:
    """承認済み・非高リスクの行だけ CSV バイト列で返す"""
    safe_df = normalize_for_streamlit(df)
    approved = safe_df[
        safe_df["approved"] &
        (safe_df["risk_level"].astype(str).str.lower() != "high")
    ]
    buf = io.StringIO()
    approved.to_csv(buf, index=False, encoding="utf-8-sig")
    return buf.getvalue().encode("utf-8-sig")


def load_mass_upload_extra() -> dict:
    """mass_upload_extra_data.json を読み込む。存在しなければ空 dict を返す。"""
    if MASS_UPLOAD_EXTRA_FILE.exists():
        import json as _je
        try:
            with open(MASS_UPLOAD_EXTRA_FILE, encoding="utf-8") as f:
                return _je.load(f)
        except Exception:
            pass
    return {}


def save_mass_upload_extra(data: dict) -> None:
    """mass_upload_extra_data.json に保存する。"""
    import json as _js
    MASS_UPLOAD_EXTRA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MASS_UPLOAD_EXTRA_FILE, "w", encoding="utf-8") as f:
        _js.dump(data, f, ensure_ascii=False, indent=2)


def _extra_key(country: str, product_name: str) -> str:
    """extra_data の辞書キーを生成する。"""
    return f"{country}|{product_name}"


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
            "🗂️ Shopee一括アップロード形式",
            "✅ 出品準備チェックリスト",
            "💴 仕入れ・価格トラッカー",
            "🔍 自動リサーチ",
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
            st.dataframe(normalize_for_streamlit(risk_counts), width="stretch", hide_index=True)

    with col_r:
        st.subheader("🌍 国別内訳")
        if "country" in df.columns:
            country_counts = df["country"].value_counts().reset_index()
            country_counts.columns = ["国", "件数"]
            st.dataframe(normalize_for_streamlit(country_counts), width="stretch", hide_index=True)

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

    st.dataframe(normalize_for_streamlit(display_df), width="stretch", hide_index=True)


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

        submitted = st.form_submit_button("＋ リストに追加する", width="stretch", type="primary")

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
            width="stretch",
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
        if st.button("💾 変更を保存", width="stretch", type="primary"):
            if edited_df is not None and not edited_df.empty:
                clean = edited_df.dropna(subset=["product_name"]).reset_index(drop=True)
                save_shopee_input(clean)
                st.success(f"✅ {len(clean)} 件を保存しました。")
            else:
                save_shopee_input(pd.DataFrame(columns=SHOPEE_INPUT_COLUMNS))
                st.success("✅ データをクリアしました。")
    with btn_c2:
        if st.button("🔄 出品下書きを再生成", width="stretch"):
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
    st.title("📝 Shopee 出品下書き確認・承認")
    st.warning(
        "⚠️ **下書き確認専用です。** "
        "Shopeeへの出品は必ず人間が内容を確認・承認してから手動で行ってください。"
        "承認ボタンは出品下書きCSVを更新するだけです。自動出品は行いません。"
    )

    # ── ページ上部ツールバー ─────────────────────────────────
    tool_col1, tool_col2, tool_col3 = st.columns([2, 2, 1])
    with tool_col1:
        regen_button("🔄 下書きを再生成", "shopee", "shopee_listing_drafts.csv")
    with tool_col3:
        # ページ上部のクイックエクスポート
        full_df_for_export = load_csv("shopee_listing_drafts.csv")
        if full_df_for_export is not None:
            approved_count_export = len(
                full_df_for_export[
                    (full_df_for_export["approved"].astype(str).str.upper() == "TRUE") &
                    (full_df_for_export["risk_level"].astype(str).str.lower() != "high")
                ]
            )
            if approved_count_export > 0:
                csv_bytes = make_approved_csv_bytes(full_df_for_export)
                st.download_button(
                    label=f"📤 承認済み {approved_count_export}件 をエクスポート",
                    data=csv_bytes,
                    file_name=f"shopee_approved_{_dt.date.today().isoformat()}.csv",
                    mime="text/csv",
                    width="stretch",
                    type="primary",
                )
            else:
                st.caption("承認済み商品がありません")

    st.divider()

    df = load_csv("shopee_listing_drafts.csv")
    if df is None:
        st.warning("まだ下書きがありません。「📥 商品入力エディタ」でデータを追加してください。")
        st.stop()

    # ── フィルター ───────────────────────────────────────────
    filter_col1, filter_col2 = st.columns([2, 1])
    with filter_col1:
        risk_filter = st.multiselect(
            "リスクフィルター",
            options=["🟢 低リスク", "🟡 要確認", "🔴 高リスク"],
            default=["🟢 低リスク", "🟡 要確認", "🔴 高リスク"],
        )
    with filter_col2:
        status_filter = st.selectbox(
            "承認状態フィルター",
            options=["すべて", "未承認のみ", "承認済みのみ", "却下済みのみ"],
        )
    risk_map = {"🟢 低リスク": "low", "🟡 要確認": "medium", "🔴 高リスク": "high"}
    selected_risks = [risk_map[r] for r in risk_filter]
    df_view = df[df["risk_level"].astype(str).str.lower().isin(selected_risks)].copy()

    if status_filter == "未承認のみ":
        df_view = df_view[
            (df_view["approved"].astype(str).str.upper() != "TRUE") &
            (df_view["status"].astype(str).str.lower() != "rejected")
        ]
    elif status_filter == "承認済みのみ":
        df_view = df_view[df_view["approved"].astype(str).str.upper() == "TRUE"]
    elif status_filter == "却下済みのみ":
        df_view = df_view[df_view["status"].astype(str).str.lower() == "rejected"]

    approved_in_view = len(df_view[df_view["approved"].astype(str).str.upper() == "TRUE"])
    rejected_in_view = len(df_view[df_view["status"].astype(str).str.lower() == "rejected"])
    st.caption(f"表示: {len(df_view)} 件　｜　✅ 承認済み: {approved_in_view} 件　｜　🚫 却下済み: {rejected_in_view} 件")
    st.divider()

    for idx, row in df_view.iterrows():
        product_name = str(row.get("product_name", ""))
        country = str(row.get("country", ""))
        genre = row.get("genre", "")
        cost = row.get("cost_price_jpy", "")
        selling = row.get("selling_price_jpy", "")
        selling_usd = row.get("selling_price_usd", "")
        profit = row.get("profit_jpy", "")
        margin = row.get("profit_margin", "")
        min_price = row.get("min_price_no_loss_jpy", "")
        fee = row.get("fee_estimate_jpy", "")
        risk = str(row.get("risk_level", "")).lower()
        risk_reason = str(row.get("risk_reason", ""))
        category_sug = str(row.get("category_suggestion", ""))
        target_cust = str(row.get("target_customer", ""))
        shopee_title = str(row.get("shopee_title", ""))
        shopee_desc = str(row.get("shopee_description", ""))
        bullets_raw = str(row.get("bullet_points", ""))
        keywords_val = str(row.get("keywords", ""))
        selling_pts_raw = str(row.get("selling_points", ""))
        caution = str(row.get("caution_notes", ""))
        source_url = str(row.get("source_url", ""))
        approved = str(row.get("approved", "FALSE")).upper()
        status_val = str(row.get("status", "")).lower()
        is_rejected = status_val == "rejected"

        item_key = f"item_{idx}"
        confirm_key = f"confirm_approve_{item_key}"
        override_key = f"override_high_{item_key}"

        with st.container(border=True):

            # ── ヘッダー行 ─────────────────────────────────────
            h_col, r_col = st.columns([5, 2])
            with h_col:
                if approved == "TRUE":
                    st.markdown(f"### ✅ {product_name}")
                elif is_rejected:
                    st.markdown(f"### 🚫 ~~{product_name}~~")
                else:
                    st.markdown(f"### 🔲 {product_name}")
                st.caption(f"🌍 {country}  ｜  {genre}  ｜  カテゴリ候補: {category_sug}")
                if source_url and source_url != "nan":
                    st.markdown(f"[🔗 商品ページを開く]({source_url})")
            with r_col:
                st.markdown(f"**{risk_badge(risk)}**")
                if approved == "TRUE":
                    st.success("✅ 承認済み")
                elif is_rejected:
                    st.error("🚫 却下済み")
                else:
                    st.info("🔲 未承認")

            # ── 価格メトリクス ──────────────────────────────────
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
            m6.metric("手数料概算", f"¥{fee}", help="取引5%+サービス5%+決済2%")
            m7.metric("損益分岐価格", f"¥{min_price}", help="この価格を下回ると赤字")

            # ── リスク詳細 ──────────────────────────────────────
            if (risk_reason and
                    risk_reason not in ("nan", "特記事項なし（簡易チェックのみ。最終確認は人間が行うこと）")):
                with st.expander("⚠️ リスク詳細を見る"):
                    if risk == "high":
                        st.error(risk_reason)
                    else:
                        st.warning(risk_reason)

            st.markdown("---")

            # ── 出品コピータブ ───────────────────────────────────
            tab1, tab2, tab3 = st.tabs(["📋 出品コピー", "🎯 販売戦略", "⚠️ 注意事項"])

            with tab1:
                st.markdown("**英語タイトル（60文字以内）**")
                st.text_area(
                    "title",
                    value=shopee_title if shopee_title != "nan" else "",
                    height=60,
                    label_visibility="collapsed",
                    key=f"title_{item_key}",
                )
                if shopee_desc and shopee_desc != "nan":
                    st.markdown("**商品説明文**")
                    st.text_area(
                        "desc",
                        value=shopee_desc,
                        height=110,
                        label_visibility="collapsed",
                        key=f"desc_{item_key}",
                    )
                if bullets_raw and bullets_raw != "nan":
                    st.markdown("**箇条書きポイント**")
                    bullet_text = "\n".join(
                        b.strip() for b in bullets_raw.split("|") if b.strip()
                    )
                    st.text_area(
                        "bullets",
                        value=bullet_text,
                        height=130,
                        label_visibility="collapsed",
                        key=f"bullets_{item_key}",
                    )
                if keywords_val and keywords_val != "nan":
                    st.markdown("**検索キーワード**")
                    st.text_area(
                        "keywords",
                        value=keywords_val,
                        height=60,
                        label_visibility="collapsed",
                        key=f"kw_{item_key}",
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

            st.markdown("---")

            # ══ 承認・却下アクションエリア ══════════════════════════

            # 承認確認ダイアログ中
            if st.session_state.get(confirm_key):
                st.warning(
                    f"**「{product_name}」（{country}）を承認しますか？**\n\n"
                    "承認すると出品下書きCSVの `approved` 列が `TRUE` になり、"
                    "エクスポート対象になります。\n"
                    "Shopeeへの自動出品は行いません。"
                )
                yes_col, no_col = st.columns(2)
                with yes_col:
                    if st.button(
                        "✅ 承認を確定する",
                        key=f"confirm_yes_{item_key}",
                        width="stretch",
                        type="primary",
                    ):
                        ok = update_draft_csv(product_name, country, {
                            "approved": True,
                            "status": "approved",
                        })
                        st.session_state.pop(confirm_key, None)
                        if ok:
                            st.success(f"✅ 「{product_name}」を承認しました。")
                        else:
                            st.error("CSVの更新に失敗しました。")
                        st.rerun()
                with no_col:
                    if st.button(
                        "キャンセル",
                        key=f"confirm_no_{item_key}",
                        width="stretch",
                    ):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()

            # 承認済み → 取り消しボタン
            elif approved == "TRUE":
                undo_col, _ = st.columns([1, 2])
                with undo_col:
                    if st.button(
                        "↩️ 承認を取り消す",
                        key=f"undo_{item_key}",
                        width="stretch",
                    ):
                        update_draft_csv(product_name, country, {
                            "approved": False,
                            "status": "draft_pending_human_approval",
                        })
                        st.rerun()

            # 却下済み → 取り消しボタン
            elif is_rejected:
                restore_col, _ = st.columns([1, 2])
                with restore_col:
                    if st.button(
                        "↩️ 却下を取り消す",
                        key=f"restore_{item_key}",
                        width="stretch",
                    ):
                        update_draft_csv(product_name, country, {
                            "approved": False,
                            "status": "draft_pending_human_approval",
                        })
                        st.rerun()

            # 未承認・未却下 → メインアクションボタン
            else:
                if risk == "high":
                    st.error(
                        "🔴 **高リスク商品です。** 通常は承認できません。\n"
                        "強制承認する場合はチェックボックスをオンにしてください。"
                    )
                    allow_high = st.checkbox(
                        "⚠️ リスク内容を確認し、自己責任で強制承認する",
                        key=override_key,
                    )
                    can_approve = allow_high
                else:
                    can_approve = True

                action_col1, action_col2 = st.columns(2)

                with action_col1:
                    if st.button(
                        "✅ 承認する" if risk != "high" else "⚠️ 強制承認する",
                        key=f"approve_{item_key}",
                        width="stretch",
                        type="primary",
                        disabled=not can_approve,
                    ):
                        st.session_state[confirm_key] = True
                        st.rerun()

                with action_col2:
                    if st.button(
                        "❌ 却下する",
                        key=f"reject_{item_key}",
                        width="stretch",
                    ):
                        update_draft_csv(product_name, country, {
                            "approved": False,
                            "status": "rejected",
                        })
                        st.rerun()

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
        st.dataframe(normalize_for_streamlit(pd.DataFrame(rows)), width="stretch", hide_index=True)


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
            "👉「📝 出品下書き確認」ページで商品を **承認** するとここに表示されます。\n"
            "高リスク商品は承認してもエクスポートされません。"
        )
    else:
        st.subheader(f"📋 エクスポート対象商品（{exportable}件）")

        display_cols = [c for c in [
            "country", "genre", "product_name", "shopee_title",
            "selling_price_jpy", "selling_price_usd",
            "profit_jpy", "profit_margin", "risk_level",
        ] if c in approved_df.columns]
        st.dataframe(normalize_for_streamlit(approved_df[display_cols]), width="stretch", hide_index=True)

        # ── ① CSV ダウンロード（メインアクション）────────────────
        st.divider()
        st.subheader("⬇️ ダウンロード")
        st.caption(
            "承認はCSVへの記録のみです。ここからダウンロードしたCSVをもとに、"
            "Shopee Seller Centerで**手動出品**してください。"
        )

        dl_col1, dl_col2 = st.columns(2)

        with dl_col1:
            csv_buffer = io.StringIO()
            normalize_for_streamlit(approved_df).to_csv(csv_buffer, index=False, encoding="utf-8-sig")
            st.download_button(
                label="📄 承認済みCSVをダウンロード",
                data=csv_buffer.getvalue().encode("utf-8-sig"),
                file_name=f"shopee_approved_{_dt.date.today().isoformat()}.csv",
                mime="text/csv",
                width="stretch",
                type="primary",
            )
            st.caption("Shopee Seller Center での手動出品に使用してください")

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
                width="stretch",
            )
            st.caption("将来の Shopee Open Platform API 連携用（確認・編集してから使用）")

        # ── ② Shopeeへ直接出品（将来機能 / DRY_RUN=True の間は無効）─
        st.divider()
        st.subheader("🚀 Shopeeへ直接出品する（将来機能）")

        from shopee_api import DRY_RUN as _SHOPEE_DRY_RUN

        if _SHOPEE_DRY_RUN:
            st.warning(
                "**🔒 DRY_RUN = True のため、この機能は現在無効です。**\n\n"
                "Shopee Open Platform API の申請・設定が完了し、"
                "`shopee_api.py` の `DRY_RUN = False` に変更すると有効になります。\n\n"
                "現在はCSVダウンロード → Shopee Seller Centerでの手動出品のみ対応しています。"
            )
            st.button(
                "🚀 承認済み商品をShopeeへ出品する（現在無効）",
                disabled=True,
                width="stretch",
                help="shopee_api.py の DRY_RUN を False に変更すると有効になります",
            )
            st.caption(
                "⚠️ この機能を有効にする前に必ず: "
                "① Shopee Open Platform でアプリ申請 "
                "② API キーを環境変数に設定 "
                "③ 少量の商品でテスト出品を実施"
            )
        else:
            # DRY_RUN=False になったときの最終確認フロー
            st.error(
                "⚠️ **DRY_RUN = False です。** "
                "このボタンを押すと承認済み商品が実際に Shopee へ出品されます。"
            )
            publish_confirm_key = "confirm_publish_to_shopee"
            if st.session_state.get(publish_confirm_key):
                st.error(
                    f"**本当に {exportable} 件の商品を Shopee へ出品しますか？**\n\n"
                    "この操作は取り消せません。Shopee Seller Center でも確認できますが、"
                    "出品後は手動での削除が必要になります。"
                )
                pub_yes, pub_no = st.columns(2)
                with pub_yes:
                    if st.button(
                        f"✅ {exportable}件 を今すぐ出品する",
                        key="publish_yes",
                        width="stretch",
                        type="primary",
                    ):
                        from shopee_api import create_item as _create_item
                        results = []
                        for _, r in approved_df.iterrows():
                            res = _create_item({
                                "name": r.get("shopee_title", ""),
                                "description": r.get("shopee_description", ""),
                                "price": float(r.get("selling_price_usd", 0)),
                                "stock": 10,
                                "category_id": 0,
                                "images": [],
                                "logistics": [],
                            })
                            results.append(res)
                        st.session_state.pop(publish_confirm_key, None)
                        success = [r for r in results if not r.get("error")]
                        st.success(f"✅ {len(success)} 件の出品が完了しました。")
                with pub_no:
                    if st.button(
                        "キャンセル",
                        key="publish_no",
                        width="stretch",
                    ):
                        st.session_state.pop(publish_confirm_key, None)
                        st.rerun()
            else:
                if st.button(
                    f"🚀 承認済み {exportable}件 を Shopee へ出品する",
                    width="stretch",
                    type="primary",
                ):
                    st.session_state[publish_confirm_key] = True
                    st.rerun()

    if excluded > 0:
        st.divider()
        with st.expander(f"🔴 除外された高リスク商品 ({excluded}件)"):
            st.error("以下の商品は approved=TRUE ですが、高リスクのためエクスポートから除外しました。")
            excl_cols = [c for c in ["product_name", "risk_level", "risk_reason"] if c in rejected_df.columns]
            st.dataframe(normalize_for_streamlit(rejected_df[excl_cols]), width="stretch", hide_index=True)


# ══════════════════════════════════════════════════════════
# ✅ 出品準備チェックリスト
# ══════════════════════════════════════════════════════════
elif page == "✅ 出品準備チェックリスト":
    import json as _cjson

    CHECKLIST_FILE = DATA_DIR / "checklist_state.json"

    CHECKLIST_ITEMS = [
        {
            "key": "seller_account",
            "label": "Shopee セラーアカウントを作成した",
            "detail": (
                "Shopee Seller Center（https://seller.shopee.sg など）で "
                "セラーアカウントを登録してください。"
            ),
            "link": "https://seller.shopee.sg/",
            "link_label": "Shopee Seller Center を開く",
            "category": "アカウント設定",
        },
        {
            "key": "open_platform_app",
            "label": "Shopee Open Platform でアプリを作成した",
            "detail": (
                "Shopee Open Platform（https://open.shopee.com）で "
                "Partnerアカウントを作成し、アプリを登録してください。"
            ),
            "link": "https://open.shopee.com/",
            "link_label": "Shopee Open Platform を開く",
            "category": "アカウント設定",
        },
        {
            "key": "api_keys_added",
            "label": "APIキー（Partner ID / Partner Key）を環境変数に追加した",
            "detail": (
                "環境変数（.env など）に以下を登録してください:\n"
                "- SHOPEE_PARTNER_ID\n"
                "- SHOPEE_PARTNER_KEY\n"
                "- SHOPEE_SHOP_ID\n"
                "- SHOPEE_ACCESS_TOKEN"
            ),
            "link": None,
            "link_label": None,
            "category": "アカウント設定",
        },
        {
            "key": "test_product_added",
            "label": "テスト商品を「商品入力エディタ」で追加した",
            "detail": (
                "「📥 商品入力エディタ」ページで1件だけ商品を追加し、"
                "下書き生成・リスクチェック・利益計算を一通り確認してください。"
            ),
            "link": None,
            "link_label": None,
            "category": "テスト確認",
        },
        {
            "key": "risk_check_done",
            "label": "リスクチェックの内容を確認した",
            "detail": (
                "「📝 出品下書き確認」ページでリスク判定を確認しました。\n"
                "高リスク商品は強制承認チェックボックスをオンにしないと承認できません。"
            ),
            "link": None,
            "link_label": None,
            "category": "テスト確認",
        },
        {
            "key": "profit_calc_done",
            "label": "利益計算シミュレーターで採算を確認した",
            "detail": (
                "「💰 利益計算シミュレーター」で仕入れ価格・送料・販売価格を入力し、"
                "損益分岐点と利益率を確認してください。"
            ),
            "link": None,
            "link_label": None,
            "category": "テスト確認",
        },
        {
            "key": "export_done",
            "label": "承認済み商品をCSVエクスポートした",
            "detail": (
                "「📤 承認済みエクスポート」ページから承認済みCSVをダウンロードし、"
                "内容を確認しました。"
            ),
            "link": None,
            "link_label": None,
            "category": "テスト確認",
        },
        {
            "key": "dry_run_confirmed",
            "label": "DRY_RUN = True のまま（まだ本番出品しない）",
            "detail": (
                "shopee_api.py の DRY_RUN は True のまま維持してください。\n"
                "本番出品する準備ができたら、上記の全手順を完了してから "
                "True → False に変更します。"
            ),
            "link": None,
            "link_label": None,
            "category": "安全確認",
            "locked": True,
        },
    ]

    def load_checklist() -> dict:
        if CHECKLIST_FILE.exists():
            try:
                with open(CHECKLIST_FILE, encoding="utf-8") as f:
                    return _cjson.load(f)
            except Exception:
                pass
        return {item["key"]: False for item in CHECKLIST_ITEMS}

    def save_checklist(state: dict) -> None:
        CHECKLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CHECKLIST_FILE, "w", encoding="utf-8") as f:
            _cjson.dump(state, f, ensure_ascii=False, indent=2)

    checklist_state = load_checklist()

    st.title("✅ Shopee 出品準備チェックリスト")
    st.caption("本番出品前に全項目を確認してください。チェックは自動保存されます。")

    # DRY_RUN バッジ
    from shopee_api import DRY_RUN as _CL_DRY_RUN
    if _CL_DRY_RUN:
        st.error(
            "🔒 **DRY_RUN = True**　｜　現在、Shopeeへの自動出品は無効です。\n\n"
            "すべての承認・エクスポート操作はCSVへの記録のみです。"
            "実際の出品は Shopee Seller Center で手動で行ってください。"
        )
    else:
        st.success("🟢 DRY_RUN = False　｜　本番モードが有効です。出品ボタンが機能します。")

    st.divider()

    # 進捗バー
    total_items = len(CHECKLIST_ITEMS)
    checked_count = sum(1 for item in CHECKLIST_ITEMS if checklist_state.get(item["key"], False))
    progress = checked_count / total_items
    st.progress(progress, text=f"進捗: {checked_count} / {total_items} 項目完了")

    if checked_count == total_items:
        st.success("🎉 全項目完了！出品の準備が整いました。")
    st.divider()

    # カテゴリ別にグループ表示
    categories = []
    seen_cats = set()
    for item in CHECKLIST_ITEMS:
        cat = item["category"]
        if cat not in seen_cats:
            categories.append(cat)
            seen_cats.add(cat)

    cat_icons = {
        "アカウント設定": "🔑",
        "テスト確認": "🧪",
        "安全確認": "🛡️",
    }

    state_changed = False

    for cat in categories:
        cat_items = [i for i in CHECKLIST_ITEMS if i["category"] == cat]
        icon = cat_icons.get(cat, "📋")
        st.subheader(f"{icon} {cat}")

        for item in cat_items:
            current_val = checklist_state.get(item["key"], False)
            is_locked = item.get("locked", False)

            with st.container(border=True):
                cb_col, info_col = st.columns([1, 8])

                with cb_col:
                    if is_locked:
                        # DRY_RUN確認項目は常にチェック済み表示（変更不可）
                        st.markdown("🔒")
                        new_val = True
                    else:
                        new_val = st.checkbox(
                            "チェック",
                            value=current_val,
                            key=f"cl_{item['key']}",
                            label_visibility="collapsed",
                        )
                        if new_val != current_val:
                            checklist_state[item["key"]] = new_val
                            state_changed = True

                with info_col:
                    if current_val or is_locked:
                        st.markdown(f"**✅ ~~{item['label']}~~**")
                    else:
                        st.markdown(f"**🔲 {item['label']}**")

                    if item["detail"]:
                        st.caption(item["detail"])

                    if item.get("link"):
                        st.markdown(f"[🔗 {item['link_label']}]({item['link']})")

        st.write("")

    if state_changed:
        save_checklist(checklist_state)
        st.rerun()

    st.divider()

    # リセットボタン
    reset_col, _ = st.columns([1, 3])
    with reset_col:
        if st.button("🔄 チェックをリセット", width="stretch"):
            blank = {item["key"]: False for item in CHECKLIST_ITEMS}
            save_checklist(blank)
            st.rerun()

    # 次のステップ案内
    st.divider()
    st.subheader("📋 本番出品に向けた次のステップ")
    st.markdown("""
1. **上記のチェックリストを全て完了する**
2. **Shopee Open Platform API の審査を通過する**（数日〜数週間かかる場合があります）
3. **`shopee_api.py` の `DRY_RUN = True` → `False` に変更する**
4. **「📤 承認済みエクスポート」ページの「Shopeeへ出品する」ボタンが有効になる**
5. **少量（1〜3件）でテスト出品して動作確認する**
6. **問題なければ本格運用開始**

> ⚠️ DRY_RUN を False にする前に、必ず API の動作テストを行ってください。
    """)


# ══════════════════════════════════════════════════════════
# 💴 仕入れ・価格トラッカー
# ══════════════════════════════════════════════════════════
elif page == "💴 仕入れ・価格トラッカー":
    TRACKER_FILE = DATA_DIR / "product_cost_tracker.csv"

    TRACKER_COLUMNS = [
        "product_name", "country",
        "supplier_name", "supplier_url",
        "actual_purchase_price_jpy", "domestic_shipping_jpy",
        "packaging_cost_jpy", "export_forwarding_fee_jpy",
        "international_shipping_estimate_jpy",
        "shopee_fee_rate", "target_profit_margin",
        "minimum_selling_price", "recommended_selling_price",
        "expected_profit", "expected_profit_margin",
        "stock_status", "last_checked_date", "notes",
    ]

    STOCK_OPTIONS = ["in_stock", "low_stock", "out_of_stock", "unknown"]
    STOCK_LABELS = {
        "in_stock":    "✅ 在庫あり",
        "low_stock":   "⚠️ 残りわずか",
        "out_of_stock":"❌ 在庫なし",
        "unknown":     "❓ 不明",
    }

    def load_tracker() -> pd.DataFrame:
        if TRACKER_FILE.exists():
            df = pd.read_csv(TRACKER_FILE, encoding="utf-8-sig")
            for col in TRACKER_COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            return df[TRACKER_COLUMNS]
        # 下書きCSVから商品名・国だけ引き継いで初期化
        draft = load_csv("shopee_listing_drafts.csv")
        if draft is not None and len(draft) > 0:
            rows = []
            for _, r in draft.iterrows():
                rows.append({
                    "product_name": r.get("product_name", ""),
                    "country": r.get("country", ""),
                    "supplier_name": "",
                    "supplier_url": "",
                    "actual_purchase_price_jpy": r.get("cost_price_jpy", 0),
                    "domestic_shipping_jpy": r.get("shipping_cost_jpy", 0),
                    "packaging_cost_jpy": 0,
                    "export_forwarding_fee_jpy": 0,
                    "international_shipping_estimate_jpy": 0,
                    "shopee_fee_rate": 0.12,
                    "target_profit_margin": 0.20,
                    "minimum_selling_price": 0,
                    "recommended_selling_price": 0,
                    "expected_profit": 0,
                    "expected_profit_margin": 0.0,
                    "stock_status": "unknown",
                    "last_checked_date": "",
                    "notes": "",
                })
            return pd.DataFrame(rows, columns=TRACKER_COLUMNS)
        return pd.DataFrame(columns=TRACKER_COLUMNS)

    def recalc_row(row: dict) -> dict:
        """仕入れコストと手数料から各種価格・利益を再計算する"""
        cost = (
            float(row.get("actual_purchase_price_jpy") or 0)
            + float(row.get("domestic_shipping_jpy") or 0)
            + float(row.get("packaging_cost_jpy") or 0)
            + float(row.get("export_forwarding_fee_jpy") or 0)
            + float(row.get("international_shipping_estimate_jpy") or 0)
        )
        fee_rate = float(row.get("shopee_fee_rate") or 0.12)
        margin = float(row.get("target_profit_margin") or 0.20)
        denom_min = 1 - fee_rate
        denom_rec = 1 - fee_rate - margin
        min_price = round(cost / denom_min) if denom_min > 0 else 0
        rec_price = round(cost / denom_rec) if denom_rec > 0 else 0
        exp_profit = round(rec_price * (1 - fee_rate) - cost)
        exp_margin = (exp_profit / rec_price) if rec_price > 0 else 0.0
        return {
            **row,
            "minimum_selling_price": min_price,
            "recommended_selling_price": rec_price,
            "expected_profit": exp_profit,
            "expected_profit_margin": round(exp_margin, 4),
        }

    def save_tracker(df: pd.DataFrame) -> None:
        TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(TRACKER_FILE, index=False, encoding="utf-8-sig")

    # ── 初期ロード ───────────────────────────────────────────
    if "tracker_df" not in st.session_state:
        st.session_state["tracker_df"] = load_tracker()

    tracker_df: pd.DataFrame = st.session_state["tracker_df"]

    # ── タイトルと操作ボタン（上部固定） ────────────────────
    st.title("💴 仕入れ・価格トラッカー")
    st.caption(
        "商品ごとの実際の仕入れコスト・送料・利益目標を管理します。"
        "承認・出品とは独立しており、Shopeeへの出品は行いません。"
    )

    top_col1, top_col2, top_col3 = st.columns([2, 2, 1])
    save_clicked = top_col1.button("💾 すべて保存", type="primary", width="stretch")
    recalc_clicked = top_col2.button("🔄 利益を再計算してから保存", width="stretch")
    reload_clicked = top_col3.button("↩️ 再読み込み", width="stretch")

    if reload_clicked:
        st.session_state.pop("tracker_df", None)
        st.rerun()

    if recalc_clicked or save_clicked:
        # 保存前に再計算を実行（recalc_clicked の場合のみ計算、save_clicked は現状保存）
        rows_out = []
        for _, r in tracker_df.iterrows():
            rows_out.append(recalc_row(r.to_dict()) if recalc_clicked else r.to_dict())
        tracker_df = pd.DataFrame(rows_out, columns=TRACKER_COLUMNS)
        st.session_state["tracker_df"] = tracker_df
        save_tracker(tracker_df)
        st.success("✅ 保存しました。")
        st.rerun()

    if len(tracker_df) == 0:
        st.info(
            "データがありません。\n\n"
            "「📥 商品入力エディタ」で商品を追加し、下書きを生成すると"
            "自動的にここに読み込まれます。"
        )
        st.stop()

    # ── サマリーバー ─────────────────────────────────────────
    low_margin_count = 0
    stock_warn_count = 0
    for _, r in tracker_df.iterrows():
        try:
            em = float(r.get("expected_profit_margin") or 0)
            tgt = float(r.get("target_profit_margin") or 0.20)
            if em > 0 and em < tgt:
                low_margin_count += 1
        except Exception:
            pass
        if str(r.get("stock_status", "")).lower() in ("out_of_stock", "unknown"):
            stock_warn_count += 1

    s1, s2, s3 = st.columns(3)
    s1.metric("商品数", len(tracker_df))
    s2.metric("⚠️ 利益率不足", low_margin_count, delta=None)
    s3.metric("❌ 在庫要確認", stock_warn_count, delta=None)

    if low_margin_count > 0:
        st.warning(f"⚠️ {low_margin_count} 件の商品が目標利益率を下回っています。各商品カードを確認してください。")
    if stock_warn_count > 0:
        st.error(f"❌ {stock_warn_count} 件の商品で在庫が「在庫なし」または「不明」です。")

    st.divider()

    # ── 商品カード（1件ずつ） ────────────────────────────────
    updated_rows = []

    for idx, row in tracker_df.iterrows():
        r = row.to_dict()
        pname = str(r.get("product_name", f"商品 {idx+1}"))
        country = str(r.get("country", ""))
        em = float(r.get("expected_profit_margin") or 0)
        tgt = float(r.get("target_profit_margin") or 0.20)
        ss = str(r.get("stock_status", "unknown")).lower()

        # ヘッダー警告アイコン
        warn_icons = ""
        if em > 0 and em < tgt:
            warn_icons += " ⚠️利益率不足"
        if ss in ("out_of_stock", "unknown"):
            warn_icons += " ❌在庫要確認"

        with st.expander(f"{'📦' if not warn_icons else '⚠️'} {pname}（{country}）{warn_icons}", expanded=(bool(warn_icons))):

            # ── 警告バナー ───────────────────────────────────
            if em > 0 and em < tgt:
                st.warning(
                    f"利益率 **{em*100:.1f}%** が目標 **{tgt*100:.0f}%** を下回っています。"
                    "仕入れ価格・販売価格を見直してください。"
                )
            if ss == "out_of_stock":
                st.error("❌ この商品は在庫なし（out_of_stock）です。出品前に在庫を確保してください。")
            elif ss == "unknown":
                st.warning("❓ 在庫状況が不明です。仕入れ先を確認してください。")

            # ── 仕入れ先 ─────────────────────────────────────
            st.markdown("#### 🏪 仕入れ先")
            sup_col1, sup_col2 = st.columns(2)
            r["supplier_name"] = sup_col1.text_input(
                "仕入れ先名",
                value=str(r.get("supplier_name") or ""),
                key=f"sup_name_{idx}",
            )
            r["supplier_url"] = sup_col2.text_input(
                "仕入れ先URL",
                value=str(r.get("supplier_url") or ""),
                key=f"sup_url_{idx}",
                placeholder="https://",
            )

            # ── コスト内訳 ────────────────────────────────────
            st.markdown("#### 💴 コスト内訳（円）")
            c1, c2 = st.columns(2)
            r["actual_purchase_price_jpy"] = c1.number_input(
                "実際の仕入れ価格（円）",
                min_value=0, step=100,
                value=int(float(r.get("actual_purchase_price_jpy") or 0)),
                key=f"purchase_{idx}",
            )
            r["domestic_shipping_jpy"] = c2.number_input(
                "国内送料（円）",
                min_value=0, step=50,
                value=int(float(r.get("domestic_shipping_jpy") or 0)),
                key=f"dom_ship_{idx}",
            )
            c3, c4 = st.columns(2)
            r["packaging_cost_jpy"] = c3.number_input(
                "梱包材料費（円）",
                min_value=0, step=50,
                value=int(float(r.get("packaging_cost_jpy") or 0)),
                key=f"pack_{idx}",
            )
            r["export_forwarding_fee_jpy"] = c4.number_input(
                "輸出代行手数料（円）",
                min_value=0, step=100,
                value=int(float(r.get("export_forwarding_fee_jpy") or 0)),
                key=f"fwd_{idx}",
            )
            r["international_shipping_estimate_jpy"] = st.number_input(
                "国際送料概算（円）",
                min_value=0, step=100,
                value=int(float(r.get("international_shipping_estimate_jpy") or 0)),
                key=f"intl_ship_{idx}",
            )

            total_cost = (
                float(r["actual_purchase_price_jpy"])
                + float(r["domestic_shipping_jpy"])
                + float(r["packaging_cost_jpy"])
                + float(r["export_forwarding_fee_jpy"])
                + float(r["international_shipping_estimate_jpy"])
            )
            st.info(f"**合計コスト: ¥{round(total_cost):,}**")

            # ── 利益目標 ──────────────────────────────────────
            st.markdown("#### 🎯 利益目標設定")
            m1, m2 = st.columns(2)
            fee_rate_pct = m1.number_input(
                "Shopee手数料率（%）",
                min_value=0.0, max_value=50.0, step=0.5,
                value=round(float(r.get("shopee_fee_rate") or 0.12) * 100, 1),
                key=f"fee_{idx}",
                help="取引手数料＋サービス料＋決済手数料の合計。通常10〜15%",
            )
            r["shopee_fee_rate"] = fee_rate_pct / 100.0
            tgt_pct = m2.number_input(
                "目標利益率（%）",
                min_value=0.0, max_value=80.0, step=1.0,
                value=round(float(r.get("target_profit_margin") or 0.20) * 100, 1),
                key=f"tgt_{idx}",
            )
            r["target_profit_margin"] = tgt_pct / 100.0

            # ── 計算結果（読み取り専用） ───────────────────────
            recalced = recalc_row(r)
            r["minimum_selling_price"] = recalced["minimum_selling_price"]
            r["recommended_selling_price"] = recalced["recommended_selling_price"]
            r["expected_profit"] = recalced["expected_profit"]
            r["expected_profit_margin"] = recalced["expected_profit_margin"]

            st.markdown("#### 📊 計算結果")
            res1, res2, res3, res4 = st.columns(4)
            res1.metric("損益分岐価格", f"¥{r['minimum_selling_price']:,}", help="この価格以上で売れば赤字にならない")
            res2.metric("推奨販売価格", f"¥{r['recommended_selling_price']:,}", help="目標利益率を達成する価格")
            res3.metric("想定利益", f"¥{r['expected_profit']:,}")
            margin_pct = r["expected_profit_margin"] * 100
            if margin_pct < tgt_pct and margin_pct > 0:
                res4.metric("想定利益率", f"{margin_pct:.1f}%", delta=f"-{tgt_pct - margin_pct:.1f}%")
            else:
                res4.metric("想定利益率", f"{margin_pct:.1f}%")

            # ── 在庫・その他 ──────────────────────────────────
            st.markdown("#### 📦 在庫・メモ")
            stk_col, date_col = st.columns(2)

            current_stock = str(r.get("stock_status", "unknown")).lower()
            if current_stock not in STOCK_OPTIONS:
                current_stock = "unknown"
            stock_idx = STOCK_OPTIONS.index(current_stock)
            selected_stock = stk_col.selectbox(
                "在庫状況",
                options=STOCK_OPTIONS,
                index=stock_idx,
                format_func=lambda x: STOCK_LABELS.get(x, x),
                key=f"stock_{idx}",
            )
            r["stock_status"] = selected_stock

            r["last_checked_date"] = date_col.text_input(
                "最終確認日",
                value=str(r.get("last_checked_date") or ""),
                key=f"date_{idx}",
                placeholder="例: 2026-07-09",
            )

            r["notes"] = st.text_area(
                "メモ・備考",
                value=str(r.get("notes") or ""),
                height=80,
                key=f"notes_{idx}",
                placeholder="気づいた点・交渉結果・代替仕入れ先など自由に記入",
            )

        updated_rows.append(r)

    # セッションにリアルタイム反映
    st.session_state["tracker_df"] = pd.DataFrame(updated_rows, columns=TRACKER_COLUMNS)

    st.divider()
    bot_col1, bot_col2, _ = st.columns([2, 2, 1])
    save2 = bot_col1.button("💾 すべて保存（下部）", type="primary", width="stretch")
    recalc2 = bot_col2.button("🔄 再計算して保存（下部）", width="stretch")

    if save2 or recalc2:
        rows_out = []
        for r2 in updated_rows:
            rows_out.append(recalc_row(r2) if recalc2 else r2)
        final_df = pd.DataFrame(rows_out, columns=TRACKER_COLUMNS)
        st.session_state["tracker_df"] = final_df
        save_tracker(final_df)
        st.success("✅ 保存しました。")
        st.rerun()


# ══════════════════════════════════════════════════════════
# 🔍 自動リサーチ
# ══════════════════════════════════════════════════════════
elif page == "🔍 自動リサーチ":
    import auto_research as _ar

    COUNTRIES_ALL = ["Singapore", "Malaysia", "Taiwan", "Philippines", "Thailand", "Vietnam"]
    SEASON_LABELS = {"spring": "🌸 春", "summer": "☀️ 夏", "autumn": "🍂 秋", "winter": "❄️ 冬"}
    SCORE_DIMS = [
        ("score_overseas_demand",  "海外需要"),
        ("score_japan_uniqueness", "日本独自性"),
        ("score_shipping_ease",    "配送しやすさ"),
        ("score_regulation_risk",  "規制リスク（低い=良）"),
        ("score_profit_potential", "利益ポテンシャル"),
    ]

    def _score_bar(val: int, max_val: int = 5, invert: bool = False) -> str:
        effective = (max_val + 1 - val) if invert else val
        filled = "●" * effective
        empty  = "○" * (max_val - effective)
        return filled + empty

    st.title("🔍 自動商品リサーチ")
    st.caption(
        "日本商品データベース（60+件）から海外Shopeeで売れる商品候補を自動スコアリング。"
        "高リスクカテゴリ（食品・化粧品・医薬品・電池・液体など）は自動除外されます。"
        "Shopeeへの出品は行いません。DRY_RUN=True。"
    )

    # ── 現在の季節・イベント情報 ─────────────────────────────
    current_season = _ar.get_current_season()
    events = _ar.get_seasonal_events()
    season_icon = SEASON_LABELS.get(current_season, current_season)
    info_col, _ = st.columns([3, 1])
    with info_col:
        event_str = "、".join(events) if events else "なし"
        st.info(f"**現在の季節: {season_icon}**　｜　今月のイベント: {event_str}")

    st.divider()

    # ── 検索フィルター ────────────────────────────────────────
    st.subheader("🎛️ リサーチ条件")

    kw_col, market_col = st.columns(2)
    with kw_col:
        keyword_input = st.text_input(
            "キーワード（任意・カンマ区切り）",
            placeholder="例: stationery, kitchen, bento",
            help="空欄の場合は全商品が対象になります",
        )
        keywords = [k.strip() for k in keyword_input.split(",") if k.strip()]

    with market_col:
        target_countries = st.multiselect(
            "対象市場",
            options=COUNTRIES_ALL,
            default=["Singapore", "Taiwan", "Malaysia"],
        )

    opt_col1, opt_col2, opt_col3 = st.columns(3)
    with opt_col1:
        season_override = st.selectbox(
            "季節（変更可）",
            options=["自動検出", "spring", "summer", "autumn", "winter"],
            format_func=lambda x: "🔄 自動検出" if x == "自動検出" else SEASON_LABELS.get(x, x),
        )
        season_val = None if season_override == "自動検出" else season_override

    with opt_col2:
        min_score = st.slider("最低スコア", min_value=0, max_value=90, value=60, step=5)

    with opt_col3:
        target_margin_pct = st.number_input(
            "目標利益率（%）", min_value=10, max_value=60, value=30, step=5
        )

    n_results = st.slider("最大表示件数", min_value=5, max_value=40, value=15, step=5)

    st.divider()

    # ── リサーチ実行ボタン ────────────────────────────────────
    run_col, clear_col = st.columns([3, 1])
    with run_col:
        run_research = st.button(
            "🔍 新しい商品アイデアを探す",
            type="primary",
            width="stretch",
        )
    with clear_col:
        clear_btn = st.button("🗑️ 結果をクリア", width="stretch")

    if clear_btn:
        st.session_state.pop("research_results", None)
        st.session_state.pop("research_selected", None)
        st.rerun()

    if run_research:
        with st.spinner("商品データベースをスコアリング中..."):
            results = _ar.run_research(
                keywords=keywords,
                countries=target_countries,
                min_score=min_score,
                season_override=season_val,
                target_margin=target_margin_pct / 100,
                n_results=n_results,
            )
        _ar.save_research_results(results)
        st.session_state["research_results"] = results
        st.session_state["research_selected"] = {}
        st.success(f"✅ {len(results)} 件の商品候補が見つかりました。")
        st.rerun()

    # ── 結果表示 ──────────────────────────────────────────────
    results: list[dict] = st.session_state.get("research_results") or _ar.load_research_results()

    if not results:
        st.info(
            "まだリサーチ結果がありません。\n\n"
            "上の条件を設定して「🔍 新しい商品アイデアを探す」を押してください。"
        )
        st.stop()

    if "research_selected" not in st.session_state:
        st.session_state["research_selected"] = {}

    selected_map: dict = st.session_state["research_selected"]

    st.subheader(f"📊 リサーチ結果（{len(results)} 件）")

    # 全選択/全解除
    sel_all_col, desel_all_col, _ = st.columns([1, 1, 3])
    with sel_all_col:
        if st.button("☑️ 全選択", width="stretch"):
            for i, r in enumerate(results):
                selected_map[i] = True
            st.session_state["research_selected"] = selected_map
            st.rerun()
    with desel_all_col:
        if st.button("□ 全解除", width="stretch"):
            st.session_state["research_selected"] = {}
            st.rerun()

    st.divider()

    for i, product in enumerate(results):
        score = product.get("score", 0)
        name  = product.get("product_name_ja", "")
        genre = product.get("genre", "")
        trend = product.get("trend_reason", "")
        countries_list = ", ".join(product.get("countries", []))
        selling_price = product.get("selling_price_jpy", 0)
        profit = product.get("profit_jpy", 0)
        margin = product.get("profit_margin_pct", 0)
        cost   = product.get("typical_cost_jpy", 0)
        ship   = product.get("typical_shipping_jpy", 0)
        weight = product.get("typical_weight_g", 0)

        # スコアバッジ色
        if score >= 80:
            score_badge = f"🟢 **{score}点**"
        elif score >= 65:
            score_badge = f"🟡 **{score}点**"
        else:
            score_badge = f"🔴 **{score}点**"

        is_selected = selected_map.get(i, False)
        header_prefix = "✅" if is_selected else "🔲"

        with st.container(border=True):
            hdr_col, score_col, chk_col = st.columns([5, 2, 1])
            with hdr_col:
                st.markdown(f"#### {header_prefix} {name}")
                st.caption(f"ジャンル: {genre}　｜　推奨市場: {countries_list}")
            with score_col:
                st.markdown(f"総合スコア: {score_badge}")
            with chk_col:
                new_val = st.checkbox(
                    "選択",
                    value=is_selected,
                    key=f"sel_{i}",
                    label_visibility="collapsed",
                )
                if new_val != is_selected:
                    selected_map[i] = new_val
                    st.session_state["research_selected"] = selected_map
                    st.rerun()

            # 価格・利益メトリクス
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("仕入れ目安", f"¥{int(cost):,}")
            m2.metric("国際送料目安", f"¥{int(ship):,}")
            m3.metric("推奨販売価格", f"¥{int(selling_price):,}")
            m4.metric("想定利益", f"¥{int(profit):,}")
            m5.metric("利益率", f"{margin:.1f}%")

            # トレンド理由
            st.markdown(f"💡 **トレンド理由:** {trend}")
            st.caption(f"🎯 ターゲット顧客: {product.get('target_customer', '')}")
            st.caption(f"📦 重量目安: {weight}g　｜　季節: {', '.join(product.get('seasons', ['all']))}")

            # 5軸スコア詳細
            with st.expander("📊 スコア内訳を見る"):
                for dim_key, dim_label in SCORE_DIMS:
                    val = product.get(dim_key, 3)
                    invert = "regulation" in dim_key
                    bar = _score_bar(val, invert=invert)
                    st.markdown(f"**{dim_label}**: {bar} ({val}/5)")

        st.write("")

    # ── 下書き生成セクション ──────────────────────────────────
    st.divider()
    selected_indices = [i for i, v in selected_map.items() if v]
    selected_products = [results[i] for i in selected_indices if i < len(results)]
    n_selected = len(selected_products)

    st.subheader(f"📝 下書き生成（{n_selected} 件選択中）")

    if n_selected == 0:
        st.info("商品カードのチェックボックスで下書きにする商品を選んでください。")
    else:
        draft_country_col, draft_margin_col = st.columns(2)
        with draft_country_col:
            draft_countries = st.multiselect(
                "出品する国（空欄=商品ごとの推奨国）",
                options=COUNTRIES_ALL,
                default=[],
                help="空欄にすると各商品の推奨国に合わせて自動的に国を選択します",
            )
        with draft_margin_col:
            draft_margin_pct = st.number_input(
                "下書き目標利益率（%）", min_value=10, max_value=60, value=30, step=5,
                key="draft_margin",
            )

        gen_col, _ = st.columns([2, 3])
        with gen_col:
            if st.button(
                f"📝 選択した {n_selected} 件の下書きを生成する",
                type="primary",
                width="stretch",
            ):
                with st.spinner("出品下書きを生成中..."):
                    drafts = _ar.generate_drafts_from_research(
                        selected_products=selected_products,
                        countries=draft_countries,
                        target_margin=draft_margin_pct / 100,
                    )
                    added, skipped = _ar.append_drafts_to_csv(drafts)

                if added > 0:
                    st.success(
                        f"✅ **{added} 件の下書きを生成しました。**\n\n"
                        f"「📝 出品下書き確認」ページで内容を確認・承認してください。"
                        + (f"\n（{skipped} 件は既存データと重複したためスキップ）" if skipped else "")
                    )
                else:
                    st.warning(
                        f"⚠️ 選択した商品はすでに下書きに存在します（{skipped} 件スキップ）。\n\n"
                        "「📝 出品下書き確認」ページを確認してください。"
                    )

        # 将来の出品ボタン（DRY_RUN=True の間は無効）
        st.divider()
        st.caption("━━ 将来機能（現在は無効）━━")
        from shopee_api import DRY_RUN as _RES_DRY_RUN
        st.button(
            "🚀 承認済み商品をShopeeへ出品する（DRY_RUN=True のため無効）",
            disabled=True,
            width="stretch",
            help="shopee_api.py の DRY_RUN=False に変更すると有効になります。現在は出品しません。",
        )
        if _RES_DRY_RUN:
            st.caption("🔒 DRY_RUN=True — Shopeeへの自動出品は無効です。すべての操作はCSVへの記録のみです。")



# ══════════════════════════════════════════════════════════
# 🗂️ Shopee一括アップロード形式エクスポート
# ══════════════════════════════════════════════════════════
elif page == "🗂️ Shopee一括アップロード形式":
    import json as _mu_json

    st.title("🗂️ Shopee 一括アップロード形式 CSV エクスポート")
    st.warning(
        "⚠️ **このページは内部CSV（「📤 承認済みエクスポート」）とは別のShopee公式フォーマットです。**\n\n"
        "Shopee Seller Center の「一括アップロード」機能で使えるCSVを生成します。\n"
        "**カテゴリID・商品画像URL・重量・物流チャンネルは自動入力できません。**\n"
        "各商品カードから手動で入力してください。出品は行いません。"
    )

    df_all = load_csv("shopee_listing_drafts.csv")
    if df_all is None:
        st.info("まだデータがありません。「📥 商品入力エディタ」でデータを追加して下書きを生成してください。")
        st.stop()

    # 承認済み・低リスクのみ
    df_eligible = df_all[
        (df_all["approved"].astype(str).str.upper() == "TRUE") &
        (df_all["risk_level"].astype(str).str.lower() != "high")
    ].copy().reset_index(drop=True)

    if df_eligible.empty:
        st.info(
            "一括アップロード対象の商品がありません。\n\n"
            "👉「📝 出品下書き確認」ページで **承認** された低リスク商品がここに表示されます。"
        )
        st.stop()

    # ── 国別フィルター ────────────────────────────────────────
    available_countries = sorted(df_eligible["country"].dropna().unique().tolist())
    if not available_countries:
        st.warning("承認済み商品に対象国が設定されていません。")
        st.stop()

    selected_country = st.selectbox(
        "🌍 出品先の国を選択",
        options=available_countries,
        help="国ごとに別々のCSVを生成します。Shopeeの各国 Seller Center にアップロードしてください。",
    )
    currency = _smu.COUNTRY_CURRENCY.get(selected_country, "USD")
    st.caption(
        f"通貨: **{currency}**　｜　"
        f"参考為替レート: 1 {currency} ≈ ¥{_smu.APPROX_JPY_PER_LOCAL.get(currency, 0):.1f}"
        "（概算。最新レートで必ず確認してください）"
    )

    df_country = df_eligible[
        df_eligible["country"].astype(str) == selected_country
    ].copy().reset_index(drop=True)

    if df_country.empty:
        st.info(f"{selected_country} に承認済みの低リスク商品がありません。")
        st.stop()

    st.divider()

    # ── extra データロード ────────────────────────────────────
    if "mu_extra_data" not in st.session_state:
        st.session_state["mu_extra_data"] = load_mass_upload_extra()
    extra_data: dict = st.session_state["mu_extra_data"]

    # ── 商品カード（1件ずつ入力フォーム） ────────────────────
    st.subheader(f"📋 {selected_country} の商品一覧（{len(df_country)} 件）")
    st.caption(
        "各商品カードを開いて必須フィールドを入力してください。\n"
        "すべての必須項目が入力された商品のみCSVに含まれます。"
    )

    # 全商品の検証結果をまとめて保持
    valid_rows: list[dict] = []
    all_errors: dict[str, list[str]] = {}

    for idx, draft_row in df_country.iterrows():
        product_name = str(draft_row.get("product_name", f"商品 {idx+1}"))
        e_key = _extra_key(selected_country, product_name)
        saved_extra = extra_data.get(e_key, {})
        extra = _smu.MassUploadExtra.from_dict(saved_extra)

        # 参考現地通貨価格を計算（まだ入力がない場合のデフォルト値として）
        price_jpy = float(draft_row.get("selling_price_jpy") or 0)
        suggested_price = _smu.suggest_local_price(price_jpy, selected_country)
        if extra.price_local <= 0 and suggested_price > 0:
            extra.price_local = suggested_price

        # バリデーション（入力前の初期状態でも実行）
        result = _smu.validate_product(draft_row, extra)
        all_errors[product_name] = result.errors

        # カードヘッダー：バリデーション状態を表示
        status_icon = "✅" if result.is_valid else f"⚠️ ({len(result.errors)}件の未入力)"
        category_hint = str(draft_row.get("category_suggestion", ""))
        source_url = str(draft_row.get("source_url", ""))

        with st.expander(
            f"{status_icon} {product_name}",
            expanded=(not result.is_valid),
        ):
            # 既存情報の参照表示
            ref_col1, ref_col2 = st.columns(2)
            with ref_col1:
                st.markdown(f"**カテゴリ候補（参考）:** {category_hint}")
                st.caption("※ 参考のみ。正式なカテゴリIDは下の入力欄に別途入力してください。")
            with ref_col2:
                st.markdown(f"**推奨販売価格:** ¥{int(price_jpy):,}")
                st.caption(
                    f"現地通貨換算参考値: {currency} {suggested_price:.2f}"
                    "（概算。最新レートで確認すること）"
                )
            if source_url and source_url not in ("nan", ""):
                st.markdown(f"[🔗 仕入れ先URL（参照用）]({source_url})")

            st.markdown("---")

            # ── 必須フィールド入力 ──────────────────────────────
            st.markdown("#### 🔴 必須フィールド（未入力の場合エクスポート不可）")

            f_col1, f_col2 = st.columns(2)
            with f_col1:
                new_category_id = st.text_input(
                    "Shopee カテゴリID ＊",
                    value=extra.category_id,
                    key=f"mu_cat_{idx}",
                    placeholder="例: 11042（Shopee Seller Center で確認）",
                    help=(
                        "Shopee Seller Center の「カテゴリ管理」または "
                        "Shopee Open Platform API で確認してください。"
                    ),
                )
            with f_col2:
                new_price_local = st.number_input(
                    f"販売価格（{currency}）＊",
                    min_value=0.0,
                    value=float(extra.price_local),
                    step=0.5 if currency in ("SGD", "MYR") else 1.0,
                    format="%.2f" if currency in ("SGD", "MYR") else "%.0f",
                    key=f"mu_price_{idx}",
                    help=f"参考換算値: {currency} {suggested_price:.2f}（概算・要確認）",
                )

            new_main_image = st.text_input(
                "メイン商品画像 URL ＊",
                value=extra.main_image_url,
                key=f"mu_img1_{idx}",
                placeholder="https://（商品画像をアップロードしたURLを入力）",
                help="Shopee Mass Upload には最低1枚の商品画像URLが必須です。",
            )

            w_col, lc_col = st.columns(2)
            with w_col:
                new_weight = st.number_input(
                    "重量 kg ＊",
                    min_value=0.0,
                    value=float(extra.weight_kg),
                    step=0.05,
                    format="%.3f",
                    key=f"mu_weight_{idx}",
                    help="梱包後の総重量（商品＋梱包材）をkg単位で入力",
                )
            with lc_col:
                new_stock = st.number_input(
                    "在庫数 ＊",
                    min_value=0,
                    value=int(extra.stock_qty),
                    step=1,
                    key=f"mu_stock_{idx}",
                    help="Shopeeに登録する在庫数（実在庫を確認してから入力）",
                )

            new_logistic = st.text_input(
                "物流チャンネル ＊",
                value=extra.logistic_channel,
                key=f"mu_logistic_{idx}",
                placeholder="例: Standard Express / Shopee Express / J&T Express",
                help=(
                    "Shopee Seller Center で有効化した配送チャンネル名をそのまま入力してください。"
                ),
            )

            st.markdown("#### 🔵 任意フィールド（入力推奨）")

            img_col2, img_col3 = st.columns(2)
            with img_col2:
                new_img2 = st.text_input(
                    "追加画像 URL 2",
                    value=extra.image_url_2,
                    key=f"mu_img2_{idx}",
                    placeholder="https://（任意）",
                )
            with img_col3:
                new_img3 = st.text_input(
                    "追加画像 URL 3",
                    value=extra.image_url_3,
                    key=f"mu_img3_{idx}",
                    placeholder="https://（任意）",
                )
            img_col4, img_col5 = st.columns(2)
            with img_col4:
                new_img4 = st.text_input(
                    "追加画像 URL 4",
                    value=extra.image_url_4,
                    key=f"mu_img4_{idx}",
                    placeholder="https://（任意）",
                )
            with img_col5:
                new_img5 = st.text_input(
                    "追加画像 URL 5",
                    value=extra.image_url_5,
                    key=f"mu_img5_{idx}",
                    placeholder="https://（任意）",
                )

            dim_col1, dim_col2, dim_col3 = st.columns(3)
            with dim_col1:
                new_length = st.number_input(
                    "長さ cm",
                    min_value=0.0, value=float(extra.length_cm),
                    step=1.0, key=f"mu_len_{idx}",
                )
            with dim_col2:
                new_width = st.number_input(
                    "幅 cm",
                    min_value=0.0, value=float(extra.width_cm),
                    step=1.0, key=f"mu_wid_{idx}",
                )
            with dim_col3:
                new_height = st.number_input(
                    "高さ cm",
                    min_value=0.0, value=float(extra.height_cm),
                    step=1.0, key=f"mu_hei_{idx}",
                )

            other_col1, other_col2, other_col3 = st.columns(3)
            with other_col1:
                new_preorder = st.number_input(
                    "予約注文日数",
                    min_value=0, max_value=30, value=int(extra.preorder_days),
                    step=1, key=f"mu_pre_{idx}",
                    help="0 の場合は通常販売（予約注文なし）",
                )
            with other_col2:
                new_condition = st.selectbox(
                    "商品状態",
                    options=["New", "Used"],
                    index=0 if (extra.condition or "New") == "New" else 1,
                    key=f"mu_cond_{idx}",
                )
            with other_col3:
                new_brand = st.text_input(
                    "ブランド",
                    value=extra.brand,
                    key=f"mu_brand_{idx}",
                    placeholder="任意",
                )

            # ── 保存ボタン ──────────────────────────────────────
            save_col, _ = st.columns([1, 2])
            with save_col:
                if st.button("💾 この商品の入力を保存", key=f"mu_save_{idx}", width="stretch"):
                    new_extra = _smu.MassUploadExtra(
                        category_id=new_category_id.strip(),
                        price_local=float(new_price_local),
                        stock_qty=int(new_stock),
                        main_image_url=new_main_image.strip(),
                        image_url_2=new_img2.strip(),
                        image_url_3=new_img3.strip(),
                        image_url_4=new_img4.strip(),
                        image_url_5=new_img5.strip(),
                        weight_kg=float(new_weight),
                        length_cm=float(new_length),
                        width_cm=float(new_width),
                        height_cm=float(new_height),
                        logistic_channel=new_logistic.strip(),
                        preorder_days=int(new_preorder),
                        condition=new_condition,
                        brand=new_brand.strip(),
                    )
                    extra_data[e_key] = new_extra.to_dict()
                    st.session_state["mu_extra_data"] = extra_data
                    save_mass_upload_extra(extra_data)
                    st.success("✅ 保存しました。")
                    st.rerun()

            # ── バリデーションエラー表示 ────────────────────────
            # 最新の入力値で再検証
            current_extra = _smu.MassUploadExtra(
                category_id=new_category_id.strip(),
                price_local=float(new_price_local),
                stock_qty=int(new_stock),
                main_image_url=new_main_image.strip(),
                weight_kg=float(new_weight),
                logistic_channel=new_logistic.strip(),
                image_url_2=new_img2.strip(),
                image_url_3=new_img3.strip(),
                image_url_4=new_img4.strip(),
                image_url_5=new_img5.strip(),
                length_cm=float(new_length),
                width_cm=float(new_width),
                height_cm=float(new_height),
                preorder_days=int(new_preorder),
                condition=new_condition,
                brand=new_brand.strip(),
            )
            current_result = _smu.validate_product(draft_row, current_extra)
            all_errors[product_name] = current_result.errors

            if current_result.is_valid:
                st.success("✅ この商品はエクスポート可能です。")
                export_row = _smu.build_mass_upload_row(draft_row, current_extra)
                valid_rows.append(export_row)
            else:
                st.error(
                    f"🔴 **{len(current_result.errors)} 件の必須フィールドが未入力です**\n\n"
                    + "\n".join(f"- {e.splitlines()[0]}" for e in current_result.errors)
                )

        st.write("")

    # ── エクスポートサマリーと DL ボタン ─────────────────────
    st.divider()

    n_valid = len(valid_rows)
    n_total = len(df_country)
    n_invalid = n_total - n_valid

    summary_c1, summary_c2, summary_c3 = st.columns(3)
    summary_c1.metric("対象商品（承認済み）", n_total)
    summary_c2.metric("✅ エクスポート可能", n_valid)
    summary_c3.metric("⚠️ 未入力あり（除外）", n_invalid)

    if n_invalid > 0:
        with st.expander("⚠️ エクスポートから除外される商品と理由"):
            for pname, errs in all_errors.items():
                if errs:
                    st.markdown(f"**🔴 {pname}**")
                    for e in errs:
                        st.caption(f"  - {e.splitlines()[0]}")

    st.divider()
    st.subheader("⬇️ Shopee Mass Upload CSV ダウンロード")
    st.caption(
        "このCSVは Shopee Seller Center の「商品管理 → 一括アップロード」で使用できます。\n"
        "ダウンロード後、必ず内容を確認してから Shopee にアップロードしてください。\n"
        "このファイルをアップロードしても自動出品は行われません（Shopee側の確認が必要です）。"
    )

    # 内部CSV（既存機能）との差別化注記
    with st.expander("ℹ️ 内部CSVとの違い"):
        st.markdown("""
| 項目 | 内部CSV（承認済みエクスポート）| Shopee Mass Upload CSV（このページ）|
|---|---|---|
| 用途 | 社内管理・記録用 | Shopee Seller Center への直接アップロード用 |
| 列構成 | システム内部フォーマット | Shopee公式テンプレート形式 |
| 商品画像 | なし（参照なし）| 必須（URL入力が必要）|
| カテゴリ | テキスト候補（参考）| Shopee公式カテゴリID（数値）が必要 |
| 価格 | 円建て（JPY）| 現地通貨（国ごとに異なる）|
| 重量・寸法 | なし | 必須（入力が必要）|
| 物流チャンネル | なし | 必須（入力が必要）|
        """)

    if n_valid == 0:
        st.info(
            "エクスポート可能な商品がありません。\n\n"
            "各商品カードを開いて、必須フィールドをすべて入力して「💾 保存」してください。"
        )
    else:
        csv_bytes = _smu.generate_mass_upload_csv(valid_rows)
        st.download_button(
            label=f"📥 {selected_country} 向け Shopee Mass Upload CSV をダウンロード（{n_valid}件）",
            data=csv_bytes,
            file_name=(
                f"shopee_mass_upload_{selected_country.lower()}_"
                f"{_dt.date.today().isoformat()}.csv"
            ),
            mime="text/csv",
            width="stretch",
            type="primary",
        )
        st.caption(
            f"⚠️ {n_invalid} 件は必須フィールド未入力のため除外されています。"
            if n_invalid > 0 else
            f"✅ 全 {n_valid} 件が含まれます。"
        )



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
