import { api, consent, deviceInfo, h, live, telemetry, toast, ui } from "./core.js";
import { TIMEZONES, prefs, t } from "./i18n.js";
import { mountAds } from "./ads.js";
import calendarView from "./views/calendar.js";
import darkpoolView from "./views/darkpool.js";
import futuresView from "./views/futures.js";
import quotesView from "./views/quotes.js";
import portfolioView from "./views/portfolio.js";
import privacyView from "./views/privacy.js";

const root = document.getElementById("root");
let site = { name: "Zyll财经", name_en: "Zyll Finance", copyright: "Zyll团队", register: { enabled: true }, turnstile: {}, membership: {} };
let me = null;
let cleanup = null;
let offConn = null;

const ROUTES = { calendar: calendarView, portfolio: portfolioView, darkpool: darkpoolView, futures: futuresView, quotes: quotesView };
const HIDDEN = { privacy: privacyView, "app-auth": (el) => appAuthView(el) };  // 不出现在导航里的页面
const routeEnabled = (r) => r !== "portfolio" || site.portfolio?.enabled !== false;

function applyPrefs() {
  document.documentElement.lang = prefs.lang === "zh" ? "zh-CN" : "en";
  document.documentElement.dataset.updown = prefs.updown;
}
const siteName = () => (prefs.lang === "zh" ? site.name : site.name_en || site.name);

const LOGO = () => {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 32 32");
  s.innerHTML = '<rect width="32" height="32" rx="9" fill="rgba(71,198,192,.16)" stroke="rgba(71,198,192,.5)"/><path d="M6 22l6-7 5 4 9-11" stroke="#47c6c0" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>';
  return s;
};

/* ---------- Cloudflare Turnstile（后台开启后才加载） ---------- */
let turnstileLoading = null;
function turnstileWidget(flag) {
  if (!site.turnstile?.[flag] || !site.turnstile.site_key) return null;
  const box = h("div", { class: "turnstile" });
  turnstileLoading ??= new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    s.async = true; s.onload = resolve;
    document.head.append(s);
  });
  turnstileLoading.then(() => window.turnstile?.render(box, { sitekey: site.turnstile.site_key, theme: "dark" }));
  return box;
}
const turnstileToken = (form) => form.querySelector("[name='cf-turnstile-response']")?.value || "";

