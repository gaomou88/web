/* 行情：指数（每人最多 5 个，可自选）、我的个股（登录后添加）、成交最多（成交额 / 成交量）。
   数据来自新浪 / 腾讯 / Yahoo 实时抓取；价格变化只更新对应单元格。点击代码可跳转第三方网站看 K 线。 */
import { AuthError, MembersOnly, api, compact, dirClass, fmt, h, live, lockPanel, signed, symbolInput, telemetry, toast, ui } from "../core.js";
import { sparkline } from "../chart.js";
import { prefs, t } from "../i18n.js";
import { marketStrip } from "./calendar.js";

export const STOCK_SITES = [
  { id: "sina", zh: "新浪财经", en: "Sina Finance", url: (s) => `https://stock.finance.sina.com.cn/usstock/quotes/${s.replace(".", "")}.html` },
  { id: "xueqiu", zh: "雪球", en: "Xueqiu", url: (s) => `https://xueqiu.com/S/${s.replace(".", "-")}` },
  { id: "futu", zh: "富途牛牛", en: "Futu", url: (s) => `https://www.futunn.com/stock/${s.replace(".", "-")}-US` },
  { id: "yahoo", zh: "Yahoo Finance", en: "Yahoo Finance", url: (s) => `https://finance.yahoo.com/quote/${s.replace(".", "-")}/chart` },
  { id: "tradingview", zh: "TradingView", en: "TradingView", url: (s) => `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(s.replace(".", "."))}` },
];
const INDEX_SITES = [
  { id: "yahoo", zh: "Yahoo Finance", en: "Yahoo Finance", url: (c) => `https://finance.yahoo.com/quote/${encodeURIComponent(c.yahoo)}/chart` },
  { id: "tradingview", zh: "TradingView", en: "TradingView", url: (c) => `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(c.tv)}` },
];

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#47c6c0";
const money = (v) => (!v ? "—" : `$${compact(v)}`);
const pct = (v) => (v == null ? "—" : signed(v, 2, "%"));

