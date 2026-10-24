/* 持仓分析 + 连汇盈亏：股价或汇率一变动，只更新受影响的单元格，不整表重绘。
   两个开关（存服务器，网页和 App 同步）：扣除通胀（按各货币所在地区的物价折算到今天的购买力）、计入汇率（关闭后只看股价部分）。 */
import { AuthError, MembersOnly, api, fmt, h, live, lockPanel, symbolInput, telemetry, toast, ui } from "../core.js";
import { computeSymbol, deflator, pick, totals, usdTo } from "../pnl.js";
import { prefs, t } from "../i18n.js";
import { createCapital, createSummary } from "./pf_analysis.js";
import { STOCK_SITES, openExternal } from "./quotes.js";
import { openBatches, openImport } from "./pf_import.js";

const CCY_NAMES = {
  CNY: "人民币", HKD: "港币", SGD: "新加坡元", EUR: "欧元", GBP: "英镑", JPY: "日元", AUD: "澳元", CAD: "加元", CHF: "瑞士法郎", USD: "美元",
  NZD: "新西兰元", MYR: "林吉特", RUB: "卢布", ZAR: "南非兰特", KRW: "韩元", AED: "迪拉姆", SAR: "里亚尔", HUF: "福林", PLN: "兹罗提",
  DKK: "丹麦克朗", SEK: "瑞典克朗", NOK: "挪威克朗", TRY: "土耳其里拉", MXN: "墨西哥比索", THB: "泰铢", KZT: "坚戈", MOP: "澳门元", IDR: "印尼盾",
};
const ccyLabel = (c) => `${c}${prefs.lang === "zh" && CCY_NAMES[c] ? ` ${CCY_NAMES[c]}` : ""}`;

