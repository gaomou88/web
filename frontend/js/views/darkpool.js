import { api, compact, emptyPanel, fmt, fmtDateTime, guarded, h, live, pct, symbolInput } from "../core.js";
import { interactiveChart, movingAvg } from "../chart.js";
import { prefs, t } from "../i18n.js";

const TABS = ["offExchange", "atsFirms", "stock", "rtPrints"];

function table(head, rows, numericFrom = 1) {
  return h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, head.map((x, i) => h("th", { class: i >= numericFrom ? "num" : "" }, x)))),
    h("tbody", {}, rows.length ? rows : h("tr", {}, h("td", { colspan: head.length, class: "empty" }, t("noData"))))));
}

function ratioRow(r) {
  return h("tr", {},
    h("td", {}, h("a", { href: `#/darkpool?sym=${r.symbol}` }, h("b", {}, r.symbol))),
    h("td", { class: "num" }, compact(r.total)),
    h("td", { class: "num" }, compact(r.short)),
    h("td", { class: "num" }, pct(r.ratio)),
    h("td", {}, h("div", { class: "bar", title: pct(r.ratio) }, h("i", { style: { width: `${Math.min(100, r.ratio * 100)}%` } }))));
}

/** “数据日期 X · 更新于 Y” */
function stamp(dataDate, fetched) {
  const parts = [];
  if (dataDate) parts.push(`${t("dataDate")} ${dataDate}`);
  if (fetched) parts.push(`${t("updatedAt")} ${fmtDateTime(fetched)}`);
  return parts.length ? h("span", { class: "stamp" }, parts.join(" · ")) : null;
}

/** 全市场场外卖空占比：统计指标 + 区间切换 + 交互图（柱：场外成交量；线：卖空占比和 20 日均线）。 */
function marketPanel(d) {
  const all = d.market || [];
  const box = h("section", { class: "panel glass" });
  let range = prefs.getJSON("mg.dp.range", "3m");
  let off = null;
  const r = all.map((m) => m.ratio * 100);
  const ma20 = movingAvg(r, 20);
  const vol20 = movingAvg(all.map((m) => m.total), 20);
  const last = all.length - 1;
  const recent = r.slice(-90);
  const pctile = recent.length > 5 ? (recent.filter((v) => v <= r[last]).length / recent.length) * 100 : null;
  const stat = (label, value, sub, cls = "") => h("div", { class: "stat" }, h("div", { class: "muted small" }, label), h("b", { class: cls }, value), sub ? h("div", { class: "small muted" }, sub) : null);
  const stats = last >= 0 ? h("div", { class: "stats" },
    stat(t("latestRatio"), pct(all[last].ratio), all[last].date),
    stat(t("ma20"), ma20[last] != null ? `${fmt(ma20[last], 1)}%` : "—",
      ma20[last] != null ? `${t("vsMa")} ${r[last] >= ma20[last] ? "+" : ""}${fmt(r[last] - ma20[last], 1)} pt` : t("histFilling"), ma20[last] != null ? (r[last] >= ma20[last] ? "up" : "down") : ""),
    stat(t("pctile90"), pctile != null ? `${fmt(pctile, 0)}%` : "—", pctile != null ? (pctile >= 80 ? t("pctHigh") : pctile <= 20 ? t("pctLow") : t("pctMid")) : t("histFilling")),
    stat(t("rangeHL"), recent.length ? `${fmt(Math.max(...recent), 1)}% / ${fmt(Math.min(...recent), 1)}%` : "—", `${recent.length} ${t("tradingDays")}`),
    stat(t("offVolume"), compact(all[last].total), vol20[last] ? `${t("vsAvg20")} ${all[last].total >= vol20[last] ? "+" : ""}${fmt((all[last].total / vol20[last] - 1) * 100, 0)}%` : t("histFilling")),
  ) : null;
  const canvas = h("canvas", { class: "chart chart-lg" });
  const seg = h("div", { class: "seg small-seg", role: "group" });
  const note = h("p", { class: "muted small" });
  function draw() {
    off?.();
    const n = { "1m": 22, "3m": 66, all: all.length }[range] || all.length;
    const from = Math.max(0, all.length - n);
    const sl = all.slice(from);
    seg.replaceChildren(...[["1m", t("range1m")], ["3m", t("range3m")], ["all", t("rangeAll")]].map(([k, l]) =>
      h("button", { "aria-pressed": String(k === range), onclick: () => { range = k; prefs.setJSON("mg.dp.range", k); draw(); } }, l)));
    if (sl.length < 2) { canvas.hidden = true; note.textContent = t("histFillingLong"); return; }
    canvas.hidden = false; note.textContent = sl.length < 20 ? t("histFillingLong") : "";
    off = interactiveChart(canvas, {
      labels: sl.map((m) => m.date.slice(5)),
      tipTitle: (i) => sl[i].date,
      series: [
        { name: t("offVolume"), type: "bar", values: sl.map((m) => m.total), color: "rgba(127,216,255,.28)" },
        { name: t("shortRatio"), type: "line", axis: "right", values: r.slice(from), color: "#47c6c0" },
        { name: t("ma20"), type: "line", axis: "right", values: ma20.slice(from), color: "#f5b971", dash: [5, 4], width: 1.6 },
      ],
      fmtLeft: compact, fmtRight: (v) => `${fmt(v, 1)}%`,
    });
  }
  box.append(
    h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, t("marketRatio")), h("span", { class: "spacer" }), seg),
    h("p", { class: "sub" }, t("marketRatioSub"), " ", stamp(d.date, d.fetched)),
    stats, canvas, note);
  requestAnimationFrame(draw);
  return box;
}

