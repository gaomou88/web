/* 隐私政策（按欧盟 GDPR 编写，内容随后台设置自动更新） */
import { api, h } from "../core.js";
import { prefs } from "../i18n.js";

const ZH = (p) => [
  ["1. 数据控制者", [
    `数据控制者：${p.controller}${p.address ? `，地址：${p.address}` : ""}。`,
    p.contact ? `隐私事务联系邮箱：${p.contact}。` : "隐私事务请通过网站公布的联系方式与我们联系。",
    p.dpo ? `数据保护官（DPO）：${p.dpo}。` : null,
    p.eu_rep ? `欧盟代表：${p.eu_rep}。` : null,
  ]],
  ["2. 我们处理哪些数据、为什么、依据什么", [
    "账号数据：邮箱、密码（只保存不可逆的哈希值）、注册时间、会员状态。用途：提供账号和会员功能。法律依据：履行合同（GDPR 第 6(1)(b) 条）。",
    "持仓分析（股票）与交易记录：你录入的股票、买卖记录、货币对、备注和偏好设置。用途：计算并展示你的盈亏。法律依据：履行合同（第 6(1)(b) 条）。",
    p.login_log ? `登录安全记录：每次注册、登录（含失败）、退出、修改密码时的时间、IP 地址、国家/地区、浏览器标识（User-Agent 及客户端提示）、语言、时区、屏幕与设备特征（如处理器核数、内存档位、触屏点数、是否为自动化浏览器）、由这些特征计算的设备标识，以及系统生成的风险标记（如“新设备”“新网络”“短时间多次失败”）。用途：识别盗号、撞库和欺诈，并在异常登录时提醒你。法律依据：正当利益（第 6(1)(f) 条）——保护你的账号和本网站的安全。我们不使用画布、音频等隐蔽指纹技术。保存 ${p.login_log_days} 天后自动删除。` : null,
    p.telemetry ? `性能与诊断数据（仅在你点击“同意全部”后收集）：页面加载各阶段耗时、核心网页指标、接口耗时和失败、实时连接状态、脚本错误信息、长任务、内存占用、网络类型、屏幕与窗口尺寸、语言、时区、浏览器与系统信息，以及一个仅在当前标签页有效的随机会话编号。这些数据不与账号关联，IP 地址截断后保存（IPv4 去掉最后一段）。用途：发现和修复故障、优化速度。法律依据：同意（第 6(1)(a) 条；ePrivacy 指令第 5(3) 条）。保存 ${p.telemetry_days} 天。你可随时在账号菜单或页脚的“Cookie 设置”中撤回同意。` : null,
    "服务器日志：为保障运行，Web 服务器可能短期记录请求时间、IP 和请求地址。法律依据：正当利益（第 6(1)(f) 条）。",
    p.ai ? `AI 导入结单（仅在你主动上传并勾选同意时）：你上传的券商结单内容会发送给 AI 服务商（${p.ai.providers.join("、")}）识别成交易记录。${p.ai.redact ? "发送前自动隐去邮箱、手机号、账号/证件号、姓名和地址。" : ""}文件和识别结果只在内存中处理，不写入数据库，30 分钟内自动清除；只保存调用时间、文件类型和大小、页数、用量和成功与否，用于每日限额和费用统计，随账号删除一并删除。你确认导入的交易按“持仓分析与交易记录”处理。法律依据：同意（第 6(1)(a) 条）及履行合同（第 6(1)(b) 条）。` : null,
  ]],
  ["3. Cookie", [
    "必要 Cookie：zy_user（登录状态，30 天）、zy_consent（你的 Cookie 选择，1 年）。没有它们网站无法正常工作，无需同意。",
    "性能 Cookie / 诊断：只在你同意后启用，见上文。",
    p.ads ? "广告：本网站启用了第三方广告，广告商可能根据其自身政策使用 Cookie；会在其展示前征得同意（如适用）。" : null,
    p.turnstile ? "人机验证：注册或登录时可能加载 Cloudflare Turnstile，以防止自动化滥用（正当利益）。" : null,
  ]],
  ["4. 数据接收方与跨境传输", [
    "我们不出售你的个人数据。数据存放在本网站的服务器上。",
    "第三方服务：邮件发送服务商（发送验证与通知邮件）" + (p.turnstile ? "、Cloudflare（人机验证）" : "") + (p.ads ? "、广告商" : "") + (p.ai ? `、AI 服务商 ${p.ai.providers.join("、")}（仅 AI 导入）` : "") + "。如需向欧洲经济区以外传输，我们依赖欧盟委员会的充分性决定或标准合同条款（第 46 条）；AI 服务商可能位于欧洲经济区以外，你上传前会看到提示并需主动同意（第 49(1)(a) 条）。",
    "行情数据从公开来源获取，不会向这些来源发送你的个人数据。",
  ]],
  ["5. 你的权利", [
    "你有权查阅（第 15 条）、更正（第 16 条）、删除（第 17 条）、限制处理（第 18 条）、数据可携带（第 20 条）、反对基于正当利益的处理（第 21 条），以及随时撤回同意（第 7(3) 条）。",
    "登录后可在右上角账号菜单中“导出我的数据”（JSON 格式）或“删除账号”（立即删除账号、持仓分析、交易记录和安全记录）。其他请求请发邮件联系我们，我们会在一个月内答复。",
    "你也有权向所在欧盟成员国的数据保护监管机构投诉。",
  ]],
  ["6. 保存期限", [
    "账号数据和持仓分析数据：保存到你删除账号为止。",
    p.login_log ? `登录安全记录：${p.login_log_days} 天。` : null,
    p.telemetry ? `诊断数据：${p.telemetry_days} 天。` : null,
  ]],
  ["7. 自动化决策", ["我们不进行对你产生法律效力或类似重大影响的自动化决策。风险标记只用于提醒和人工核查。"]],
  ["8. 未满 16 岁", ["本网站不面向 16 岁以下用户。"]],
  ["9. 政策更新", [`本政策更新于 ${p.updated || "—"}。重大变更会在网站上提示。`]],
];

