/* All API mutations require a server session + CSRF. No keys or business data in localStorage. */
const $ = (q, root = document) => root.querySelector(q);
const app = $("#app");
const modal = $("#modal");
const state = {
  page: "dashboard",
  tab: "basic",
  market: "SG",
  search: "",
  status: "",
  filterMarket: "",
  ids: new Set(),
  data: null,
  csrf: "",
  dirty: false,
  productId: null,
  ideas: [],
  ideaSearch: "",
  suggestion: null,
};
const icons = {
  dashboard: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  research: "M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  finance: "M4 21V10 M10 21V3 M16 21v-7 M22 21H2",
  prep: "M9 5H5v16h14V5h-4 M9 3h6v4H9z M8 13l2 2 5-5",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M10 2h4l1 3 3 1 3 3-1 3 1 3-3 3-3 1-1 3h-4l-1-3-3-1-3-3 1-3-1-3 3-3 3-1z",
  plus: "M12 5v14 M5 12h14",
  arrow: "M5 12h14 M14 7l5 5-5 5",
  back: "M19 12H5 M10 7l-5 5 5 5",
  box: "M3 7l9-5 9 5v10l-9 5-9-5z M3 7l9 5 9-5 M12 12v10 M7 4l10 5",
  check: "M5 12l4 4L19 6",
  warn: "M12 3l10 18H2z M12 9v4 M12 17v1",
  globe:
    "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M3 12h18 M12 3c-5 4-5 14 0 18 M12 3c5 4 5 14 0 18",
  doc: "M14 2H5v20h14V7z M14 2v6h5 M8 12h8 M8 16h8",
  lock: "M5 10h14v11H5z M8 10V6a4 4 0 0 1 8 0v4",
  spark: "M12 2l3 7 7 3-7 3-3 7-3-7-7-3 7-3z",
  download: "M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5",
  exit: "M9 3H3v18h6 M9 12h12 M16 7l5 5-5 5",
};
function icon(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${icons[name] || icons.box}"/></svg>`;
}
function esc(v) {
  return String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
}
const yen = (n) =>
  n === null || n === undefined
    ? "未算出"
    : `¥${Number(n).toLocaleString("ja-JP", { maximumFractionDigits: 0 })}`;
