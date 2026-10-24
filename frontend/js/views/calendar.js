import { api, dayKey, telemetry, fmtDay, fmtTime, h, live, tzMidnight } from "../core.js";
import { drawLines } from "../chart.js";
import { DEFAULT_REGIONS, REGIONS, eventTitle, prefs, regionName, t } from "../i18n.js";

const RANGES = ["yesterday", "today", "tomorrow", "thisWeek", "nextWeek"];

function rangeBounds(range) {
  const now = Date.now() / 1000;
  const today = dayKey(now);
  const start = tzMidnight(today);
  const day = 86400;
  // 周一为一周开始
  const dow = (new Date(today + "T12:00:00Z").getUTCDay() + 6) % 7;
  const weekStart = tzMidnight(dayKey(start + 43200 - dow * day));
  switch (range) {
    case "yesterday": return [tzMidnight(dayKey(start - 43200)), start];
    case "today": return [start, tzMidnight(dayKey(start + day + 43200))];
    case "tomorrow": { const s = tzMidnight(dayKey(start + day + 43200)); return [s, tzMidnight(dayKey(s + day + 43200))]; }
    case "thisWeek": return [weekStart, tzMidnight(dayKey(weekStart + 7 * day + 43200))];
    case "nextWeek": { const s = tzMidnight(dayKey(weekStart + 7 * day + 43200)); return [s, tzMidnight(dayKey(s + 7 * day + 43200))]; }
  }
  return [start, start + day];
}

/** 公布值相对预测值的方向：优先使用源站给出的“利好/利空本币”判断。 */
function actualClass(ev) {
  if (!ev.actual) return "";
  if (ev.surprise > 0) return "up";
  if (ev.surprise < 0) return "down";
  return "";
}

const HOLIDAY_REGION = { NYSE: "US", CME: "US", CFETS: "CN" };

/** 美股/期货/外汇今天的休市情况（显示在日历上方）。 */
export function marketStrip(today) {
  if (!today) return null;
  const items = [];
  if (today.us_closed) items.push(`🇺🇸 ${t("usClosed")}${today.us_closed_zh ? `（${today.us_closed_zh}）` : ""}`);
  else if (today.us_early) items.push(`🇺🇸 ${t("usEarly")}（${today.us_early}）`);
  if (today.cme && !today.weekend) items.push(`📈 ${today.cme}`);
  if (!today.cfets_open && !today.weekend) items.push(`🇨🇳 ${t("cfetsClosed")}`);
  if (!items.length) return null;
  return h("div", { class: "market-strip glass", role: "status" }, items.map((x) => h("span", {}, x)));
}

