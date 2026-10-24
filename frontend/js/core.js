import { prefs, t } from "./i18n.js";

/* ---------- DOM ---------- */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function toast(msg, ms = 2600) {
  document.querySelectorAll(".toast").forEach((x) => x.remove());
  const el = h("div", { class: "toast glass", role: "status" }, msg);
  document.body.append(el);
  setTimeout(() => el.remove(), ms);
}

/* ---------- 格式化 ---------- */
const nf = {};
export function fmt(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return "—";
  const k = digits;
  nf[k] ??= new Intl.NumberFormat(prefs.lang === "zh" ? "zh-CN" : "en-US", { minimumFractionDigits: k, maximumFractionDigits: k });
  return nf[k].format(n);
}
export function compact(n) {
  if (n == null || Number.isNaN(n)) return "—";
  if (prefs.lang === "zh") {
    const a = Math.abs(n);
    if (a >= 1e8) return fmt(n / 1e8, 2) + "亿";
    if (a >= 1e4) return fmt(n / 1e4, 1) + "万";
    return fmt(n, 0);
  }
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(n);
}
export function pct(n, digits = 1) {
  return n == null ? "—" : fmt(n * 100, digits) + "%";
}
export function signed(n, digits = 2, suffix = "") {
  if (n == null) return "—";
  return (n > 0 ? "+" : "") + fmt(n, digits) + suffix;
}
export function dirClass(n) {
  return n > 0 ? "up" : n < 0 ? "down" : "";
}

const dtf = {};
function formatter(key, opts) {
  const id = `${key}|${prefs.tz}|${prefs.lang}`;
  dtf[id] ??= new Intl.DateTimeFormat(prefs.lang === "zh" ? "zh-CN" : "en-GB", { timeZone: prefs.tz, ...opts });
  return dtf[id];
}
export const fmtTime = (sec) => formatter("t", { hour: "2-digit", minute: "2-digit", hour12: false }).format(sec * 1000);
export const fmtDay = (sec) => formatter("d", { month: "short", day: "numeric", weekday: "short" }).format(sec * 1000);
export const fmtDateTime = (sec) =>
  formatter("dt", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(sec * 1000);
/** 所选时区下的日期键 YYYY-MM-DD */
export function dayKey(sec) {
  const id = `k|${prefs.tz}`;
  dtf[id] ??= new Intl.DateTimeFormat("en-CA", { timeZone: prefs.tz, year: "numeric", month: "2-digit", day: "2-digit" });
  return dtf[id].format(sec * 1000); // en-CA 输出 YYYY-MM-DD
}

/** 所选时区内某天 00:00 对应的 Unix 秒（通过偏移量推算，处理夏令时）。 */
export function tzMidnight(dateKey) {
  const [y, m, d] = dateKey.split("-").map(Number);
  let guess = Date.UTC(y, m - 1, d) / 1000;
  for (let i = 0; i < 2; i++) {
    const parts = formatter("p", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })
      .formatToParts(guess * 1000).reduce((o, p) => ((o[p.type] = p.value), o), {});
    const asUTC = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour % 24, +parts.minute) / 1000;
    guess -= asUTC - Date.UTC(y, m - 1, d) / 1000;
  }
  return guess;
}