/* ---------- 通用弹窗表单 ---------- */
function formDialog({ title, desc, fields, submit, extra, footer, onSubmit }) {
  const err = h("div", { class: "err", role: "alert" });
  const inputs = fields.map((f) => h("input", { type: f.type || "text", name: f.name, autocomplete: f.autocomplete, required: true, minlength: f.minlength }));
  const btn = h("button", { class: "btn primary", type: "submit" }, submit);
  const dlg = h("dialog", { class: "glass" });
  const form = h("form", { class: "dialog-form", onsubmit: async (e) => {
    e.preventDefault();
    btn.disabled = true; err.textContent = "";
    const values = Object.fromEntries(fields.map((f, i) => [f.name, inputs[i].value]));
    values.turnstile = turnstileToken(form);
    if (form.querySelector(".turnstile") && !values.turnstile) {
      err.textContent = t("turnstileFirst"); btn.disabled = false; return;
    }
    try {
      const close = await onSubmit(values, err);
      if (close !== false) dlg.close();
    } catch (ex) {
      err.textContent = ex.message;
      window.turnstile?.reset?.();
    } finally { btn.disabled = false; }
  } },
    h("h2", {}, title),
    desc ? h("p", { class: "muted small" }, desc) : null,
    fields.map((f, i) => h("label", {}, f.label, inputs[i])),
    extra || null,
    err,
    h("div", { class: "row" }, footer || null, h("span", { class: "spacer" }),
      h("button", { class: "btn", type: "button", onclick: () => dlg.close() }, t("cancel")), btn),
  );
  dlg.append(form);
  dlg.addEventListener("close", () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
  inputs[0].focus();
  return dlg;
}

function loginDialog() {
  const dlg = formDialog({
    title: t("login"),
    submit: t("login"),
    fields: [
      { name: "email", label: t("email"), type: "email", autocomplete: "email" },
      { name: "password", label: t("password"), type: "password", autocomplete: "current-password" },
    ],
    extra: h("div", { class: "row" }, turnstileWidget("on_login"), h("span", { class: "spacer" }),
      h("button", { class: "linkbtn small", type: "button", onclick: () => { dlg.close(); forgotDialog(); } }, t("forgotPassword"))),
    footer: site.register?.enabled ? h("button", { class: "linkbtn", type: "button", onclick: () => { dlg.close(); registerDialog(); } }, t("noAccount")) : null,
    onSubmit: async (v) => {
      try {
        const r = await api("/api/auth/login", { method: "POST", body: { email: v.email.trim(), password: v.password, turnstile: v.turnstile, device: deviceInfo() } });
        me = r.user; await reloadSite(); toast(t("loggedIn"));
      } catch (e) {
        if (e.data?.unverified) {
          api("/api/auth/resend", { method: "POST", body: { email: v.email.trim() } }).catch(() => {});
          throw new Error(t("verifyFirst"));
        }
        throw e;
      }
    },
  });
}

function forgotDialog() {
  if (!site.password_reset) { toast(t("resetUnavailable"), 6000); return; }
  formDialog({
    title: t("forgotTitle"), desc: t("forgotDesc"), submit: t("sendResetLink"),
    fields: [{ name: "email", label: t("email"), type: "email", autocomplete: "email" }],
    extra: turnstileWidget("on_forgot"),
    onSubmit: async (v) => {
      await api("/api/auth/forgot", { method: "POST", body: { email: v.email.trim(), turnstile: v.turnstile, device: deviceInfo() } });
      toast(t("resetSent"), 8000);
    },
  });
}

function resetDialog(token) {
  formDialog({
    title: t("resetTitle"), submit: t("save"),
    fields: [
      { name: "password", label: t("newPassword"), type: "password", autocomplete: "new-password", minlength: 8 },
      { name: "confirm", label: t("confirmPassword"), type: "password", autocomplete: "new-password", minlength: 8 },
    ],
    onSubmit: async (v) => {
      if (v.password !== v.confirm) throw new Error(t("mismatch"));
      await api("/api/auth/reset", { method: "POST", body: { token, password: v.password, device: deviceInfo() } });
      toast(t("resetDone"), 6000);
      await reloadSite();
    },
  });
}

/* ---------- 安卓 App 网页登录：确认授权后带一次性授权码跳回 App（PKCE，App 自己保管 verifier） ---------- */
function appAuthView(el) {
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  const challenge = q.get("challenge") || "", state = q.get("state") || "", device = (q.get("device") || "").slice(0, 80);
  const card = h("section", { class: "panel glass app-auth" });
  el.append(card);
  const ok = /^[A-Za-z0-9_-]{43,128}$/.test(challenge) && /^[A-Za-z0-9_-]{8,128}$/.test(state);
  if (!ok) { card.append(h("h2", {}, t("appAuthTitle")), h("p", { class: "err" }, t("appAuthBad"))); return; }
  card.append(h("h2", {}, t("appAuthTitle")), h("p", { class: "muted" }, t("appAuthDesc")));
  if (device) card.append(h("p", {}, `${t("appAuthDevice")}：`, h("b", {}, device)));
  if (!me) {
    card.append(h("p", {}, t("appAuthLogin")), h("div", { class: "row" },
      h("button", { class: "btn primary", onclick: loginDialog }, t("login")),
      site.register?.enabled ? h("button", { class: "btn", onclick: registerDialog }, t("register")) : null,
      h("button", { class: "linkbtn", onclick: forgotDialog }, t("forgotPassword"))));
    return;
  }
  const err = h("div", { class: "err" });
  const back = (params) => `zyllfinance://auth?${new URLSearchParams({ ...params, state })}`;
  const approve = h("button", { class: "btn primary", onclick: async () => {
    approve.disabled = true; err.textContent = "";
    try {
      const r = await api("/api/auth/app-code", { method: "POST", body: { challenge, device_name: device } });
      const url = back({ code: r.code });
      card.replaceChildren(h("h2", {}, t("appAuthTitle")), h("p", {}, t("appAuthDone")),
        h("a", { class: "btn primary", href: url }, t("appAuthBack")));
      location.href = url;
    } catch (e) { err.textContent = e.message; approve.disabled = false; }
  } }, t("appAuthApprove"));
  card.append(h("p", {}, `${t("appAuthAccount")}：`, h("b", {}, me.email)),
    h("p", { class: "warn small" }, t("appAuthWarn")), err,
    h("div", { class: "row" }, approve,
      h("button", { class: "btn", onclick: () => { card.replaceChildren(h("p", {}, t("appAuthDenied")), h("a", { class: "btn", href: back({ error: "denied" }) }, t("appAuthBack"))); } }, t("appAuthDeny"))));
}

function registerDialog() {
  const dlg = formDialog({
    title: t("register"),
    desc: site.register?.email_verify ? t("registerVerifyDesc") : null,
    submit: t("register"),
    fields: [
      { name: "email", label: t("email"), type: "email", autocomplete: "email" },
      { name: "password", label: t("newPassword"), type: "password", autocomplete: "new-password", minlength: 8 },
      { name: "confirm", label: t("confirmPassword"), type: "password", autocomplete: "new-password", minlength: 8 },
    ],
    extra: turnstileWidget("on_register"),
    footer: h("button", { class: "linkbtn", type: "button", onclick: () => { dlg.close(); loginDialog(); } }, t("haveAccount")),
    onSubmit: async (v) => {
      if (v.password !== v.confirm) throw new Error(t("mismatch"));
      const r = await api("/api/auth/register", { method: "POST", body: { email: v.email.trim(), password: v.password, turnstile: v.turnstile, device: deviceInfo() } });
      if (r.verify_required) { toast(t("checkInbox"), 6000); return; }
      me = r.user; await reloadSite(); toast(t("registered"));
    },
  });
}

function passwordDialog() {
  formDialog({
    title: t("changePassword"),
    submit: t("save"),
    fields: [
      { name: "old", label: t("oldPassword"), type: "password", autocomplete: "current-password" },
      { name: "new", label: t("newPassword"), type: "password", autocomplete: "new-password", minlength: 8 },
    ],
    onSubmit: async (v) => {
      await api("/api/auth/password", { method: "POST", body: { old_password: v.old, new_password: v.new } });
      toast(t("saved"));
    },
  });
}

function deleteAccountDialog() {
  formDialog({
    title: t("deleteAccount"),
    desc: t("deleteAccountDesc"),
    submit: t("deleteAccount"),
    fields: [{ name: "password", label: t("password"), type: "password", autocomplete: "current-password" }],
    onSubmit: async (v) => {
      await api("/api/me/delete", { method: "POST", body: { password: v.password } });
      me = null; await reloadSite(); toast(t("accountDeleted"), 5000);
    },
  });
}

/* ---------- 会员：卡密激活 / 续期（会员模式关闭时不会出现） ---------- */
const dateOf = (ts) => new Date(ts * 1000).toLocaleDateString(prefs.lang === "zh" ? "zh-CN" : "en-US", { year: "numeric", month: "2-digit", day: "2-digit" });

function memberLabel(m) {
  if (!m) return null;
  if (m.permanent) return t("memberPermanent");
  if (m.active) return t("memberUntil").replace("{d}", dateOf(m.expires));
  return m.expired ? t("memberExpired") : t("activateMember");
}

async function becomeMember() {
  if (!site.membership?.enabled) return;
  if (!me) { loginDialog(); return; }
  let info = null;
  try { info = await api("/api/member"); } catch { /* 网络问题时仍可输入卡密 */ }
  const st = info?.status || me.membership;
  const renew = st?.active && !st.permanent;
  const desc = st?.permanent ? t("memberPermanentDesc")
    : st?.active ? t("memberRenewDesc").replace("{d}", dateOf(st.expires))
    : st?.expired ? t("memberExpiredDesc").replace("{d}", dateOf(st.expires)) : t("memberActivateDesc");
  if (st?.permanent) { toast(desc, 4000); return; }
  formDialog({
    title: renew ? t("renewMember") : t("activateMember"),
    desc,
    submit: renew ? t("renewNow") : t("activateNow"),
    fields: [{ name: "code", label: t("cardCode"), autocomplete: "off" }],
    extra: info?.buy_hint ? h("div", { class: "buy-hint" }, ...info.buy_hint.split(/\n+/).map((x) => h("p", {}, x))) : null,
    onSubmit: async (v) => {
      const r = await api("/api/member/redeem", { method: "POST", body: { code: v.code } });
      me = r.user;
      toast(r.permanent ? t("memberNowPermanent") : t("memberNowUntil").replace("{d}", dateOf(r.expires)), 6000);
      await reloadSite();
    },
  });
}

/* ---------- Cookie 同意 ---------- */
function consentBar() {
  if (consent.get()) return null;
  const bar = h("div", { class: "consent glass", role: "region", "aria-label": t("cookieTitle") },
    h("p", {}, t("cookieText"), " ", h("a", { href: "#/privacy" }, t("privacy"))),
    h("div", { class: "row" },
      h("button", { class: "btn", onclick: () => { consent.set("necessary"); bar.remove(); } }, t("cookieNecessary")),
      h("button", { class: "btn primary", onclick: () => { consent.set("necessary,perf"); bar.remove(); telemetry.start(); } }, t("cookieAll"))));
  return bar;
}

/* ---------- 外壳 ---------- */
function renderShell() {
  document.title = siteName();
  const dot = h("span", { class: "live-dot" + (live.connected ? " on" : ""), title: t("liveConn") });
  offConn?.();
  offConn = live.on("_conn", (on) => dot.classList.toggle("on", on));

  const tz = h("select", { "aria-label": t("timezone"), onchange: (e) => { prefs.tz = e.target.value; route(); } },
    TIMEZONES.map((z) => h("option", { value: z.id, selected: z.id === prefs.tz }, z[prefs.lang])));
  const lang = h("button", { class: "btn", onclick: () => { prefs.lang = prefs.lang === "zh" ? "en" : "zh"; applyPrefs(); refresh(); } },
    prefs.lang === "zh" ? "EN" : "中文");

  let account;
  if (me) {
    account = h("select", { "aria-label": t("account"), class: "ctl", onchange: (e) => {
      const v = e.target.value; e.target.value = "";
      if (v === "pw") passwordDialog();
      if (v === "member") becomeMember();
      if (v === "updown") { prefs.updown = prefs.updown === "red" ? "green" : "red"; applyPrefs(); toast(t("saved")); }
      if (v === "cookie") { consent.set(""); document.cookie = "zy_consent=; path=/; max-age=0"; refresh(); }
      if (v === "export") location.href = "/api/me/export";
      if (v === "delete") deleteAccountDialog();
      if (v === "logout") api("/api/auth/logout", { method: "POST" }).finally(async () => { me = null; await reloadSite(); });
    } },
      h("option", { value: "" }, me.email + (site.membership?.enabled && me.membership?.active ? " ★" : "")),
      site.membership?.enabled && me.membership ? h("option", { value: "member" }, memberLabel(me.membership)) : null,
      h("option", { value: "updown" }, `${t("upDown")}: ${prefs.updown === "red" ? t("greenUp") : t("redUp")}`),
      h("option", { value: "cookie" }, t("cookieSettings")),
      h("option", { value: "pw" }, t("changePassword")),
      h("option", { value: "export" }, t("exportMyData")),
      h("option", { value: "delete" }, t("deleteAccount")),
      h("option", { value: "logout" }, t("logout")),
    );
  } else {
    account = h("div", { class: "row" },
      h("button", { class: "btn", onclick: loginDialog }, t("login")),
      site.register?.enabled ? h("button", { class: "btn primary", onclick: registerDialog }, t("register")) : null);
  }

  const links = Object.keys(ROUTES).filter(routeEnabled).map((r) => h("a", { href: `#/${r}`, "data-route": r }, t(r)));
  const year = new Date().getFullYear();
  const footer = h("footer", { class: "site-footer" },
    h("div", { class: "ad-slot", "data-slot": "footer" }),
    h("p", {}, `© ${year} ${site.copyright} ${t("allRights")}`, " · ", h("a", { href: "#/privacy" }, t("privacy")),
      " · ", h("button", { class: "linkbtn", type: "button", onclick: () => { consent.set(""); document.cookie = "zy_consent=; path=/; max-age=0"; refresh(); } }, t("cookieSettings"))),
    site.icp ? h("p", {}, h("a", { href: "https://beian.miit.gov.cn/", target: "_blank", rel: "noopener" }, site.icp)) : null,
    h("p", { class: "muted small" }, t("disclaimer")));

  root.replaceChildren(...[
    h("header", { class: "topbar glass" },
      h("div", { class: "brand" }, LOGO(), h("span", {}, siteName())),
      h("nav", { class: "nav", "aria-label": "Main" }, links),
      h("div", { class: "tools" }, dot, tz, lang, account),
    ),
    site.announcement ? h("div", { class: "announce glass", role: "status" }, site.announcement) : null,
    h("div", { class: "ad-side", "data-slot": "side" }),
    h("main", { id: "view" }),
    footer,
    consentBar(),
  ].filter(Boolean));
}

function route() {
  const raw = (location.hash.replace(/^#\//, "") || "calendar").split("?")[0];
  if (raw === "verified" || raw === "verify-failed") {
    toast(raw === "verified" ? t("verifiedOk") : t("verifiedFail"), 5000);
    history.replaceState(null, "", "#/calendar");
  }
  if (raw.startsWith("reset/")) {   // 邮件里的重置密码链接：#/reset/<token>
    const token = raw.slice(6);
    history.replaceState(null, "", "#/calendar");
    setTimeout(() => resetDialog(token), 0);
  }
  if (raw === "forgot") {
    history.replaceState(null, "", "#/calendar");
    setTimeout(forgotDialog, 0);
  }
  const name = HIDDEN[raw] ? raw : ROUTES[raw] && routeEnabled(raw) ? raw : "calendar";
  if (name === "app-auth") document.title = `${t("appAuthTitle")} - ${siteName()}`;
  document.querySelectorAll(".nav a").forEach((a) => (a.dataset.route === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  cleanup?.();
  const el = document.getElementById("view");
  el.replaceChildren();
  cleanup = (HIDDEN[name] || ROUTES[name])(el, { me, site }) || null;
  mountAds(site.ads, document);
}

function refresh() {
  renderShell();
  route();
}

async function reloadSite() {
  try {
    site = await api("/api/site");
    me = site.user;
  } catch { /* 网络失败时保留默认值 */ }
  telemetry.enabled = !!site.telemetry;
  telemetry.sample = site.telemetry_sample ?? 20;
  ui.onLocked = site.membership?.enabled ? becomeMember : null;
  refresh();
}

ui.onAuth = loginDialog;
applyPrefs();
window.addEventListener("hashchange", route);
reloadSite().finally(() => { live.start(); telemetry.start(); });
