// DOM-independent renderer and interaction tests. These do not replace real browser QA.
import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import fs from "node:fs";
const source = fs.readFileSync(
  new URL("../shopee_workbench/static/app.js", import.meta.url),
  "utf8",
);
const defaults = {
  name: "",
  market: "SG",
  sku: "",
  category: "",
  notes: "",
  cost_jpy: null,
  price_local: null,
  risk_reviewed: false,
};
const product = {
  ...defaults,
  id: "p1",
  version: 1,
  name: '<script>alert("x")</script>',
  market: "SG",
  status: "candidate",
  category: "Stationery",
  sku: "N1",
  demand_level: "unknown",
  competitor_count: null,
  observed_sales: null,
  research_source_url: "",
  research_note: "",
  research_date: "",
  readiness_errors: ["カテゴリIDが未入力です。"],
  risk: { level: "review", reasons: [{ reason: "要確認" }], note: "未検証" },
  finance: { available: false, missing: ["cost_jpy"] },
  updated_at: "2026-10-17T12:00:00Z",
};
const profile = {
  version: 1,
  checked_on: "",
  verified: false,
  title_limit: 120,
  description_limit: 3000,
  template_note: "",
  target_margin_pct: 25,
  fx_stress_pct: 10,
  shipping_stress_pct: 20,
  price_stress_pct: 10,
};
function fixture() {
  const listeners = {};
  const nodes = new Map();
  function node(key) {
    if (!nodes.has(key))
      nodes.set(key, {
        innerHTML: "",
        textContent: "",
        className: "",
        addEventListener() {},
        querySelector() {
          return null;
        },
        showModal() {
          this.open = true;
        },
        close() {
          this.open = false;
        },
        classList: { add() {} },
        scrollIntoView() {},
      });
    return nodes.get(key);
  }
  const context = vm.createContext({
    document: {
      querySelector: node,
      addEventListener: (name, fn) => (listeners[name] = fn),
      body: { append() {} },
      createElement: () => ({ click() {}, remove() {} }),
    },
    window: { addEventListener() {}, scrollTo() {} },
    fetch: async () => {
      throw new Error("disabled");
    },
    setTimeout: () => 0,
    clearTimeout() {},
    confirm: () => true,
    URL,
    Blob,
    console,
  });
  vm.runInContext(source.replace(/\nstart\(\);\s*$/, ""), context);
  const data = {
    markets: {
      SG: {
        name: "シンガポール",
        currency: "SGD",
        seller_url: "https://seller.shopee.sg/",
      },
      MY: {
        name: "マレーシア",
        currency: "MYR",
        seller_url: "https://seller.shopee.com.my/",
      },
    },
    statuses: {
      candidate: "候補",
      researching: "調査中",
      approved: "承認済み",
      ready: "出品準備完了",
      rejected: "見送り",
    },
    profiles: { SG: { ...profile }, MY: { ...profile } },
    product_defaults: defaults,
    profile_defaults: profile,
    products: [product, { ...product, id: "p2", market: "MY", name: "Other" }],
    ai_available: false,
  };
  context.fixtureData = data;
  vm.runInContext(
    'state.data=fixtureData; state.productId="p1"; state.simProduct={...fixtureData.product_defaults,name:"試算"}; state.simProfile=fixtureData.profiles.SG;',
    context,
  );
  return {
    context,
    nodes,
    listeners,
    run: (code) => vm.runInContext(code, context),
  };
}
test("all screens render without runtime errors and escape product content", () => {
  const f = fixture();
  for (const page of [
    "dashboard",
    "products",
    "finance",
    "settings",
    "prep",
    "compare",
    "ideas",
  ]) {
    f.run(`state.page='${page}'; state.ids=new Set(['p1','p2']); render();`);
    const html = f.nodes.get("#app").innerHTML;
    assert.ok(html.includes("Research Desk"));
    assert.ok(!html.includes("<script>alert("));
  }
  for (const tab of ["basic", "finance", "copy", "prep", "history"]) {
    f.run(`state.page='detail';state.tab='${tab}';render();`);
    assert.ok(f.nodes.get("#app").innerHTML.includes("&lt;script&gt;"));
  }
});
test("filters distinguish markets and statuses without fabricated observations", () => {
  const f = fixture();
  f.run(
    'state.filterMarket="MY";state.search="Other";state.page="products";render();',
  );
  const html = f.nodes.get("#app").innerHTML;
  assert.ok(html.includes("Other"));
  assert.ok(!html.includes("&lt;script&gt;"));
  assert.ok(html.includes("需要未確認"));
  assert.ok(html.includes("未算出"));
});
test("form serialization keeps unrendered fields and explicit zero costs", () => {
  const f = fixture();
  f.context.testForm = {
    elements: [
      { name: "cost_jpy", type: "number", value: "0" },
      { name: "price_local", type: "number", value: "" },
      { name: "risk_reviewed", type: "checkbox", checked: true },
    ],
  };
  const value = f.run(
    'formData(testForm,{...state.data.product_defaults,name:"Notebook",notes:"keep"},state.data.product_defaults)',
  );
  assert.equal(value.cost_jpy, 0);
  assert.equal(value.price_local, null);
  assert.equal(value.notes, "keep");
  assert.equal(value.risk_reviewed, true);
});
test("comparison cap is enforced and selected products survive filters", async () => {
  const f = fixture();
  f.run('state.ids=new Set(["1","2","3","4","5","6"]);');
  const el = { dataset: { select: "7" }, checked: true, closest: () => null };
  await f.listeners.change({ target: el });
  assert.equal(el.checked, false);
  assert.equal(f.run("state.ids.size"), 6);
});
test("unsaved navigation can be cancelled and copy provenance is cleared on discard", () => {
  const f = fixture();
  f.context.confirm = () => false;
  f.run('state.dirty=true;state.page="detail";go("settings");');
  assert.equal(f.run("state.page"), "detail");
  f.context.confirm = () => true;
  f.run('state.pendingCopySource="openai";go("settings");');
  assert.equal(f.run("state.page"), "settings");
  assert.equal(f.run("state.pendingCopySource"), null);
});
test("copy suggestions are escaped and do not replace stored descriptions", () => {
  const f = fixture();
  f.run(
    'state.suggestion={source:"openai",language:"en",title:"<img src=x onerror=alert(1)>",description:"new",review_notes:"review"};',
  );
  const html = f.run("suggestionHtml()");
  assert.ok(html.includes("&lt;img"));
  assert.ok(!html.includes("<img src=x"));
  assert.equal(f.run("state.data.products[0].name"), product.name);
});

test('expired authentication preserves an open editor and its unsaved input', async () => {
  const f = fixture();
  const dialog = f.nodes.get('#modal');
  const originalEditor = { value: 'keep my unsaved input' };
  const saveButton = { disabled: true };
  dialog.childNodes = [originalEditor];
  dialog.open = true;
  dialog.replaceChildren = function (...children) { this.childNodes = children; };
  dialog.querySelectorAll = () => [saveButton];
  f.context.fetch = async (url) => url === '/api/session'
    ? { ok: true, json: async () => ({ csrf: 'login-csrf' }) }
    : { ok: false, status: 401, headers: { get: () => 'application/json' }, json: async () => ({ error: 'ログインしてください。' }) };
  f.run('state.dirty=true;');
  await assert.rejects(f.run('api("/products/p1",{method:"PUT",body:{}})'), /ログイン/);
  assert.equal(f.run('state.reauthMode'), true);
  assert.equal(f.run('state.dirty'), true);
  f.run('endReauthentication();');
  assert.equal(dialog.childNodes[0], originalEditor);
  assert.equal(originalEditor.value, 'keep my unsaved input');
  assert.equal(saveButton.disabled, false);
});
