/* 持仓分析：汇总卡片（带折线和悬停分析）+ 总资本（多币种现金、换汇、资产占比）。 */
import { api, fmt, h, hideCard, hoverCard, toast } from "../core.js";
import { interactiveChart, sparkline } from "../chart.js";
import { capital, cashBalances, usdTo } from "../pnl.js";
import { prefs, t } from "../i18n.js";

const css = (name, fb) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fb;
const pctTxt = (v, d = 2) => (v == null || !Number.isFinite(v) ? "—" : `${v > 0 ? "+" : ""}${fmt(v, d)}%`);

/**
 * ctx: { data(), money(v, c?), signedMoney(v), cls(v), positions() -> [{symbol, p}], totals(), ccy(), view() -> {infl, fx}, V(p) -> {unreal, realized, today, total} }
 * 所有盈亏数字和图表都按两个开关（扣除通胀 / 计入汇率）取值。
 */
export function createSummary(ctx) {
  let hist = null;      // /api/portfolio/history
  const el = h("div", { class: "grid-4 pf-tiles" });
  const mk = (key, label) => {
    const main = h("div", { class: "px" }), sub = h("div", { class: "meta" }), extra = h("div", { class: "meta tile-extra" });
    const spark = h("div", { class: "tile-spark" });
    const tile = h("div", { class: "tile glass pf-tile", "data-key": key, "aria-label": `${label}：${t("pfHoverHint")}` },
      h("div", { class: "row" }, h("div", { class: "name" }, label), h("span", { class: "spacer" }), h("span", { class: "hint", "aria-hidden": "true" }, "ⓘ")),
      h("div", { class: "tile-body" }, h("div", {}, main, sub, extra), spark));
    return { tile, main, sub, extra, spark };
  };
  const T = { mv: mk("mv", t("pfTotalMv")), today: mk("today", t("pfToday")), unreal: mk("unreal", t("pfUnreal")), total: mk("total", t("pfTotalPl")) };
  el.append(T.mv.tile, T.today.tile, T.unreal.tile, T.total.tile);

  /** 历史 + 今天（实时）合成的序列 */
  function series() {
    const { infl, fx } = ctx.view();
    const pk = infl ? (fx ? "pl_r" : "pl_rp") : (fx ? "total_pl" : "pl_p");
    const uk = infl ? (fx ? "u_r" : "u_rp") : (fx ? "unreal" : "u_p");
    let prevP = null;
    const pts = (hist?.points || []).map((p) => {
      const total = p[pk] ?? p.total_pl, unreal = p[uk] ?? p.unreal;
      // 今日盈亏不受通胀影响；不计汇率时用“只含股价”的总盈亏逐日相减
      const day = fx ? p.day_pl : (prevP != null && p.pl_p != null ? p.pl_p - prevP : null);
      prevP = p.pl_p ?? null;
      return { ...p, total_pl: total, unreal, realized: total - unreal, day_pl: day };
    });
    const tt = ctx.totals(), v = ctx.V(tt);
    const today = ctx.data().session.session_date;
    const live = { date: today, mv: tt.mvBase, cost: infl ? tt.costReal : tt.costBase, unreal: v.unreal, realized: v.realized, total_pl: v.total, day_pl: v.today, live: true };
    if (pts.length && pts[pts.length - 1].date >= today) pts[pts.length - 1] = { ...pts[pts.length - 1], ...live };
    else pts.push(live);
    return pts;
  }

  function drawSparks() {
    const pts = series();
    const put = (box, values, color) => {
      const v = values.filter((x) => x != null && Number.isFinite(x));
      box.replaceChildren(...(v.length >= 2 ? [sparkline(v, { w: 120, h: 34, color })] : []));
    };
    const upc = css("--up", "#ff5d5d"), dnc = css("--down", "#2fcf87");
    const v = ctx.V(ctx.totals());
    put(T.mv.spark, pts.map((p) => p.mv), "#47c6c0");
    put(T.today.spark, pts.slice(-20).map((p) => p.day_pl), (v.today ?? 0) >= 0 ? upc : dnc);
    put(T.unreal.spark, pts.map((p) => p.unreal), (v.unreal ?? 0) >= 0 ? upc : dnc);
    put(T.total.spark, pts.map((p) => p.total_pl), (v.total ?? 0) >= 0 ? upc : dnc);
  }

  function prevDays(n) {
    const pts = series().filter((p) => !p.live && p.date < ctx.data().session.session_date && p.day_pl != null);
    return pts.slice(-n);
  }
  /** 当前视图的盈亏和说明 */
  const viewOf = () => {
    const tt = ctx.totals(), v = ctx.V(tt), vw = ctx.view();
    const cost = vw.infl ? tt.costReal : tt.costBase;
    return { tt, v, vw, cost, pct: cost ? (v.unreal / cost) * 100 : null };
  };
  const viewNotes = () => {
    const vw = ctx.view();
    return [vw.infl ? h("p", { class: "muted small" }, t("pfInflCardNote")) : null, !vw.fx ? h("p", { class: "muted small" }, t("pfNoFxNote")) : null].filter(Boolean);
  };

  function update() {
    const { tt, v, vw, cost, pct } = viewOf(), m = ctx.money, sm = ctx.signedMoney, c = ctx.cls;
    T.mv.main.textContent = m(tt.mvBase);
    T.mv.sub.textContent = `${vw.infl ? t("pfRealCost") : t("pfCost")} ${m(cost)}`;
    T.today.main.textContent = sm(v.today); T.today.main.className = `px ${c(v.today)}`;
    T.today.sub.textContent = vw.fx ? `${t("pfPricePart")} ${sm(tt.todayPrice)}，${t("pfFxPart")} ${sm(tt.todayFx)}` : t("pfExFx");
    const y = prevDays(1)[0], wk = prevDays(5);
    const avg = wk.length ? wk.reduce((a, p) => a + p.day_pl, 0) / wk.length : null;
    T.today.extra.replaceChildren(...[
      y ? h("span", {}, `${t("pfVsYesterday")} `, h("b", { class: c(v.today - y.day_pl) }, sm(v.today - y.day_pl))) : null,
      avg != null ? h("span", {}, `  ${t("pfVsWeekAvg")} `, h("b", { class: c(v.today - avg) }, sm(v.today - avg))) : null,
    ].filter(Boolean));
    T.unreal.main.replaceChildren(sm(v.unreal), ...(pct != null ? [h("span", { class: "px-pct" }, ` ${pctTxt(pct)}`)] : []));
    T.unreal.main.className = `px ${c(v.unreal)}`;
    T.unreal.sub.textContent = vw.fx ? `${t("pfPricePart")} ${sm(tt.unrealPrice)}，${t("pfFxPart")} ${sm(tt.unrealFx)}` : t("pfExFx");
    if (vw.infl) T.unreal.sub.textContent += `；${t("pfInflShort")}`;
    T.total.main.textContent = sm(v.total); T.total.main.className = `px ${c(v.total)}`;
    T.total.sub.textContent = `${t("pfRealized")} ${sm(v.realized)}，${t("pfUnreal")} ${sm(v.unreal)}`;
  }

  /* ---------- 悬停分析 ---------- */
  const head = (title, value, cls) => h("div", { class: "row" }, h("b", {}, title), h("span", { class: "spacer" }), h("b", { class: cls }, value),
    h("button", { class: "btn small-btn", "aria-label": t("close"), onclick: hideCard }, "✕"));
  const statGrid = (items) => h("div", { class: "stats compact" }, items.filter(Boolean).map(([k, v, cl]) =>
    h("div", { class: "stat" }, h("div", { class: "muted small" }, k), h("b", { class: cl || "" }, v))));
  const notes = () => [
    !hist ? h("p", { class: "muted small" }, t("pfHistLoading")) : null,
    hist && hist.points.length < 2 ? h("p", { class: "muted small" }, t("pfHistShort")) : null,
    hist?.approx_fx ? h("p", { class: "muted small" }, t("pfHistApproxFx")) : null,
    hist?.missing?.length ? h("p", { class: "muted small" }, `${t("pfHistMissing")}：${hist.missing.join("、")}`) : null,
  ].filter(Boolean);
  const label = (d) => d.slice(5).replace("-", "/");
  const change = (pts, key, back) => {
    if (pts.length < 2) return [null, null];
    const now = pts[pts.length - 1][key], i = Math.max(0, pts.length - 1 - back), was = pts[i][key];
    return [now - was, was ? ((now - was) / Math.abs(was)) * 100 : null];
  };

  function chartOf(card, opts) {
    const canvas = h("canvas", { class: "ev-chart" });
    card.append(canvas);
    requestAnimationFrame(() => interactiveChart(canvas, opts));
  }

  function mvCard(card, replace) {
    const pts = series(), tt = ctx.totals(), m = ctx.money, sm = ctx.signedMoney, c = ctx.cls;
    const [d1, p1] = change(pts, "mv", 1), [d5, p5] = change(pts, "mv", 5), [d21, p21] = change(pts, "mv", 21);
    const mvs = pts.map((p) => p.mv).filter((v) => v != null);
    // 盈亏回撤：总盈亏从高点回落的最大幅度（不受买入卖出资金进出的影响）
    let peak = -Infinity, dd = 0;
    for (const p of pts) { peak = Math.max(peak, p.total_pl ?? -Infinity); dd = Math.max(dd, peak - (p.total_pl ?? peak)); }
    const pos = ctx.positions().filter((x) => x.p.mvBase > 0).sort((a, b) => b.p.mvBase - a.p.mvBase);
    card.replaceChildren(
      head(t("pfTotalMv"), m(tt.mvBase)),
      statGrid([
        [t("pfChg1d"), `${sm(d1)} (${pctTxt(p1)})`, c(d1)], [t("pfChg1w"), `${sm(d5)} (${pctTxt(p5)})`, c(d5)],
        [t("pfChg1m"), `${sm(d21)} (${pctTxt(p21)})`, c(d21)],
        [t("pfHighLow"), mvs.length ? `${m(Math.max(...mvs))} / ${m(Math.min(...mvs))}` : "—"],
        [t("pfMaxDd"), dd > 0 ? m(-dd) : "—", dd > 0 ? "down" : ""],
        [t("pfConcentration"), pos.length && tt.mvBase ? `${pos[0].symbol} ${fmt((pos[0].p.mvBase / tt.mvBase) * 100, 1)}%` : "—"],
      ]),
      h("p", { class: "muted small" }, t("pfMvNote")),
    );
    if (pts.length >= 2) chartOf(card, {
      labels: pts.map((p) => label(p.date)), tipTitle: (i) => `${pts[i].date}${pts[i].live ? `（${t("pfLive")}）` : ""}`,
      series: [{ name: t("pfMv"), type: "area", values: pts.map((p) => p.mv), color: "#47c6c0" },
               { name: t("pfCost"), type: "line", values: pts.map((p) => (p.live ? ctx.totals().costBase : p.cost)), color: "#f5b971", dash: [5, 4], width: 1.5 }],
      fmtLeft: (v) => m(v).replace(/\.\d+$/, ""),
    });
    if (pos.length) card.append(h("div", { class: "alloc" }, h("div", { class: "small muted" }, t("pfWeights")),
      ...pos.slice(0, 6).map((x) => { const w = (x.p.mvBase / tt.mvBase) * 100; return h("div", { class: "alloc-row" },
        h("span", {}, x.symbol), h("div", { class: "bar" }, h("i", { style: { width: `${w}%` } })), h("span", { class: "num small" }, `${fmt(w, 1)}%`)); })));
    card.append(...notes(), ...viewNotes());
    replace();
  }

  function todayCard(card, replace) {
    const { tt, v, vw } = viewOf(), sm = ctx.signedMoney, c = ctx.cls;
    const days = prevDays(20), y = days[days.length - 1], wk = days.slice(-5);
    const avg = wk.length ? wk.reduce((a, p) => a + p.day_pl, 0) / wk.length : null;
    const wins = days.filter((p) => p.day_pl > 0).length;
    const dv = (p) => ctx.V(p).today;
    const movers = ctx.positions().filter((x) => dv(x.p)).sort((a, b) => Math.abs(dv(b.p)) - Math.abs(dv(a.p))).slice(0, 5);
    card.replaceChildren(
      head(t("pfToday"), sm(v.today), c(v.today)),
      statGrid([
        [t("pfYesterday"), y ? sm(y.day_pl) : "—", y ? c(y.day_pl) : ""],
        [t("pfVsYesterday"), y ? sm(v.today - y.day_pl) : "—", y ? c(v.today - y.day_pl) : ""],
        [t("pfWeekAvg"), avg != null ? sm(avg) : "—", c(avg)],
        [t("pfVsWeekAvg"), avg != null ? sm(v.today - avg) : "—", avg != null ? c(v.today - avg) : ""],
        vw.fx ? [t("pfPricePart"), sm(tt.todayPrice), c(tt.todayPrice)] : null, vw.fx ? [t("pfFxPart"), sm(tt.todayFx), c(tt.todayFx)] : null,
        days.length ? [t("pfWinDays"), `${wins} / ${days.length}`] : null,
      ]),
    );
    const pts = [...days, { date: ctx.data().session.session_date, day_pl: v.today, live: true }];
    if (pts.length >= 2) {
      const upc = css("--up", "#ff5d5d"), dnc = css("--down", "#2fcf87");
      chartOf(card, {
        labels: pts.map((p) => label(p.date)), tipTitle: (i) => `${pts[i].date}${pts[i].live ? `（${t("pfLive")}）` : ""}`, zeroLine: true,
        series: [{ name: t("pfDayPl"), type: "bar", values: pts.map((p) => p.day_pl), color: (v) => (v >= 0 ? upc : dnc) },
                 ...(avg != null ? [{ name: t("pfWeekAvg"), type: "line", values: pts.map(() => avg), color: "#f5b971", dash: [4, 4], width: 1.2 }] : [])],
        fmtLeft: (v) => ctx.money(v).replace(/\.\d+$/, ""),
      });
    }
    if (movers.length) card.append(h("div", { class: "alloc" }, h("div", { class: "small muted" }, t("pfMovers")),
      ...movers.map((x) => h("div", { class: "alloc-row" }, h("span", {}, x.symbol),
        vw.fx ? h("span", { class: "small muted" }, `${t("pfPricePart")} ${sm(x.p.todayPrice)} · ${t("pfFxPart")} ${sm(x.p.todayFx)}`) : h("span"),
        h("b", { class: `num ${c(dv(x.p))}` }, sm(dv(x.p)))))));
    card.append(...notes(), ...viewNotes());
    replace();
  }

  function unrealCard(card, replace) {
    const { tt, v, vw, cost, pct } = viewOf(), sm = ctx.signedMoney, c = ctx.cls, pts = series();
    const uv = (p) => ctx.V(p).unreal;
    const pos = ctx.positions().filter((x) => x.p.qty).sort((a, b) => (uv(b.p) ?? 0) - (uv(a.p) ?? 0));
    const fxShare = vw.fx && v.unreal ? (tt.unrealFx / Math.abs(v.unreal)) * 100 : null;
    const ppct = (p) => (p.costReal ? (uv(p) / (vw.infl ? p.costReal : p.costBase)) * 100 : null);
    card.replaceChildren(
      head(t("pfUnreal"), `${sm(v.unreal)} (${pctTxt(pct)})`, c(v.unreal)),
      statGrid([
        vw.fx ? [t("pfPricePart"), sm(tt.unrealPrice), c(tt.unrealPrice)] : null, vw.fx ? [t("pfFxPart"), sm(tt.unrealFx), c(tt.unrealFx)] : null,
        vw.fx ? [t("pfFxShare"), fxShare != null ? pctTxt(fxShare, 1) : "—", c(tt.unrealFx)] : null,
        [vw.infl ? t("pfRealCost") : t("pfCost"), ctx.money(cost)],
        vw.infl ? [t("pfInflImpact"), sm(tt.costBase - tt.costReal), c(tt.costBase - tt.costReal)] : null,
        [t("pfWinners"), `${pos.filter((x) => uv(x.p) > 0).length} / ${pos.length}`],
      ]),
    );
    if (pts.length >= 2) chartOf(card, {
      labels: pts.map((p) => label(p.date)), tipTitle: (i) => pts[i].date, zeroLine: true,
      series: [{ name: t("pfUnreal"), type: "area", values: pts.map((p) => p.unreal), color: "#47c6c0" }],
      fmtLeft: (v) => ctx.money(v).replace(/\.\d+$/, ""),
    });
    if (pos.length) card.append(h("div", { class: "alloc" }, h("div", { class: "small muted" }, t("pfContrib")),
      ...[...pos.slice(0, 3), ...pos.slice(-3).filter((x) => !pos.slice(0, 3).includes(x))].map((x) => h("div", { class: "alloc-row" },
        h("span", {}, x.symbol), vw.fx ? h("span", { class: "small muted" }, `${t("pfPricePart")} ${sm(x.p.unrealPrice)} · ${t("pfFxPart")} ${sm(x.p.unrealFx)}`) : h("span"),
        h("b", { class: `num ${c(uv(x.p))}` }, `${sm(uv(x.p))} (${pctTxt(ppct(x.p), 1)})`)))));
    card.append(...notes(), ...viewNotes());
    replace();
  }

  function totalCard(card, replace) {
    const { v, vw } = viewOf(), sm = ctx.signedMoney, c = ctx.cls, pts = series();
    const total = v.total;
    const [d5] = change(pts, "total_pl", 5), [d21] = change(pts, "total_pl", 21);
    const rv = (p) => ctx.V(p).realized;
    const realizedBy = ctx.positions().filter((x) => rv(x.p)).sort((a, b) => rv(b.p) - rv(a.p));
    card.replaceChildren(
      head(t("pfTotalPl"), sm(total), c(total)),
      statGrid([
        [t("pfRealized"), sm(v.realized), c(v.realized)], [t("pfUnreal"), sm(v.unreal), c(v.unreal)],
        [t("pfChg1w"), sm(d5), c(d5)], [t("pfChg1m"), sm(d21), c(d21)],
      ]),
      h("p", { class: "muted small" }, vw.fx && !vw.infl ? t("pfTotalNote") : t("pfTotalNoteView")),
    );
    if (pts.length >= 2) chartOf(card, {
      labels: pts.map((p) => label(p.date)), tipTitle: (i) => pts[i].date, zeroLine: true,
      series: [{ name: t("pfTotalPl"), type: "area", values: pts.map((p) => p.total_pl), color: "#47c6c0" },
               { name: t("pfRealized"), type: "line", values: pts.map((p) => p.realized), color: "#f5b971", dash: [5, 4], width: 1.5 }],
      fmtLeft: (v) => ctx.money(v).replace(/\.\d+$/, ""),
    });
    if (realizedBy.length) card.append(h("div", { class: "alloc" }, h("div", { class: "small muted" }, t("pfRealizedBy")),
      ...realizedBy.slice(0, 6).map((x) => h("div", { class: "alloc-row" }, h("span", {}, x.symbol), h("span"), h("b", { class: `num ${c(rv(x.p))}` }, sm(rv(x.p)))))));
    card.append(...notes(), ...viewNotes());
    replace();
  }

  const offs = [
    hoverCard(T.mv.tile, mvCard, { width: 520 }), hoverCard(T.today.tile, todayCard, { width: 500 }),
    hoverCard(T.unreal.tile, unrealCard, { width: 500 }), hoverCard(T.total.tile, totalCard, { width: 500 }),
  ];

  async function loadHistory() {
    try { hist = await api("/api/portfolio/history"); } catch { hist = { points: [], missing: [], approx_fx: false }; }
    update(); drawSparks();
  }
  let sparkTimer = null;
  return {
    el, loadHistory,
    update() { update(); if (!sparkTimer) sparkTimer = setTimeout(() => { sparkTimer = null; drawSparks(); }, 3000); },
    redrawSparks: drawSparks,
    dispose() { offs.forEach((f) => f()); clearTimeout(sparkTimer); },
  };
}