/* ---------- API ---------- */
export class AuthError extends Error {}
export class MembersOnly extends Error {}
export async function api(path, opts = {}) {
  let res;
  const t0 = performance.now();
  try {
    res = await fetch(path, {
      credentials: "same-origin",
      ...opts,
      headers: { "X-Requested-With": "zyll", ...(opts.body ? { "Content-Type": "application/json" } : {}), ...(opts.headers || {}) },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  } catch (e) {
    telemetry.push("api", path, "network");
    throw new Error(t("netError"));
  }
  telemetry.timing(path, performance.now() - t0, res.status);
  if (res.status >= 500) telemetry.push("api", path, `HTTP ${res.status}`);
  if (res.status >= 502 && res.status <= 504) throw new Error(t("backendDown"));
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  const msg = data?.detail || `HTTP ${res.status}`;
  if (res.status === 401) throw new AuthError(msg);
  if (res.status === 403 && msg === "members_only") throw new MembersOnly(data.notice || "");
  if (!res.ok) { const e = new Error(msg); e.data = data; throw e; }
  return data;
}

/* ---------- 性能与诊断：仅在访客同意“性能 Cookie”后上报 ---------- */
export const consent = {
  get() { return (document.cookie.match(/(?:^|; )zy_consent=([^;]*)/) || [])[1] || ""; },
  set(v) { document.cookie = `zy_consent=${v}; path=/; max-age=${365 * 86400}; samesite=lax`; },
  perf() { return this.get().includes("perf"); },
};

/* 设备与环境信息：登录/注册时随请求提交，用于识别异常登录（防欺诈）；诊断数据里也会带上 */
export function deviceInfo() {
  const n = navigator, sc = window.screen || {};
  let tz = "";
  try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { /* 忽略 */ }
  return {
    tz, tzOffset: new Date().getTimezoneOffset(), langs: (n.languages || [n.language]).join(","), platform: n.userAgentData?.platform || n.platform || "",
    screen: `${sc.width}x${sc.height}`, viewport: `${innerWidth}x${innerHeight}`, dpr: devicePixelRatio, colorDepth: sc.colorDepth,
    cores: n.hardwareConcurrency || "", memory: n.deviceMemory || "", touch: n.maxTouchPoints || 0, webdriver: !!n.webdriver,
    cookies: n.cookieEnabled, dnt: n.doNotTrack || "", pdf: n.pdfViewerEnabled ?? "",
    uaData: n.userAgentData ? { brands: (n.userAgentData.brands || []).map((b) => `${b.brand} ${b.version}`).join("; "), mobile: n.userAgentData.mobile } : "",
  };
}

/* 诊断上报：只在访客同意“性能 Cookie”后启用；不与账号关联 */
export const telemetry = {
  enabled: false,
  sample: 20,
  queue: [],
  sid: (() => { try { let v = sessionStorage.getItem("zy_sid"); if (!v) { v = Math.random().toString(36).slice(2, 12); sessionStorage.setItem("zy_sid", v); } return v; } catch { return Math.random().toString(36).slice(2, 12); } })(),
  ctx() {
    const c = navigator.connection || {};
    const mem = performance.memory;
    return {
      ...deviceInfo(), url: location.pathname + location.hash, ref: document.referrer ? new URL(document.referrer).origin : "",
      theme: matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light", reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
      net: { type: c.effectiveType || "", rtt: c.rtt ?? "", downlink: c.downlink ?? "", saveData: !!c.saveData },
      heapMB: mem ? Math.round(mem.usedJSHeapSize / 1048576) : "", visible: document.visibilityState, online: navigator.onLine,
      lang: prefs.lang, tzPref: prefs.tz, sse: live.connected,
    };
  },
  start() {
    if (this.started || !this.enabled || !consent.perf()) return;
    this.started = true;
    window.addEventListener("error", (e) => this.push("error", location.hash, `${e.message} @ ${(e.filename || "").split("/").pop()}:${e.lineno}:${e.colno}`, null, { stack: String(e.error?.stack || "").slice(0, 1500) }));
    window.addEventListener("unhandledrejection", (e) => this.push("error", location.hash, String(e.reason?.message || e.reason), null, { stack: String(e.reason?.stack || "").slice(0, 1500) }));
    const sendLoad = () => {
      const nav = performance.getEntriesByType("navigation")[0];
      if (!nav) return;
      const r = (x) => Math.round(x);
      const res = performance.getEntriesByType("resource");
      this.push("load", location.pathname, nav.type || "", r(nav.loadEventEnd || nav.domContentLoadedEventEnd), {
        dns: r(nav.domainLookupEnd - nav.domainLookupStart), tcp: r(nav.connectEnd - nav.connectStart),
        tls: nav.secureConnectionStart ? r(nav.connectEnd - nav.secureConnectionStart) : 0, ttfb: r(nav.responseStart - nav.requestStart),
        download: r(nav.responseEnd - nav.responseStart), domInteractive: r(nav.domInteractive), dcl: r(nav.domContentLoadedEventEnd),
        transferKB: Math.round((nav.transferSize || 0) / 1024), protocol: nav.nextHopProtocol || "",
        resources: res.length, resourceKB: Math.round(res.reduce((a, x) => a + (x.transferSize || 0), 0) / 1024),
        slowest: res.sort((a, b) => b.duration - a.duration).slice(0, 5).map((x) => `${x.name.split("/").pop().slice(0, 40)} ${r(x.duration)}ms`),
      });
    };
    if (document.readyState === "complete") setTimeout(sendLoad, 0); else window.addEventListener("load", () => setTimeout(sendLoad, 0));
    // 核心网页指标
    const obs = (type, fn, opts = {}) => { try { new PerformanceObserver((l) => l.getEntries().forEach(fn)).observe({ type, buffered: true, ...opts }); } catch { /* 浏览器不支持 */ } };
    let lcp = 0, cls = 0, inp = 0, longTasks = 0, longMs = 0;
    obs("paint", (e) => { if (e.name === "first-contentful-paint") this.push("vitals", location.pathname, "FCP", Math.round(e.startTime)); });
    obs("largest-contentful-paint", (e) => { lcp = e.startTime; });
    obs("layout-shift", (e) => { if (!e.hadRecentInput) cls += e.value; });
    obs("event", (e) => { if (e.duration > inp) inp = e.duration; }, { durationThreshold: 40 });
    obs("longtask", (e) => { longTasks += 1; longMs += e.duration; });
    const final = () => {
      if (lcp) this.push("vitals", location.pathname, "LCP", Math.round(lcp));
      this.push("vitals", location.pathname, "CLS", Math.round(cls * 1000) / 1000);
      if (inp) this.push("vitals", location.pathname, "INP", Math.round(inp));
      if (longTasks) this.push("longtask", location.pathname, `${longTasks} 个长任务`, Math.round(longMs));
      lcp = 0; cls = 0; inp = 0; longTasks = 0; longMs = 0;
      this.flush();
    };
    window.addEventListener("hashchange", () => this.push("view", location.hash));
    setInterval(() => this.flush(), 15000);
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") final(); });
    window.addEventListener("pagehide", final);
  },
  timing(path, ms, status) {
    if (!this.started || path.startsWith("/api/telemetry")) return;
    if (Math.random() * 100 >= (this.sample ?? 20)) return;
    this.push("resource", path.split("?")[0].replace(/\/(\d+|[A-Z.\-]{1,10})$/, "/:id"), `HTTP ${status}`, Math.round(ms));
  },
  push(kind, path, message = "", value = null, detail = null) {
    if (!this.enabled || !consent.perf()) return;
    if (this.queue.length < 80) this.queue.push({ kind, path: String(path).slice(0, 200), message: String(message).slice(0, 1000), value, detail });
  },
  flush() {
    if (!this.queue.length) return;
    const body = JSON.stringify({ sid: this.sid, ctx: this.ctx(), events: this.queue.splice(0, 30) });
    if (!navigator.sendBeacon?.("/api/telemetry", new Blob([body], { type: "application/json" }))) {
      fetch("/api/telemetry", { method: "POST", body, keepalive: true, headers: { "Content-Type": "application/json" } }).catch(() => {});
    }
  },
};

/* ---------- 实时推送：SSE，浏览器原生断线重连 ---------- */
export const live = {
  listeners: new Map(),
  connected: false,
  on(topic, fn) {
    if (!this.listeners.has(topic)) this.listeners.set(topic, new Set());
    this.listeners.get(topic).add(fn);
    return () => this.listeners.get(topic).delete(fn);
  },
  emit(topic, data) { this.listeners.get(topic)?.forEach((fn) => fn(data)); },
  start() {
    if (this.es) return;
    this.es = new EventSource("/api/stream");
    this.es.onopen = () => { this.connected = true; this.emit("_conn", true); };
    this.es.onerror = () => {
      if (this.connected) telemetry.push("sse", location.hash, "disconnected");
      this.connected = false; this.emit("_conn", false);
    };
    this.es.onmessage = (e) => {
      try { const m = JSON.parse(e.data); this.emit(m.topic, m.data); } catch { /* 忽略 */ }
    };
  },
};

/* ---------- 前台统一的出错处理：不展示错误细节，只显示“暂无数据”，并记录到诊断数据 ---------- */
export const ui = { onAuth: () => {}, onLocked: null };
export function emptyPanel(text) {
  return h("div", { class: "panel glass empty" }, text || t("noData"));
}
export function lockPanel(notice) {
  return h("div", { class: "panel glass lock" },
    h("div", { class: "lock-icon", "aria-hidden": "true" }, "🔒"),
    h("p", {}, notice || t("membersOnly")),
    ui.onLocked ? h("button", { class: "btn primary", onclick: ui.onLocked }, t("activateMember")) : null);
}
/** 包装视图里的异步加载：会员锁 → 锁面板；其他错误 → 静默为空并上报。 */
export function guarded(target, fn) {
  return async (...a) => {
    try { await fn(...a); } catch (e) {
      if (e instanceof MembersOnly) target.replaceChildren(lockPanel(e.message));
      else if (e instanceof AuthError) ui.onAuth();
      else { telemetry.push("error", location.hash, e.message); target.replaceChildren(emptyPanel()); }
    }
  };
}

/* ---------- 股票代码联想输入：输入代码或公司名，方向键选择，回车确认 ---------- */
export function symbolInput({ value = "", placeholder = "", onPick = null, width = "220px" } = {}) {
  const input = h("input", {
    type: "text", value, placeholder, autocomplete: "off", spellcheck: "false", role: "combobox",
    "aria-autocomplete": "list", "aria-expanded": "false", "aria-label": placeholder, style: { width, textTransform: "uppercase" },
  });
  // 下拉列表挂在 body 上、按输入框位置浮动显示：不会被面板裁切或被后面的面板盖住
  const list = h("ul", { class: "ac-list glass", role: "listbox", hidden: true });
  const wrap = h("div", { class: "ac" }, input);
  let items = [], active = -1, timer = null, seq = 0;

  const place = () => {
    const r = input.getBoundingClientRect();
    const w = Math.min(Math.max(r.width, 320), innerWidth - 16);
    Object.assign(list.style, { left: `${Math.max(8, Math.min(r.left, innerWidth - w - 8))}px`, top: `${r.bottom + 4}px`, minWidth: `${w}px` });
  };
  const onMove = () => { if (!list.hidden) { if (!input.isConnected) close(); else place(); } };
  const close = () => {
    list.hidden = true; input.setAttribute("aria-expanded", "false"); active = -1;
    list.remove();
    window.removeEventListener("scroll", onMove, true); window.removeEventListener("resize", onMove);
  };
  const pick = (it) => {
    input.value = it.symbol;
    close();
    onPick?.(it.symbol);
  };
  const paint = () => {
    list.replaceChildren(...items.map((it, i) => h("li", {
      role: "option", class: i === active ? "on" : "", "aria-selected": String(i === active),
      onmousedown: (e) => { e.preventDefault(); pick(it); },
    }, h("b", {}, it.symbol), h("span", { class: "ac-name" }, it.name), h("span", { class: "ac-ex" }, it.etf ? "ETF" : it.exchange || ""))));
    if (!items.length || !input.isConnected) { close(); return; }
    if (!list.isConnected) {
      document.body.append(list);
      window.addEventListener("scroll", onMove, true); window.addEventListener("resize", onMove);
    }
    list.hidden = false;
    place();
    input.setAttribute("aria-expanded", "true");
  };
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { items = []; paint(); return; }
    timer = setTimeout(async () => {
      const my = ++seq;
      try {
        const r = await fetch(`/api/symbols/search?q=${encodeURIComponent(q)}`, { headers: { "X-Requested-With": "zyll" } });
        const d = r.ok ? await r.json() : [];
        if (my !== seq) return;  // 只显示最新一次输入的结果
        items = Array.isArray(d) ? d : [];
        active = items.length && items[0].symbol === q.toUpperCase() ? 0 : -1;
        paint();
      } catch { /* 联想失败不影响手动输入 */ }
    }, 120);
  });
  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    if (e.key === "ArrowDown") { e.preventDefault(); active = (active + 1) % items.length; paint(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); active = (active - 1 + items.length) % items.length; paint(); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); pick(items[active]); }
    else if (e.key === "Escape") close();
  });
  input.addEventListener("blur", () => setTimeout(close, 100));
  return { wrap, input, close };
}