const EN = (p) => [
  ["1. Controller", [
    `Controller: ${p.controller}${p.address ? `, ${p.address}` : ""}.`,
    p.contact ? `Privacy contact: ${p.contact}.` : "Please contact us through the contact details published on this site.",
    p.dpo ? `Data Protection Officer: ${p.dpo}.` : null,
    p.eu_rep ? `EU representative: ${p.eu_rep}.` : null,
  ]],
  ["2. What we process, why, and on what legal basis", [
    "Account data: e-mail, password (stored only as an irreversible hash), sign-up time, membership status. Purpose: provide your account and membership. Basis: contract (Art. 6(1)(b) GDPR).",
    "Watchlist and trades: symbols, trades, currency pairs, notes and preferences you enter. Purpose: calculate and show your P&L. Basis: contract (Art. 6(1)(b)).",
    p.login_log ? `Sign-in security log: for every sign-up, sign-in (including failures), sign-out and password change we record time, IP address, country, browser identification (User-Agent and client hints), language, time zone, screen and device characteristics (e.g. CPU cores, memory class, touch points, automated-browser flag), a device identifier derived from them, and risk flags (e.g. "new device", "new network", "repeated failures"). Purpose: detect account takeover, credential stuffing and fraud, and alert you to unusual sign-ins. Basis: legitimate interests (Art. 6(1)(f)) in keeping your account and this service secure. We do not use canvas, audio or other covert fingerprinting. Deleted automatically after ${p.login_log_days} days.` : null,
    p.telemetry ? `Performance and diagnostics (only after you click "Accept all"): page-load timings, Core Web Vitals, API timings and failures, live-connection status, script errors, long tasks, memory use, network type, screen and window size, language, time zone, browser and OS, and a random per-tab session ID. Not linked to your account; IP addresses are truncated (last IPv4 octet removed). Purpose: find and fix faults, improve speed. Basis: consent (Art. 6(1)(a); Art. 5(3) ePrivacy Directive). Kept ${p.telemetry_days} days. You can withdraw consent at any time via "Cookie settings".` : null,
    "Server logs: the web server may briefly log request time, IP and URL to keep the service running. Basis: legitimate interests (Art. 6(1)(f)).",
    p.ai ? `AI statement import (only when you upload a file and tick the consent box): the statement content is sent to the AI provider(s) ${p.ai.providers.join(", ")} to extract trades.${p.ai.redact ? " E-mail addresses, phone numbers, account/ID numbers, names and addresses are removed first." : ""} Files and results are processed in memory only, never written to the database, and cleared within 30 minutes; we keep only the time, file type and size, page count, usage and outcome for daily limits and cost tracking, deleted together with your account. Trades you confirm are handled as watchlist data. Basis: consent (Art. 6(1)(a)) and contract (Art. 6(1)(b)).` : null,
  ]],
  ["3. Cookies", [
    "Strictly necessary: zy_user (sign-in, 30 days), zy_consent (your cookie choice, 1 year). No consent required.",
    "Performance / diagnostics: only with your consent, see above.",
    p.ads ? "Advertising: third-party ads are enabled; ad providers may use cookies under their own policies, subject to consent where required." : null,
    p.turnstile ? "Bot protection: Cloudflare Turnstile may load during sign-up or sign-in to prevent automated abuse (legitimate interests)." : null,
  ]],
  ["4. Recipients and international transfers", [
    "We do not sell your personal data. Data is stored on this site's server.",
    "Processors: e-mail delivery provider" + (p.turnstile ? ", Cloudflare (bot protection)" : "") + (p.ads ? ", ad providers" : "") + (p.ai ? `, AI provider(s) ${p.ai.providers.join(", ")} (AI import only)` : "") + ". Transfers outside the EEA rely on adequacy decisions or Standard Contractual Clauses (Art. 46); AI providers may be located outside the EEA, which you are told about and explicitly consent to before uploading (Art. 49(1)(a)).",
    "Market data is fetched from public sources; none of your personal data is sent to them.",
  ]],
  ["5. Your rights", [
    "You have the right of access (Art. 15), rectification (Art. 16), erasure (Art. 17), restriction (Art. 18), data portability (Art. 20), to object to processing based on legitimate interests (Art. 21), and to withdraw consent at any time (Art. 7(3)).",
    "When signed in, use the account menu to \"Export my data\" (JSON) or \"Delete account\" (immediately erases your account, watchlist, trades and security log). For other requests e-mail us; we reply within one month.",
    "You may also lodge a complaint with the data protection authority of your EU member state.",
  ]],
  ["6. Retention", [
    "Account and watchlist data: until you delete your account.",
    p.login_log ? `Sign-in security log: ${p.login_log_days} days.` : null,
    p.telemetry ? `Diagnostics: ${p.telemetry_days} days.` : null,
  ]],
  ["7. Automated decisions", ["We make no automated decisions with legal or similarly significant effects. Risk flags are used only for alerts and manual review."]],
  ["8. Children", ["This site is not directed at anyone under 16."]],
  ["9. Changes", [`Last updated ${p.updated || "—"}. Material changes will be announced on the site.`]],
];

export default function privacyView(el) {
  const box = h("section", { class: "panel glass privacy" }, h("p", { class: "muted" }, "…"));
  el.append(box);
  api("/api/privacy").then((p) => {
    const zh = prefs.lang === "zh";
    const sections = (zh ? ZH : EN)(p);
    box.replaceChildren(
      h("h2", {}, zh ? "隐私政策" : "Privacy Policy"),
      h("p", { class: "muted small" }, zh ? "本政策依据欧盟《通用数据保护条例》（GDPR）编写。" : "This policy is written under the EU General Data Protection Regulation (GDPR)."),
      ...sections.map(([title, paras]) => h("div", {}, h("h3", {}, title), ...paras.filter(Boolean).map((x) => h("p", {}, x)))),
      p.extra ? h("div", {}, h("h3", {}, zh ? "补充条款" : "Additional terms"), ...p.extra.split(/\n+/).map((x) => h("p", {}, x))) : null,
    );
  }).catch(() => box.replaceChildren(h("p", { class: "empty" }, "—")));
}
