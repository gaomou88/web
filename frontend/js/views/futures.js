import { api, compact, dirClass, fmt, h, live, lockPanel, signed, telemetry } from "../core.js";
import { sparkline } from "../chart.js";
import { t } from "../i18n.js";

export default function futuresView(el) {
  const tiles = h("div", { class: "grid-4" });
  const quoteSub = h("p", { class: "sub" }, "");
  const cot = h("div");
  const blocks = h("div", { style: { display: "contents" } });

  el.append(
    h("section", { class: "panel glass" }, h("h2", {}, t("futQuotes")), quoteSub, tiles),
    h("section", { class: "panel glass" }, h("h2", {}, t("cot")), h("p", { class: "sub" }, t("cotSub")), cot),
    blocks,
  );

  function renderQuotes(cme) {
    if (!cme?.futures) { tiles.replaceChildren(h("div", { class: "empty" }, t("noData"))); return; }
    const srcs = [...new Set(Object.values(cme.futures).map((f) => f.source || "CME"))];
    quoteSub.textContent = `${t("dataSource")}：${srcs.join("、")}` + (srcs.includes("CME") ? `（CME ${t("delayed")}）` : "");
    tiles.replaceChildren(...Object.values(cme.futures).map((f) => {
      const q = f.front;
      return h("div", { class: "tile" },
        h("div", { class: "row" }, h("span", { class: "name" }, `${f.root}  ${f.name}`), h("span", { class: "spacer" }), h("span", { class: "badge" }, q.month === "主力" ? t("frontMonth") : q.contract)),
        h("div", { class: `px ${dirClass(q.change)}` }, fmt(q.last, 2)),
        h("div", { class: `chg ${dirClass(q.change)}` }, `${signed(q.change, 2)}  ${signed(q.change_pct, 2, "%")}`),
        h("div", { class: "meta" }, [q.volume != null ? `${t("volume")} ${compact(q.volume)}` : null, `${t("priorSettle")} ${fmt(q.prior_settle, 2)}`].filter(Boolean).join("，")),
        h("div", { class: "meta" }, q.updated),
      );
    }));
  }

  function renderCot(c) {
    if (c === "locked") { cot.replaceChildren(lockPanel()); return; }
    if (!c?.markets?.length) { cot.replaceChildren(h("div", { class: "empty" }, t("noData"))); return; }
    const cell = (g) => h("td", { class: "num" }, h("div", {}, compact(g.net)), h("div", { class: `small ${dirClass(g.net_change)}` }, signed(g.net_change, 0)));
    cot.replaceChildren(h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, [t("market"), t("oi"), t("levMoney"), "", t("assetMgr"), t("dealer")].map((x, i) => h("th", { class: i ? "num" : "" }, x)))),
      h("tbody", {}, c.markets.map((m) => {
        const g = m.latest.groups;
        return h("tr", {},
          h("td", { class: "wrap" }, m.market, h("div", { class: "muted small" }, m.latest.date)),
          h("td", { class: "num" }, compact(m.latest.open_interest), h("div", { class: `small ${dirClass(m.latest.oi_change)}` }, signed(m.latest.oi_change, 0))),
          cell(g.lev_money),
          h("td", {}, sparkline(m.history.map((x) => x.groups.lev_money.net))),
          cell(g.asset_mgr), cell(g.dealer));
      })))));
  }

  function renderBlocks(b) {
    if (!b?.rows?.length) { blocks.replaceChildren(); return; }  // 未启用或无数据时整块不显示
    blocks.replaceChildren(h("section", { class: "panel glass" }, h("h2", {}, t("blocks")), h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, [t("time"), t("market"), "", "", t("size"), t("price")].map((x, i) => h("th", { class: i > 3 ? "num" : "" }, x)))),
      h("tbody", {}, b.rows.length ? b.rows.map((r) => h("tr", {}, h("td", {}, r.time), h("td", {}, r.product), h("td", {}, r.contract),
        h("td", {}, r.type), h("td", { class: "num" }, compact(r.qty)), h("td", { class: "num" }, fmt(r.price, 2))))
        : h("tr", {}, h("td", { colspan: 6, class: "empty" }, t("noData"))))))));
  }

  async function load() {
    try {
      const d = await api("/api/futures");
      renderQuotes(d.cme); renderCot(d.cot); renderBlocks(d.blocks);
    } catch (e) { telemetry.push("error", "#/futures", e.message); renderQuotes(null); renderCot(null); }
  }
  load();
  const offs = [
    live.on("futures", renderQuotes),
    live.on("cftc", load),
    live.on("futures_blocks", load),
  ];
  return () => offs.forEach((f) => f());
}