/** 跳转第三方网站前：让用户选择网站，并提示离开本站的风险。 */
export function openExternal(title, sites, arg) {
  const zh = prefs.lang === "zh";
  const remembered = prefs.getJSON("mg.ext.site", "");
  const dlg = h("dialog", { class: "glass ext-dlg" });
  const remember = h("input", { type: "checkbox" });
  const go = (site) => {
    if (remember.checked) prefs.setJSON("mg.ext.site", site.id);
    dlg.close();
    window.open(site.url(arg), "_blank", "noopener,noreferrer");
  };
  dlg.append(h("div", { class: "dialog-form" },
    h("h2", {}, t("extTitle").replace("{s}", title)),
    h("p", { class: "ext-warn" }, "⚠️ ", t("extWarn")),
    h("div", { class: "ext-sites" }, sites.map((s) => h("button", { class: `btn ${s.id === remembered ? "primary" : ""}`, onclick: () => go(s) }, zh ? s.zh : s.en))),
    h("label", { class: "small muted", style: { display: "flex", gap: "8px", alignItems: "center" } }, remember, t("extRemember")),
    h("div", { class: "row" }, h("span", { class: "spacer" }), h("button", { class: "btn", onclick: () => dlg.close() }, t("cancel")))));
  dlg.addEventListener("close", () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
}

export default function quotesView(el) {
  let d = null;              // /api/market
  let tab = prefs.getJSON("mg.q.tab", "mine");
  let rankKind = prefs.getJSON("mg.q.rank", "amount");
  const rows = new Map();    // symbol -> { tr, cells }
  const offs = [];
  const body = h("div", { style: { display: "grid", gap: "16px" } });
  el.append(body);

  const head = h("div", { class: "row" });
  const strip = h("div");
  const idxGrid = h("div", { class: "grid-5" });
  const tabBox = h("div");

  function needLogin() {
    toast(t("loginToEdit"));
    ui.onAuth?.();
  }

  /* ---------- 指数 ---------- */
  function renderIndices() {
    const cat = Object.fromEntries(d.catalog.map((c) => [c.code, c]));
    idxGrid.replaceChildren(...d.indices.map((code) => {
      const q = d.index_quotes[code];
      const c = cat[code] || { zh: code, en: code };
      return h("button", { class: "tile idx-tile", type: "button", title: t("viewChart"), onclick: () => openExternal(prefs.lang === "zh" ? c.zh : c.en, INDEX_SITES, c) },
        h("div", { class: "name" }, prefs.lang === "zh" ? c.zh : c.en),
        h("div", { class: `px ${dirClass(q?.change)}` }, q ? fmt(q.live ?? q.price, 2) : "—"),
        h("div", { class: `chg ${dirClass(q?.change)}` }, q ? `${signed(q.change, 2)}  ${pct(q.change_pct)}` : t("noData")),
        q?.spark?.length > 3 ? sparkline(q.spark, { w: 150, h: 30, color: cssVar(q.change >= 0 ? "--up" : "--down") }) : null);
    }));
  }

  function editIndices() {
    if (!d.logged_in) { needLogin(); return; }
    const chosen = new Set(d.indices);
    const dlg = h("dialog", { class: "glass" });
    const err = h("div", { class: "err" });
    const count = h("span", { class: "muted small" });
    const boxes = d.catalog.map((c) => {
      const cb = h("input", { type: "checkbox", value: c.code, checked: chosen.has(c.code), onchange: () => {
        cb.checked ? chosen.add(c.code) : chosen.delete(c.code);
        if (chosen.size > d.max_indices) { cb.checked = false; chosen.delete(c.code); toast(t("maxIndices").replace("{n}", d.max_indices)); }
        count.textContent = `${chosen.size} / ${d.max_indices}`;
      } });
      return h("label", { class: "chk" }, cb, `${prefs.lang === "zh" ? c.zh : c.en}`, h("span", { class: "muted small" }, ` ${c.code}`));
    });
    count.textContent = `${chosen.size} / ${d.max_indices}`;
    dlg.append(h("form", { class: "dialog-form", onsubmit: async (e) => {
      e.preventDefault();
      try {
        const order = [...d.indices.filter((x) => chosen.has(x)), ...[...chosen].filter((x) => !d.indices.includes(x))];
        await api("/api/market/indices", { method: "PUT", body: { codes: order } });
        dlg.close(); load();
      } catch (ex) { err.textContent = ex.message; }
    } },
      h("h2", {}, t("editIndices")), h("p", { class: "muted small" }, t("editIndicesDesc").replace("{n}", d.max_indices)),
      h("div", { class: "chk-grid" }, boxes), err,
      h("div", { class: "row" }, count, h("span", { class: "spacer" }),
        h("button", { class: "btn", type: "button", onclick: () => dlg.close() }, t("cancel")),
        h("button", { class: "btn primary", type: "submit" }, t("save")))));
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg); dlg.showModal();
  }

  /* ---------- 个股表格 ---------- */
  const COLS = () => [t("symbol"), t("last"), t("chg"), t("chgPct"), t("extHours"), t("openHL"), t("prevClose"), t("volume"), t("amount"), t("mktcap")];

  function stockCells(sym, q, extraFirst) {
    const live = q?.live ?? q?.price;
    return {
      sym: h("td", {}, extraFirst || null, h("button", { class: "linkbtn sym-link", onclick: () => openExternal(sym, STOCK_SITES, sym) }, h("b", {}, sym)),
        q?.name ? h("div", { class: "muted small ellipsis" }, q.name) : null),
      last: h("td", { class: `num ${dirClass(q?.change)}` }, live != null ? fmt(live, 2) : "—"),
      chg: h("td", { class: `num ${dirClass(q?.change)}` }, signed(q?.change, 2)),
      pct: h("td", { class: `num ${dirClass(q?.change)}` }, pct(q?.change_pct)),
      ext: h("td", { class: `num ${dirClass(q?.ext_pct)}` }, q?.ext_price ? h("div", {}, fmt(q.ext_price, 2), h("div", { class: "small" }, pct(q.ext_pct))) : "—"),
      ohl: h("td", { class: "num small" }, q ? `${fmt(q.open, 2)} / ${fmt(q.high, 2)} / ${fmt(q.low, 2)}` : "—"),
      prev: h("td", { class: "num" }, fmt(q?.prev_close, 2)),
      vol: h("td", { class: "num" }, compact(q?.volume)),
      amt: h("td", { class: "num" }, money(q?.amount)),
      cap: h("td", { class: "num" }, money(q?.mktcap)),
    };
  }

  function updateStock(sym, flash) {
    const r = rows.get(sym);
    if (!r) return;
    const q = d.snaps[sym];
    const prev = r.price;
    const c = stockCells(sym, q);
    for (const k of Object.keys(c)) if (k !== "sym") r.c[k].replaceWith(c[k]);
    Object.assign(r.c, { ...c, sym: r.c.sym });
    const now = q?.live ?? q?.price;
    if (flash && prev != null && now != null && now !== prev) {
      c.last.classList.add(now > prev ? "tick-up" : "tick-down");
      setTimeout(() => c.last.classList.remove("tick-up", "tick-down"), 600);
    }
    r.price = now;
  }

  function renderMine() {
    rows.clear();
    if (!d.logged_in) {
      return h("div", { class: "empty" }, h("p", {}, t("mineLogin")), h("button", { class: "btn primary", onclick: needLogin }, t("login")));
    }
    const ac = symbolInput({ placeholder: t("pfAddPh"), onPick: () => form.requestSubmit() });
    const form = h("form", { class: "row", onsubmit: async (e) => {
      e.preventDefault(); ac.close();
      const sym = ac.input.value.trim().toUpperCase();
      if (!sym) return;
      try {
        const r = await api("/api/market/stocks", { method: "POST", body: { symbol: sym } });
        d.stocks.push(r.symbol); d.snaps[r.symbol] = r.snap; ac.input.value = "";
        renderTab();
      } catch (ex) { if (ex instanceof AuthError) needLogin(); else toast(ex.message); }
    } }, ac.wrap, h("button", { class: "btn primary", type: "submit" }, t("pfAdd")), h("span", { class: "spacer" }),
      h("span", { class: "muted small" }, `${d.stocks.length} / ${d.max_stocks}`));
    const tbody = h("tbody");
    for (const sym of d.stocks) {
      const c = stockCells(sym, d.snaps[sym]);
      const del = h("td", {}, h("button", { class: "btn danger small-btn", "aria-label": t("remove"), onclick: async () => {
        try {
          const r = await api(`/api/market/stocks/${encodeURIComponent(sym)}`, { method: "DELETE" });
          d.stocks = d.stocks.filter((x) => x !== sym); renderTab();
          if (r.kept_in_portfolio) toast(t("keptInPf"), 5000);
        } catch (ex) { toast(ex.message); }
      } }, "✕"));
      const tr = h("tr", {}, Object.values(c), del);
      rows.set(sym, { tr, c, price: d.snaps[sym]?.live ?? d.snaps[sym]?.price });
      tbody.append(tr);
    }
    return h("div", {}, form,
      h("div", { class: "table-wrap", style: { marginTop: "10px" } }, h("table", { class: "q-table" },
        h("thead", {}, h("tr", {}, [...COLS(), ""].map((x, i) => h("th", { class: i && i < 10 ? "num" : "" }, x)))),
        d.stocks.length ? tbody : h("tbody", {}, h("tr", {}, h("td", { colspan: 11, class: "empty" }, t("mineEmpty")))))));
  }

  function renderRank() {
    const r = d.rank;
    if (!r) return h("div", { class: "empty" }, t("noData"));
    const list = r[rankKind] || [];
    const seg = h("div", { class: "seg", role: "group" }, ["amount", "volume"].map((k) => h("button", { "aria-pressed": String(k === rankKind), onclick: () => {
      rankKind = k; prefs.setJSON("mg.q.rank", k); renderTab();
    } }, t(k === "amount" ? "byAmount" : "byVolume"))));
    return h("div", {},
      h("div", { class: "row" }, seg, h("span", { class: "spacer" }), h("span", { class: "muted small" }, `${t("updatedAt")} ${new Date(r.updated * 1000).toLocaleTimeString()}`)),
      h("div", { class: "table-wrap", style: { marginTop: "10px" } }, h("table", { class: "q-table" },
        h("thead", {}, h("tr", {}, ["#", t("symbol"), t("last"), t("chgPct"), t("extHours"), t("volume"), t("amount"), t("mktcap")].map((x, i) => h("th", { class: i > 1 ? "num" : "" }, x)))),
        h("tbody", {}, list.map((q, i) => h("tr", {},
          h("td", { class: "muted" }, i + 1),
          h("td", {}, h("button", { class: "linkbtn sym-link", onclick: () => openExternal(q.symbol, STOCK_SITES, q.symbol) }, h("b", {}, q.symbol)),
            q.name ? h("div", { class: "muted small ellipsis" }, q.name) : null),
          h("td", { class: `num ${dirClass(q.change_pct)}` }, fmt(q.live ?? q.price, 2)),
          h("td", { class: `num ${dirClass(q.change_pct)}` }, pct(q.change_pct)),
          h("td", { class: `num ${dirClass(q.ext_pct)}` }, q.ext_price ? `${fmt(q.ext_price, 2)} (${pct(q.ext_pct)})` : "—"),
          h("td", { class: `num ${rankKind === "volume" ? "strong" : ""}` }, compact(q.volume)),
          h("td", { class: `num ${rankKind === "amount" ? "strong" : ""}` }, money(q.amount)),
          h("td", { class: "num" }, money(q.mktcap))))))));
  }

  function renderTab() {
    const tabs = h("div", { class: "seg", role: "tablist" }, [["mine", t("myStocks")], ...(d.rank !== null ? [["rank", t("mostActive")]] : [])].map(([k, label]) =>
      h("button", { role: "tab", "aria-pressed": String(k === tab), onclick: () => { tab = k; prefs.setJSON("mg.q.tab", k); renderTab(); } }, label)));
    tabBox.replaceChildren(h("div", { class: "row", style: { marginBottom: "10px" } }, tabs, h("span", { class: "spacer" }),
      h("span", { class: "muted small" }, t("clickForChart"))),
      tab === "rank" && d.rank !== null ? renderRank() : renderMine());
  }

  function render() {
    const s = d.session;
    head.replaceChildren(h("h2", { style: { margin: 0 } }, t("quotes")), h("span", { class: `badge ${s}` }, t(`session.${s}`)),
      h("span", { class: "spacer" }), h("span", { class: "muted small" }, t("quotesSrc")));
    strip.replaceChildren(...[marketStrip(d.market)].filter(Boolean));
    renderIndices();
    body.replaceChildren(
      h("section", { class: "panel glass" }, head, strip),
      h("section", { class: "panel glass" },
        h("div", { class: "row", style: { marginBottom: "10px" } }, h("h2", { style: { margin: 0 } }, t("indexes")), h("span", { class: "spacer" }),
          h("button", { class: "btn", onclick: editIndices }, d.logged_in ? t("editIndices") : `🔒 ${t("editIndices")}`)),
        idxGrid),
      h("section", { class: "panel glass" }, tabBox),
    );
    renderTab();
  }

  async function load() {
    try {
      d = await api("/api/market");
      render();
    } catch (e) {
      if (e instanceof MembersOnly) body.replaceChildren(lockPanel(e.message));
      else { telemetry.push("error", "#/quotes", e.message); body.replaceChildren(h("div", { class: "panel glass empty" }, t("noData"))); }
    }
  }

  /* ---------- 实时更新 ---------- */
  offs.push(live.on("ticks", (batch) => {
    if (!d) return;
    for (const [sym, [price]] of Object.entries(batch)) {
      const q = d.snaps[sym];
      if (!q || !rows.has(sym)) continue;
      q.live = price;
      if (q.prev_close) { q.change = price - q.prev_close; q.change_pct = (price / q.prev_close - 1) * 100; }
      updateStock(sym, true);
    }
  }));
  offs.push(live.on("snap", (map) => {
    if (!d || !map) return;
    for (const [sym, q] of Object.entries(map)) {
      if (!rows.has(sym)) continue;
      d.snaps[sym] = q;
      updateStock(sym, true);
    }
  }));
  offs.push(live.on("indices", (map) => {
    if (!d || !map) return;
    let hit = false;
    for (const [code, q] of Object.entries(map)) if (d.indices.includes(code)) { d.index_quotes[code] = q; hit = true; }
    if (hit) renderIndices();
  }));
  offs.push(live.on("rank", (r) => { if (d && r && d.rank !== null) { d.rank = r; if (tab === "rank") renderTab(); } }));
  offs.push(live.on("holidays", (x) => { if (d && x?.today) { d.market = x.today; strip.replaceChildren(...[marketStrip(d.market)].filter(Boolean)); } }));

  load();
  return () => offs.forEach((fn) => fn());
}
