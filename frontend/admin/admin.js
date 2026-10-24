/* Zyll财经 后台：安装向导、登录（密码 + 谷歌验证器）、各项设置。所有设置表单根据后端定义自动生成。 */
import { api, deviceInfo, fmt, h, toast } from "/js/core.js";

const root = document.getElementById("root");
let state = null;     // /api/admin/state
let schema = null;    // 设置定义 + 当前值
let cleanup = null;

const PAGES = [
  ["overview", "概览"],
  ["sources", "数据源"],
  ["calendar", "日历日程"],
  ["site", "站点"],
  ["users", "用户与注册"],
  ["mail", "邮件"],
  ["membership", "会员"],
  ["cards", "卡密"],
  ["app", "安卓 App"],
  ["portfolio", "持仓分析"],
  ["inflation", "通胀数据"],
  ["ai", "AI 导入"],
  ["ads", "广告"],
  ["security", "安全与管理员"],
  ["privacy", "隐私与合规"],
  ["diagnostics", "诊断数据"],
  ["logs", "运行日志"],
];

const dt = (sec) => (sec ? new Date(sec * 1000).toLocaleString("zh-CN", { hour12: false }) : "—");
const LOGO = () => {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 32 32");
  s.innerHTML = '<rect width="32" height="32" rx="9" fill="rgba(71,198,192,.16)" stroke="rgba(71,198,192,.5)"/><path d="M6 22l6-7 5 4 9-11" stroke="#47c6c0" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>';
  return s;
};

/* ================= 通用小部件 ================= */
function field(label, input, help) {
  return h("label", { class: "a-field" }, h("span", { class: "a-label" }, label), input, help ? h("span", { class: "a-help" }, help) : null);
}
function toggle(checked, onchange) {
  const input = h("input", { type: "checkbox", role: "switch", checked, onchange });
  return h("span", { class: "switch" }, input, h("i"));
}
function errBox() { return h("div", { class: "err", role: "alert" }); }

function qrBlock(setup) {
  const qr = h("div", { class: "qr" });
  qr.innerHTML = setup.qr; // 服务器生成的二维码 SVG
  return h("div", { class: "qr-wrap" }, qr,
    h("div", { class: "qr-text" },
      h("p", {}, "用谷歌验证器（Google Authenticator）或其他 TOTP 应用扫描二维码。无法扫码时，手动输入下面的密钥："),
      h("code", { class: "secret" }, setup.secret.replace(/(.{4})/g, "$1 ").trim()),
      h("p", { class: "muted small" }, "类型选“基于时间”。请妥善保存密钥，手机丢失时可用它恢复。")));
}

/* 设置分组表单：只提交本组的字段 */
function groupForm(group, { onSaved } = {}) {
  const values = schema.values;
  const inputs = {};
  const els = {};
  const clears = new Set();
  const rows = group.fields.map((f) => {
    const v = values[f.key];
    let input;
    if (f.type === "bool") {
      const sw = toggle(!!v);
      inputs[f.key] = () => sw.querySelector("input").checked;
      return h("div", { class: "a-field a-row" }, h("span", { class: "a-label" }, f.label), sw, f.help ? h("span", { class: "a-help" }, f.help) : null);
    }
    if (f.type === "select") {
      input = h("select", {}, f.options.map(([val, lab]) => h("option", { value: val, selected: val === v }, lab)));
      inputs[f.key] = () => input.value;
    } else if (f.type === "multi") {
      const boxes = f.options.map(([val, lab]) => {
        const cb = h("input", { type: "checkbox", value: val, checked: (v || []).includes(val) });
        return h("label", { class: "chk" }, cb, lab);
      });
      input = h("div", { class: "chk-group" }, boxes);
      inputs[f.key] = () => boxes.map((b) => b.querySelector("input")).filter((c) => c.checked).map((c) => c.value);
    } else if (f.type === "text") {
      input = h("textarea", { rows: 4, spellcheck: "false" }, v ?? "");
      inputs[f.key] = () => input.value;
    } else if (f.type === "secret") {
      // 防止浏览器密码管理器把登录密码自动填进密钥框：用普通文本框 + 圆点遮挡，并在聚焦前只读
      input = h("input", { type: "text", class: "masked", autocomplete: "off", spellcheck: "false", readonly: true,
        "data-lpignore": "true", "data-1p-ignore": "true", "data-form-type": "other",
        placeholder: v?.set ? `已设置：${v.hint}（留空则不修改）` : "未设置",
        onfocus: (e) => e.target.removeAttribute("readonly") });
      inputs[f.key] = () => input.value;
      if (v?.set) {
        const clr = h("button", { class: "btn small-btn", type: "button", onclick: () => { clears.add(f.key); input.placeholder = "将在保存时清除"; input.value = ""; } }, "清除");
        input = h("div", { class: "row nowrap" }, input, clr);
      }
    } else {
      input = h("input", { type: f.type === "int" || f.type === "float" ? "number" : "text", step: f.type === "float" ? "any" : "1", value: v ?? "",
        autocomplete: "off", "data-lpignore": "true", "data-1p-ignore": "true", "data-form-type": "other" });
      inputs[f.key] = () => input.value;
    }
    els[f.key] = input.tagName === "DIV" ? input.querySelector("input") || input : input;
    return field(f.label, input, f.help);
  });
  const err = errBox();
  const save = h("button", { class: "btn primary", type: "submit" }, "保存");
  const form = h("form", { class: "panel glass a-group", "data-group": group.id, onsubmit: async (e) => {
    e.preventDefault();
    err.textContent = ""; save.disabled = true;
    const payload = Object.fromEntries(Object.entries(inputs).map(([k, get]) => [k, get()]));
    try {
      schema = await api("/api/admin/settings", { method: "PUT", body: { values: payload, clear: [...clears] } });
      toast("已保存，立即生效");
      onSaved?.();
    } catch (ex) { err.textContent = ex.message; } finally { save.disabled = false; }
  } },
    h("div", { class: "a-group-head" }, h("h2", {}, group.title), group.desc ? h("p", { class: "sub" }, group.desc) : null),
    h("div", { class: "a-fields" }, rows),
    err,
    h("div", { class: "row" }, h("span", { class: "spacer" }), save));
  form.fieldEls = els; // 供个别页面增强（例如 AI 服务商联动）
  return form;
}
const groupsOf = (page) => schema.groups.filter((g) => g.page === page);

/* ================= 安装向导 ================= */
function renderInstall() {
  const err = errBox();
  const user = h("input", { type: "text", autocomplete: "username", required: true, minlength: 2 });
  const pw = h("input", { type: "password", autocomplete: "new-password", required: true, minlength: 8 });
  const pw2 = h("input", { type: "password", autocomplete: "new-password", required: true, minlength: 8 });
  const tokenInput = state.install_token_required ? h("input", { type: "password", required: true }) : null;
  const card = h("div", { class: "auth-card glass" });
  const step1 = h("form", { class: "dialog-form", onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    if (pw.value !== pw2.value) { err.textContent = "两次输入的密码不一致"; return; }
    try {
      const setup = await api("/api/admin/install/start", { method: "POST", body: { username: user.value.trim(), password: pw.value, install_token: tokenInput?.value } });
      showStep2(setup);
    } catch (ex) { err.textContent = ex.message; }
  } },
    h("div", { class: "steps" }, h("b", {}, "1 创建管理员"), h("span", {}, "2 绑定谷歌验证器")),
    h("h1", {}, LOGO(), `${state.site_name} 后台安装`),
    h("p", { class: "muted small" }, "这是第一次进入后台。请设置管理员账号，下一步绑定谷歌验证器，之后登录需要密码加 6 位动态码。"),
    tokenInput ? field("安装口令", tokenInput, "服务器设置了 ZYLL_INSTALL_TOKEN，请输入该口令") : null,
    field("管理员用户名", user), field("密码（至少 8 位）", pw), field("再次输入密码", pw2), err,
    h("button", { class: "btn primary", type: "submit" }, "下一步"));
  function showStep2(setup) {
    const code = h("input", { type: "text", inputmode: "numeric", autocomplete: "one-time-code", maxlength: 6, required: true, placeholder: "6 位数字" });
    const err2 = errBox();
    card.replaceChildren(h("form", { class: "dialog-form", onsubmit: async (e) => {
      e.preventDefault(); err2.textContent = "";
      try {
        await api("/api/admin/install/finish", { method: "POST", body: { token: setup.token, code: code.value, device: deviceInfo() } });
        toast("安装完成");
        boot();
      } catch (ex) { err2.textContent = ex.message; }
    } },
      h("div", { class: "steps" }, h("span", {}, "1 创建管理员"), h("b", {}, "2 绑定谷歌验证器")),
      h("h1", {}, "绑定谷歌验证器"),
      qrBlock(setup),
      field("验证器上显示的 6 位动态码", code), err2,
      h("button", { class: "btn primary", type: "submit" }, "完成安装")));
    code.focus();
  }
  card.append(step1);
  root.replaceChildren(h("div", { class: "auth-page" }, card));
  user.focus();
}

/* ================= 登录 ================= */
function renderLogin() {
  const err = errBox();
  const user = h("input", { type: "text", autocomplete: "username", required: true });
  const pw = h("input", { type: "password", autocomplete: "current-password", required: true });
  const code = h("input", { type: "text", inputmode: "numeric", autocomplete: "one-time-code", maxlength: 6, required: true, placeholder: "6 位数字" });
  let ts = null;
  if (state.turnstile) {
    ts = h("div", { class: "turnstile" });
    const s = document.createElement("script");
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    s.onload = () => window.turnstile?.render(ts, { sitekey: state.turnstile, theme: "dark" });
    document.head.append(s);
  }
  const form = h("form", { class: "dialog-form auth-card glass", onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    if (ts && !form.querySelector("[name='cf-turnstile-response']")?.value) { err.textContent = "请先完成人机验证（出现绿色对勾后再登录）"; return; }
    try {
      await api("/api/admin/login", { method: "POST", body: {
        username: user.value.trim(), password: pw.value, code: code.value,
        turnstile: form.querySelector("[name='cf-turnstile-response']")?.value || "", device: deviceInfo() } });
      boot();
    } catch (ex) { err.textContent = ex.message; code.value = ""; window.turnstile?.reset?.(); }
  } },
    h("h1", {}, LOGO(), `${state.site_name} 后台`),
    field("用户名", user), field("密码", pw), field("谷歌验证器动态码", code), ts, err,
    h("button", { class: "btn primary", type: "submit" }, "登录"));
  root.replaceChildren(h("div", { class: "auth-page" }, form));
  user.focus();
}