export default function darkpoolView(el) {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  let tab = params.get("sym") ? "stock" : prefs.getJSON("mg.dp.tab", "offExchange");
  const body = h("div", { style: { display: "grid", gap: "16px" } });
  const seg = h("div", { class: "seg", role: "tablist" });
  const cleanups = [];
  const tabCleanups = [];

  el.append(h("section", { class: "panel glass" },
    h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, t("darkpool")), h("span", { class: "spacer" }), seg)), body);

  const guard = (fn) => guarded(body, fn);

  function renderSeg() {
    seg.replaceChildren(...TABS.map((k) => h("button", { role: "tab", "aria-pressed": String(k === tab), onclick: () => { tab = k; prefs.setJSON("mg.dp.tab", k); renderSeg(); show(); } }, t(k))));
  }

  /* ----- 场外成交（FINRA 每日） ----- */
  const showDaily = guard(async () => {
    const [d, w] = await Promise.all([api("/api/darkpool/daily"), api("/api/darkpool/watch").catch(() => null)]);
    if (!d) { body.replaceChildren(emptyPanel()); return; }
    const head = [t("symbol"), t("offVol"), t("shortVol"), t("shortRatio"), ""];
    const watchRows = w ? w.rows : d.watchlist;
    body.replaceChildren(
      marketPanel(d),
      h("div", { class: "grid-2" },
        h("section", { class: "panel glass" },
          h("h2", {}, w?.synced ? t("watchSynced") : t("watchlist")),
          h("p", { class: "sub" }, w?.synced ? t("watchSyncedSub") : t("watchDefaultSub"), " ", stamp(w?.date || d.date, d.fetched)),
          table(head, watchRows.map(ratioRow)),
          w?.missing?.length ? h("p", { class: "muted small" }, `${t("noOffData")}：${w.missing.join("、")}`) : null),
        h("section", { class: "panel glass" }, h("h2", {}, t("topShort")), h("p", { class: "sub" }, stamp(d.date, d.fetched)),
          table(head, d.top_short_ratio.slice(0, 20).map(ratioRow)))),
      h("section", { class: "panel glass" }, h("h2", {}, t("topVolume")), h("p", { class: "sub" }, stamp(d.date, d.fetched)),
        table(head, d.top_volume.slice(0, 40).map(ratioRow))),
    );
  });

  /* ----- ATS 机构排行 ----- */
  const showAts = guard(async () => {
    const d = await api("/api/darkpool/ats");
    if (!d) { body.replaceChildren(emptyPanel()); return; }
    const max = d.firms[0]?.share_pct || 1;
    body.replaceChildren(h("section", { class: "panel glass" },
      h("h2", {}, `${t("atsFirms")}（${t("week")} ${d.week}）`), h("p", { class: "sub" }, t("atsSub"), " ", stamp(`${t("week")} ${d.week}`, d.fetched)),
      table([t("firm"), "MPID", t("shares"), t("trades"), t("avgSize"), t("share"), ""], d.firms.slice(0, 40).map((f) => h("tr", {},
        h("td", { class: "wrap" }, f.name), h("td", { class: "num muted" }, f.mpid),
        h("td", { class: "num" }, compact(f.shares)), h("td", { class: "num" }, compact(f.trades)),
        h("td", { class: "num" }, fmt(f.avg_size, 0)), h("td", { class: "num" }, pct(f.share_pct)),
        h("td", {}, h("div", { class: "bar" }, h("i", { style: { width: `${(f.share_pct / max) * 100}%` } }))))), 1)));
  });

  /* ----- 个股 ----- */
  const showStock = guard(async () => {
    const ac = symbolInput({ placeholder: t("searchSymbol"), value: params.get("sym") || prefs.getJSON("mg.dp.sym", "NVDA"), onPick: () => go() });
    const input = ac.input;
    const out = h("div", { style: { display: "grid", gap: "16px" } });
    const go = guarded(out, async () => {
      const sym = input.value.trim().toUpperCase();
      if (!sym) return;
      prefs.setJSON("mg.dp.sym", sym);
      out.replaceChildren(emptyPanel("…"));
      const d = await api(`/api/darkpool/symbol/${encodeURIComponent(sym)}`);
      const canvas = h("canvas", { class: "chart" });
      const ats = d.ats && d.ats.firms ? d.ats : null;
      out.replaceChildren(
        h("section", { class: "panel glass" }, h("h2", {}, `${sym} ${t("symHistory")}`),
          h("p", { class: "sub" }, stamp(d.history.at(-1)?.date, null)),
          d.history.length ? canvas : h("div", { class: "empty" }, t("noData")),
          d.history.length && d.history.length < 5 ? h("p", { class: "muted small" }, t("histFillingLong")) : null),
        h("section", { class: "panel glass" }, h("h2", {}, `${t("symAts")}${ats ? `（${t("week")} ${ats.week}）` : ""}`),
          h("p", { class: "sub" }, t("atsSub"), " ", ats ? stamp(`${t("week")} ${ats.week}`, ats.fetched) : null),
          ats ? table([t("firm"), "MPID", t("shares"), t("trades"), t("avgSize"), t("share")], ats.firms.map((f) => h("tr", {},
            h("td", { class: "wrap" }, f.name), h("td", { class: "num muted" }, f.mpid), h("td", { class: "num" }, compact(f.shares)),
            h("td", { class: "num" }, compact(f.trades)), h("td", { class: "num" }, fmt(f.avg_size, 0)), h("td", { class: "num" }, pct(f.share_pct)))))
            : h("div", { class: "empty" }, t("noData"))),
      );
      if (d.history.length) {
        const r = d.history.map((x) => x.ratio * 100);
        tabCleanups.push(interactiveChart(canvas, {
          labels: d.history.map((x) => x.date.slice(5)), tipTitle: (i) => d.history[i].date,
          series: [
            { name: t("offVolume"), type: "bar", values: d.history.map((x) => x.total), color: "rgba(127,216,255,.28)" },
            { name: t("shortRatio"), type: "line", axis: "right", values: r, color: "#47c6c0" },
            { name: t("ma20"), type: "line", axis: "right", values: movingAvg(r, 20), color: "#f5b971", dash: [5, 4], width: 1.6 },
          ],
          fmtLeft: compact, fmtRight: (v) => `${fmt(v, 1)}%`,
        }));
      }
    });
    body.replaceChildren(h("section", { class: "panel glass" },
      h("form", { class: "row", onsubmit: (e) => { e.preventDefault(); ac.close(); go(); } }, ac.wrap, h("button", { class: "btn primary", type: "submit" }, t("look")))), out);
    go();
  });

  /* ----- 实时大单（付费源） ----- */
  const showPrints = guard(async () => {
    const d = await api("/api/darkpool/prints?limit=300");
    if (!d.meta.enabled) {
      body.replaceChildren(emptyPanel(t("rtUnavailable")));
      return;
    }
    const row = (p) => h("tr", {},
      h("td", {}, fmtDateTime(p.ts)), h("td", {}, h("b", {}, p.symbol)), h("td", { class: "num" }, fmt(p.price, 2)),
      h("td", { class: "num" }, compact(p.size)), h("td", { class: "num" }, compact(p.notional)), h("td", { class: "num muted" }, p.venue));
    const tbody = h("tbody", {}, d.prints.length ? d.prints.map(row) : h("tr", {}, h("td", { colspan: 6, class: "empty" }, t("waitingPrints"))));
    body.replaceChildren(h("section", { class: "panel glass" },
      h("p", { class: "sub" }, `${t("minNotional")} ${compact(d.meta.min_notional)}`, " ", stamp(null, d.prints[0]?.ts)),
      h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, [t("time"), t("symbol"), t("price"), t("size"), t("notional"), t("venue")].map((x, i) => h("th", { class: i > 1 ? "num" : "" }, x)))),
        tbody))));
    tabCleanups.push(live.on("dark_print", (p) => {
      if (tbody.querySelector(".empty")) tbody.replaceChildren();
      const r = row(p); r.classList.add("flash");
      tbody.prepend(r);
      while (tbody.children.length > 300) tbody.lastChild.remove();
    }));
  });

  function show() {
    while (tabCleanups.length) tabCleanups.pop()();
    ({ offExchange: showDaily, atsFirms: showAts, stock: showStock, rtPrints: showPrints })[tab]();
  }

  renderSeg();
  show();
  cleanups.push(live.on("finra_daily", () => tab === "offExchange" && showDaily()));
  cleanups.push(live.on("finra_ats", () => tab === "atsFirms" && showAts()));
  return () => { [...cleanups, ...tabCleanups].forEach((f) => f()); };
}