export default function portfolioView(el, opts = {}) {
  let data = null;          // /api/portfolio 返回的全部数据
  let rows = new Map();     // symbol -> { tr, cells }
  const offs = [];
  const body = h("div", { style: { display: "grid", gap: "16px" } });
  el.append(body);

  /* ---------- 格式 ---------- */
  const ccy = () => data.settings.base_currency;
  const money = (v, c = ccy()) => {
    if (v == null || Number.isNaN(v)) return "—";
    try {
      return new Intl.NumberFormat(prefs.lang === "zh" ? "zh-CN" : "en-US", { style: "currency", currency: c, maximumFractionDigits: c === "JPY" ? 0 : 2 }).format(v);
    } catch { return fmt(v, 2); }
  };
  const signedMoney = (v) => (v == null ? "—" : (v > 0 ? "+" : "") + money(v));
  const cls = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");
  const fxNow = (c = ccy()) => usdTo(data.fx.now?.rates, c, data.settings.fx_mode);
  const fxPrev = (c = ccy()) => usdTo(data.fx.prev, c, data.settings.fx_mode);
  const fxCtx = () => ({ now: data.fx.now?.rates, prev: data.fx.prev, mode: data.settings.fx_mode });

  const view = () => ({ infl: !!data.settings.inflation, fx: data.settings.include_fx !== false });
  let deflCache = null;
  const deflate = () => (view().infl ? (deflCache ||= deflator(data.inflation, data.today)) : null);
  const position = (sym) => computeSymbol(data.trades.filter((x) => x.symbol === sym), data.quotes[sym], fxCtx(), ccy(), data.session.session_date, deflate());
  const V = (p) => pick(p, view().fx);

  /* ---------- 汇总卡片与总资本（只创建一次，数据变化时更新内容） ---------- */
  const positionsAll = () => data.symbols.map((s) => ({ symbol: s.symbol, p: position(s.symbol) }));
  let totalsCache = null;
  const totalsNow = () => totalsCache || (totalsCache = totals(positionsAll().map((x) => x.p)));
  const ctx = {
    data: () => data, money: (v, c) => money(v, c), signedMoney: (v) => signedMoney(v), cls: (v) => cls(v), ccy: () => ccy(),
    positions: positionsAll, totals: totalsNow, reload: () => load(), ccyLabel, fxNow: (c) => fxNow(c),
    view: () => view(), V: (p) => V(p),
  };
  const importCtx = { reload: () => load(), ccyLabel };
  const summaryBox = createSummary(ctx);
  const capitalBox = createCapital(ctx);
  offs.push(() => summaryBox.dispose());

  /* ---------- 加载 ---------- */
  async function load() {
    try {
      data = await api("/api/portfolio");
      totalsCache = null; deflCache = null;
      render();
      summaryBox.loadHistory();
    } catch (e) {
      if (e instanceof MembersOnly) body.replaceChildren(lockPanel(e.message));
      else if (e instanceof AuthError) body.replaceChildren(h("div", { class: "panel glass lock" },
        h("div", { class: "lock-icon", "aria-hidden": "true" }, "📈"), h("p", {}, t("pfLoginFirst")),
        h("button", { class: "btn primary", onclick: () => ui.onAuth() }, t("login"))));
      else { telemetry.push("error", "#/portfolio", e.message); body.replaceChildren(h("div", { class: "panel glass empty" }, t("noData"))); }
    }
  }

  /* ---------- 渲染 ---------- */
  const fxLine = h("p", { class: "sub", style: { margin: "4px 0 0" } });

  function render() {
    rows = new Map();
    const ccySel = h("select", { "aria-label": t("pfBase"), onchange: (e) => saveSettings({ base_currency: e.target.value }) },
      data.currencies.map((c) => h("option", { value: c, selected: c === ccy() }, ccyLabel(c))));
    const modeSel = h("select", { "aria-label": t("pfFxMode"), onchange: (e) => saveSettings({ fx_mode: e.target.value }) },
      h("option", { value: "mid", selected: data.settings.fx_mode === "mid" }, t("pfMid")),
      h("option", { value: "bid", selected: data.settings.fx_mode === "bid" }, t("pfBid")));
    const ac = symbolInput({ placeholder: t("pfAddPh"), onPick: () => addForm.requestSubmit() });
    const addInput = ac.input;
    const addForm = h("form", { class: "row", onsubmit: async (e) => {
      e.preventDefault();
      ac.close();
      const sym = addInput.value.trim().toUpperCase();
      if (!sym) return;
      try {
        const r = await api("/api/portfolio/symbols", { method: "POST", body: { symbol: sym } });
        data.symbols.push({ symbol: r.symbol, note: "", target: null, stop: null });
        data.quotes[r.symbol] = r.quote;
        addInput.value = "";
        render();
      } catch (ex) { toast(ex.message); }
    } }, ac.wrap, h("button", { class: "btn primary", type: "submit" }, t("pfAdd")));

    const sw = (key, label, title) => h("label", { class: "pf-switch small", title },
      h("input", { type: "checkbox", role: "switch", checked: key === "include_fx" ? view().fx : view().infl,
        onchange: (e) => saveSettings({ [key]: e.target.checked }) }), h("span", {}, label));
    const tbody = h("tbody");
    for (const s of data.symbols) tbody.append(buildRow(s));
    const head = [t("symbol"), t("pfLast"), t("pfQty"), t("pfAvg"), t("pfMv"), t("pfToday"), t("pfUnreal"), t("pfTargets"), ""];

    body.replaceChildren(
      h("section", { class: "panel glass" },
        h("div", { class: "row" },
          h("h2", { style: { margin: 0 } }, t("portfolio")),
          h("span", { class: `badge ${data.realtime ? "regular" : ""}` }, data.realtime ? t("pfRealtime") : t("pfDelayed")),
          h("span", { class: "spacer" }),
          h("label", { class: "row small muted" }, t("pfBase"), ccySel),
          h("label", { class: "row small muted" }, t("pfFxMode"), modeSel),
          sw("inflation", t("pfInflation"), t("pfInflationTip")),
          sw("include_fx", t("pfIncludeFx"), t("pfIncludeFxTip")),
          opts.site?.ai_import?.enabled ? h("button", { class: "btn primary", onclick: () => openImport(importCtx) }, "✨ ", t("aiImport")) : null,
          opts.site?.ai_import?.enabled || data.trades.some((x) => x.batch) ? h("button", { class: "btn", onclick: () => openBatches(importCtx) }, t("importHistory")) : null,
          h("a", { class: "btn", href: "/api/portfolio/export.csv" }, t("pfExport"))),
        fxLine, inflLine()),
      summaryBox.el,
      capitalBox.el,
      h("section", { class: "panel glass" },
        h("div", { class: "row", style: { marginBottom: "10px" } }, addForm, h("span", { class: "spacer" }),
          h("span", { class: "muted small" }, `${data.symbols.length} / ${data.limits.symbols}`)),
        h("div", { class: "table-wrap" }, h("table", { class: "pf-table" },
          h("thead", {}, h("tr", {}, head.map((x, i) => h("th", { class: i && i < 8 ? "num" : "" }, x)))),
          data.symbols.length ? tbody : h("tbody", {}, h("tr", {}, h("td", { colspan: 9, class: "empty" }, t("pfEmpty")))))),
        h("p", { class: "muted small", style: { marginTop: "10px" } }, t("pfHelp"))),
    );
    updateFxLine();
    updateAll();
  }

  function buildRow(s) {
    const c = {
      sym: h("td", {}), last: h("td", { class: "num" }), qty: h("td", { class: "num" }), avg: h("td", { class: "num" }),
      mv: h("td", { class: "num" }), today: h("td", { class: "num" }), unreal: h("td", { class: "num" }), tgt: h("td", { class: "num small" }),
    };
    c.sym.append(h("button", { class: "linkbtn sym-link", title: t("viewChart"), onclick: () => openExternal(s.symbol, STOCK_SITES, s.symbol) }, h("b", {}, s.symbol)));
    if (data.quotes[s.symbol]?.name) c.sym.append(h("div", { class: "muted small ellipsis" }, data.quotes[s.symbol].name));
    if (s.note) c.sym.append(h("div", { class: "muted small" }, s.note));
    const tr = h("tr", {}, c.sym, c.last, c.qty, c.avg, c.mv, c.today, c.unreal, c.tgt,
      h("td", { class: "row nowrap" },
        h("button", { class: "btn", onclick: () => tradesDialog(s.symbol) }, t("pfTrades")),
        h("button", { class: "btn", onclick: () => editDialog(s) }, t("pfEdit")),
        h("button", { class: "btn danger", "aria-label": t("remove"), onclick: () => removeSymbol(s.symbol) }, "✕")));
    rows.set(s.symbol, { tr, c, s });
    return tr;
  }

  const two = (main, a, b) => [h("div", {}, main), h("div", { class: "small muted" }, `${t("pfPricePart")} ${a}  ${t("pfFxPart")} ${b}`)];

  function updateRow(sym, flash) {
    const r = rows.get(sym);
    if (!r) return null;
    const p = position(sym);
    const q = data.quotes[sym] || {};
    const prevText = r.c.last.dataset.v;
    r.c.last.className = `num ${cls(p.dayChangePct)}`;
    r.c.last.replaceChildren(h("div", {}, q.price != null ? fmt(q.price, 2) : "—"),
      h("div", { class: "small" }, p.dayChangePct != null ? `${p.dayChangePct > 0 ? "+" : ""}${fmt(p.dayChangePct, 2)}%` : "", q.delayed === false ? "" : h("span", { class: "tag" }, t("delayed"))));
    if (flash && prevText && String(q.price) !== prevText) {
      r.c.last.classList.add(Number(q.price) > Number(prevText) ? "tick-up" : "tick-down");
      setTimeout(() => r.c.last.classList.remove("tick-up", "tick-down"), 600);
    }
    r.c.last.dataset.v = String(q.price);
    r.c.qty.textContent = p.qty ? fmt(p.qty, p.qty % 1 ? 4 : 0) : "—";
    const fxTxt = p.qty && p.ccys.length > 1 ? `${t("pfMultiCcy")} ${p.ccys.join("/")}` : p.avgFx ? `@ ${fmt(p.avgFx, 4)}${p.ccys[0] !== ccy() ? ` USD/${p.ccys[0]}` : ""}` : "";
    r.c.avg.replaceChildren(h("div", {}, p.avgUsd != null ? `$${fmt(p.avgUsd, 2)}` : "—"), h("div", { class: "small muted" }, fxTxt));
    r.c.mv.textContent = p.qty ? money(p.mvBase) : "—";
    const v = V(p), fxOn = view().fx;
    const pct = p.qty && p.costReal ? (v.unreal / p.costReal) * 100 : null;
    r.c.today.className = `num ${cls(v.today)}`;
    r.c.today.replaceChildren(...(p.qty || p.today ? (fxOn ? two(signedMoney(p.today), signedMoney(p.todayPrice), signedMoney(p.todayFx)) : [signedMoney(v.today)]) : ["—"]));
    r.c.unreal.className = `num ${cls(v.unreal)}`;
    const unrealTxt = `${signedMoney(v.unreal)}${pct != null ? ` (${pct > 0 ? "+" : ""}${fmt(pct, 2)}%)` : ""}`;
    r.c.unreal.replaceChildren(...(p.qty ? (fxOn ? two(unrealTxt, signedMoney(p.unrealPrice), signedMoney(p.unrealFx)) : [unrealTxt])
      : [v.realized ? h("span", { class: "small" }, `${t("pfRealized")} ${signedMoney(v.realized)}`) : "—"]));
    const dist = (target) => (target && q.price ? `${fmt(target, 2)}（${fmt((target / q.price - 1) * 100, 1)}%）` : "—");
    r.c.tgt.replaceChildren(h("div", {}, `${t("pfTarget")} ${dist(r.s.target)}`), h("div", { class: "muted" }, `${t("pfStop")} ${dist(r.s.stop)}`));
    return p;
  }

  function updateTotals() {
    totalsCache = null;
    summaryBox.update();
    capitalBox.update();
  }

  /** 扣除通胀时说明用的是哪里的物价、近 12 个月通胀多少、数据截至哪个月 */
  function inflLine() {
    if (!view().infl && view().fx) return null;
    const parts = [];
    if (view().infl) {
      const used = [...new Set([ccy(), ...data.trades.map((x) => x.ccy || ccy())])];
      for (const c of used) {
        const x = data.inflation?.[c];
        if (!x) { parts.push(t("pfInflNone").replace("{c}", c)); continue; }
        if (x.no_data) { parts.push(t("pfInflNone").replace("{c}", c)); continue; }
        parts.push(t("pfInflInfo").replace("{r}", x.region || c).replace("{p}", x.yoy_12m != null ? `${fmt(x.yoy_12m, 1)}%` : "—")
          .replace("{m}", x.last_known || "—") + (x.approx ? t("pfInflApprox") : ""));
      }
    }
    if (!view().fx) parts.push(t("pfNoFxNote"));
    return h("p", { class: "sub pf-view-note", style: { margin: "4px 0 0" } }, `${view().infl ? t("pfInflNote") : ""}${parts.join("；")}`);
  }

  function updateFxLine() {
    const now = fxNow(), prev = fxPrev();
    if (now == null) { fxLine.textContent = t("pfNoFx"); return; }
    const chg = prev ? ` ${t("pfVsPrev")} ${now >= prev ? "+" : ""}${fmt(((now / prev) - 1) * 100, 3)}%` : `（${t("pfNoPrevFx")}）`;
    const when = new Date((data.fx.prev_ts || data.fx.ref_ts) * 1000).toLocaleString(prefs.lang === "zh" ? "zh-CN" : "en-US", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
    const base = prev ? `${t("pfFxBase")} ${fmt(prev, 4)}（${data.fx.prev_approx ? t("pfFxBaseApprox").replace("{t}", when) : t("pfFxBaseClose")}）` : "";
    fxLine.textContent = `1 USD = ${fmt(now, 4)} ${ccy()}${chg}；${base ? base + "；" : ""}${t("pfFxSrc")} ${data.fx.now.time || ""}`;
  }

  function updateAll() {
    for (const sym of rows.keys()) updateRow(sym, false);
    updateTotals();
  }

  /* ---------- 实时更新 ---------- */
  offs.push(live.on("ticks", (batch) => {
    if (!data) return;
    let hit = false;
    for (const [sym, [price, ts]] of Object.entries(batch)) {
      if (!rows.has(sym)) continue;
      data.quotes[sym] = { ...data.quotes[sym], price, ts, delayed: false };
      updateRow(sym, true);
      hit = true;
    }
    if (hit) updateTotals();
  }));
  const onSnap = (map) => {
    if (!data || !map) return;
    let hit = false;
    for (const [sym, q] of Object.entries(map)) {
      if (!rows.has(sym)) continue;
      const cur = data.quotes[sym] || {};
      // 快照里的昨收已按盘前/盘中区分；最新价取时间更新的那个（WebSocket 逐笔或轮询）
      const newer = !cur.ts || (q.ts && q.ts >= cur.ts);
      data.quotes[sym] = { ...cur, prev_close: q.prev_close, name: q.name, delayed: false, ...(newer ? { price: q.live ?? q.price, ts: q.ts } : {}) };
      updateRow(sym, true);
      hit = true;
    }
    if (hit) updateTotals();
  };
  offs.push(live.on("snap", onSnap));
  offs.push(live.on("fx", (fx) => {
    if (!data) return;
    data.fx.now = fx;
    updateFxLine();
    updateAll();
  }));

  /* ---------- 操作 ---------- */
  async function saveSettings(patch) {
    try {
      await api("/api/portfolio/settings", { method: "PUT", body: { ...data.settings, ...patch } });
      await load();
    } catch (e) { toast(e.message); }
  }

  async function removeSymbol(sym) {
    if (!confirm(t("pfRemoveConfirm").replace("{s}", sym))) return;
    try { await api(`/api/portfolio/symbols/${encodeURIComponent(sym)}`, { method: "DELETE" }); await load(); } catch (e) { toast(e.message); }
  }

  function dialog(title, content, onClose) {
    const dlg = h("dialog", { class: "glass pf-dialog" });
    dlg.append(h("div", { class: "dialog-form" }, h("div", { class: "row" }, h("h2", {}, title), h("span", { class: "spacer" }),
      h("button", { class: "btn", onclick: () => dlg.close() }, t("close"))), content));
    dlg.addEventListener("close", () => { dlg.remove(); onClose?.(); });
    document.body.append(dlg);
    dlg.showModal();
    return dlg;
  }

  function editDialog(s) {
    const note = h("input", { type: "text", value: s.note || "", maxlength: 200 });
    const target = h("input", { type: "number", step: "any", min: 0, value: s.target ?? "" });
    const stop = h("input", { type: "number", step: "any", min: 0, value: s.stop ?? "" });
    const err = h("div", { class: "err" });
    const dlg = dialog(`${s.symbol} ${t("pfEdit")}`, h("form", { class: "dialog-form", onsubmit: async (e) => {
      e.preventDefault();
      try {
        await api(`/api/portfolio/symbols/${s.symbol}`, { method: "PATCH", body: { note: note.value, target: target.value, stop: stop.value } });
        dlg.close(); await load();
      } catch (ex) { err.textContent = ex.message; }
    } }, h("label", {}, t("pfNote"), note), h("label", {}, `${t("pfTarget")}（USD）`, target), h("label", {}, `${t("pfStop")}（USD）`, stop), err,
      h("div", { class: "row" }, h("span", { class: "spacer" }), h("button", { class: "btn primary", type: "submit" }, t("save")))));
  }

  function tradesDialog(sym) {
    const listBody = h("tbody");
    const err = h("div", { class: "err" });
    const today = data.session.session_date;
    const lastCcy = data.trades.filter((x) => x.symbol === sym).at(-1)?.ccy || ccy();
    const fxLabel = h("span", {});
    const f = {
      side: h("select", {}, h("option", { value: "buy" }, t("pfBuy")), h("option", { value: "sell" }, t("pfSell"))),
      ccy: h("select", { onchange: () => { syncFx(true); } }, data.currencies.map((c) => h("option", { value: c, selected: c === lastCcy }, `USD/${c}${prefs.lang === "zh" && CCY_NAMES[c] ? ` ${CCY_NAMES[c]}` : ""}`))),
      date: h("input", { type: "date", value: today, max: new Date(Date.now() + 86400000).toISOString().slice(0, 10), required: true }),
      shares: h("input", { type: "number", step: "any", min: 0, required: true }),
      price: h("input", { type: "number", step: "any", min: 0, required: true, value: data.quotes[sym]?.price ?? "" }),
      fx: h("input", { type: "number", step: "any", min: 0, required: true, value: fxNow(lastCcy) ? fxNow(lastCcy).toFixed(4) : "" }),
      fee: h("input", { type: "number", step: "any", min: 0, value: 0 }),
      note: h("input", { type: "text", maxlength: 200 }),
      funding: h("select", { onchange: () => syncFx(true) },
        h("option", { value: "ccy" }, t("fundCcy")), h("option", { value: "usd" }, t("fundUsd"))),
    };
    const fundLabel = h("label", { class: "wide" }, t("fundLabel"), f.funding, h("span", { class: "muted small" }, t("fundHint")));
    let editing = null;
    let fxReq = 0;
    function syncFx(setValue) {
      const c = f.ccy.value;
      fxLabel.textContent = `${f.funding.value === "usd" && c !== "USD" ? t("fundCostFx") : t("pfTradeFx")}（1 USD = ? ${c}）`;
      f.fx.readOnly = c === "USD";
      fundLabel.style.display = c === "USD" ? "none" : "";
      if (!(setValue || c === "USD")) return;
      if (c === "USD") { f.fx.value = 1; return; }
      if (f.funding.value === "usd") {  // 用之前换好的美元：默认填换汇记录的平均成本
        const my = ++fxReq;
        api(`/api/portfolio/fx-cost?ccy=${c}&date=${f.date.value}`).then((r) => {
          if (my === fxReq && r.rate) f.fx.value = r.rate.toFixed(4);
          else if (my === fxReq && !r.rate) toast(t("fundNoRecords").replace("{c}", c), 5000);
        }).catch(() => {});
      } else f.fx.value = fxNow(c) ? fxNow(c).toFixed(4) : "";
    }
    const submit = h("button", { class: "btn primary", type: "submit" }, t("pfAddTrade"));
    const cancelEdit = h("button", { class: "btn", type: "button", style: { display: "none" }, onclick: () => resetForm() }, t("cancel"));
    function resetForm() {
      editing = null; submit.textContent = t("pfAddTrade"); cancelEdit.style.display = "none";
      f.shares.value = ""; f.note.value = ""; f.fee.value = 0; f.date.value = today; f.side.value = "buy"; f.funding.value = "ccy";
      f.price.value = data.quotes[sym]?.price ?? ""; syncFx(true);
    }
    function fill() {
      const list = data.trades.filter((x) => x.symbol === sym);
      listBody.replaceChildren(...(list.length ? list.map((x) => h("tr", {},
        h("td", {}, x.trade_date), h("td", { class: x.side === "buy" ? "up" : "down" }, x.side === "buy" ? t("pfBuy") : t("pfSell")),
        h("td", { class: "num" }, fmt(x.shares, x.shares % 1 ? 4 : 0)), h("td", { class: "num" }, `$${fmt(x.price, 2)}`),
        h("td", {}, `USD/${x.ccy}`, x.funding === "usd" ? h("span", { class: "tag", title: t("fundUsd") }, "USD") : null, x.batch ? h("span", { class: "tag" }, t("imported")) : null), h("td", { class: "num" }, fmt(x.fx, 4)), h("td", { class: "num" }, `$${fmt(x.fee, 2)}`), h("td", { class: "wrap small" }, x.note),
        h("td", { class: "row nowrap" },
          h("button", { class: "btn", onclick: () => {
            editing = x.id; submit.textContent = t("save"); cancelEdit.style.display = "";
            f.side.value = x.side; f.date.value = x.trade_date; f.shares.value = x.shares; f.price.value = x.price; f.ccy.value = x.ccy; f.funding.value = x.funding || "ccy"; syncFx(false); f.fx.value = x.fx; f.fee.value = x.fee; f.note.value = x.note;
          } }, t("pfEdit")),
          h("button", { class: "btn danger", onclick: async () => {
            if (!confirm(t("pfDelTrade"))) return;
            try { await api(`/api/portfolio/trades/${x.id}`, { method: "DELETE" }); await refreshData(); } catch (ex) { toast(ex.message); }
          } }, "✕"))))
        : [h("tr", {}, h("td", { colspan: 9, class: "empty" }, t("pfNoTrades")))]));
    }
    async function refreshData() {
      const d = await api("/api/portfolio");
      data = d; fill(); render();
    }
    const form = h("form", { class: "pf-trade-form", onsubmit: async (e) => {
      e.preventDefault(); err.textContent = "";
      const payload = { symbol: sym, side: f.side.value, trade_date: f.date.value, shares: f.shares.value, price: f.price.value, ccy: f.ccy.value, fx: f.fx.value, fee: f.fee.value || 0, note: f.note.value, funding: f.funding.value };
      try {
        if (editing) await api(`/api/portfolio/trades/${editing}`, { method: "PATCH", body: payload });
        else await api("/api/portfolio/trades", { method: "POST", body: payload });
        resetForm(); await refreshData();
      } catch (ex) { err.textContent = ex.message; }
    } },
      h("label", {}, t("pfSide"), f.side), h("label", {}, t("pfDate"), f.date), h("label", {}, t("pfQty"), f.shares),
      h("label", {}, `${t("price")}（USD）`, f.price), h("label", {}, t("pfPair"), f.ccy), h("label", {}, fxLabel, f.fx),
      h("label", {}, `${t("pfFee")}（USD）`, f.fee), fundLabel, h("label", { class: "wide" }, t("pfNote"), f.note),
      h("div", { class: "row wide" }, err, h("span", { class: "spacer" }), cancelEdit, submit));
    dialog(`${sym} ${t("pfTrades")}`, h("div", { style: { display: "grid", gap: "14px" } },
      h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, [t("pfDate"), t("pfSide"), t("pfQty"), t("price"), t("pfPair"), t("pfTradeFx"), t("pfFee"), t("pfNote"), ""].map((x, i) => h("th", { class: i > 1 && i < 7 && i !== 4 ? "num" : "" }, x)))),
        listBody)),
      h("p", { class: "muted small", style: { margin: 0 } }, t("pfFxHint")),
      form));
    syncFx(false);
    fill();
  }

  load();
  return () => offs.forEach((fn) => fn());
}