function money(n, market = "SG") {
  return n === null || n === undefined
    ? "未入力"
    : `${state.data.markets[market].currency} ${Number(n).toLocaleString("ja-JP", { maximumFractionDigits: 2 })}`;
}
function badge(text, kind = "") {
  return `<span class="tag ${kind}">${esc(text)}</span>`;
}
function isVerified(s) {
  const age = (Date.now() - Date.parse(s.checked_on + "T00:00:00Z")) / 86400000;
  return s.verified && age >= 0 && age < 31;
}
function statusTag(status) {
  return badge(
    state.data.statuses[status],
    status === "ready"
      ? "good"
      : status === "approved"
        ? "dark"
        : status === "rejected"
          ? "bad"
          : "",
  );
}
function button(text, action, kind = "", extra = "") {
  return `<button type="button" class="btn ${kind}" data-action="${action}" ${extra}>${text}</button>`;
}
function note(text, kind = "") {
  return `<div class="note ${kind}">${esc(text)}</div>`;
}
function empty(title, body, action = "new", label = "商品を登録") {
  return `<div class="empty"><div class="empty-icon">${icon("box")}</div><h3>${esc(title)}</h3><p>${esc(body)}</p>${button(icon("plus") + esc(label), action, "primary")}</div>`;
}
function toast(text, error = false) {
  const el = $("#toast");
  el.textContent = text;
  el.className = "visible" + (error ? " error" : "");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => (el.className = ""), 6000);
}
async function api(path, options = {}) {
  const headers = { ...options.headers };
  if (options.body) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  if (options.method && options.method !== "GET")
    headers["X-CSRF-Token"] = state.csrf;
  const res = await fetch("/api" + path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  const type = res.headers.get("content-type") || "";
  const body = type.includes("application/json")
    ? await res.json()
    : await res.text();
  if (
    res.status === 401 &&
    path !== "/login" &&
    state.data &&
    !state.reauthMode
  ) {
    await reauthenticate();
  }
  if (!res.ok)
    throw new Error(
      body.error || "通信に失敗しました。接続を確認してください。",
    );
  return body;
}
async function reauthenticate() {
  const response = await fetch("/api/session", { credentials: "same-origin" });
  if (!response.ok) return;
  const session = await response.json();
  state.csrf = session.csrf;
  state.suspendedModal = modal.open ? Array.from(modal.childNodes) : null;
  state.reauthMode = true;
  modal.replaceChildren();
  modal.innerHTML = `<h2 id="modal-title">もう一度ログインしてください</h2><p class="muted">セッションの有効期限が切れました。入力中の内容は保持しています。</p><form id="reauth-form" class="spaced"><label class="field"><span>パスワード</span><input name="password" type="password" autocomplete="current-password" required maxlength="1024"></label>${inlineError()}<div class="form-actions">${button("後でログイン", "reauth-cancel")}<button class="btn primary">再ログイン</button></div></form>`;
  if (!modal.open) modal.showModal();
  $("input", modal)?.focus();
}
function endReauthentication() {
  if (state.suspendedModal) {
    modal.replaceChildren(...state.suspendedModal);
    modal.querySelectorAll("button").forEach((b) => {
      b.disabled = false;
    });
  } else {
    modal.close();
  }
  state.suspendedModal = null;
  state.reauthMode = false;
}
async function refresh() {
  state.history = null;
  state.data = await api("/bootstrap");
  state.ids = new Set(
    [...state.ids].filter((id) => state.data.products.some((p) => p.id === id)),
  );
}
function guard() {
  if (
    state.dirty &&
    !confirm("保存されていない変更があります。移動してもよろしいですか？")
  )
    return false;
  state.dirty = false;
  state.pendingCopySource = null;
  return true;
}
function go(page, id = null, tab = "basic") {
  if (!guard()) return;
  if (state.productId !== id) state.history = null;
  state.page = page;
  state.productId = id;
  state.tab = tab;
  state.suggestion = null;
  render();
  window.scrollTo(0, 0);
}
function current() {
  return state.data.products.find((p) => p.id === state.productId);
}
function field(key, label, value, options = {}) {
  const type = options.type || "text",
    wide = options.wide ? " wide" : "";
  let input;
  if (type === "textarea")
    input = `<textarea name="${key}" rows="${options.rows || 4}" maxlength="${options.max || 10000}" ${options.required ? "required" : ""}>${esc(value)}</textarea>`;
  else if (type === "select")
    input = `<select name="${key}">${options.options.map(([v, l]) => `<option value="${esc(v)}" ${String(value) === String(v) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  else
    input = `<input name="${key}" type="${type}" value="${esc(value)}" ${type === "number" ? `min="0" max="1000000000" step="${options.step || "any"}"` : ""} ${options.required ? "required" : ""} ${options.placeholder ? `placeholder="${esc(options.placeholder)}"` : ""} ${type === "text" ? 'maxlength="1000"' : ""}>`;
  return `<label class="field${wide}"><span>${esc(label)}${options.required ? " *" : ""}</span>${input}${options.help ? `<small>${esc(options.help)}</small>` : ""}</label>`;
}
function check(key, label, value) {
  return `<label class="check"><input type="checkbox" name="${key}" ${value ? "checked" : ""}><span>${esc(label)}</span></label>`;
}
function inlineError() {
  return '<div class="inline-error" role="alert"></div>';
}
function showError(form, error) {
  const node = $(".inline-error", form);
  if (node) {
    node.textContent = error.message;
    node.classList.add("visible");
    node.scrollIntoView({ block: "nearest" });
  } else toast(error.message, true);
}
function formData(form, base, defaults) {
  const next = { ...base };
  for (const el of form.elements) {
    if (!el.name || !(el.name in defaults)) continue;
    if (el.type === "checkbox") next[el.name] = el.checked;
    else if (el.type === "number")
      next[el.name] =
        el.value === ""
          ? defaults[el.name] === null
            ? null
            : 0
          : Number(el.value);
    else next[el.name] = el.value;
  }
  return Object.fromEntries(
    Object.keys(defaults).map((k) => [k, next[k] ?? defaults[k]]),
  );
}
function pageTitle(label, sub, action = "") {
  return `<div class="page-head"><div><div class="eyebrow">YOUR CROSS-BORDER WORKSPACE</div><h1>${label}</h1><p>${sub}</p></div>${action}</div>`;
}
function render() {
  if (!state.data) return;
  const names = {
    dashboard: "ダッシュボード",
    products: "商品リサーチ",
    ideas: "商品アイデア",
    finance: "利益シミュレーター",
    prep: "出品準備",
    settings: "設定・データ",
    detail: "商品詳細",
    compare: "商品比較",
  };
  const active =
    state.page === "detail" ||
    state.page === "ideas" ||
    state.page === "compare"
      ? "products"
      : state.page;
  app.innerHTML = `<div class="shell"><aside class="sidebar"><div class="brand"><img src="/assets/mark.svg" alt=""><div><strong>Research Desk</strong><small>SHOPEE WORKSPACE</small></div></div><div class="nav-label">WORKSPACE</div><nav class="nav" aria-label="メインメニュー">${[
    ["dashboard", "dashboard", "概要"],
    ["products", "research", "商品リサーチ"],
    ["finance", "finance", "利益計算"],
    ["prep", "prep", "出品準備"],
    ["settings", "settings", "設定"],
  ]
    .map(
      ([key, ic, label]) =>
        `<button data-action="nav" data-value="${key}" class="${active === key ? "active" : ""}" ${active === key ? 'aria-current="page"' : ""}>${icon(ic)}<span>${label}</span>${key === "products" ? `<span class="count">${state.data.products.length}</span>` : ""}</button>`,
    )
    .join(
      "",
    )}</nav><div class="sidebar-foot"><b>${icon("lock")} 人間が最終確認</b>リサーチから出品準備まで。<br>自動出品・仕入れは行いません。<br><br>Research Desk / v2.0</div></aside><div class="workspace"><header class="topbar"><div class="breadcrumb">Workspace <span> / </span> <b>${names[state.page]}</b></div><div class="mobile-brand"><img src="/assets/mark.svg" alt="">Research Desk</div><div class="top-actions"><span class="mode-text"><span class="dot"></span>${state.data.ai_available ? "AI接続設定あり" : "基本モード"}</span>${button("ログアウト", "logout", "subtle")}<div class="avatar" aria-label="個人ワークスペース">ME</div></div></header><main id="main" class="main" tabindex="-1">${content()}<footer class="footer"><span>Shopee Research Desk — 日本から、次のマーケットへ。</span><span>独立した運用支援ツール / Shopee非公式</span></footer></main></div></div>`;
}
function content() {
  switch (state.page) {
    case "dashboard":
      return dashboard();
    case "products":
      return products();
    case "detail":
      return detail();
    case "ideas":
      return ideas();
    case "settings":
      return settings();
    case "finance":
      return simulator();
    case "prep":
      return preparations();
    case "compare":
      return comparePage();
    default:
      return "";
  }
}
function metric(label, value, unit, sub, ic = "box", color = "") {
  return `<div class="metric"><div class="metric-top">${esc(label)}${icon(ic)}</div><div class="metric-value ${color}">${esc(value)}<span>${esc(unit)}</span></div><small>${esc(sub)}</small></div>`;
}
function dashboard() {
  const p = state.data.products,
    approved = p.filter(
      (x) => x.status === "approved" || x.status === "ready",
    ).length,
    ready = p.filter(
      (x) => x.status === "ready" && !x.readiness_errors.length,
    ).length,
    loss = p.filter(
      (x) => x.finance.available && x.finance.stress_profit_jpy < 0,
    ).length;
  const unknown = p.filter((x) => x.demand_level === "unknown").length;
  return `${pageTitle("今日のワークスペース", "リサーチ、採算確認、出品準備。次に進める商品を見つけましょう。", button(icon("plus") + "商品を登録", "new", "primary"))}
 <section class="hero"><div><div class="hero-badge">RESEARCH WITH CONFIDENCE</div><h2>次の一手を、確かな数字で。</h2><p>売れそう、だけで終わらせない。<br>市場の根拠と手元に残る利益を確認して、一つずつ進めましょう。</p></div><svg class="hero-art" viewBox="0 0 180 120" fill="none" aria-hidden="true"><path d="M10 102h160" stroke="#c1cdb6"/><rect x="25" y="68" width="26" height="34" rx="5" fill="#b7c6a9"/><rect x="62" y="50" width="26" height="52" rx="5" fill="#9caf89"/><rect x="99" y="28" width="26" height="74" rx="5" fill="#7d976c"/><path d="m29 48 40-23 34 4 49-23m-16-1 17 1-5 16" stroke="#d4764b" stroke-width="2.5" stroke-linecap="round"/><circle cx="149" cy="80" r="23" fill="#eff3e9" stroke="#c0cdb5"/><path d="m139 80 7 7 12-14" stroke="#709066" stroke-width="2.5"/></svg></section>
 <section class="metrics" aria-label="商品状況">${metric("管理中の商品", p.length, "件", "商品 × 販売国で管理", "box")}${metric("人間による承認済み", approved, "件", "準備完了の商品を含む", "check", "green")}${metric("出品準備完了", ready, "件", "現在のチェックを通過", "doc", "green")}${metric("ストレス時の赤字", loss, "件", "計算可能な商品のみ", "warn", loss ? "red" : "")}</section>
 <div class="split"><section class="panel"><div class="section-head"><div><h2>次にやること</h2><p>確認を済ませて、安心して次のステップへ。</p></div>${badge("ACTION LIST")}</div>
 ${task("settings", "国別の費用条件を確認", `${Object.values(state.data.profiles).filter((x) => !isVerified(x)).length}市場の手数料・為替が未確認です。`, "settings")}
 ${task("research", "需要と競合の根拠を集める", `${unknown}件の需要が未確認です。出典と観測日を記録しましょう。`, "products")}
 ${task("prep", "承認した商品を出品準備へ", `${ready}件が準備完了。商品情報と最新テンプレートを確認します。`, "prep")}</section>
 <section class="panel"><div class="section-head"><div><h2>マーケットの設定</h2><p>手数料・為替の確認状況</p></div>${icon("globe")}</div>${Object.entries(
   state.data.markets,
 )
   .map(
     ([k, m]) =>
       `<div class="market-row"><span class="market-code">${k}</span><div class="market-info"><b>${m.name}</b><small>${m.currency} / ${state.data.profiles[k].checked_on || "確認日未登録"}</small></div>${badge(isVerified(state.data.profiles[k]) ? "入力者確認済み" : "未確認", isVerified(state.data.profiles[k]) ? "good" : "warn")}</div>`,
   )
   .join("")}</section></div>
 <section class="panel table-panel"><div class="toolbar"><div><h2>最近の商品</h2><small>登録・更新した候補をここから再開できます。</small></div>${button("すべて見る " + icon("arrow"), "nav", "", 'data-value="products"')}</div>${p.length ? productTable(p.slice(0, 5), false) : empty("最初の商品を登録しましょう", "自分で見つけた商品を登録するか、カタログの着想から調査を始められます。", "ideas", "商品アイデアを見る")}<div class="table-foot"><span>需要・競合はユーザーの観測情報です。未取得の値は表示しません。</span><span>自動取引なし</span></div></section>`;
}
function task(ic, title, sub, to) {
  return `<div class="task"><div class="task-icon">${icon(ic)}</div><div class="task-info"><b>${esc(title)}</b><p>${esc(sub)}</p></div>${button(icon("arrow"), "nav", "subtle", `data-value="${to}" aria-label="${esc(title)}"`)}</div>`;
}
function productTable(rows, select = true) {
  return `<div class="table-wrap"><table class="products"><thead><tr>${select ? '<th><span class="sr-only">比較選択</span></th>' : ""}<th>商品</th><th>販売国 / 状態</th><th>利益 / ストレス時</th><th>調査・リスク</th></tr></thead><tbody>${rows.map((p) => `<tr>${select ? `<td class="select-td"><input class="comparison-check" type="checkbox" data-select="${p.id}" ${state.ids.has(p.id) ? "checked" : ""} aria-label="${esc(p.name)}を比較に追加"></td>` : ""}<td class="product-td"><div class="product-cell"><div class="product-icon">${icon("box")}</div><div><button class="product-name" data-action="detail" data-id="${p.id}">${esc(p.name)}</button><small>${esc(p.category || "カテゴリ未入力")} · ${esc(p.sku || "SKU未設定")}</small></div></div></td><td data-label="市場"><div><div class="badge-row">${badge(p.market)}${statusTag(p.status)}</div><small>${state.data.markets[p.market].currency}</small></div></td><td data-label="利益"><div><span class="num ${p.finance.available && p.finance.profit_jpy < 0 ? "red" : ""}">${p.finance.available ? yen(p.finance.profit_jpy) : "未算出"}</span><small class="${p.finance.available && p.finance.stress_profit_jpy < 0 ? "red" : ""}">${p.finance.available ? "ストレス " + yen(p.finance.stress_profit_jpy) : "費用・売価の入力が必要"}</small></div></td><td data-label="確認"><div class="badge-row">${badge(p.demand_level === "unknown" ? "需要未確認" : "観測情報あり", p.demand_level === "unknown" ? "" : "good")}${badge(p.risk.level === "high" ? "高リスク" : p.risk.level === "review" ? "要確認" : "未判定", p.risk.level === "high" ? "bad" : p.risk.level === "review" ? "warn" : "")}</div></td></tr>`).join("")}</tbody></table></div>`;
}
function products() {
  const rows = state.data.products.filter(
    (p) =>
      (!state.search ||
        (p.name + " " + p.category + " " + p.sku)
          .toLowerCase()
          .includes(state.search.toLowerCase())) &&
      (!state.status || p.status === state.status) &&
      (!state.filterMarket || p.market === state.filterMarket),
  );
  return `${pageTitle("商品リサーチ", "販売国ごとに、需要の根拠・競合・採算を比較します。", `<div class="actions">${button("着想カタログ", "ideas")}${button(icon("plus") + "商品を登録", "new", "primary")}</div>`)}
 <section class="panel table-panel"><div class="toolbar"><form id="filter-form"><input name="search" value="${esc(state.search)}" aria-label="商品を検索" placeholder="商品名・SKU・カテゴリを検索"><select name="market" aria-label="販売国で絞り込み"><option value="">すべての国</option>${Object.entries(
   state.data.markets,
 )
   .map(
     ([k, m]) =>
       `<option value="${k}" ${state.filterMarket === k ? "selected" : ""}>${m.name}</option>`,
   )
   .join(
     "",
   )}</select><select name="status" aria-label="状態で絞り込み"><option value="">すべての状態</option>${Object.entries(
   state.data.statuses,
 )
   .map(
     ([k, m]) =>
       `<option value="${k}" ${state.status === k ? "selected" : ""}>${m}</option>`,
   )
   .join(
     "",
   )}</select><button class="btn search-button">検索</button></form>${button(`比較する（${state.ids.size}）`, "compare", "", state.ids.size < 2 ? "disabled" : "")}</div>${rows.length ? productTable(rows) : empty("該当する商品がありません", "商品を登録するか、絞り込み条件を変更してください。")}<div class="table-foot"><span>${rows.length} / ${state.data.products.length} 件 · 比較は2〜6件</span><span>データは自動取得していません</span></div></section>
 ${note("観測数値には、出典URL・観測日・観測条件をセットで保存します。固定カタログの「人気」や需要スコアを実測値として使うことはありません。")}`;
}
function detailsForm(p, body) {
  return `<form id="product-form" data-id="${p.id}"><div class="form-grid">${body}${inlineError()}</div><div class="form-actions"><small>重要項目の変更後は調査中に戻り、再承認が必要です。</small><button class="btn primary">変更を保存</button></div></form>`;
}
function detail() {
  const p = current();
  if (!p)
    return empty(
      "商品が見つかりません",
      "商品リサーチから選び直してください。",
      "products",
      "一覧に戻る",
    );
  const s = state.data.profiles[p.market];
  const options = Object.entries(state.data.statuses)
    .map(
      ([v, l]) =>
        `<option value="${v}" ${v === p.status ? "selected" : ""}>${l}</option>`,
    )
    .join("");
  const tabs = [
    ["basic", "商品・調査"],
    ["finance", "利益分析"],
    ["copy", "出品コピー"],
    ["prep", "出品前チェック"],
    ["history", "変更履歴"],
  ];
  return `<div class="back">${button(icon("back") + "商品リサーチへ", "nav", "subtle", 'data-value="products"')}</div><div class="page-head details-head"><div><div class="eyebrow">PRODUCT WORKSPACE / ${p.market}</div><h1>${esc(p.name)}</h1><div class="detail-summary">${statusTag(p.status)}${badge(state.data.markets[p.market].name)}<small>更新 ${new Date(p.updated_at).toLocaleString("ja-JP")}</small></div></div><div class="actions">${button("別の国へ複製", "clone", "", 'data-id="' + p.id + '"')}<select class="status-select" id="status-change" aria-label="商品状態の変更">${options}</select>${button("状態を変更", "status", "primary", `data-id="${p.id}"`)}</div></div><nav class="tabs" aria-label="商品詳細のタブ">${tabs.map(([k, l]) => `<button data-action="tab" data-value="${k}" class="${state.tab === k ? "active" : ""}" ${state.tab === k ? 'aria-current="page"' : ""}>${l}</button>`).join("")}</nav>${state.tab === "basic" ? basic(p) : state.tab === "finance" ? financial(p, s) : state.tab === "copy" ? copyPage(p) : state.tab === "prep" ? prepDetail(p, s) : historyView(p)}`;
}
function basic(p) {
  return `<section class="panel"><div class="section-head"><div><h2>商品と仕入れ先</h2><p>同じ商品名でもSKUを分ければバリエーションを管理できます。</p></div>${badge("手入力")}</div>${detailsForm(
    p,
    field("name", "商品名", p.name, { required: true }) +
      field("sku", "Seller SKU", p.sku, { placeholder: "例: ST-001" }) +
      field("category", "カテゴリ（調査用）", p.category) +
      field("english_name", "英語の商品名", p.english_name) +
      field("supplier_name", "仕入れ先名", p.supplier_name) +
      field("supplier_url", "仕入れ先URL", p.supplier_url, { type: "url" }) +
      field("facts_en", "確認済みの商品仕様（英語）", p.facts_en, {
        type: "textarea",
        wide: true,
        help: "素材、サイズ、内容数など、根拠を確認した仕様だけを記入。AIへ送るのは商品名・英語仕様・カテゴリ・ブランド・状態です。",
      }) +
      '<h3 class="form-section field wide">市場の観測メモ</h3>' +
      field("demand_level", "需要の主観評価", p.demand_level, {
        type: "select",
        options: [
          ["unknown", "未確認"],
          ["low", "低い（主観）"],
          ["medium", "中程度（主観）"],
          ["high", "高い（主観）"],
        ],
      }) +
      field("competitor_count", "観測した競合件数", p.competitor_count, {
        type: "number",
        step: 1,
      }) +
      field(
        "competitor_price_local",
        `観測した競合価格（${state.data.markets[p.market].currency}）`,
        p.competitor_price_local,
        { type: "number" },
      ) +
      field("observed_sales", "ページに表示された販売数", p.observed_sales, {
        type: "number",
        step: 1,
        help: "期間や表示条件もメモしてください。月間販売数とは限りません。",
      }) +
      field("research_source_url", "観測の出典URL", p.research_source_url, {
        type: "url",
      }) +
      field("research_date", "観測日", p.research_date, { type: "date" }) +
      field(
        "research_note",
        "検索語・比較範囲・期間・判断理由",
        p.research_note,
        { type: "textarea", wide: true },
      ) +
      field("notes", "自分用メモ", p.notes, { type: "textarea", wide: true }),
  )}</section>`;
}
const costLabels = {
  cost_jpy: "仕入れ原価",
  domestic_shipping_jpy: "国内送料",
  international_shipping_jpy: "国際送料",
  packaging_jpy: "梱包費",
  customs_jpy: "販売者負担の関税・税等",
  other_jpy: "その他経費",
  shipping_rebate_jpy: "送料還付・リベート",
};
function financial(p, s) {
  return `<section class="panel"><div class="section-head"><div><h2>費用と販売価格</h2><p>すべて1商品・1注文分。費用がない項目には0を入力してください。</p></div>${button("国別設定へ", "nav", "", 'data-value="settings"')}</div>${detailsForm(
    p,
    Object.entries(costLabels)
      .map(([k, l]) => field(k, l + "（JPY）", p[k], { type: "number" }))
      .join("") +
      field(
        "price_local",
        `販売価格（${state.data.markets[p.market].currency}）`,
        p.price_local,
        { type: "number" },
      ) +
      field(
        "buyer_shipping_local",
        "購入者から受け取る送料（現地通貨）",
        p.buyer_shipping_local,
        { type: "number" },
      ) +
      field("discount_pct", "販売者負担の値引き率（%）", p.discount_pct, {
        type: "number",
      }),
  )}</section>${financeResult(p.finance, p.market, s)}`;
}
function financeResult(f, market, s) {
  if (!f.available)
    return `<section class="panel">${note("利益はまだ計算できません。商品原価・各種送料・販売価格と、国別設定の手数料・為替を入力してください。", "warn")}<p class="muted spaced">未入力: ${esc(f.missing.join(", "))}</p></section>`;
  const lines = [
    ["売上（値引き後＋購入者送料）", f.revenue_jpy],
    ["Shopee手数料＋手数料への税", -f.marketplace_fees_jpy],
    ["送金・換金手数料", -f.payout_fee_jpy],
    ["広告費", -f.advertising_jpy],
    ["返品・損失引当", -f.reserve_jpy],
    ["原価・送料・その他経費（還付控除後）", -f.cost_total_jpy],
  ];
  return `<section class="metrics">${metric("試算利益", yen(f.profit_jpy), "", `売上利益率 ${f.margin_pct}%`, "finance", f.profit_jpy < 0 ? "red" : "green")}${metric("ストレス時の利益", yen(f.stress_profit_jpy), "", "悪化条件を同時に反映", "warn", f.stress_profit_jpy < 0 ? "red" : "green")}${metric("損益分岐価格", f.break_even_local === null ? "算出不能" : money(f.break_even_local, market), "", "現地通貨・切り上げ", "finance")}${metric("目標利益率の売価", f.target_price_local === null ? "達成不能" : money(f.target_price_local, market), "", `目標 ${s.target_margin_pct}%`, "finance")}</section><div class="split"><section class="panel"><div class="section-head"><h2>利益の内訳</h2>${badge(f.verified ? "入力者確認済みの条件" : "未確認条件の試算", f.verified ? "good" : "warn")}</div>${lines.map(([l, v]) => `<div class="cost-row"><span>${l}</span><span>${yen(v)}</span></div>`).join("")}<div class="cost-row total"><span>手元に残る利益の試算</span><span>${yen(f.profit_jpy)}</span></div><p class="muted spaced">売上の所得税・法人税は含みません。固定費は1商品あたりに配賦して入力してください。</p></section><section class="panel"><div class="section-head"><h2>売価を変えた場合</h2>${badge("感応度")}</div><div class="scenario-list">${f.scenarios.map((r, i) => `<div class="scenario-row"><span>${money(r.price_local, market)}</span><div class="bar p${i}"><div class="bar-fill ${r.profit_jpy < 0 ? "loss" : ""}"></div></div><b class="${r.profit_jpy < 0 ? "red" : "green"}">${yen(r.profit_jpy)}</b></div>`).join("")}</div><p class="muted spaced">棒の長さは売価の相対水準（80〜120%）を表します。利益額は右の数値を確認してください。</p><div class="note spaced">ストレス条件：円換算レート −${s.fx_stress_pct}% / 国際送料 ＋${s.shipping_stress_pct}% / 販売価格 −${s.price_stress_pct}%</div></section></div>${f.warnings.map((w) => note(w, "warn")).join("<br>")}`;
}
function copyPage(p) {
  return `<section class="panel"><div class="section-head"><div><h2>タイトル・説明文</h2><p>生成案は確認後に取り込みます。保存済みのコピーは再生成しても残ります。</p></div>${button(icon("spark") + (state.data.ai_available ? "AIで下書き案を作る" : "定型の英語案を作る"), "generate", "", 'data-id="' + p.id + '"')}</div>${note(state.data.ai_available ? "生成ボタンを押した場合のみ、商品名・英語名・確認済み英語仕様・カテゴリ・ブランド・状態をOpenAIへ送信します。API利用料金が発生する場合があります。" : "APIキー未設定でも、英語の商品名と確認済み英語仕様から定型案を作れます。日本語の自由翻訳にはAIか手動入力が必要です。")}
 <div id="suggestion">${suggestionHtml()}</div><div class="spaced">${detailsForm(
   p,
   field("listing_language", "出品言語", p.listing_language, {
     type: "select",
     options: [
       ["en", "英語"],
       ["zh-TW", "繁体字中国語"],
       ["th", "タイ語"],
       ["vi", "ベトナム語"],
       ["ms", "マレー語"],
     ],
   }) +
     field("english_name", "英語の商品名（基本モードに必要）", p.english_name) +
     field("facts_en", "確認済み商品仕様（英語）", p.facts_en, {
       type: "textarea",
       wide: true,
     }) +
     field("title", "商品タイトル", p.title, {
       wide: true,
       help: "文字数上限は国別設定で確認してください。",
     }) +
     field("description", "商品説明", p.description, {
       type: "textarea",
       rows: 9,
       wide: true,
     }) +
     `<div class="field wide">${check("copy_reviewed", "商品仕様・表現・言語を確認した（本文を変更した場合は、保存後に再チェック）", p.copy_reviewed)}</div>`,
 )}<p class="muted spaced">下書きの由来: ${esc(p.copy_source || "手動入力または未生成")}</p></div></section>`;
}
function suggestionHtml() {
  const s = state.suggestion;
  if (!s) return "";
  return `<div class="copy-preview"><span class="tag">${s.source === "openai" ? "AI生成案" : "定型案"} / ${esc(s.language)}</span><h3>${esc(s.title || "商品名の入力が必要です")}</h3><p>${esc(s.description)}</p><div class="note spaced">${esc(s.review_notes)}</div>${s.title ? `<div class="actions spaced">${button("この案を編集欄に取り込む", "use-suggestion", "primary")}${button("案を閉じる", "dismiss-suggestion")}</div>` : ""}</div>`;
}
function prepDetail(p, s) {
  return `<div class="split"><section class="panel"><div class="section-head"><h2>出品に必要な情報</h2>${badge("手動確認")}</div>${detailsForm(
    p,
    field("category_id", "ShopeeカテゴリID", p.category_id, {
      help: "対象国のSeller Centerから確認。IDは推測しません。",
    }) +
      field("brand", "ブランド", p.brand) +
      field("image_url", "画像URL（利用権を確認）", p.image_url, {
        type: "url",
        wide: true,
        help: "画像URLは保存するだけで、自動取得・アップロードしません。",
      }) +
      field("stock", "確認済み在庫数", p.stock, { type: "number", step: 1 }) +
      field("weight_kg", "梱包後重量（kg）", p.weight_kg, { type: "number" }) +
      field("length_cm", "梱包後の長さ（cm）", p.length_cm, {
        type: "number",
      }) +
      field("width_cm", "幅（cm）", p.width_cm, { type: "number" }) +
      field("height_cm", "高さ（cm）", p.height_cm, { type: "number" }) +
      field("logistics", "有効な物流チャンネル", p.logistics) +
      field("condition", "商品状態", p.condition, {
        type: "select",
        options: [
          ["New", "新品"],
          ["Used", "中古"],
        ],
      }) +
      `<div class="field wide">${check("risk_reviewed", "対象国の販売規制・通関・配送条件を確認した", p.risk_reviewed)}</div><div class="field wide">${check("rights_reviewed", "正規の仕入れ先・商品と画像の知的財産権を確認した", p.rights_reviewed)}</div><div class="field wide">${check("market_reviewed", "対象国での販売資格・ショップの出店状況を確認した", p.market_reviewed)}</div><div class="field wide">${check("copy_reviewed", "タイトル・説明文の事実・出品言語を確認した", p.copy_reviewed)}</div>`,
  )}</section><div><section class="panel"><div class="section-head"><h2>不足・再確認項目</h2>${badge(p.readiness_errors.length + "項目", p.readiness_errors.length ? "warn" : "good")}</div>${p.readiness_errors.length ? `<div class="check-list">${p.readiness_errors.map((x) => `<div class="check-item">${icon("warn")}<span>${esc(x)}</span></div>`).join("")}</div>` : note("必要情報のチェックを通過しました。「出品準備完了」に変更できます。", "success")}<div class="spaced">${button("国別のテンプレート設定へ", "nav", "", 'data-value="settings"')}</div></section><section class="panel"><h2>リスク確認の理由</h2><div class="check-list">${p.risk.reasons.length ? p.risk.reasons.map((x) => `<div class="check-item">${icon("warn")}<span>${esc(x.reason)}</span></div>`).join("") : '<p class="muted">キーワードによる要確認項目は未検出です。</p>'}</div><p class="muted spaced">${esc(p.risk.note)}</p><a class="btn spaced" href="${state.data.markets[p.market].seller_url}" target="_blank" rel="noopener noreferrer">Seller Centerを開く ${icon("arrow")}</a></section></div></div>`;
}
function historyView(p) {
  if (!state.history)
    return `<section class="panel">${button("変更履歴を読み込む", "history", "", 'data-id="' + p.id + '"')}</section>`;
  return `<section class="panel"><h2>変更履歴（直近30件）</h2>${state.history.map((h) => `<div class="history"><b>${esc(h.action)}</b><small>${new Date(h.created_at).toLocaleString("ja-JP")}</small><details><summary>保存した内容を見る</summary><pre>${esc(JSON.stringify(h.snapshot, null, 2))}</pre></details></div>`).join("")}</section>`;
}
function ideas() {
  const rows = state.ideas.filter((p) =>
    (p.name + " " + p.keywords.join(" "))
      .toLowerCase()
      .includes(state.ideaSearch.toLowerCase()),
  );
  return `${pageTitle("商品アイデア", "旧版のカタログを、調査のきっかけとして活用します。", button("管理商品へ", "products"))}${note("ここは編集された着想カタログです。需要・競合・売価・送料は未取得で、記載の市場やトレンドも未検証です。商品を登録して根拠を調べてください。", "warn")}<form id="idea-filter" class="actions spaced"><input name="search" aria-label="カタログを検索" placeholder="日本語・英語でアイデアを探す" value="${esc(state.ideaSearch)}"><button class="btn">検索</button></form><div class="idea-grid spaced">${rows.map((p) => `<article class="idea"><div class="product-icon">${icon("box")}</div><h3>${esc(p.name)}</h3><div>${badge("着想 / 未検証")}${badge(p.category)}</div><p>${esc(p.hypothesis)}<br><br>キーワード: ${esc(p.keywords.join(", "))}</p>${button(icon("plus") + "調査候補に追加", "idea-new", "", 'data-id="' + p.id + '"')}</article>`).join("")}</div>`;
}
function settings() {
  const s = state.data.profiles[state.market];
  const fees = [
    ["commission_pct", "販売手数料（%）"],
    ["transaction_pct", "取引・決済手数料（%）"],
    ["service_pct", "サービス料（%）"],
    ["fee_tax_pct", "手数料への税（%）"],
    ["payout_pct", "送金・換金費（手数料控除後の受取額に対する%）"],
    ["ad_pct", "広告費（商品代金に対する%）"],
    ["reserve_pct", "返品・損失引当（商品代金に対する%）"],
    ["fixed_fee_local", "注文ごとの固定手数料（現地通貨）"],
  ];
  return `${pageTitle("設定・データ", "国・ショップ・カテゴリにより条件が異なります。現在の契約条件を確認してください。")}
 <nav class="tabs" aria-label="販売国の設定">${Object.entries(
   state.data.markets,
 )
   .map(
     ([k, m]) =>
       `<button data-action="market" data-value="${k}" class="${k === state.market ? "active" : ""}">${k} ${m.name}</button>`,
   )
   .join("")}</nav>
 <section class="panel"><div class="section-head"><div><h2>${state.data.markets[state.market].name} / ${state.data.markets[state.market].currency}</h2><p>数値の初期値は空欄です。未入力を0%として計算しません。</p></div><a class="btn" href="${state.data.markets[state.market].seller_url}" target="_blank" rel="noopener noreferrer">Seller Center ${icon("arrow")}</a></div>
 <form id="profile-form"><div class="form-grid">${field("jpy_per_local", `1 ${state.data.markets[state.market].currency} あたりの日本円`, s.jpy_per_local, { type: "number", help: "入金時の実効為替または保守的な想定レート。ライブ為替ではありません。" })}${field("target_margin_pct", "目標売上利益率（%）", s.target_margin_pct, { type: "number" })}${fees.map(([k, l]) => field(k, l, s[k], { type: "number" })).join("")}${[
   "commission",
   "transaction",
   "service",
 ]
   .map((kind, i) =>
     field(
       kind + "_basis",
       ["販売手数料", "取引・決済手数料", "サービス料"][i] + "の課金基準",
       s[kind + "_basis"],
       {
         type: "select",
         options: [
           ["item", "値引き後の商品代金"],
           ["order", "商品代金＋購入者送料"],
         ],
       },
     ),
   )
   .join("")}
 <div class="field wide">${note("モデルに合わない段階料率・上限・免除・税控除等は自動計算しません。対象商品の実効率またはその他経費で調整し、実際の精算明細と照合してください。")}</div>
 ${field("fee_source_url", "手数料の確認先URL", s.fee_source_url, { type: "url" })}${field("fx_source_url", "為替の確認先URL", s.fx_source_url, { type: "url" })}${field("checked_on", "条件を確認した日", s.checked_on, { type: "date" })}<div class="field">${check("verified", "自分のショップ・カテゴリの全費用と為替を確認した（30日有効）", s.verified)}</div>
 <h3 class="form-section field wide">ストレス条件（同時に悪化した場合）</h3>${field("fx_stress_pct", "円換算レートの下落率（%）", s.fx_stress_pct, { type: "number" })}${field("shipping_stress_pct", "国際送料の上昇率（%）", s.shipping_stress_pct, { type: "number" })}${field("price_stress_pct", "販売価格の下落率（%）", s.price_stress_pct, { type: "number" })}
 <h3 class="form-section field wide">出品仕様の確認</h3><div class="field wide">${note("公式の国別・カテゴリ別テンプレートの完全な公開仕様は未検証です。文字数の初期値120/3000はこのアプリの暫定上限です。最新のSeller Centerテンプレートで実際の上限・必須属性・画像・物流・言語を確認して更新してください。", "warn")}</div>
 ${field("title_limit", "タイトル文字数上限（暫定値・要確認）", s.title_limit, { type: "number", step: 1 })}${field("description_limit", "説明文文字数上限（暫定値・要確認）", s.description_limit, { type: "number", step: 1 })}${field("template_source_url", "テンプレートの確認先URL", s.template_source_url, { type: "url" })}${field("template_checked_on", "テンプレート確認日", s.template_checked_on, { type: "date" })}${field("template_note", "対象カテゴリ・テンプレート版・必須属性・物流・言語の確認メモ", s.template_note, { type: "textarea", wide: true })}<div class="field wide">${check("template_confirmed", "対象国・カテゴリの最新テンプレートと必要な属性を確認した（30日有効）", s.template_confirmed)}</div>${inlineError()}</div>
 <div class="form-actions"><small>変更すると、この国の承認済み商品は調査中へ戻ります。</small><button class="btn primary">国別設定を保存</button></div></form></section>
 <section class="panel"><div class="section-head"><div><h2>バックアップとデータ移行</h2><p>バックアップにAPIキー・パスワード・ログインセッションは含めません。</p></div>${button(icon("download") + "JSONバックアップ", "backup")}</div>${note("復元は商品が空の環境で行います。既存データは上書きしません。復元した承認状態と確認チェックは再確認が必要です。バックアップには仕入れ情報が含まれるため大切に保管してください。")}<form id="restore-form" class="form-grid spaced"><label class="field wide"><span>復元するバックアップJSON</span><input name="backup" type="file" accept=".json,application/json" required class="file-input"></label>${inlineError()}<button class="btn">空の環境に復元する</button></form></section>
 <section class="panel"><div class="section-head"><div><h2>商品CSVを取り込む</h2><p>新規候補を追加します。同じ国の同じSKU（空なら商品名）はスキップし、編集済みデータは保持します。</p></div>${button("入力テンプレート", "input-template")}</div><form id="import-form" class="form-grid"><label class="field wide"><span>UTF-8 CSV（1回500件まで）</span><input name="csv" type="file" accept=".csv,text/csv" required class="file-input"></label>${inlineError()}<button class="btn">候補として取り込む</button></form></section>`;
}
function preparations() {
  const rows = state.data.products.filter((p) =>
    ["approved", "ready"].includes(p.status),
  );
  return `${pageTitle("出品準備", "必要情報を揃え、Seller Centerでの最終確認につなげます。")}${note("生成するCSVは出品準備・転記用です。Shopee公式アップロード形式としての互換性は未検証です。対象国の最新テンプレートに転記し、Seller Centerで内容を確認してください。このアプリからの自動出品はありません。", "warn")}
 <section class="panel spaced"><div class="section-head"><div><h2>国別に準備CSVを作成</h2><p>「出品準備完了」の全件を再検証し、不備があればダウンロードを止めます。</p></div></div>${Object.entries(
   state.data.markets,
 )
   .map(([k, m]) => {
     const ready = rows.filter(
       (p) => p.market === k && p.status === "ready",
     ).length;
     return `<div class="market-row"><span class="market-code">${k}</span><div class="market-info"><b>${m.name}</b><small>${ready}件が出品準備完了 / ${m.currency}</small></div>${button(icon("download") + "CSV", "export", "", `data-value="${k}" ${ready ? "" : "disabled"}`)}</div>`;
   })
   .join("")}</section>
 <section class="panel table-panel"><div class="toolbar"><h2>承認後の準備状況</h2></div>${rows.length ? `<div class="table-wrap"><table class="products"><thead><tr><th>商品</th><th>状態</th><th>不足</th><th>操作</th></tr></thead><tbody>${rows.map((p) => `<tr><td class="product-td"><button class="product-name" data-action="detail-prep" data-id="${p.id}">${esc(p.name)} / ${p.market}</button></td><td>${statusTag(p.status)}</td><td>${badge(p.readiness_errors.length ? p.readiness_errors.length + "項目を確認" : "入力チェック通過", p.readiness_errors.length ? "warn" : "good")}</td><td>${button("詳細を確認", "detail-prep", "", 'data-id="' + p.id + '"')}</td></tr>`).join("")}</tbody></table></div>` : empty("承認済みの商品がありません", "商品詳細で費用とリスクを確認し、承認するとここに表示されます。", "products", "商品リサーチへ")}</section>`;
}
function simulator() {
  if (!state.simProduct) {
    state.simProduct = {
      ...state.data.product_defaults,
      name: "単品試算",
      market: state.market,
    };
    state.simProfile = { ...state.data.profiles[state.market] };
  }
  const p = state.simProduct,
    s = state.simProfile;
  return `${pageTitle("利益シミュレーター", "保存済みの条件を使って試算できます。ここでの入力は商品や国別設定へ保存されません。", button("架空の入力例で試す", "sim-example"))}${note("1商品・1注文を想定した計算です。下の国を変更すると保存済みの国別費用条件に切り替わります。")}
 <form id="simulation-form" class="panel spaced"><div class="form-grid">${field("market", "販売国", p.market, { type: "select", options: Object.entries(state.data.markets).map(([k, m]) => [k, m.name]) })}${field("price_local", "販売価格（現地通貨）", p.price_local, { type: "number" })}${Object.entries(
   costLabels,
 )
   .map(([k, l]) => field(k, l + "（JPY）", p[k], { type: "number" }))
   .join(
     "",
   )}${field("buyer_shipping_local", "購入者送料（現地通貨）", p.buyer_shipping_local, { type: "number" })}${field("discount_pct", "値引き（%）", p.discount_pct, { type: "number" })}<div class="field wide"><h3>この試算だけの手数料・為替</h3><small>設定済み数値を読み込みます。変更した場合は未確認条件の試算として表示します。</small></div>${["jpy_per_local", "commission_pct", "transaction_pct", "service_pct", "fee_tax_pct", "payout_pct", "ad_pct", "reserve_pct", "fixed_fee_local"].map((k) => field(k, { jpy_per_local: "1現地通貨あたりの日本円", commission_pct: "販売手数料（%）", transaction_pct: "取引手数料（%）", service_pct: "サービス料（%）", fee_tax_pct: "手数料への税（%）", payout_pct: "送金費（%）", ad_pct: "広告費（%）", reserve_pct: "返品引当（%）", fixed_fee_local: "固定手数料（現地通貨）" }[k], s[k], { type: "number" })).join("")}${inlineError()}</div><div class="form-actions"><small>ゼロの費用も明示的に0を入力してください。</small><button class="btn primary">利益を計算する</button></div></form>${state.simResult ? financeResult(state.simResult, p.market, s) : ""}`;
}
function comparePage() {
  const rows = state.data.products.filter((p) => state.ids.has(p.id));
  const labels = [
    ["販売国", (p) => state.data.markets[p.market].name],
    ["販売価格", (p) => money(p.price_local, p.market)],
    [
      "試算利益",
      (p) => (p.finance.available ? yen(p.finance.profit_jpy) : "未算出"),
    ],
    [
      "ストレス時利益",
      (p) =>
        p.finance.available ? yen(p.finance.stress_profit_jpy) : "未算出",
    ],
    [
      "需要（主観評価）",
      (p) =>
        ({ unknown: "未確認", low: "低い", medium: "中程度", high: "高い" })[
          p.demand_level
        ],
    ],
    ["観測競合件数", (p) => p.competitor_count ?? "未確認"],
    ["観測競合価格", (p) => money(p.competitor_price_local, p.market)],
    ["表示販売数", (p) => p.observed_sales ?? "未確認"],
    ["観測日", (p) => p.research_date || "未入力"],
    ["観測条件", (p) => p.research_note || "未入力"],
    [
      "リスク理由",
      (p) =>
        p.risk.reasons.map((x) => x.reason).join(" / ") || "未検出・要手動確認",
    ],
  ];
  return `${pageTitle("商品を比較する", "入力した観測情報と計算条件を、横並びで確認します。", button("一覧へ戻る", "products"))}${note("他国の販売価格や国際送料は自動では取得しません。同一商品を別の国へ複製し、その国の売価・送料・観測データを入力すると比較できます。")}<section class="panel comparison spaced"><table><thead><tr><th>比較項目</th>${rows.map((p) => `<th>${esc(p.name)}<br>${p.market}</th>`).join("")}</tr></thead><tbody>${labels.map(([l, fn]) => `<tr><th>${l}</th>${rows.map((p) => `<td>${esc(fn(p))}</td>`).join("")}</tr>`).join("")}<tr><th>出典</th>${rows.map((p) => `<td>${p.research_source_url ? `<a href="${esc(p.research_source_url)}" target="_blank" rel="noopener noreferrer">観測元を開く</a>` : "未登録"}</td>`).join("")}</tr></tbody></table></section><section class="panel"><div class="section-head"><h2>比較の理由を確認</h2>${button("計算結果から理由を整理", "compare-explain")}</div><div id="comparison-explanation" class="readable">${state.comparison ? esc(state.comparison.explanation + "\n\n" + state.comparison.items.map((x) => x.name + " / " + x.market + "\n" + x.reason).join("\n\n")) : "根拠のある数値だけで比較します。需要確率や売上予測を生成することはありません。"}</div></section>`;
}
function newProduct(seed = {}, clone = false) {
  state.newSeed = { ...state.data.product_defaults, ...seed };
  const p = state.newSeed;
  modal.innerHTML = `<div class="dialog-head"><h2 id="modal-title">${clone ? "別の国で調査する" : "商品を登録"}</h2><button type="button" class="modal-close" data-action="close-modal" aria-label="閉じる">×</button></div><form id="new-form"><div class="form-grid">${field("name", "商品名", p.name, { required: true })}${field("market", "販売国", p.market, { type: "select", options: Object.entries(state.data.markets).map(([k, m]) => [k, m.name]) })}${field("sku", "Seller SKU", p.sku)}${field("category", "カテゴリ（調査用）", p.category)}${field("english_name", "英語の商品名", p.english_name, { wide: true })}${field("supplier_url", "仕入れ先URL", p.supplier_url, { type: "url", wide: true })}<div class="field wide">${note(clone ? "共通の仕様と仕入れ情報をコピーします。国ごとに異なる売価・国際送料・物流・調査データ・承認は引き継ぎません。" : "費用・調査データ・出品情報は登録後に詳しく入力できます。")}</div>${inlineError()}</div><div class="form-actions"><button class="btn primary">候補として登録</button></div></form>`;
  modal.showModal();
  $("input", modal)?.focus();
}
async function download(path, filename) {
  const res = await fetch("/api" + path, { credentials: "same-origin" });
  if (!res.ok) {
    const body = await res.json();
    throw new Error(body.error || "ダウンロードに失敗しました。");
  }
  saveBlob(await res.blob(), filename);
}
function saveBlob(blob, filename) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
async function openIdeas() {
  if (!guard()) return;
  if (!state.ideas.length) state.ideas = await api("/ideas");
  state.page = "ideas";
  render();
  window.scrollTo(0, 0);
}
function loginView() {
  state.data = null;
  app.innerHTML = `<main class="login" id="main"><section class="login-card"><img src="/assets/mark.svg" alt=""><div class="eyebrow">SHOPEE RESEARCH DESK</div><h1>自分のペースで、<br>世界に売る準備を。</h1><p>商品リサーチと利益分析のための<br>あなた専用ワークスペース。</p><form id="login-form"><label class="field"><span>ワークスペースのパスワード</span><input name="password" type="password" autocomplete="current-password" required maxlength="1024"></label><div class="inline-error" role="alert"></div><button class="btn primary">ワークスペースを開く ${icon("arrow")}</button></form><small>${icon("lock")} 商品データはサーバーに保存されます。<br>設定したAPP_PASSWORDでログインしてください。</small></section></main>`;
}
async function start() {
  try {
    const s = await api("/session");
    state.csrf = s.csrf;
    if (s.authenticated) {
      await refresh();
      render();
    } else loginView();
  } catch (e) {
    app.innerHTML = `<main class="login"><section class="login-card"><h1>接続できませんでした</h1><p>${esc(e.message)}</p>${button("再試行", "retry")}</section></main>`;
  }
}

document.addEventListener("input", (event) => {
  if (
    event.target.closest(
      "#product-form,#profile-form,#new-form,#simulation-form",
    )
  )
    state.dirty = true;
});
document.addEventListener("change", async (event) => {
  const id = event.target.dataset.select;
  if (id) {
    if (event.target.checked) {
      if (state.ids.size >= 6) {
        event.target.checked = false;
        return toast("比較は6件まで選べます。", true);
      }
      state.ids.add(id);
    } else state.ids.delete(id);
    render();
  }
  if (
    event.target.closest("#simulation-form") &&
    event.target.name === "market"
  ) {
    const form = $("#simulation-form");
    state.simProduct = formData(
      form,
      state.simProduct,
      state.data.product_defaults,
    );
    state.simProfile = { ...state.data.profiles[event.target.value] };
    state.simResult = null;
    state.dirty = false;
    render();
  }
});
window.addEventListener("beforeunload", (e) => {
  if (state.dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
modal.addEventListener("cancel", (event) => {
  if (state.reauthMode) {
    event.preventDefault();
    endReauthentication();
    return;
  }
  if (!guard()) event.preventDefault();
});
document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action,
    id = target.dataset.id,
    value = target.dataset.value;
  try {
    if (action === "retry") return await start();
    if (action === "reauth-cancel") return endReauthentication();
    if (action === "nav") {
      if (value === "settings" && current()) state.market = current().market;
      return go(value);
    }
    if (action === "products") return go("products");
    if (action === "detail" || action === "detail-prep") {
      state.history = null;
      return go("detail", id, action === "detail-prep" ? "prep" : "basic");
    }
    if (action === "tab") {
      if (guard()) {
        state.tab = value;
        state.suggestion = null;
        render();
      }
      return;
    }
    if (action === "market") {
      if (guard()) {
        state.market = value;
        render();
      }
      return;
    }
    if (action === "new") return newProduct();
    if (action === "close-modal") {
      if (guard()) modal.close();
      return;
    }
    if (action === "ideas") return await openIdeas();
    if (action === "idea-new") {
      const idea = state.ideas.find((p) => p.id === id);
      return newProduct({
        name: idea.name,
        category: idea.category,
        notes: "着想カタログ（未検証）: " + idea.hypothesis,
      });
    }
    if (action === "clone") {
      if (!guard()) return;
      const p = state.data.products.find((p) => p.id === id),
        seed = {};
      for (const k of [
        "name",
        "sku",
        "category",
        "english_name",
        "facts_en",
        "supplier_name",
        "supplier_url",
        "cost_jpy",
        "domestic_shipping_jpy",
        "packaging_jpy",
      ])
        seed[k] = p[k];
      seed.market = Object.keys(state.data.markets).find((k) => k !== p.market);
      return newProduct(seed, true);
    }
    if (action === "logout") {
      if (!guard()) return;
      await api("/logout", { method: "POST" });
      state.page = "dashboard";
      state.productId = null;
      return await start();
    }
    if (action === "status") {
      if (state.dirty) return toast("先に変更を保存してください。", true);
      target.disabled = true;
      await api("/products/" + id + "/status", {
        method: "POST",
        body: { status: $("#status-change").value, version: current().version },
      });
      await refresh();
      render();
      return toast("状態を更新しました。");
    }
    if (action === "generate") {
      if (state.dirty) return toast("先に商品情報を保存してください。", true);
      target.disabled = true;
      target.textContent = "下書き案を作成中…";
      state.suggestion = await api("/products/" + id + "/copy", {
        method: "POST",
      });
      $("#suggestion").innerHTML = suggestionHtml();
      return;
    }
    if (action === "use-suggestion") {
      const form = $("#product-form"),
        s = state.suggestion;
      form.elements.title.value = s.title;
      form.elements.description.value = s.description;
      form.elements.listing_language.value = s.language;
      state.pendingCopySource = s.source;
      state.dirty = true;
      state.suggestion = null;
      $("#suggestion").innerHTML = "";
      return toast("編集欄に取り込みました。内容を確認して保存してください。");
    }
    if (action === "dismiss-suggestion") {
      state.suggestion = null;
      $("#suggestion").innerHTML = "";
      return;
    }
    if (action === "history") {
      state.history = await api("/products/" + id + "/history");
      render();
      return;
    }
    if (action === "backup")
      return await download(
        "/backup",
        "shopee_backup_" + new Date().toISOString().slice(0, 10) + ".json",
      );
    if (action === "export")
      return await download(
        "/export/" + value,
        "listing_preparation_" + value + ".csv",
      );
    if (action === "compare") {
      if (state.ids.size < 2) return;
      state.comparison = null;
      return go("compare");
    }
    if (action === "compare-explain") {
      target.disabled = true;
      state.comparison = await api("/compare", {
        method: "POST",
        body: { ids: [...state.ids] },
      });
      $("#comparison-explanation").textContent =
        state.comparison.explanation +
        "\n\n" +
        state.comparison.items
          .map((x) => x.name + " / " + x.market + "\n" + x.reason)
          .join("\n\n");
      return;
    }
    if (action === "input-template")
      return saveBlob(
        new Blob(
          [
            "\uFEFFname,market,sku,category,supplier_url,cost_jpy,domestic_shipping_jpy,international_shipping_jpy,packaging_jpy,customs_jpy,other_jpy,price_local\r\n",
          ],
          { type: "text/csv;charset=utf-8" },
        ),
        "product_input_template.csv",
      );
    if (action === "sim-example") {
      if (!guard()) return;
      state.simProduct = {
        ...state.data.product_defaults,
        name: "架空の単品試算",
        market: "SG",
        cost_jpy: 800,
        domestic_shipping_jpy: 200,
        international_shipping_jpy: 700,
        packaging_jpy: 80,
        customs_jpy: 0,
        other_jpy: 50,
        price_local: 35,
      };
      state.simProfile = {
        ...state.data.profile_defaults,
        jpy_per_local: 100,
        commission_pct: 8,
        transaction_pct: 3,
        service_pct: 0,
        fee_tax_pct: 0,
        payout_pct: 2,
        ad_pct: 2,
        reserve_pct: 3,
        fixed_fee_local: 0,
      };
      state.simResult = await api("/finance", {
        method: "POST",
        body: { product: state.simProduct, profile: state.simProfile },
      });
      render();
      toast("全数値が架空の試算例です。最新相場やShopeeの料率ではありません。");
      return;
    }
  } catch (e) {
    toast(e.message, true);
  } finally {
    if (target.isConnected) {
      target.disabled = false;
      if (action === "generate")
        target.textContent = state.data?.ai_available
          ? "AIで下書き案を作る"
          : "定型の英語案を作る";
    }
  }
});
document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!form.id) return;
  event.preventDefault();
  const submit = $("button[type=submit],button:not([type])", form);
  if (submit) submit.disabled = true;
  try {
    if (form.id === "reauth-form") {
      const result = await api("/login", {
        method: "POST",
        body: { password: form.elements.password.value },
      });
      state.csrf = result.csrf;
      form.elements.password.value = "";
      endReauthentication();
      toast(
        "再ログインしました。入力を確認し、保存をもう一度実行してください。",
      );
      return;
    }
    if (form.id === "login-form") {
      const result = await api("/login", {
        method: "POST",
        body: { password: form.elements.password.value },
      });
      state.csrf = result.csrf;
      form.elements.password.value = "";
      await refresh();
      render();
      return;
    }
    if (form.id === "filter-form") {
      state.search = form.elements.search.value;
      state.filterMarket = form.elements.market.value;
      state.status = form.elements.status.value;
      render();
      return;
    }
    if (form.id === "idea-filter") {
      state.ideaSearch = form.elements.search.value;
      render();
      return;
    }
    if (form.id === "new-form") {
      const p = formData(form, state.newSeed, state.data.product_defaults);
      const result = await api("/products", { method: "POST", body: p });
      state.dirty = false;
      modal.close();
      await refresh();
      go("detail", result.id);
      toast("商品を候補として登録しました。");
      return;
    }
    if (form.id === "product-form") {
      const p = current(),
        data = formData(form, p, state.data.product_defaults);
      if (state.pendingCopySource) {
        data.copy_source = state.pendingCopySource;
      }
      await api("/products/" + p.id, {
        method: "PUT",
        body: { data, version: p.version },
      });
      state.pendingCopySource = null;
      state.dirty = false;
      await refresh();
      render();
      toast(
        "変更を保存しました。必要に応じて確認チェックと承認をやり直してください。",
      );
      return;
    }
    if (form.id === "profile-form") {
      const s = state.data.profiles[state.market],
        data = formData(form, s, state.data.profile_defaults);
      await api("/profiles/" + state.market, {
        method: "PUT",
        body: { data, version: s.version },
      });
      state.dirty = false;
      await refresh();
      render();
      toast("国別設定を保存しました。");
      return;
    }
    if (form.id === "restore-form") {
      const file = form.elements.backup.files[0];
      if (file.size > 4 * 1024 * 1024)
        throw new Error("ファイルは4MB以下にしてください。");
      const json = JSON.parse(await file.text());
      const result = await api("/restore", { method: "POST", body: json });
      await refresh();
      render();
      toast(
        result.restored + "件を復元しました。費用と承認は再確認してください。",
      );
      return;
    }
    if (form.id === "import-form") {
      const file = form.elements.csv.files[0];
      if (file.size > 2 * 1024 * 1024)
        throw new Error("CSVは2MB以下にしてください。");
      const result = await api("/import", {
        method: "POST",
        body: { csv: await file.text() },
      });
      await refresh();
      render();
      toast(
        result.added +
          "件を追加 / 重複" +
          result.skipped +
          "件をスキップしました。",
      );
      return;
    }
    if (form.id === "simulation-form") {
      state.simProduct = formData(
        form,
        state.simProduct,
        state.data.product_defaults,
      );
      const next = formData(
        form,
        state.simProfile,
        state.data.profile_defaults,
      );
      if (Object.keys(next).some((k) => next[k] !== state.simProfile[k]))
        next.verified = false;
      state.simProfile = next;
      state.simResult = await api("/finance", {
        method: "POST",
        body: { product: state.simProduct, profile: next },
      });
      state.dirty = false;
      render();
      return;
    }
  } catch (e) {
    showError(form, e);
  } finally {
    if (submit?.isConnected) submit.disabled = false;
  }
});
start();