/* ---------- 分析浮窗：电脑鼠标悬停自动显示，手机点击显示（底部弹出）；点击可固定 ---------- */
let cardEl = null, cardOwner = null, cardPinned = false, cardTimer = null;
const canHover = () => matchMedia("(hover: hover) and (pointer: fine)").matches;

function placeCard(target) {
  if (matchMedia("(max-width: 700px)").matches) { cardEl.classList.add("sheet"); return; }
  cardEl.classList.remove("sheet");
  const r = target.getBoundingClientRect();
  const pw = Math.min(Number(cardEl.dataset.w) || 460, innerWidth - 24);
  const left = Math.min(Math.max(12, r.left + r.width / 2 - pw / 2), innerWidth - pw - 12);
  let top = r.bottom + 6;
  const ph = cardEl.offsetHeight || 360;
  if (top + ph > innerHeight - 8) top = Math.max(8, r.top - ph - 6);
  Object.assign(cardEl.style, { left: `${left}px`, top: `${top}px`, width: `${pw}px` });
}

export function hideCard() {
  if (cardEl) cardEl.hidden = true;
  cardOwner = null; cardPinned = false;
}

/** 给元素加分析浮窗。build(card) 负责填充内容（可以是异步的），返回清理函数。 */
export function hoverCard(target, build, { width = 460 } = {}) {
  if (!cardEl) {
    cardEl = h("div", { class: "ev-pop glass", role: "dialog", hidden: true });
    document.body.append(cardEl);
    cardEl.addEventListener("mouseleave", () => { if (!cardPinned) hideCard(); });
    document.addEventListener("click", (e) => { if (cardEl && !cardEl.hidden && !cardEl.contains(e.target) && !cardOwner?.contains(e.target)) hideCard(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideCard(); });
  }
  const open = async (pin) => {
    cardOwner = target; cardPinned = pin;
    cardEl.dataset.w = width;
    cardEl.hidden = false;
    cardEl.replaceChildren(h("div", { class: "muted small" }, "…"));
    placeCard(target);
    await build(cardEl, () => placeCard(target));
    if (cardOwner === target) placeCard(target);
  };
  const enter = () => { if (!canHover() || cardPinned) return; clearTimeout(cardTimer); cardTimer = setTimeout(() => { if (cardOwner !== target) open(false); }, 200); };
  const leave = () => { clearTimeout(cardTimer); setTimeout(() => { if (!cardPinned && cardOwner === target && !cardEl.matches(":hover") && !target.matches(":hover")) hideCard(); }, 150); };
  const click = (e) => {
    if (e.target.closest("button, a, input, select")) return;
    if (cardOwner === target && cardPinned) { hideCard(); return; }
    open(true);
  };
  target.classList.add("has-card");
  target.setAttribute("tabindex", "0");
  target.addEventListener("mouseenter", enter);
  target.addEventListener("mouseleave", leave);
  target.addEventListener("click", click);
  target.addEventListener("keydown", (e) => { if (e.key === "Enter") open(true); });
  return () => { if (cardOwner === target) hideCard(); };
}