export default function calendarView(el) {
  let events = [];
  let holidays = [];
  let today = null;
  let nextList = [];
  let range = prefs.getJSON("mg.cal.range", "today");
  let impacts = new Set(prefs.getJSON("mg.cal.imp", [3, 2, 1, 0]));
  if (!prefs.getJSON("mg.cal.v2", false)) {  // 新版默认显示节假日（旧版保存的筛选里没有“假日”）
    impacts.add(0); prefs.setJSON("mg.cal.imp", [...impacts]); prefs.setJSON("mg.cal.v2", true);
  }
  let regions = new Set(prefs.getJSON("mg.cal.regions", DEFAULT_REGIONS));
  const flashed = new Set();

  const countdown = h("section", { class: "countdown glass", "aria-live": "polite" });
  const tbody = h("tbody");
  const filters = h("div", { class: "filters" });
  const rangeSeg = h("div", { class: "seg", role: "group" });

  const strip = h("div");
  el.append(
    strip,
    countdown,
    h("section", { class: "panel glass" },
      h("div", { class: "row", style: { marginBottom: "12px" } },
        h("h2", { style: { margin: 0 } }, t("calendar")), h("span", { class: "spacer" }), rangeSeg),
      filters,
      h("div", { class: "table-wrap" },
        h("table", {},
          h("thead", {}, h("tr", {},
            h("th", {}, t("time")), h("th", {}, t("region")), h("th", {}, t("importance")), h("th", {}, t("event")),
            h("th", { class: "num" }, t("actual")), h("th", { class: "num" }, t("forecast")), h("th", { class: "num" }, t("previous")))),
          tbody)),
    ),
  );

  function renderFilters() {
    rangeSeg.replaceChildren(...RANGES.map((r) => h("button", { "aria-pressed": String(r === range), onclick: () => { range = r; prefs.setJSON("mg.cal.range", r); renderFilters(); renderTable(); } }, t(r))));
    const imp = [3, 2, 1, 0].map((n) => h("button", { class: "chip", "aria-pressed": String(impacts.has(n)), onclick: () => {
      impacts.has(n) ? impacts.delete(n) : impacts.add(n); prefs.setJSON("mg.cal.imp", [...impacts]); renderFilters(); renderTable();
    } }, n ? h("span", { class: `imp l${n}` }, h("i"), h("i"), h("i")) : null, t(`imp${n}`)));
    const reg = Object.keys(REGIONS).map((code) => h("button", { class: "chip", "aria-pressed": String(regions.has(code)), onclick: () => {
      regions.has(code) ? regions.delete(code) : regions.add(code); prefs.setJSON("mg.cal.regions", [...regions]); renderFilters(); renderTable();
    } }, regionName(code)));
    filters.replaceChildren(h("div", { class: "row" }, imp), h("div", { class: "row" }, reg));
  }

  /** 节假日作为“假日”行放在当天最前面（受“假日”重要性筛选和地区筛选控制）。 */
  function holidayEvents() {
    const seen = new Set();
    const out = [];
    const marketDays = new Set(holidays.filter((x) => x.region === "NYSE" && x.kind === "closed").map((x) => x.date));
    const zh = prefs.lang === "zh";
    for (const x of holidays) {
      if (x.kind === "workday") continue;
      if (x.region === "US" && marketDays.has(x.date)) continue;  // 已有“美股休市”行
      const region = HOLIDAY_REGION[x.region] || x.region;
      const label = x.region in HOLIDAY_REGION
        ? (zh ? x.name_zh : `${x.region}: ${x.name} (${x.kind === "early" ? "early close" : "closed"})`)
        : (zh ? x.name_zh || x.name : x.name);
      const key = `${x.date}|${region}|${label}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ id: `h:${key}`, ts: tzMidnight(x.date), holiday: true, kind: x.kind, market: x.region in HOLIDAY_REGION,
        region, impact: 0, title: label, actual: "", forecast: "", previous: "" });
    }
    return out;
  }

  function visible() {
    const [lo, hi] = rangeBounds(range);
    const all = [...holidayEvents(), ...events.filter((e) => !(e.impact === 0 && /holiday/i.test(e.title)))];
    all.sort((a, b) => a.ts - b.ts || (b.holiday ? 1 : 0) - (a.holiday ? 1 : 0));
    return all.filter((e) => e.ts >= lo && e.ts < hi && impacts.has(e.impact) && regions.has(e.region));
  }

  function renderTable() {
    const now = Date.now() / 1000;
    const rows = [];
    let lastDay = null;
    let markedNow = false;
    for (const ev of visible()) {
      const dk = dayKey(ev.ts);
      if (dk !== lastDay) { rows.push(h("tr", { class: "day-row" }, h("td", { colspan: 7 }, fmtDay(ev.ts)))); lastDay = dk; }
      const cls = [ev.ts < now - 60 ? "past" : "", !markedNow && ev.ts >= now - 60 ? "now" : "", flashed.has(ev.id) ? "flash" : ""].join(" ");
      if (ev.ts >= now - 60) markedNow = true;
      if (ev.holiday) {
        rows.push(h("tr", { class: `holiday-row ${ev.market ? "market" : ""}` },
          h("td", {}, t("allDay")), h("td", {}, regionName(ev.region)),
          h("td", {}, h("span", { class: "tag hol" }, ev.kind === "early" ? t("earlyClose") : ev.market ? t("closedTag") : t("imp0"))),
          h("td", { colspan: 4, class: "wrap" }, ev.title)));
        continue;
      }
      rows.push(h("tr", { class: `${cls} ev-row`, "data-id": ev.id, tabindex: "0", "aria-label": `${eventTitle(ev.title)}：${t("evDetail")}` },
        h("td", {}, ev.impact === 0 ? t("allDay") : fmtTime(ev.ts)),
        h("td", {}, regionName(ev.region)),
        h("td", {}, h("span", { class: `imp l${ev.impact}`, title: t(`imp${ev.impact}`) }, h("i"), h("i"), h("i"))),
        h("td", { class: "wrap", title: ev.title }, eventTitle(ev.title), ev.is_org ? h("span", { class: "tag org" }, t("org")) : null),
        h("td", { class: `num ${actualClass(ev)}` }, h("b", {}, ev.actual || "—"),
          ev.revision ? h("div", { class: "muted small" }, `${t("revised")} ${ev.revision}`) : null),
        h("td", { class: "num" }, ev.forecast || "—"),
        h("td", { class: "num" }, ev.previous || "—"),
      ));
    }
    tbody.replaceChildren(...(rows.length ? rows : [h("tr", {}, h("td", { colspan: 7, class: "empty" }, t("noEvents")))]));
    flashed.clear();
  }

  function renderCountdown() {
    const now = Date.now() / 1000;
    // 到点后还没公布值的继续显示（等待公布，最多 30 分钟），公布后再显示 2 分钟，避免在两个事件之间跳来跳去
    const active = (e) => e.ts > now || (!e.actual && now - e.ts < 1800) || (e.actual && now - e.ts < 120);
    const seen = new Set();
    const pool = [...events, ...nextList].filter((e) => e.impact === 3 && !seen.has(e.id) && seen.add(e.id) && active(e)).sort((a, b) => a.ts - b.ts);
    const next = pool.find((e) => regions.has(e.region)) || pool[0];
    if (!next) {
      countdown.replaceChildren(h("div", { class: "what" }, h("span", {}, t("nextKey")), h("strong", {}, t("noNextKey"))));
      return;
    }
    let s = Math.max(0, Math.floor(next.ts - now));
    const d = Math.floor(s / 86400); s %= 86400;
    const hh = String(Math.floor(s / 3600)).padStart(2, "0");
    const mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
    const ss = String(s % 60).padStart(2, "0");
    const due = next.ts <= now;
    countdown.replaceChildren(
      due ? h("div", { class: `clock due${next.actual ? " done" : ""}`, "aria-live": "polite" }, next.actual ? t("released") : t("awaitingPrint"))
        : h("div", { class: "clock", "aria-label": t("nextKey") }, d ? h("b", {}, `${d}d `) : null, `${hh}:${mm}:`, h("b", {}, ss)),
      h("div", { class: "what" },
        h("span", {}, `${t("nextKey")}${prefs.lang === "zh" ? "：" : ": "}${fmtDay(next.ts)} ${fmtTime(next.ts)}`),
        h("strong", {}, `${regionName(next.region)}  ${eventTitle(next.title)}`)),
      h("div", { class: "vals" },
        next.actual ? h("div", {}, t("actual"), h("b", { class: actualClass(next) }, next.actual)) : null,
        h("div", {}, t("forecast"), h("b", {}, next.forecast || "—")),
        h("div", {}, t("previous"), h("b", {}, next.previous || "—"))),
    );
  }

  async function load() {
    try {
      const [ev, nx, hol] = await Promise.all([api("/api/calendar"), api("/api/calendar/next").catch(() => []), api("/api/holidays").catch(() => null)]);
      events = ev || [];
      nextList = nx || [];
      if (hol) { holidays = hol.items || []; today = hol.today; strip.replaceChildren(...[marketStrip(today)].filter(Boolean)); }
      renderTable(); renderCountdown();
    } catch (e) { telemetry.push("error", "#/calendar", e.message); renderTable(); renderCountdown(); }
  }

  /* ---------- 详情：电脑悬停自动显示，手机点击显示 ---------- */
  const pop = h("div", { class: "ev-pop glass", role: "dialog", hidden: true });
  document.body.append(pop);
  const cacheDetail = new Map();
  let popFor = null, pinned = false, hoverTimer = null;
  const canHover = matchMedia("(hover: hover) and (pointer: fine)").matches;

  async function showDetail(row, pin) {
    const id = row.dataset.id;
    popFor = id; pinned = pin;
    pop.hidden = false;
    place(row);
    if (!cacheDetail.has(id)) {
      pop.replaceChildren(h("div", { class: "muted small" }, "…"));
      try { cacheDetail.set(id, await api(`/api/calendar/event/${encodeURIComponent(id)}`)); } catch { pop.hidden = true; return; }
    }
    if (popFor !== id) return;
    renderDetail(cacheDetail.get(id));
    place(row);
  }

  function place(row) {
    if (matchMedia("(max-width: 700px)").matches) { pop.classList.add("sheet"); return; }
    pop.classList.remove("sheet");
    const r = row.getBoundingClientRect();
    const pw = Math.min(460, innerWidth - 24);
    let left = Math.min(Math.max(12, r.left + r.width / 2 - pw / 2), innerWidth - pw - 12);
    let top = r.bottom + 6;
    const ph = pop.offsetHeight || 360;
    if (top + ph > innerHeight - 8) top = Math.max(8, r.top - ph - 6);
    Object.assign(pop.style, { left: `${left}px`, top: `${top}px`, width: `${pw}px` });
  }

  function renderDetail(d) {
    const ev = d.event;
    const canvas = h("canvas", { class: "ev-chart" });
    const hist = d.history || [];
    const effect = d.effect === "up" ? t("effUp") : d.effect === "down" ? t("effDown") : d.effect ? "" : t("effNone");
    pop.replaceChildren(...[
      h("div", { class: "row" },
        h("b", {}, `${regionName(ev.region)}  ${d.name_zh || eventTitle(ev.title)}`), h("span", { class: "spacer" }),
        h("button", { class: "btn small-btn", "aria-label": t("close"), onclick: hide }, "✕")),
      h("div", { class: "muted small" }, ev.title),
      d.desc ? h("p", { class: "ev-desc" }, d.desc) : h("p", { class: "ev-desc muted" }, t("evNoDesc")),
      effect ? h("p", { class: "small muted" }, effect) : null,
      hist.filter((x) => x.a != null || x.f != null).length >= 2 ? canvas : h("p", { class: "muted small" }, t("evNoHistory")),
      hist.length ? h("div", { class: "table-wrap" }, h("table", { class: "ev-hist" },
        h("thead", {}, h("tr", {}, [t("date"), t("actual"), t("forecast")].map((x, i) => h("th", { class: i ? "num" : "" }, x)))),
        h("tbody", {}, hist.slice(-6).reverse().map((x) => h("tr", {}, h("td", {}, fmtDay(x.ts)),
          h("td", { class: "num" }, x.actual || "—"), h("td", { class: "num" }, x.forecast || "—")))))) : null,
    ].filter(Boolean));
    if (canvas.isConnected) {
      requestAnimationFrame(() => drawLines(canvas, {
        labels: hist.map((x) => { const d = new Date(x.ts * 1000); return `${d.getMonth() + 1}/${d.getDate()}`; }),
        series: [{ name: t("actual"), values: hist.map((x) => x.a), color: "#47c6c0" },
                 { name: t("forecast"), values: hist.map((x) => x.f), color: "#f5b971", dash: [5, 4] }],
        fmt: (v) => { const a = Math.abs(v); const u = d.unit;
          if (u === "K" || a >= 1e3 && a < 1e6) return `${(v / 1e3).toFixed(a >= 1e5 ? 0 : 1)}K`;
          if (u === "M" || a >= 1e6 && a < 1e9) return `${(v / 1e6).toFixed(1)}M`;
          if (u === "B" || a >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
          return `${+v.toFixed(2)}${u === "%" ? "%" : ""}`; },
      }));
    }
  }

  function hide() { pop.hidden = true; popFor = null; pinned = false; }

  tbody.addEventListener("click", (e) => {
    const row = e.target.closest("tr.ev-row");
    if (!row) return;
    if (popFor === row.dataset.id && pinned) { hide(); return; }
    showDetail(row, true);
  });
  tbody.addEventListener("keydown", (e) => {
    const row = e.target.closest("tr.ev-row");
    if (row && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); showDetail(row, true); }
  });
  if (canHover) {
    tbody.addEventListener("mouseover", (e) => {
      const row = e.target.closest("tr.ev-row");
      if (!row || pinned || popFor === row.dataset.id) return;
      clearTimeout(hoverTimer);
      hoverTimer = setTimeout(() => showDetail(row, false), 220);
    });
    tbody.addEventListener("mouseleave", () => { clearTimeout(hoverTimer); if (!pinned) setTimeout(() => { if (!pinned && !pop.matches(":hover")) hide(); }, 150); });
    pop.addEventListener("mouseleave", () => { if (!pinned) hide(); });
  }
  const onDocClick = (e) => { if (!pop.hidden && !pop.contains(e.target) && !e.target.closest("tr.ev-row")) hide(); };
  const onKey = (e) => { if (e.key === "Escape") hide(); };
  document.addEventListener("click", onDocClick);
  document.addEventListener("keydown", onKey);
  window.addEventListener("scroll", () => { if (!pop.hidden && !pinned) hide(); }, { passive: true });

  renderFilters();
  load();
  const offLive = live.on("calendar", (updated) => {
    if (Array.isArray(updated) && updated.length) {
      const byId = new Map(updated.map((u) => [u.id, u]));
      events = events.map((e) => byId.get(e.id) || e);
      nextList = nextList.map((e) => byId.get(e.id) || e);
      updated.forEach((u) => flashed.add(u.id));
      renderTable(); renderCountdown();
    } else load();
  });
  const offHol = live.on("holidays", (d) => { if (d?.items) { holidays = d.items; today = d.today; strip.replaceChildren(...[marketStrip(today)].filter(Boolean)); renderTable(); } });
  const tick = setInterval(renderCountdown, 1000);
  const minute = setInterval(renderTable, 60000); // 推进“已过去”高亮
  return () => { offLive(); clearInterval(tick); clearInterval(minute); pop.remove(); offHol(); document.removeEventListener("click", onDocClick); document.removeEventListener("keydown", onKey); };
}