/* ======================= 总资本 ======================= */
const KIND_KEY = { deposit: "capDeposit", withdraw: "capWithdraw", fx: "capFx", dividend: "capDividend", interest: "capInterest", fee: "capFeeKind", tax: "capTax" };
const kindName = (k) => t(KIND_KEY[k] || k);
const COLORS = ["#47c6c0", "#7fd8ff", "#f5b971", "#c084fc", "#f472b6", "#a3e635", "#fb923c", "#60a5fa"];

/** ctx: { data(), money(v, c?), ccy(), totals(), reload(), ccyLabel(c), fxNow(c) } */
export function createCapital(ctx) {
  const el = h("section", { class: "panel glass capital" });

  function update() {
    const d = ctx.data();
    const tt = ctx.totals();
    const cap = capital(d.trades, d.cash || [], d.fx.now?.rates, ctx.ccy(), d.settings.fx_mode, tt.mvBase || 0);
    const name = (x) => (x.kind === "stocks" ? t("capStocks") : `${t("capCash")} ${ctx.ccyLabel(x.ccy)}`);
    const pos = cap.items.filter((x) => x.value > 0);
    el.replaceChildren(...[
      h("div", { class: "row" },
        h("h2", { style: { margin: 0 } }, t("capTitle")),
        h("b", { class: "cap-total" }, ctx.money(cap.net)),
        h("span", { class: "muted small" }, t("capIn").replace("{c}", ctx.ccy())),
        h("span", { class: "spacer" }),
        h("button", { class: "btn", onclick: () => cashDialog("deposit") }, t("capDeposit")),
        h("button", { class: "btn", onclick: () => cashDialog("withdraw") }, t("capWithdraw")),
        h("button", { class: "btn primary", onclick: () => cashDialog("fx") }, t("capFx")),
        h("button", { class: "btn", onclick: recordsDialog }, t("capRecords"))),
      pos.length ? h("div", { class: "cap-bar", role: "img", "aria-label": t("capAlloc") },
        ...pos.map((x, i) => h("i", { title: `${name(x)} ${fmt(x.pct, 1)}%`, style: { width: `${x.pct}%`, background: COLORS[i % COLORS.length] } }))) : null,
      cap.items.length ? h("div", { class: "table-wrap" }, h("table", { class: "cap-table" },
        h("thead", {}, h("tr", {}, [t("capAsset"), t("capAmount"), t("capValue").replace("{c}", ctx.ccy()), t("capPct")].map((x, i) => h("th", { class: i ? "num" : "" }, x)))),
        h("tbody", {}, cap.items.map((x) => {
          const i = pos.indexOf(x);
          return h("tr", { class: x.value < 0 ? "neg" : "" },
            h("td", {}, i >= 0 ? h("span", { class: "dot", style: { background: COLORS[i % COLORS.length] } }) : h("span", { class: "dot" }), name(x)),
            h("td", { class: "num" }, x.kind === "stocks" ? ctx.money(ctx.positions().reduce((a, y) => a + (y.p.mvUsd || 0), 0), "USD") : ctx.money(x.amount, x.ccy)),
            h("td", { class: `num ${x.value < 0 ? "down" : ""}` }, x.value == null ? t("capNoRate") : ctx.money(x.value)),
            h("td", { class: "num" }, x.pct != null ? `${fmt(x.pct, 1)}%` : "—"));
        })))) : h("p", { class: "muted" }, t("capEmpty")),
      cap.negative.length ? h("p", { class: "warn small" }, "⚠️ ", t("capNegative").replace("{c}", cap.negative.map((x) => x.ccy).join("、"))) : null,
      h("p", { class: "muted small" }, t("capHelp")),
    ].filter(Boolean));
  }

  function cashDialog(kind, rec = null) {
    const d = ctx.data();
    const today = d.session.session_date > new Date().toISOString().slice(0, 10) ? new Date().toISOString().slice(0, 10) : new Date().toISOString().slice(0, 10);
    const sel = (v) => h("select", {}, d.currencies.map((c) => h("option", { value: c, selected: c === v }, ctx.ccyLabel(c))));
    const num = (v) => h("input", { type: "number", step: "any", min: 0, required: true, value: v ?? "" });
    const date = h("input", { type: "date", required: true, value: rec?.trade_date || today, max: today });
    const note = h("input", { type: "text", maxlength: 200, value: rec?.note || "" });
    const err = h("div", { class: "err" });
    let fields, payload, info = null;
    if (kind === "fx") {
      const out = rec?.legs.find((x) => x.amount < 0), inn = rec?.legs.find((x) => x.amount > 0);
      const fromC = sel(out?.ccy || ctx.ccy()), toC = sel(inn?.ccy || (ctx.ccy() === "USD" ? "CNY" : "USD"));
      const fromA = num(out ? -out.amount : ""), toA = num(inn?.amount ?? "");
      info = h("div", { class: "small muted fx-info" });
      const recalc = () => {
        const a = fromC.value, c = toC.value, fa = +fromA.value, ta = +toA.value;
        const mkt = ctx.fxNow(c) && ctx.fxNow(a) ? ctx.fxNow(c) / ctx.fxNow(a) : null;  // 1 a = ? c
        const parts = [];
        if (mkt) parts.push(`${t("capMktRate")}：1 ${a} = ${fmt(mkt, 4)} ${c}`);
        if (fa > 0 && ta > 0) {
          const rate = ta / fa;
          parts.push(`${t("capYourRate")}：1 ${a} = ${fmt(rate, 4)} ${c}（1 ${c} = ${fmt(1 / rate, 4)} ${a}）`);
          if (mkt) parts.push(`${t("capVsMkt")} ${pctTxt((rate / mkt - 1) * 100, 2)}`);
        }
        info.textContent = parts.join("；");
      };
      [fromC, toC, fromA, toA].forEach((x) => x.addEventListener("input", recalc));
      const fill = h("button", { class: "btn small-btn", type: "button", onclick: () => {
        const mkt = ctx.fxNow(toC.value) / ctx.fxNow(fromC.value);
        if (+fromA.value > 0 && mkt) toA.value = (+fromA.value * mkt).toFixed(2);
        else if (+toA.value > 0 && mkt) fromA.value = (+toA.value / mkt).toFixed(2);
        recalc();
      } }, t("capFillMkt"));
      recalc();
      fields = [h("label", {}, t("pfDate"), date), h("label", {}, t("capFromCcy"), fromC), h("label", {}, t("capFromAmt"), fromA),
        h("label", {}, t("capToCcy"), toC), h("label", {}, t("capToAmt"), toA), h("div", { class: "wide row" }, info, h("span", { class: "spacer" }), fill)];
      payload = () => ({ kind: "fx", trade_date: date.value, from_ccy: fromC.value, from_amount: fromA.value, to_ccy: toC.value, to_amount: toA.value, note: note.value });
    } else {
      const leg = rec?.legs[0];
      const c = sel(leg?.ccy || ctx.ccy()), a = num(leg ? Math.abs(leg.amount) : "");
      fields = [h("label", {}, t("pfDate"), date), h("label", {}, t("capCcy"), c), h("label", {}, t("capAmountIn"), a)];
      payload = () => ({ kind, trade_date: date.value, ccy: c.value, amount: a.value, note: note.value });
    }
    const dlg = h("dialog", { class: "glass pf-dialog" });
    const submit = h("button", { class: "btn primary", type: "submit" }, rec ? t("save") : t("capAdd"));
    dlg.append(h("form", { class: "dialog-form", onsubmit: async (e) => {
      e.preventDefault(); err.textContent = ""; submit.disabled = true;
      try {
        if (rec) await api(`/api/portfolio/cash/${rec.grp}`, { method: "PUT", body: payload() });
        else await api("/api/portfolio/cash", { method: "POST", body: payload() });
        dlg.close(); toast(t("saved")); await ctx.reload();
      } catch (ex) { err.textContent = ex.message; } finally { submit.disabled = false; }
    } },
      h("div", { class: "row" }, h("h2", {}, kindName(kind)), h("span", { class: "spacer" }),
        h("button", { class: "btn", type: "button", onclick: () => dlg.close() }, t("close"))),
      kind === "fx" ? h("p", { class: "muted small" }, t("capFxHint")) : null,
      h("div", { class: "pf-trade-form" }, ...fields, h("label", { class: "wide" }, t("pfNote"), note)),
      h("div", { class: "row" }, err, h("span", { class: "spacer" }), submit)));
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg); dlg.showModal();
  }

  function groups() {
    const by = new Map();
    for (const m of ctx.data().cash || []) {
      if (!by.has(m.grp)) by.set(m.grp, { grp: m.grp, kind: m.kind, trade_date: m.trade_date, note: m.note, legs: [] });
      by.get(m.grp).legs.push(m);
    }
    return [...by.values()].sort((a, b) => (a.trade_date < b.trade_date ? 1 : -1));
  }

  function recordsDialog() {
    const dlg = h("dialog", { class: "glass pf-dialog" });
    const d = ctx.data();
    const draw = () => {
      const list = groups();
      const bal = cashBalances(d.trades, [], ctx.ccy());
      dlg.replaceChildren(h("div", { class: "dialog-form" },
        h("div", { class: "row" }, h("h2", {}, t("capRecords")), h("span", { class: "spacer" }), h("button", { class: "btn", onclick: () => dlg.close() }, t("close"))),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, [t("pfDate"), t("capType"), t("capDetail"), t("pfNote"), ""].map((x) => h("th", {}, x)))),
          h("tbody", {}, list.length ? list.map((g) => {
            const out = g.legs.find((x) => x.amount < 0), inn = g.legs.find((x) => x.amount > 0);
            const detail = g.kind === "fx" ? `${ctx.money(-out.amount, out.ccy)} → ${ctx.money(inn.amount, inn.ccy)}（1 ${out.ccy} = ${fmt(inn.amount / -out.amount, 4)} ${inn.ccy}）`
              : ctx.money(g.legs[0].amount, g.legs[0].ccy);
            return h("tr", {}, h("td", { class: "nowrap" }, g.trade_date), h("td", {}, kindName(g.kind), g.legs[0].batch ? h("span", { class: "tag" }, t("imported")) : null),
              h("td", {}, detail), h("td", { class: "small wrap" }, g.note),
              h("td", { class: "row nowrap" },
                h("button", { class: "btn small-btn", onclick: () => { dlg.close(); cashDialog(g.kind, g); } }, t("pfEdit")),
                h("button", { class: "btn danger small-btn", onclick: async () => {
                  if (!confirm(t("capDelConfirm"))) return;
                  try { await api(`/api/portfolio/cash/${g.grp}`, { method: "DELETE" }); await ctx.reload(); draw(); } catch (ex) { toast(ex.message); }
                } }, "✕")));
          }) : h("tr", {}, h("td", { colspan: 5, class: "empty" }, t("capNoRecords")))))),
        Object.keys(bal).length ? h("p", { class: "muted small" }, `${t("capTradeEffect")}：`,
          Object.entries(bal).map(([c, v]) => `${ctx.money(v, c)}`).join("，")) : null));
    };
    draw();
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg); dlg.showModal();
  }

  return { el, update };
}

export { usdTo };