/* ================= 主界面 ================= */
function renderShell() {
  const nav = h("nav", { class: "a-nav" }, PAGES.map(([id, label]) => h("a", { href: `#/${id}`, "data-page": id }, label)));
  root.replaceChildren(h("div", { class: "a-layout" },
    h("aside", { class: "a-side glass" },
      h("div", { class: "brand" }, LOGO(), h("span", {}, `${state.site_name}`), h("span", { class: "badge" }, "后台")),
      nav,
      h("div", { class: "a-side-foot" },
        h("span", { class: "muted small" }, state.admin.username),
        h("a", { href: "/", target: "_blank", class: "small" }, "查看网站"),
        h("button", { class: "btn", onclick: async () => { await api("/api/admin/logout", { method: "POST" }); boot(); } }, "退出"))),
    h("main", { id: "a-main", class: "a-main" })));
}

async function route() {
  const page = (location.hash.replace(/^#\//, "") || "overview").split("?")[0];
  const [id] = PAGES.find(([p]) => p === page) || PAGES[0];
  document.querySelectorAll(".a-nav a").forEach((a) => (a.dataset.page === id ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  cleanup?.(); cleanup = null;
  const main = document.getElementById("a-main");
  main.replaceChildren(h("div", { class: "empty" }, "加载中…"));
  try {
    if (!schema) schema = await api("/api/admin/settings");
    const out = await VIEWS[id](main);
    if (typeof out === "function") cleanup = out;
  } catch (e) {
    if (e.message === "请先登录后台") { boot(); return; }
    main.replaceChildren(h("div", { class: "panel glass" }, h("div", { class: "err" }, e.message)));
  }
}

const pageHead = (title, desc) => h("div", { class: "a-head" }, h("h1", {}, title), desc ? h("p", { class: "sub" }, desc) : null);

function statusRow(s, extra) {
  const cls = s.disabled ? "off" : s.ok ? "ok" : (s.checked_at ? "" : "off");
  return h("div", { class: "status-item" },
    h("span", { class: `dot ${cls}` }),
    h("b", {}, s.title || s.name),
    h("span", { class: "muted small" }, s.disabled ? "已关闭" : (s.message || "等待首次运行")),
    h("span", { class: "row nowrap small muted" }, s.last_success ? `上次成功 ${dt(s.last_success)}` : "", extra || null));
}

/* ================= 各页面 ================= */
/* ---------- 时区换算（日历日程用）---------- */
const TZS = [["Asia/Shanghai", "北京时间"], ["UTC", "UTC"], ["America/New_York", "美东时间"], ["Europe/London", "伦敦时间"], ["Europe/Berlin", "法兰克福时间"], ["Asia/Tokyo", "东京时间"]];
function tzParts(ts, tz) {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(new Date(ts * 1000)).map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, time: `${p.hour}:${p.minute}` };
}
function tzToTs(date, time, tz) {
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = (time || "00:00").split(":").map(Number);
  const guess = Date.UTC(y, m - 1, d, hh, mm) / 1000;
  const off = (t) => { const p = tzParts(t, tz); const [a, b, c] = p.date.split("-").map(Number); const [e, f] = p.time.split(":").map(Number); return Date.UTC(a, b - 1, c, e, f) / 1000 - t; };
  let ts = guess - off(guess);
  ts = guess - off(ts);
  return ts;
}

const VIEWS = {
  async overview(main) {
    const [o, sources] = await Promise.all([api("/api/admin/overview"), api("/api/admin/sources")]);
    const tile = (label, value, sub) => h("div", { class: "tile" }, h("div", { class: "name" }, label), h("div", { class: "px" }, value), sub ? h("div", { class: "meta" }, sub) : null);
    main.replaceChildren(
      pageHead("概览"),
      h("section", { class: "panel glass" }, h("div", { class: "grid-4" },
        tile("注册用户", o.users.total, `近 7 天新增 ${o.users.new7}`),
        tile("有效会员", o.users.members),
        tile("当前在线", o.online, "正在打开网页的浏览器"),
        tile("数据源", `${o.sources.ok} 正常`, `${o.sources.failed} 异常，${o.sources.off} 已关闭`),
        tile("24 小时访问", o.telemetry.views, "仅统计同意性能 Cookie 的访客"),
        tile("平均加载耗时", o.telemetry.avg_load ? `${fmt(o.telemetry.avg_load / 1000, 2)} 秒` : "—"),
        tile("24 小时前端错误", o.telemetry.errors),
        tile("24 小时接口失败", o.telemetry.api_fail),
        tile("24 小时运行错误", h("a", { href: "#/logs", class: o.logs.ERROR ? "down" : "" }, String(o.logs.ERROR)), `警告 ${o.logs.WARNING} 条`))),
      h("section", { class: "panel glass" }, h("h2", {}, "数据源状态"),
        h("div", { class: "status-list" }, sources.map((s) => statusRow(s)))));
  },

  async sources(main) {
    const render = async () => {
      const list = await api("/api/admin/sources");
      const byName = Object.fromEntries(list.map((s) => [s.name, s]));
      const cards = groupsOf("sources").map((g) => {
        const form = groupForm(g, { onSaved: () => setTimeout(render, 1500) });
        if (g.source) {
          const s = byName[g.source] || { name: g.source };
          const run = h("button", { class: "btn", type: "button", onclick: async () => {
            await api(`/api/admin/sources/${g.source}/run`, { method: "POST" }); toast("已触发，几秒后刷新状态"); setTimeout(render, 4000);
          } }, "立即刷新");
          form.querySelector(".a-group-head").append(statusRow({ ...s, title: "运行状态" }, run));
        }
        return form;
      });
      main.replaceChildren(pageHead("数据源", "每个数据源可单独开关、修改参数和 Key，保存后立即生效。运行状态和错误只在后台显示，前台不会出现。"), ...cards);
    };
    await render();
    const timer = setInterval(() => { if (!main.querySelector("form :focus")) render(); }, 30000);
    return () => clearInterval(timer);
  },

  async site(main) {
    main.replaceChildren(pageHead("站点"), ...groupsOf("site").map((g) => groupForm(g)));
  },

  async calendar(main) {
    const now = Math.floor(Date.now() / 1000);
    let tz = localStorage.getItem("zyll_admin_tz") || "Asia/Shanghai";
    const st = { start: tzParts(now - 2 * 86400, tz).date, end: tzParts(now + 100 * 86400, tz).date, currency: "", source: "", impact: "", pending: false, hidden: false, q: "" };
    const selected = new Set();
    const listBox = h("div"), statsBox = h("div", { class: "row" });
    const SRC = { official: ["官方", "good-txt"], ff: ["抓取", "muted"], admin: ["手动", ""] };
    const CCY = ["USD", "EUR", "GBP", "JPY", "CNY", "CAD", "AUD", "NZD", "CHF", "ALL"];
    const sel = (opts, val, on) => h("select", { style: { width: "auto" }, onchange: (e) => on(e.target.value) }, opts.map(([v, l]) => h("option", { value: v, selected: v === val }, l)));
    const fmtTs = (ts) => { const p = tzParts(ts, tz); return `${p.date} ${p.time}`; };
    const call = async (fn, msg) => { try { const r = await fn(); if (msg) toast(typeof msg === "function" ? msg(r) : msg); load(); } catch (e) { toast(e.message, 6000); } };

    function editDialog(ev) {
      const p = ev ? tzParts(ev.ts, tz) : { date: tzParts(now + 86400, tz).date, time: "20:30" };
      const f = { date: h("input", { type: "date", value: p.date, required: true }), time: h("input", { type: "time", value: p.time, required: true }),
        currency: h("select", {}, CCY.map((c) => h("option", { value: c, selected: c === (ev?.currency || "USD") }, c))),
        title: h("input", { value: ev?.title || "", placeholder: "例如 CPI m/m（与 Forex Factory 英文名称一致，公布值才能自动对上）", required: true }),
        impact: h("select", {}, [[3, "高（红色）"], [2, "中"], [1, "低"], [0, "假日 / 全天"]].map(([v, l]) => h("option", { value: v, selected: v === (ev?.impact ?? 3) }, l))),
        forecast: h("input", { value: ev?.forecast || "" }), previous: h("input", { value: ev?.previous || "" }),
        locked: h("input", { type: "checkbox", checked: ev ? !!ev.locked : true }) };
      const errEl = errBox();
      const dlg = h("dialog", { class: "glass" });
      dlg.append(h("form", { class: "dialog-form", onsubmit: async (e) => {
        e.preventDefault();
        const body = { ts: tzToTs(f.date.value, f.time.value, tz), currency: f.currency.value, title: f.title.value.trim(), impact: Number(f.impact.value),
          forecast: f.forecast.value.trim(), previous: f.previous.value.trim(), locked: f.locked.checked };
        try {
          if (ev) await api(`/api/admin/calendar/${encodeURIComponent(ev.id)}`, { method: "PATCH", body });
          else await api("/api/admin/calendar", { method: "POST", body });
          dlg.close(); toast("已保存，前台日历立即更新"); load();
        } catch (ex) { errEl.textContent = ex.message; }
      } },
        h("h2", {}, ev ? "编辑事件" : "添加事件"),
        h("div", { class: "row" }, field(`日期（${TZS.find((x) => x[0] === tz)?.[1] || tz}）`, f.date), field("时间", f.time)),
        h("div", { class: "row" }, field("货币", f.currency), field("重要性", f.impact)),
        field("事件名称", f.title),
        h("div", { class: "row" }, field("预测值", f.forecast), field("前值", f.previous)),
        h("label", { class: "chk" }, f.locked, "锁定时间（抓取到的时间不同时只提示，不自动修改）"),
        errEl,
        h("div", { class: "row" }, h("span", { class: "spacer" }), h("button", { class: "btn", type: "button", onclick: () => dlg.close() }, "取消"),
          h("button", { class: "btn primary", type: "submit" }, "保存"))));
      dlg.addEventListener("close", () => dlg.remove());
      document.body.append(dlg); dlg.showModal();
    }

    function importDialog() {
      const ta = h("textarea", { rows: 12, spellcheck: "false", placeholder: "日期,时间,货币,事件名称,重要性,预测值,前值\n2027-01-13,08:30,USD,CPI m/m,3,,\n2027-01-13,08:30,USD,CPI y/y,3,," });
      const tzSel = sel(TZS, "America/New_York", () => {});
      const skip = h("input", { type: "checkbox" });
      const out = h("div", { class: "small wrap" });
      const dlg = h("dialog", { class: "glass" });
      dlg.append(h("form", { class: "dialog-form", onsubmit: async (e) => {
        e.preventDefault();
        out.textContent = "导入中…"; out.className = "muted small wrap";
        try {
          const r = await api("/api/admin/calendar/import", { method: "POST", body: { csv: ta.value, tz: tzSel.value, skip_errors: skip.checked } });
          out.className = "good-txt small wrap";
          out.replaceChildren(h("div", {}, `新增 ${r.added} 条，更新 ${r.updated} 条（已锁定）`), ...r.errors.map((x) => h("div", { class: "bad-txt" }, x)));
          load();
        } catch (ex) { out.className = "bad-txt small wrap"; out.replaceChildren(h("div", {}, ex.message), ...((ex.data?.errors) || []).map((x) => h("div", {}, x))); }
      } },
        h("h2", {}, "批量导入日程"),
        h("p", { class: "sub" }, "每行一条：日期,时间,货币,事件名称,重要性(0~3)[,预测值,前值]。时间按下面选的时区（官方日程通常写当地时间，例如美国数据选美东时间，会自动处理夏令时）。同一天同货币同名称的事件已存在时，改为这里的时间并锁定。可以直接从 Excel 复制成 CSV。"),
        ta, h("div", { class: "row" }, field("时间所在时区", tzSel), h("label", { class: "chk" }, skip, "跳过格式不对的行")),
        out,
        h("div", { class: "row" }, h("span", { class: "spacer" }), h("button", { class: "btn", type: "button", onclick: () => dlg.close() }, "关闭"),
          h("button", { class: "btn primary", type: "submit" }, "导入"))));
      dlg.addEventListener("close", () => dlg.remove());
      document.body.append(dlg); dlg.showModal();
    }

    const bulk = (action, label) => {
      if (!selected.size) { toast("请先勾选事件"); return; }
      call(() => api("/api/admin/calendar/bulk", { method: "POST", body: { ids: [...selected], action } }), (r) => `${label}：${r.updated} 条`);
    };

    async function load() {
      const qs = new URLSearchParams({ start: tzToTs(st.start, "00:00", tz), end: tzToTs(st.end, "23:59", tz), currency: st.currency, source: st.source,
        impact: st.impact, pending: st.pending ? "1" : "", hidden: st.hidden ? "1" : "", q: st.q });
      const d = await api(`/api/admin/calendar?${qs}`);
      const s = d.stats || {};
      statsBox.replaceChildren(...[["官方日程", s.official], ["抓取", s.ff], ["手动", s.admin], ["待确认时间", s.pending], ["已隐藏", s.hidden]]
        .map(([k, v]) => h("span", { class: `tag${k === "待确认时间" && v ? " warn" : ""}` }, `${k} ${v || 0}`)),
        h("span", { class: "muted small" }, `内置官方日程版本 ${d.seed_version}${d.seeded === d.seed_version ? "（已写入）" : "（未写入）"}；统计范围：昨天以后`));
      selected.clear();
      const all = h("input", { type: "checkbox", onchange: (e) => listBox.querySelectorAll("tbody input[type=checkbox]").forEach((c) => { c.checked = e.target.checked; c.dispatchEvent(new Event("change")); }) });
      let lastDay = "";
      const rows = [];
      for (const ev of d.events) {
        const day = tzParts(ev.ts, tz).date;
        if (day !== lastDay) { rows.push(h("tr", { class: "day-row" }, h("td", { colspan: 9 }, day))); lastDay = day; }
        const [srcName, srcCls] = SRC[ev.source] || [ev.source, ""];
        rows.push(h("tr", { class: ev.hidden ? "muted" : "" },
          h("td", {}, h("input", { type: "checkbox", onchange: (e) => (e.target.checked ? selected.add(ev.id) : selected.delete(ev.id)) })),
          h("td", { class: "nowrap" }, tzParts(ev.ts, tz).time, ev.locked ? h("span", { title: "时间已锁定" }, " 🔒") : null),
          h("td", {}, ev.currency),
          h("td", { class: "wrap" }, h("b", {}, ev.title), ev.hidden ? h("span", { class: "tag" }, ev.hidden === 2 ? "抓取源已删除" : "已删除") : null),
          h("td", {}, ["假日", "低", "中", "高"][ev.impact] || ev.impact),
          h("td", { class: "small" }, `${ev.forecast || "—"} / ${ev.previous || "—"} / `, h("b", {}, ev.actual || "—")),
          h("td", { class: `small ${srcCls}` }, srcName),
          h("td", { class: "small" }, ev.pending_ts ? h("div", {}, h("span", { class: "bad-txt" }, `抓取到：${fmtTs(ev.pending_ts)}`), " ",
            h("button", { class: "btn small-btn", onclick: () => call(() => api(`/api/admin/calendar/${encodeURIComponent(ev.id)}`, { method: "PATCH", body: { apply_pending: true } }), "已采用新时间") }, "采用"),
            h("button", { class: "btn small-btn", onclick: () => call(() => api(`/api/admin/calendar/${encodeURIComponent(ev.id)}`, { method: "PATCH", body: { dismiss_pending: true } }), "已忽略") }, "忽略")) : ""),
          h("td", { class: "row nowrap" },
            h("button", { class: "btn small-btn", onclick: () => editDialog(ev) }, "编辑"),
            ev.hidden ? h("button", { class: "btn small-btn", onclick: () => call(() => api(`/api/admin/calendar/${encodeURIComponent(ev.id)}`, { method: "PATCH", body: { hidden: false } }), "已恢复") }, "恢复")
              : h("button", { class: "btn danger small-btn", onclick: () => { if (confirm(`删除“${ev.title}”？（前台不再显示，抓取也不会再加回来）`)) call(() => api(`/api/admin/calendar/${encodeURIComponent(ev.id)}`, { method: "DELETE" }), "已删除"); } }, "删除"))));
      }
      listBox.replaceChildren(h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, all), ...["时间", "货币", "事件", "重要性", "预测 / 前值 / 公布", "来源", "时间变化", ""].map((x) => h("th", {}, x)))),
        h("tbody", {}, rows.length ? rows : h("tr", {}, h("td", { colspan: 9, class: "empty" }, "所选范围内没有事件"))))),
      h("p", { class: "muted small" }, `共 ${d.events.length} 条${d.events.length >= 1000 ? "（只显示前 1000 条，请缩小范围）" : ""}`));
    }
    const q = h("input", { type: "search", placeholder: "搜索事件名称", style: { width: "180px" }, oninput: () => { clearTimeout(q._t); q._t = setTimeout(() => { st.q = q.value.trim(); load(); }, 300); } });
    const dateIn = (k) => h("input", { type: "date", value: st[k], style: { width: "auto" }, onchange: (e) => { st[k] = e.target.value; load(); } });
    const chk = (k, label) => h("label", { class: "chk" }, h("input", { type: "checkbox", onchange: (e) => { st[k] = e.target.checked; load(); } }), label);
    main.replaceChildren(
      pageHead("日历日程", "主要经济体的重要发布时间是固定的：内置官方日程（美联储、BLS、欧央行、英国央行等，已写入并锁定）+ Forex Factory 提前 3 个月抓取的日程。之后的抓取只更新预测值、前值和公布值；抓到的时间与库里不同时，锁定的事件只在这里提示“时间变化”，由你决定是否采用，前台“下一个重要数据”不会再跳来跳去。"),
      h("section", { class: "panel glass" },
        statsBox,
        h("div", { class: "row wrap", style: { marginTop: "10px", gap: "8px" } },
          sel(TZS, tz, (v) => { tz = v; localStorage.setItem("zyll_admin_tz", v); load(); }),
          dateIn("start"), h("span", {}, "~"), dateIn("end"),
          sel([["", "全部货币"], ...CCY.map((c) => [c, c])], "", (v) => { st.currency = v; load(); }),
          sel([["", "全部来源"], ["official", "官方"], ["ff", "抓取"], ["admin", "手动"]], "", (v) => { st.source = v; load(); }),
          sel([["", "全部重要性"], ["2", "中及以上"], ["3", "只看高"]], "", (v) => { st.impact = v; load(); }),
          q, chk("pending", "只看时间有变化的"), chk("hidden", "显示已删除")),
        h("div", { class: "row wrap", style: { marginTop: "10px", gap: "8px" } },
          h("button", { class: "btn primary", onclick: () => editDialog(null) }, "添加事件"),
          h("button", { class: "btn", onclick: importDialog }, "批量导入"),
          h("button", { class: "btn", onclick: (e) => { e.target.disabled = true; call(() => api("/api/admin/calendar/sync", { method: "POST" }), (r) => r.messages.join("；") || "已是最新").finally(() => { e.target.disabled = false; }); } }, "立即抓取未来 3 个月"),
          h("span", { class: "spacer" }), h("span", { class: "muted small" }, "勾选后："),
          h("button", { class: "btn small-btn", onclick: () => bulk("apply_pending", "已采用抓取到的时间") }, "采用新时间"),
          h("button", { class: "btn small-btn", onclick: () => bulk("dismiss_pending", "已忽略") }, "忽略时间变化"),
          h("button", { class: "btn small-btn", onclick: () => bulk("lock", "已锁定") }, "锁定"),
          h("button", { class: "btn small-btn", onclick: () => bulk("unlock", "已解锁") }, "解锁"),
          h("button", { class: "btn small-btn", onclick: () => bulk("unhide", "已恢复") }, "恢复"),
          h("button", { class: "btn danger small-btn", onclick: () => { if (confirm(`删除选中的 ${selected.size} 条？`)) bulk("hide", "已删除"); } }, "删除"))),
      h("section", { class: "panel glass" }, listBox),
    );
    await load();
  },

  async users(main) {
    const q = h("input", { type: "search", placeholder: "按邮箱搜索" });
    const tbody = h("tbody");
    const pager = h("div", { class: "row" });
    let offset = 0;
    const patch = async (id, body) => { try { await api(`/api/admin/users/${id}`, { method: "PATCH", body }); toast("已保存"); load(); } catch (e) { toast(e.message); } };
    const memberDialog = (u) => {
      const days = h("input", { type: "number", min: 0, value: 30 });
      const dlg = h("dialog", { class: "glass" });
      dlg.append(h("form", { class: "dialog-form", onsubmit: async (e) => {
        e.preventDefault();
        const d = parseInt(days.value, 10) || 0;
        await patch(u.id, { member_level: 1, member_expires: d ? Math.floor(Date.now() / 1000) + d * 86400 : null });
        dlg.close();
      } },
        h("h2", {}, `开通会员：${u.email}`),
        field("有效天数（0 表示永久）", days),
        h("div", { class: "row" }, h("span", { class: "spacer" }),
          h("button", { class: "btn", type: "button", onclick: () => dlg.close() }, "取消"),
          h("button", { class: "btn primary", type: "submit" }, "开通"))));
      dlg.addEventListener("close", () => dlg.remove());
      document.body.append(dlg); dlg.showModal();
    };
    async function load() {
      const d = await api(`/api/admin/users?q=${encodeURIComponent(q.value.trim())}&offset=${offset}`);
      tbody.replaceChildren(...(d.users.length ? d.users.map((u) => h("tr", {},
        h("td", {}, h("b", {}, u.email)),
        h("td", {}, u.email_verified ? "已验证" : h("span", { class: "muted" }, "未验证")),
        h("td", {}, u.is_member ? `会员${u.member_expires ? `（至 ${dt(u.member_expires).slice(0, 10)}）` : "（永久）"}` : "—"),
        h("td", {}, u.is_active ? "正常" : h("span", { class: "down" }, "已停用")),
        h("td", { class: "muted" }, dt(u.created_at)),
        h("td", { class: "muted" }, dt(u.last_login_at), u.last_ip ? h("div", { class: "small" }, `${u.last_ip}${u.last_country ? ` · ${u.last_country}` : ""}`) : null),
        h("td", { class: "small" }, u.last_risk ? h("span", { class: "down" }, u.last_risk) : h("span", { class: "muted" }, "—")),
        h("td", { class: "row nowrap" },
          h("a", { class: "btn", href: `/api/admin/users/${u.id}/export` }, "导出数据"),
          h("a", { class: "btn", href: `#/privacy?q=${encodeURIComponent(u.email)}` }, "登录记录"),
          u.is_member ? h("button", { class: "btn", onclick: () => patch(u.id, { member_level: 0, member_expires: null }) }, "取消会员")
            : h("button", { class: "btn", onclick: () => memberDialog(u) }, "开通会员"),
          !u.email_verified ? h("button", { class: "btn", onclick: () => patch(u.id, { email_verified: true }) }, "标记已验证") : null,
          h("button", { class: "btn", onclick: () => patch(u.id, { is_active: !u.is_active }) }, u.is_active ? "停用" : "启用"),
          h("button", { class: "btn", onclick: () => { const p = prompt("新密码（至少 8 位）"); if (p) patch(u.id, { password: p }); } }, "重置密码"),
          h("button", { class: "btn danger", onclick: async () => { if (confirm(`删除用户 ${u.email} 及其全部数据（持仓分析、交易记录、登录记录）？此操作不可恢复。`)) { await api(`/api/admin/users/${u.id}`, { method: "DELETE" }); load(); } } }, "删除")),
      )) : [h("tr", {}, h("td", { colspan: 8, class: "empty" }, "没有用户"))]));
      pager.replaceChildren(...[h("span", { class: "muted small" }, `共 ${d.total} 个用户`), h("span", { class: "spacer" }),
        offset > 0 ? h("button", { class: "btn", onclick: () => { offset -= 50; load(); } }, "上一页") : null,
        offset + 50 < d.total ? h("button", { class: "btn", onclick: () => { offset += 50; load(); } }, "下一页") : null].filter(Boolean));
    }
    let timer;
    q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { offset = 0; load(); }, 300); });
    main.replaceChildren(
      pageHead("用户与注册"),
      h("section", { class: "panel glass" }, h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, "前台用户"), h("span", { class: "spacer" }), q),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, ["邮箱", "邮箱验证", "会员", "状态", "注册时间", "最近登录", "最近风险", "操作"].map((x) => h("th", {}, x)))), tbody)), pager),
      ...groupsOf("users").map((g) => groupForm(g)));
    await load();
  },

  async membership(main) {
    const d = await api("/api/admin/member-log");
    const SRC = (x) => (x.startsWith("admin-revoke") ? `后台取消（${x.split(":")[1] || ""}）` : x.startsWith("admin") ? `后台开通（${x.split(":")[1] || ""}）` : x === "app" ? "App 卡密" : "网页卡密");
    const exp = (v) => (v == null ? "永久" : v ? dt(v).slice(0, 16) : "—");
    main.replaceChildren(pageHead("会员", "会员通过卡密激活或续期（见“卡密”页），也可在“用户与注册”页手动开通。会员模式关闭时前台不显示任何会员信息。"),
      ...groupsOf("membership").map((g) => groupForm(g)),
      h("section", { class: "panel glass" }, h("h2", {}, "最近的开通 / 续期记录"),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, ["时间", "用户", "方式", "卡密", "天数", "原到期", "新到期"].map((x) => h("th", {}, x)))),
          h("tbody", {}, d.log.length ? d.log.map((r) => h("tr", {}, h("td", { class: "muted nowrap" }, dt(r.ts)), h("td", {}, r.email || `#${r.user_id}`),
            h("td", {}, SRC(r.source)), h("td", {}, h("code", {}, r.code || "—")), h("td", { class: "num" }, r.days === 0 ? "永久" : r.days ?? "—"),
            h("td", { class: "muted" }, r.old_expires ? dt(r.old_expires).slice(0, 16) : "—"), h("td", {}, exp(r.new_expires))))
            : h("tr", {}, h("td", { colspan: 7, class: "empty" }, "暂无记录")))))));
  },

  async cards(main) {
    const st = { status: "", batch: "", q: "", offset: 0 };
    const listBox = h("div");
    const statsBox = h("div", { class: "row" });
    const batchSel = h("select", { style: { width: "auto" } });
    const statusSel = h("select", { style: { width: "auto" } }, [["", "全部状态"], ["unused", "未使用"], ["used", "已使用"], ["disabled", "已停用"]].map(([v, l]) => h("option", { value: v }, l)));
    const q = h("input", { type: "search", placeholder: "搜索卡密、使用者邮箱或备注", style: { width: "240px" } });
    const STATUS = { unused: "未使用", used: "已使用", disabled: "已停用" };
    const selected = new Set();
    const qs = () => new URLSearchParams({ status: st.status, batch: st.batch, q: st.q }).toString();

    async function load() {
      const d = await api(`/api/admin/cards?${qs()}&offset=${st.offset}`);
      const s = d.stats;
      statsBox.replaceChildren(...[["未使用", s.unused || 0], ["已使用", s.used || 0], ["已停用", s.disabled || 0]].map(([k, v]) => h("span", { class: "tag" }, `${k} ${v}`)));
      const cur = batchSel.value;
      batchSel.replaceChildren(h("option", { value: "" }, "全部批次"), ...d.batches.map((b) => h("option", { value: b.batch, selected: b.batch === cur },
        `${b.batch || "（无批次）"} · ${b.days === 0 ? "永久" : `${b.days} 天`} · 未用 ${b.unused}/${b.total}`)));
      selected.clear();
      const all = h("input", { type: "checkbox", onchange: (e) => { listBox.querySelectorAll("tbody input[type=checkbox]").forEach((c) => { c.checked = e.target.checked; c.dispatchEvent(new Event("change")); }); } });
      listBox.replaceChildren(
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, h("th", {}, all), ...["卡密", "时长", "批次", "状态", "兑换截止", "备注", "生成时间", "使用者 / 时间"].map((x) => h("th", {}, x)))),
          h("tbody", {}, d.cards.length ? d.cards.map((c) => h("tr", {},
            h("td", {}, c.status !== "used" ? h("input", { type: "checkbox", onchange: (e) => (e.target.checked ? selected.add(c.id) : selected.delete(c.id)) }) : null),
            h("td", {}, h("code", { class: "card-code" }, c.code)),
            h("td", {}, c.days === 0 ? "永久" : `${c.days} 天`), h("td", { class: "small" }, c.batch),
            h("td", { class: c.status === "used" ? "muted" : c.status === "disabled" ? "bad-txt" : "good-txt" }, STATUS[c.status] || c.status),
            h("td", { class: "small muted" }, c.valid_until ? dt(c.valid_until).slice(0, 10) : "不限"),
            h("td", { class: "small wrap" }, c.note), h("td", { class: "small muted" }, dt(c.created_at)),
            h("td", { class: "small" }, c.used_email ? `${c.used_email} · ${dt(c.used_at)}` : "—")))
            : h("tr", {}, h("td", { colspan: 9, class: "empty" }, "没有卡密"))))),
        h("div", { class: "row" }, h("span", { class: "muted small" }, `共 ${d.total} 张`), h("span", { class: "spacer" }),
          ...[st.offset > 0 ? h("button", { class: "btn", onclick: () => { st.offset -= 100; load(); } }, "上一页") : null,
            st.offset + 100 < d.total ? h("button", { class: "btn", onclick: () => { st.offset += 100; load(); } }, "下一页") : null].filter(Boolean)));
    }
    const bulk = async (url, body, msg) => {
      const target = selected.size ? { ids: [...selected] } : st.batch ? { batch: st.batch } : null;
      if (!target) { toast("请先勾选卡密，或在上方选择一个批次"); return; }
      if (!confirm(`${msg}${selected.size ? `选中的 ${selected.size} 张` : `批次“${st.batch}”中符合条件的`}卡密？已使用的卡密不会被改动。`)) return;
      try { const r = await api(url, { method: "POST", body: { ...target, ...body } }); toast(`已处理 ${r.changed ?? r.deleted} 张`); load(); } catch (e) { toast(e.message); }
    };

    // 生成
    const g = { count: h("input", { type: "number", min: 1, max: 5000, value: 10 }), days: h("select", {}, [[30, "30 天（月卡）"], [90, "90 天（季卡）"], [365, "365 天（年卡）"], [7, "7 天（体验）"], [0, "永久"], ["x", "自定义天数"]].map(([v, l]) => h("option", { value: v }, l))),
      custom: h("input", { type: "number", min: 1, max: 36500, placeholder: "天数", style: { display: "none" } }),
      batch: h("input", { type: "text", placeholder: "例如 2026-11-月卡" }), prefix: h("input", { type: "text", value: "ZYLL", maxlength: 8 }),
      until: h("input", { type: "date" }), note: h("input", { type: "text", placeholder: "可选" }) };
    g.days.addEventListener("change", () => { g.custom.style.display = g.days.value === "x" ? "" : "none"; });
    const genOut = h("div");
    const genErr = errBox();
    const genForm = h("form", { class: "panel glass a-group", onsubmit: async (e) => {
      e.preventDefault(); genErr.textContent = "";
      const days = g.days.value === "x" ? +g.custom.value : +g.days.value;
      try {
        const r = await api("/api/admin/cards/generate", { method: "POST", body: { count: +g.count.value, days, batch: g.batch.value.trim(), prefix: g.prefix.value.trim(), valid_until: g.until.value, note: g.note.value } });
        const text = r.codes.join("\n");
        const ta = h("textarea", { rows: Math.min(12, r.codes.length + 1), readonly: true, class: "card-out" }, text);
        const blob = URL.createObjectURL(new Blob([text + "\n"], { type: "text/plain" }));
        genOut.replaceChildren(h("p", { class: "sub" }, `已生成 ${r.codes.length} 张（${days === 0 ? "永久" : `${days} 天`}）：`), ta,
          h("div", { class: "row" }, h("button", { class: "btn", type: "button", onclick: async () => { try { await navigator.clipboard.writeText(text); toast("已复制"); } catch { ta.select(); document.execCommand("copy"); toast("已复制"); } } }, "复制全部"),
            h("a", { class: "btn", href: blob, download: `cards-${Date.now()}.txt` }, "下载 TXT")));
        load();
      } catch (ex) { genErr.textContent = ex.message; }
    } },
      h("div", { class: "a-group-head" }, h("h2", {}, "随机生成卡密"), h("p", { class: "sub" }, "格式如 ZYLL-ABCD-EFGH-JKMN，不含容易混淆的 0/O/1/I/L；每次最多 5000 张。")),
      h("div", { class: "a-fields" }, field("数量", g.count), field("时长", h("div", { class: "row" }, g.days, g.custom)), field("批次名称", g.batch, "留空则按时间自动命名"),
        field("前缀", g.prefix, "可留空"), field("兑换截止日期", g.until, "过了这一天卡密无法再兑换；留空表示不限"), field("备注", g.note)),
      genErr, h("div", { class: "row" }, h("span", { class: "spacer" }), h("button", { class: "btn primary", type: "submit" }, "生成")), genOut);

    // 导入
    const im = { text: h("textarea", { rows: 6, placeholder: "每行一个卡密；也可以写成“卡密,天数”。\n例如：\nABC123DEF456\nXYZ789XYZ789,365" }),
      days: h("input", { type: "number", min: 0, max: 36500, value: 30 }), batch: h("input", { type: "text", placeholder: "例如 渠道A-导入" }), until: h("input", { type: "date" }), note: h("input", { type: "text" }) };
    const imOut = h("div");
    const imErr = errBox();
    const imForm = h("form", { class: "panel glass a-group", onsubmit: async (e) => {
      e.preventDefault(); imErr.textContent = "";
      try {
        const r = await api("/api/admin/cards/import", { method: "POST", body: { text: im.text.value, days: +im.days.value, batch: im.batch.value.trim(), valid_until: im.until.value, note: im.note.value } });
        imOut.replaceChildren(h("p", { class: "sub" }, `成功导入 ${r.imported} 张；已存在 ${r.duplicate_count} 张；格式错误 ${r.error_count} 行。`),
          ...(r.errors.length ? [h("pre", { class: "code" }, r.errors.join("\n"))] : []),
          ...(r.duplicates.length ? [h("p", { class: "muted small" }, `已存在：${r.duplicates.join("、")}${r.duplicate_count > r.duplicates.length ? " …" : ""}`)] : []));
        if (r.imported) im.text.value = "";
        load();
      } catch (ex) { imErr.textContent = ex.message; }
    } },
      h("div", { class: "a-group-head" }, h("h2", {}, "导入指定卡密"), h("p", { class: "sub" }, "导入别处生成或第三方发卡平台的卡密。大小写、空格和横线不影响兑换。")),
      h("div", { class: "a-fields" }, h("label", { class: "a-field wide" }, h("span", { class: "a-label" }, "卡密列表"), im.text),
        field("默认天数（0 = 永久）", im.days), field("批次名称", im.batch), field("兑换截止日期", im.until), field("备注", im.note)),
      imErr, h("div", { class: "row" }, h("span", { class: "spacer" }), h("button", { class: "btn primary", type: "submit" }, "导入")), imOut);

    let timer;
    q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { st.q = q.value.trim(); st.offset = 0; load(); }, 300); });
    statusSel.addEventListener("change", () => { st.status = statusSel.value; st.offset = 0; load(); });
    batchSel.addEventListener("change", () => { st.batch = batchSel.value; st.offset = 0; load(); });
    main.replaceChildren(
      pageHead("卡密", "用户在前台账户菜单里输入卡密激活或续期会员。需要先在“会员”页开启会员模式。"),
      h("div", { class: "grid-2" }, genForm, imForm),
      h("section", { class: "panel glass" },
        h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, "卡密列表"), statsBox, h("span", { class: "spacer" }), batchSel, statusSel, q),
        h("div", { class: "row", style: { margin: "10px 0" } },
          h("button", { class: "btn", onclick: () => bulk("/api/admin/cards/status", { disabled: true }, "停用") }, "停用"),
          h("button", { class: "btn", onclick: () => bulk("/api/admin/cards/status", { disabled: false }, "恢复") }, "恢复"),
          h("button", { class: "btn danger", onclick: () => bulk("/api/admin/cards/delete", {}, "删除") }, "删除"),
          h("span", { class: "spacer" }),
          h("button", { class: "btn", onclick: () => { location.href = `/api/admin/cards/export.csv?${qs()}`; } }, "导出当前筛选（CSV）")),
        listBox));
    await load();
  },

  async app(main) {
    const d = await api("/api/admin/app/devices");
    const forms = groupsOf("app").map((g) => groupForm(g));
    const keyForm = forms[0];
    if (keyForm) {
      keyForm.append(h("div", { class: "row" }, h("span", { class: "muted small" }, "生成后点“保存”才生效；保存后需要把同样的 Key 写进 APK。"), h("span", { class: "spacer" }),
        h("button", { class: "btn", type: "button", onclick: () => {
          const bytes = crypto.getRandomValues(new Uint8Array(24));
          const key = "zak_" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
          const inp = keyForm.querySelector("input.masked");
          inp.removeAttribute("readonly"); inp.value = key; inp.classList.remove("masked");
          toast("已生成，请复制保存后点“保存”");
        } }, "生成 App Key")));
    }
    main.replaceChildren(
      pageHead("安卓 App", "接口地址：/api/app/v1；文档：/api/app/v1/docs（也在项目的 docs/APP_API.md）。"),
      ...forms,
      h("section", { class: "panel glass" }, h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, "已登录的 App 设备"), h("span", { class: "spacer" }),
        h("a", { class: "btn", href: "/api/app/v1/docs", target: "_blank" }, "查看接口文档")),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, ["用户", "设备", "系统", "App 版本", "登录时间", "最近使用", "IP", ""].map((x) => h("th", {}, x)))),
          h("tbody", {}, d.devices.length ? d.devices.map((r) => h("tr", {}, h("td", {}, r.email || "—"), h("td", {}, r.device_name || "—"), h("td", {}, r.platform),
            h("td", {}, r.app_version), h("td", { class: "muted small" }, dt(r.created_at)), h("td", { class: "muted small" }, dt(r.last_used_at)), h("td", { class: "small" }, r.last_ip),
            h("td", {}, h("button", { class: "btn danger small-btn", onclick: async () => { if (confirm("让这台设备下线？")) { await api(`/api/admin/app/devices/${r.id}`, { method: "DELETE" }); VIEWS.app(main); } } }, "下线"))))
            : h("tr", {}, h("td", { colspan: 8, class: "empty" }, "还没有 App 设备登录")))))));
  },

  async ai(main) {
    const [d, pv] = await Promise.all([api("/api/admin/ai/jobs"), api("/api/admin/ai/providers")]);
    const P = pv.providers;
    const forms = groupsOf("ai").map((g) => groupForm(g, { onSaved: () => VIEWS.ai(main) }));
    const RULES = { thinking_forced: "该模型只能开启思考，改为不关闭思考、不用 JSON 模式", no_json: "不使用 JSON 模式", no_max_tokens: "不传输出上限",
      no_temperature: "不传温度参数", no_stream: "改为非流式", no_stream_options: "不传 stream_options", no_thinking_param: "不传关闭思考参数", minimal: "只保留基本参数" };
    const describe = (a) => Object.entries(a || {}).map(([k, v]) => (k === "max_tokens" ? `输出上限改为 ${v}` : k === "image_raw" ? (v ? "图片改用纯 base64" : "图片改用 data URL") : v === true ? RULES[k] : null)).filter(Boolean);
    const testBtn = (kind, form) => {
      const out = h("div", { class: "muted small wrap" });
      form.append(h("div", { class: "row" }, out, h("span", { class: "spacer" }), h("button", { class: "btn", type: "button", onclick: async (e) => {
        e.target.disabled = true; out.textContent = "测试中…"; out.className = "muted small wrap";
        try {
          const r = await api("/api/admin/ai/test", { method: "POST", body: { kind } });
          const adj = describe(r.adjusted);
          out.replaceChildren(...[h("div", {}, `连接成功（${r.ms} 毫秒，${r.model}）：${r.reply}`),
            adj.length ? h("div", { class: "muted" }, `已根据接口返回自动调整：${adj.join("；")}（已记住，正式识别时直接使用）`) : null].filter(Boolean));
          out.className = "good-txt small wrap";
        } catch (ex) { out.textContent = ex.message; out.className = "bad-txt small wrap"; } finally { e.target.disabled = false; }
      } }, "测试连接（先保存）")));
    };
    const byId = Object.fromEntries(groupsOf("ai").map((g, i) => [g.id, forms[i]]));
    // 服务商联动：接口地址提示、推荐模型、获取模型列表
    const enhance = (kind, form) => {
      const el = form.fieldEls || {};
      const prov = el[`ai.${kind}_provider`], base = el[`ai.${kind}_base_url`], model = el[`ai.${kind}_model`];
      if (!prov || !base || !model) return;
      const dl = h("datalist", { id: `ai-models-${kind}` });
      model.setAttribute("list", dl.id);
      model.after(dl);
      const note = h("div", { class: "a-help" });
      prov.after(note);
      const fetched = h("span", { class: "muted small" });
      const fill = (list) => dl.replaceChildren(...[...new Set(list)].map((m) => h("option", { value: m })));
      const update = (changed) => {
        const p = P[prov.value] || P.custom;
        const rec = kind === "vision" ? p.vision : p.text;
        base.placeholder = p.base ? `留空 = ${p.base}` : "例如 https://api.example.com/v1";
        note.textContent = p.note || "";
        fill(rec);
        if (changed && rec.length) {
          const all = Object.values(P).flatMap((x) => [...x.text, ...x.vision]);
          if (!model.value || (all.includes(model.value) && !rec.includes(model.value))) model.value = rec[0];
          if (base.value && Object.values(P).some((x) => x.base && x.base === base.value.replace(/\/$/, ""))) base.value = "";
        }
        fetched.textContent = rec.length ? `推荐：${rec.join("、")}` : "";
      };
      prov.addEventListener("change", () => update(true));
      update(false);
      model.parentElement.append(h("div", { class: "row small" }, fetched, h("span", { class: "spacer" }), h("button", { class: "btn small-btn", type: "button", onclick: async (e) => {
        e.target.disabled = true;
        try {
          const r = await api(`/api/admin/ai/models?kind=${kind}`);
          if (r.models.length) { fill([...r.preset, ...r.models]); fetched.textContent = `账号可用 ${r.models.length} 个模型，已加入下拉选项`; }
          else fetched.textContent = `获取失败（${r.error || "服务商不支持"}），可直接填写模型名`;
        } catch (ex) { fetched.textContent = ex.message; } finally { e.target.disabled = false; }
      } }, "获取模型列表（先保存 Key）")));
    };
    if (byId.ai_text) { enhance("text", byId.ai_text); testBtn("text", byId.ai_text); }
    if (byId.ai_vision) { enhance("vision", byId.ai_vision); testBtn("vision", byId.ai_vision); }
    const modeSel = byId.ai_mode?.fieldEls?.["ai.mode"];
    if (modeSel && byId.ai_vision) {
      const sync = () => byId.ai_vision.classList.toggle("a-dim", modeSel.value !== "split");
      modeSel.addEventListener("change", sync);
      sync();
    }
    const kb = (n) => (n >= 1048576 ? `${fmt(n / 1048576, 1)} MB` : `${Math.round(n / 1024)} KB`);
    const tile = (label, value, sub) => h("div", { class: "tile" }, h("div", { class: "name" }, label), h("div", { class: "px" }, value), sub ? h("div", { class: "meta" }, sub) : null);
    main.replaceChildren(
      pageHead("AI 导入", "用户在“持仓分析”里上传券商结单，AI 识别后由用户逐条核对再导入。文件不保存；下表只记录调用情况。费用参考：一页文字结单精简后约 1~2 千个 token，DeepSeek / 千问 Flash 不到 1 分钱。"),
      h("section", { class: "panel glass" }, h("div", { class: "grid-4" },
        tile("24 小时识别", d.day.n, `失败 ${d.day.failed || 0} 次`),
        tile("24 小时用量", `${fmt((d.day.ti + d.day.tout) / 1000, 1)}k`, `输入 ${d.day.ti} / 输出 ${d.day.tout} token`),
        tile("30 天识别", d.month.n, `用量 ${fmt((d.month.ti + d.month.tout) / 1000, 1)}k token`),
        tile("已导入", `${d.imports.n} 批`, `共 ${d.imports.trades} 笔交易`))),
      ...forms,
      h("section", { class: "panel glass" }, h("h2", {}, "最近的识别记录"),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, ["时间", "用户", "文件", "页数", "方式", "结果", "识别条数", "用量（入/出）", "耗时", "错误"].map((x) => h("th", {}, x)))),
          h("tbody", {}, d.jobs.length ? d.jobs.map((r) => h("tr", {},
            h("td", { class: "muted small" }, dt(r.created_at)), h("td", {}, r.email || "（已删除）"), h("td", {}, `${r.file_type} ${kb(r.size)}`),
            h("td", { class: "num" }, r.pages || "—"), h("td", {}, r.mode === "vision" ? "图片" : r.mode ? "文字" : "—"),
            h("td", { class: r.status === "ok" ? "good-txt" : r.status === "failed" ? "bad-txt" : "" }, { ok: "成功", failed: "失败", running: "进行中" }[r.status] || r.status),
            h("td", { class: "num" }, r.rows), h("td", { class: "num small" }, `${r.tokens_in} / ${r.tokens_out}`), h("td", { class: "num small" }, r.ms ? `${fmt(r.ms / 1000, 1)}s` : "—"),
            h("td", { class: "small wrap" }, r.error || "")))
            : h("tr", {}, h("td", { colspan: 10, class: "empty" }, "还没有识别记录")))))));
  },

  async inflation(main) {
    const d = await api("/api/admin/inflation");
    const SRC = d.sources;
    const SRC_CLS = { admin: "good-txt", fred: "good-txt", calendar: "", worldbank: "muted", extrapolated: "bad-txt", none: "bad-txt" };
    const pct = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${fmt(v, 2)}%`);
    const addForm = () => {
      const ccy = h("select", {}, d.regions.map((r) => h("option", { value: r.ccy }, `${r.ccy} ${r.region}`)));
      const month = h("input", { type: "month", required: true });
      const yoy = h("input", { type: "number", step: "any", placeholder: "例如 2.4" });
      const idx = h("input", { type: "number", step: "any", placeholder: "可不填" });
      const err = errBox();
      return h("form", { class: "panel glass a-group", onsubmit: async (e) => {
        e.preventDefault(); err.textContent = "";
        try { await api("/api/admin/inflation", { method: "POST", body: { ccy: ccy.value, month: month.value, yoy: yoy.value, idx: idx.value } }); toast("已保存，立即生效"); VIEWS.inflation(main); }
        catch (ex) { err.textContent = ex.message; }
      } },
        h("div", { class: "a-group-head" }, h("h2", {}, "手动补录"), h("p", { class: "sub" }, "某个月的数据缺失或不准确时在这里补录（优先级最高）。填同比（%）即可；如果填了物价指数，连续两个月都有指数时按指数的实际比值计算。")),
        h("div", { class: "a-fields" }, field("货币 / 地区", ccy), field("月份", month), field("同比（%）", yoy), field("物价指数（可选）", idx)),
        err, h("div", { class: "row" }, h("span", { class: "spacer" }), h("button", { class: "btn primary", type: "submit" }, "保存")));
    };
    const regionCard = (r) => h("section", { class: "panel glass" },
      h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, `${r.region} · ${r.ccy}`), h("span", { class: "spacer" }),
        h("span", { class: "tag" }, `近 12 个月 ${pct(r.yoy_12m)}`), h("span", { class: `tag${r.approx ? " warn" : ""}` }, `已公布数据截至 ${r.last_known || "—"}`)),
      h("p", { class: "sub" }, [r.fred ? `官方指数 FRED ${r.fred}` : null, r.calendar_titles.length ? `日历公布值：${r.calendar_titles.join(" / ")}` : "日历里没有该地区的 CPI", `世界银行 ${r.wb}`].filter(Boolean).join("；"),
        "。近 24 个月来源：", Object.entries(r.counts).map(([k, v]) => `${SRC[k] || k} ${v}`).join("、")),
      h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, ["月份", "指数（起点 = 100）", "环比", "同比", "来源"].map((x, i) => h("th", { class: i && i < 4 ? "num" : "" }, x)))),
        h("tbody", {}, r.rows.slice(0, 13).map((x) => h("tr", {},
          h("td", {}, x.month), h("td", { class: "num" }, fmt(x.idx, 3)), h("td", { class: "num" }, pct(x.mom)), h("td", { class: "num" }, pct(x.yoy)),
          h("td", { class: SRC_CLS[x.src] || "" }, SRC[x.src] || x.src)))))));
    main.replaceChildren(...[
      pageHead("通胀数据", "用于“持仓分析 → 扣除通胀”：每笔成本和卖出所得按付款货币所在地区的物价折算到今天的购买力。优先级：管理员补录 > 官方物价指数（美国 FRED）> 经济日历抓到的 CPI 公布值 > 世界银行年度通胀率 > 按最近 12 个月的速度推算。数据每天更新（“数据源 → 通胀数据”）。"),
      addForm(),
      d.admin.length ? h("section", { class: "panel glass" }, h("h2", {}, "已补录的数据"), h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, ["货币", "月份", "同比", "指数", "补录时间", ""].map((x) => h("th", {}, x)))),
        h("tbody", {}, d.admin.map((x) => h("tr", {}, h("td", {}, x.region), h("td", {}, x.month), h("td", {}, x.yoy != null ? `${fmt(x.yoy, 2)}%` : "—"),
          h("td", {}, x.idx ?? "—"), h("td", { class: "muted small" }, dt(x.updated_at)),
          h("td", {}, h("button", { class: "btn danger small-btn", onclick: async () => {
            if (!confirm(`删除 ${x.region} ${x.month} 的补录数据？`)) return;
            await api(`/api/admin/inflation/${x.region}/${x.month}`, { method: "DELETE" }); VIEWS.inflation(main);
          } }, "删除")))))))) : null,
      ...d.regions.map(regionCard),
    ].filter(Boolean));
  },

  async portfolio(main) {
    main.replaceChildren(pageHead("持仓分析与连汇盈亏", "股价来自“数据源”页的实时行情（未开启时用 Cboe 延迟价），汇率来自中国外汇交易中心。通胀数据见下方“通胀数据”。"),
      ...groupsOf("portfolio").map((g) => groupForm(g)));
  },

  async ads(main) {
    main.replaceChildren(pageHead("广告", "支持 Google AdSense、Adsterra、PropellerAds、Media.net 和自定义代码。"), ...groupsOf("ads").map((g) => groupForm(g)));
  },

  async security(main) {
    const [list, srcs] = await Promise.all([api("/api/admin/admins"), api("/api/admin/sources")]);
    const tsStatus = h("div", {});
    const showTs = (s) => tsStatus.replaceChildren(s ? statusRow({ ...s, title: "最近一次校验" }) : h("p", { class: "muted small" }, "还没有校验记录"));
    showTs(srcs.find((x) => x.name === "turnstile"));
    const tsTest = h("section", { class: "panel glass" }, h("h2", {}, "人机验证诊断"),
      h("p", { class: "sub" }, "检查服务器能否连上 Cloudflare、Secret Key 是否有效。请先保存上面的 Key 再测试。"),
      tsStatus,
      h("div", { class: "row", style: { marginTop: "10px" } }, h("button", { class: "btn", onclick: async () => {
        const r = await api("/api/admin/turnstile/test", { method: "POST" });
        toast(r.message, 5000);
        showTs({ name: "turnstile", ok: r.ok, message: r.message, last_success: r.ok ? Date.now() / 1000 : null, checked_at: Date.now() / 1000 });
      } }, "测试连接")));
    const adminRows = list.admins.map((a) => h("tr", {},
      h("td", {}, h("b", {}, a.username), a.id === list.me ? h("span", { class: "tag" }, "当前") : null),
      h("td", { class: "muted" }, dt(a.created_at)), h("td", { class: "muted" }, dt(a.last_login_at)),
      h("td", {}, a.id !== list.me ? h("button", { class: "btn danger", onclick: async () => {
        if (confirm(`删除管理员 ${a.username}？`)) { await api(`/api/admin/admins/${a.id}`, { method: "DELETE" }); VIEWS.security(main); }
      } }, "删除") : null)));

    // 新增管理员（需要对方扫码绑定）
    const nu = h("input", { type: "text", placeholder: "用户名" });
    const np = h("input", { type: "password", placeholder: "密码（至少 8 位）", autocomplete: "new-password" });
    const addErr = errBox();
    const addBox = h("div", {});
    const addBtn = h("button", { class: "btn primary", onclick: async () => {
      addErr.textContent = "";
      try {
        const setup = await api("/api/admin/admins/start", { method: "POST", body: { username: nu.value.trim(), password: np.value } });
        const code = h("input", { type: "text", inputmode: "numeric", maxlength: 6, placeholder: "6 位动态码" });
        addBox.replaceChildren(h("p", { class: "muted small" }, "请新管理员用自己的手机扫描二维码，然后输入其验证器上的动态码完成添加。"), qrBlock(setup),
          h("div", { class: "row" }, code, h("button", { class: "btn primary", onclick: async () => {
            try { await api("/api/admin/admins/finish", { method: "POST", body: { token: setup.token, code: code.value } }); toast("已添加管理员"); VIEWS.security(main); } catch (e) { addErr.textContent = e.message; }
          } }, "确认添加")));
      } catch (e) { addErr.textContent = e.message; }
    } }, "下一步：绑定验证器");

    // 修改自己的密码
    const op = h("input", { type: "password", autocomplete: "current-password" });
    const npw = h("input", { type: "password", autocomplete: "new-password" });
    const oc = h("input", { type: "text", inputmode: "numeric", maxlength: 6 });
    const pwErr = errBox();

    // 重新绑定谷歌验证器
    const rebindBox = h("div", {});
    const rebindErr = errBox();
    const rebindBtn = h("button", { class: "btn", onclick: async () => {
      const setup = await api("/api/admin/me/2fa/start", { method: "POST" });
      const code = h("input", { type: "text", inputmode: "numeric", maxlength: 6, placeholder: "新验证器上的 6 位动态码" });
      rebindBox.replaceChildren(qrBlock(setup), h("div", { class: "row" }, code, h("button", { class: "btn primary", onclick: async () => {
        try { await api("/api/admin/me/2fa/finish", { method: "POST", body: { token: setup.token, code: code.value } }); toast("已更换验证器，旧的动态码不再有效"); VIEWS.security(main); } catch (e) { rebindErr.textContent = e.message; }
      } }, "确认更换")));
    } }, "更换手机 / 重新绑定");

    main.replaceChildren(
      pageHead("安全与管理员"),
      ...groupsOf("security").map((g) => groupForm(g)),
      tsTest,
      h("section", { class: "panel glass" }, h("h2", {}, "管理员"),
        h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["用户名", "创建时间", "最近登录", ""].map((x) => h("th", {}, x)))), h("tbody", {}, adminRows))),
        h("h2", { style: { marginTop: "18px" } }, "添加管理员"),
        h("div", { class: "row" }, nu, np, addBtn), addErr, addBox),
      h("div", { class: "grid-2" },
        h("section", { class: "panel glass" }, h("h2", {}, "修改我的密码"),
          h("div", { class: "a-fields" }, field("原密码", op), field("新密码（至少 8 位）", npw), field("当前动态码", oc)), pwErr,
          h("div", { class: "row" }, h("span", { class: "spacer" }), h("button", { class: "btn primary", onclick: async () => {
            pwErr.textContent = "";
            try { await api("/api/admin/me/password", { method: "POST", body: { old_password: op.value, new_password: npw.value, code: oc.value } }); toast("密码已修改"); op.value = npw.value = oc.value = ""; } catch (e) { pwErr.textContent = e.message; }
          } }, "保存"))),
        h("section", { class: "panel glass" }, h("h2", {}, "谷歌验证器"),
          h("p", { class: "sub" }, "换手机或验证器丢失前，先在这里重新绑定。"), rebindBtn, rebindErr, rebindBox)),
      h("section", { class: "panel glass" }, h("h2", {}, "应急命令"),
        h("p", { class: "sub" }, "无法登录后台时，在服务器上运行以下命令，然后执行 docker restart zyll："),
        h("pre", { class: "code" }, "docker exec zyll python -m app.cli disable-turnstile   # 关闭所有人机验证\ndocker exec zyll python -m app.cli reset-admin         # 删除所有管理员，重新进入安装向导")),
    );
  },

  async mail(main) {
    const to = h("input", { type: "email", placeholder: "收件邮箱" });
    const testErr = errBox();
    const smtpTest = h("section", { class: "panel glass" }, h("h2", {}, "发送测试邮件"),
      h("p", { class: "sub" }, "先保存上面的 SMTP 设置，再发一封测试邮件确认能收到。"),
      h("div", { class: "row" }, to, h("button", { class: "btn", onclick: async () => {
        testErr.textContent = "";
        try { await api("/api/admin/smtp/test", { method: "POST", body: { to: to.value.trim() } }); toast("已发送，请查收"); } catch (e) { testErr.textContent = e.message; }
      } }, "发送")), testErr);
    const forms = groupsOf("mail").map((g) => {
      const form = groupForm(g);
      if (!g.template) return form;
      const preview = h("div", { class: "mail-preview", hidden: true });
      const tto = h("input", { type: "email", placeholder: "测试收件邮箱" });
      const perr = errBox();
      const show = async () => {
        perr.textContent = "";
        try {
          const r = await api("/api/admin/mail/preview", { method: "POST", body: { key: g.template } });
          const frame = h("iframe", { sandbox: "", title: "HTML 预览", class: "mail-frame", src: `/api/admin/mail/preview.html?key=${g.template}&t=${Date.now()}` });
          preview.replaceChildren(...[h("div", { class: "small muted" }, "主题"), h("b", {}, r.subject),
            h("div", { class: "small muted", style: { marginTop: "8px" } }, "纯文本正文"), h("pre", { class: "code" }, r.body),
            r.html ? h("div", { class: "small muted", style: { marginTop: "8px" } }, "HTML 正文") : null, r.html ? frame : null].filter(Boolean));
          preview.hidden = false;
        } catch (e) { perr.textContent = e.message; }
      };
      form.append(h("div", { class: "row", style: { marginTop: "6px" } },
        h("span", { class: "muted small" }, "预览使用示例数据，请先保存再预览"), h("span", { class: "spacer" }),
        h("button", { class: "btn", type: "button", onclick: show }, "预览"), tto,
        h("button", { class: "btn", type: "button", onclick: async () => {
          perr.textContent = "";
          try { await api("/api/admin/mail/test", { method: "POST", body: { key: g.template, to: tto.value.trim() } }); toast("已发送，请查收"); } catch (e) { perr.textContent = e.message; }
        } }, "发送测试")), perr, preview);
      return form;
    });
    main.replaceChildren(pageHead("邮件", "SMTP 发信设置和系统邮件模板。模板中的 {占位符} 会在发送时替换为实际内容。"), forms[0], smtpTest, ...forms.slice(1));
  },

  async privacy(main) {
    const params = new URLSearchParams(location.hash.split("?")[1] || "");
    const q = h("input", { type: "search", placeholder: "邮箱或 IP", value: params.get("q") || "", style: { width: "220px" } });
    const realm = h("select", { style: { width: "auto" } }, h("option", { value: "" }, "全部账号"), h("option", { value: "user" }, "前台用户"), h("option", { value: "admin" }, "管理员"));
    const riskOnly = h("input", { type: "checkbox" });
    const tbody = h("tbody");
    const pager = h("div", { class: "row" });
    let offset = 0;
    const EV = { login_ok: "登录成功", login_fail: "登录失败", register: "注册", register_fail: "注册失败", logout: "退出", password: "改密码",
      password_fail: "改密码失败", export: "导出数据", export_user: "导出用户数据", export_all: "导出全部用户", install: "安装后台" };
    async function load() {
      const d = await api(`/api/admin/logins?q=${encodeURIComponent(q.value.trim())}&realm=${realm.value}&risk=${riskOnly.checked ? 1 : 0}&offset=${offset}`);
      tbody.replaceChildren(...(d.events.length ? d.events.flatMap((e) => {
        const rawRow = h("tr", { class: "raw-row", hidden: true }, h("td", { colspan: 8 }, h("pre", { class: "code raw" }, JSON.stringify({ ip_chain: e.ip_chain, ua: e.ua, ...e.data }, null, 2))));
        return [h("tr", {},
        h("td", { class: "muted nowrap" }, dt(e.ts)),
        h("td", {}, e.realm === "admin" ? h("span", { class: "tag" }, "管理员") : null, " ", e.email || "—"),
        h("td", { class: e.event.endsWith("fail") ? "down" : "" }, EV[e.event] || e.event, e.reason ? h("div", { class: "small muted" }, e.reason) : null),
        h("td", { class: "nowrap" }, e.ip, e.country ? h("div", { class: "small muted" }, e.country) : null),
        h("td", { class: "small wrap" }, e.ua.slice(0, 90)),
        h("td", { class: "small" }, h("code", {}, e.device_hash)),
        h("td", { class: "small down" }, e.risk),
        h("td", {}, h("button", { class: "btn small-btn", onclick: () => { rawRow.hidden = !rawRow.hidden; } }, "原始数据")),
        ), rawRow];
      }) : [h("tr", {}, h("td", { colspan: 8, class: "empty" }, "没有记录"))]));
      pager.replaceChildren(...[h("span", { class: "muted small" }, `共 ${d.total} 条`), h("span", { class: "spacer" }),
        offset > 0 ? h("button", { class: "btn", onclick: () => { offset -= 100; load(); } }, "上一页") : null,
        offset + 100 < d.total ? h("button", { class: "btn", onclick: () => { offset += 100; load(); } }, "下一页") : null].filter(Boolean));
    }
    let timer;
    q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { offset = 0; load(); }, 300); });
    realm.addEventListener("change", () => { offset = 0; load(); });
    riskOnly.addEventListener("change", () => { offset = 0; load(); });
    main.replaceChildren(
      pageHead("隐私与合规", "按欧盟 GDPR 处理个人数据：前台“隐私政策”页面根据这里的设置自动生成；用户可自行导出或删除自己的数据，管理员也可代为导出。"),
      h("section", { class: "panel glass" }, h("h2", {}, "数据导出"),
        h("p", { class: "sub" }, "导出内容包括账号信息、持仓分析、交易记录、付款记录和登录安全记录（不含密码哈希）。用于响应用户的查阅、可携带请求或监管要求。"),
        h("div", { class: "row" },
          h("a", { class: "btn primary", href: "/api/admin/users/export" }, "一键导出全部用户数据（JSON）"),
          h("a", { class: "btn", href: "/api/admin/telemetry/export" }, "导出全部诊断数据（JSON）"),
          h("a", { class: "btn", href: "/#/privacy", target: "_blank" }, "查看前台隐私政策"))),
      ...groupsOf("privacy").map((g) => groupForm(g)),
      h("section", { class: "panel glass" },
        h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, "登录安全记录"), h("span", { class: "spacer" }),
          realm, h("label", { class: "small", style: { display: "flex", gap: "6px", alignItems: "center", whiteSpace: "nowrap" } }, riskOnly, "只看有风险"), q),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, ["时间", "账号", "事件", "IP / 地区", "浏览器", "设备标识", "风险", ""].map((x) => h("th", {}, x)))), tbody)), pager),
    );
    await load();
  },

  async diagnostics(main) {
    let rawN = 100;
    const d = await api(`/api/admin/telemetry?raw=${rawN}`);
    const kindName = { load: "页面加载", error: "前端错误", api: "接口失败", sse: "推送断开", vitals: "网页指标", view: "切换页面", longtask: "长任务", resource: "接口耗时" };
    const VITAL = { FCP: ["首次内容绘制", "ms", 1800], LCP: ["最大内容绘制", "ms", 2500], CLS: ["累计布局偏移", "", 0.1], INP: ["交互响应", "ms", 200] };
    const rawBox = h("div", { class: "raw-list" });
    const renderRaw = (rows) => rawBox.replaceChildren(...(rows.length ? rows.map((r) => h("details", { class: "raw-item" },
      h("summary", {}, h("span", { class: "muted" }, dt(r.ts)), " ", h("b", {}, kindName[r.kind] || r.kind), " ", r.path, " ",
        h("span", { class: "muted" }, r.message.slice(0, 80)), r.value != null ? h("span", { class: "tag" }, r.value) : null),
      h("pre", { class: "code raw" }, JSON.stringify(r, null, 2)))) : [h("div", { class: "empty" }, "暂无数据")]));
    renderRaw(d.raw);
    const nSel = h("select", { style: { width: "auto" }, onchange: async (e) => { rawN = +e.target.value; const x = await api(`/api/admin/telemetry?raw=${rawN}`); renderRaw(x.raw); } },
      [100, 300, 1000].map((n) => h("option", { value: n }, `最近 ${n} 条`)));
    main.replaceChildren(
      pageHead("诊断数据", "来自同意了性能 Cookie 的访客浏览器。不与账号关联，IP 截断保存。"),
      ...groupsOf("diagnostics").map((g) => groupForm(g)),
      h("section", { class: "panel glass" }, h("h2", {}, "近 14 天"),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, ["日期", "访问", "平均加载", "前端错误", "接口失败", "推送断开"].map((x, i) => h("th", { class: i ? "num" : "" }, x)))),
          h("tbody", {}, d.daily.length ? d.daily.map((r) => h("tr", {}, h("td", {}, r.day), h("td", { class: "num" }, r.views),
            h("td", { class: "num" }, r.avg_load ? `${fmt(r.avg_load / 1000, 2)} 秒` : "—"), h("td", { class: "num" }, r.errors),
            h("td", { class: "num" }, r.api_fail), h("td", { class: "num" }, r.sse_drop)))
            : h("tr", {}, h("td", { colspan: 6, class: "empty" }, "暂无数据")))))),
      h("div", { class: "grid-2" },
        h("section", { class: "panel glass" }, h("h2", {}, "核心网页指标（平均 / 最差）"),
          h("div", { class: "table-wrap" }, h("table", {},
            h("thead", {}, h("tr", {}, ["指标", "样本", "平均", "最差"].map((x, i) => h("th", { class: i ? "num" : "" }, x)))),
            h("tbody", {}, d.vitals.length ? d.vitals.map((v) => {
              const [name, unit, good] = VITAL[v.name] || [v.name, "", Infinity];
              const f = (x) => (unit ? `${fmt(x, 0)} ${unit}` : fmt(x, 3));
              return h("tr", {}, h("td", {}, `${v.name} ${name}`), h("td", { class: "num" }, v.n), h("td", { class: `num ${v.avg > good ? "bad-txt" : "good-txt"}` }, f(v.avg)), h("td", { class: "num" }, f(v.max)));
            }) : h("tr", {}, h("td", { colspan: 4, class: "empty" }, "暂无数据")))))),
        h("section", { class: "panel glass" }, h("h2", {}, "最慢的接口（采样）"),
          h("div", { class: "table-wrap" }, h("table", {},
            h("thead", {}, h("tr", {}, ["接口", "样本", "平均", "最慢"].map((x, i) => h("th", { class: i ? "num" : "" }, x)))),
            h("tbody", {}, d.apis.length ? d.apis.map((a) => h("tr", {}, h("td", { class: "wrap" }, a.path), h("td", { class: "num" }, a.n),
              h("td", { class: "num" }, `${fmt(a.avg, 0)} ms`), h("td", { class: "num" }, `${fmt(a.max, 0)} ms`)))
              : h("tr", {}, h("td", { colspan: 4, class: "empty" }, "暂无数据"))))))),
      h("section", { class: "panel glass" }, h("h2", {}, "最常见的问题"),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, ["类型", "位置", "内容", "次数", "最近一次"].map((x) => h("th", {}, x)))),
          h("tbody", {}, d.top.length ? d.top.map((r) => h("tr", {}, h("td", {}, kindName[r.kind] || r.kind), h("td", {}, r.path),
            h("td", { class: "wrap" }, r.message), h("td", { class: "num" }, r.n), h("td", { class: "muted" }, dt(r.last))))
            : h("tr", {}, h("td", { colspan: 5, class: "empty" }, "没有错误记录")))))),
      h("section", { class: "panel glass" },
        h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, "收集到的原始数据"), h("span", { class: "muted small" }, `数据库共 ${d.total} 条`), h("span", { class: "spacer" }),
          nSel, h("a", { class: "btn", href: "/api/admin/telemetry/export" }, "导出 JSON"),
          h("button", { class: "btn danger", onclick: async () => { if (confirm("清空全部诊断数据？")) { await api("/api/admin/telemetry", { method: "DELETE" }); VIEWS.diagnostics(main); } } }, "清空")),
        h("p", { class: "sub" }, "每条记录包含：事件本身、浏览器环境（设备、网络、屏幕、语言、时区等）和服务器看到的请求信息。点击展开查看完整内容。"),
        rawBox),
    );
  },
};

VIEWS.logs = async (main) => {
  const level = h("select", { style: { width: "auto" } }, [["INFO", "信息及以上"], ["WARNING", "警告及以上"], ["ERROR", "只看错误"], ["DEBUG", "全部"]].map(([v, l]) => h("option", { value: v }, l)));
  const q = h("input", { type: "search", placeholder: "搜索内容、模块或堆栈", style: { width: "260px" } });
  const auto = h("input", { type: "checkbox", checked: true });
  const list = h("div", { class: "log-list" });
  const info = h("span", { class: "muted small" });
  let items = [], lastId = 0;
  const LV = { DEBUG: "调试", INFO: "信息", WARNING: "警告", ERROR: "错误", CRITICAL: "严重" };
  const row = (it) => h("details", { class: `log-item lv-${it.level}` },
    h("summary", {},
      h("span", { class: "muted nowrap" }, dt(Math.floor(it.ts))),
      h("span", { class: `lv lv-${it.level}` }, LV[it.level] || it.level),
      h("span", { class: "muted small" }, it.logger),
      h("span", { class: "log-msg" }, it.message.split("\n")[0].slice(0, 300)),
      it.count > 1 ? h("span", { class: "tag" }, `×${it.count}`) : null),
    h("pre", { class: "code raw" }, [it.message, it.trace ? `\n${it.trace}` : "", `\n位置：${it.where}${it.count > 1 ? `\n重复 ${it.count} 次，最近一次 ${dt(Math.floor(it.last))}` : ""}`].join("")));
  async function load(reset) {
    if (reset) { items = []; lastId = 0; }
    const d = await api(`/api/admin/logs?level=${level.value}&q=${encodeURIComponent(q.value.trim())}&since=${lastId}&limit=1000`);
    if (d.items.length) {
      items = [...d.items, ...items].slice(0, 1500);
      lastId = Math.max(lastId, ...d.items.map((x) => x.id));
    }
    info.textContent = `显示 ${items.length} 条；近 24 小时错误 ${d.counts.ERROR} 条、警告 ${d.counts.WARNING} 条`;
    list.replaceChildren(...(items.length ? items.map(row) : [h("div", { class: "empty" }, "没有符合条件的日志")]));
  }
  let timer;
  level.addEventListener("change", () => load(true));
  q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => load(true), 300); });
  main.replaceChildren(
    pageHead("运行日志", "程序运行时的信息、警告和错误（含完整堆栈），包括数据源抓取失败、接口报错、后台操作。最近 3000 条保存在内存，同时写入服务器 /data/logs/zyll.log（5 MB 轮转，保留 5 份）。"),
    h("section", { class: "panel glass" },
      h("div", { class: "row" }, level, q, h("label", { class: "small", style: { display: "flex", gap: "6px", alignItems: "center", whiteSpace: "nowrap" } }, auto, "每 5 秒自动刷新"), h("span", { class: "spacer" }),
        h("button", { class: "btn", onclick: () => load(true) }, "刷新"),
        h("a", { class: "btn", href: "/api/admin/logs/download" }, "下载日志文件")),
      h("p", {}, info), list));
  await load(true);
  const iv = setInterval(() => { if (auto.checked && !main.querySelector("details[open]")) load(false).catch(() => {}); }, 5000);
  return () => clearInterval(iv);
};

/* ================= 启动 ================= */
async function boot() {
  schema = null;
  state = await api("/api/admin/state");
  document.title = `${state.site_name} 后台`;
  if (!state.installed) return renderInstall();
  if (!state.admin) return renderLogin();
  renderShell();
  route();
}
window.addEventListener("hashchange", () => state?.admin && route());
boot().catch((e) => root.replaceChildren(h("div", { class: "auth-page" }, h("div", { class: "auth-card glass" }, h("div", { class: "err" }, e.message)))));
