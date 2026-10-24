/* 持仓分析：AI 导入券商结单（上传 → 识别 → 逐条核对 → 选择美元来源 → 试算 → 导入；可整批撤销）。 */
import { api, fmt, h, toast, ui } from "../core.js";
import { prefs } from "../i18n.js";

const ZH = {
  title: "AI 导入券商结单", batches: "导入记录",
  intro: "上传券商的交易记录或月结单，AI 会识别出成交、股息、换汇等明细，你核对后一键导入。只需记录一次换汇，导入的每笔交易都会自动按你的换汇成本计算汇率盈亏。",
  types: "支持：文字版 PDF、Excel（.xlsx）、CSV", typesImg: "、截图 / 照片 / 扫描件（PNG、JPG）",
  pick: "选择文件", drop: "或把文件拖到这里（可一次选多个，例如几份日结单 + 月结单）", maxMb: "单个文件不超过 {n} MB，PDF 不超过 {p} 页",
  consent: "我同意把文件内容（已自动隐去姓名、地址、邮箱、手机号，账号和订单号换成代号）交给第三方 AI 服务（可能位于欧洲经济区以外）识别。文件不会保存，识别结果只用于本次导入。",
  dedupHint: "不用担心重复：已经记录过的交易（包括手动录入的）会按“同一天 + 同一股票 + 同一方向”对账后自动跳过，多次上传同一份或日结单、月结单混着传都只会导入一次。",
  tooMany: "一次最多 10 个文件", fileFailed: "{f}：{e}", continueRest: "继续导入其余文件", merging: "合并多个文件并去重",
  skipped: "已自动跳过 {n} 笔已经记录过的记录", showSkipped: "显示已跳过的", files: "文件", fileN: "文件 {n}",
  start: "开始识别", used: "今天已识别 {u} 次，每天最多 {n} 次",
  needConsent: "请先勾选同意", needFile: "请先选择文件", working: "正在识别", elapsed: "已用 {s} 秒", cancel: "取消",
  broker: "券商", period: "期间", stats: "{p} 页 · {m} · 用时 {s} 秒",
  modeText: "文字识别", modeVision: "图片识别",
  fxTitle: "这些美元是怎么来的？", fxRecords: "用我记录过的换汇：", fxRecordsHint: "{n} 笔，平均 1 美元 = {r} {c}（按每笔交易当天以前的换汇加权平均）",
  fxNone: "（还没有记录过换汇）", fxNew: "现在补记一笔换汇：", fxNewDate: "日期", fxNewFrom: "换出", fxNewTo: "得到美元",
  fxUsd: "不计算汇率盈亏（直接按美元记账）", fxStmt: "对账单里的换汇也会计入平均成本",
  trades: "成交", cash: "资金流水", positions: "期初持仓（可作为买入导入）", notes: "AI 的备注",
  colDate: "日期", colSym: "代码", colSide: "方向", colQty: "数量", colPrice: "价格 USD", colFee: "费用 USD", colRate: "成本汇率", colCheck: "检查",
  colType: "类型", colAmount: "金额", buy: "买入", sell: "卖出", all: "全选", none: "全不选",
  planning: "试算中…", planOk: "将导入 {t} 笔交易（买 {b} / 卖 {s}）、{c} 笔资金记录{n}", newSyms: "，新增股票 {s}",
  confirm: "确认导入", done: "已导入 {t} 笔交易、{c} 笔资金记录。可在“导入记录”里整批撤销。",
  nothing: "没有识别到可以导入的记录", rawTip: "原文", undo: "撤销这批", undone: "已撤销", undoConfirm: "撤销这次导入？这批导入的交易和资金记录会全部删除。",
  noBatches: "还没有导入过", typeNames: { deposit: "入金", withdrawal: "出金", dividend: "股息", interest: "利息", fee: "费用", tax: "税费", fx: "换汇", other: "其他" },
  borrowed: "早于第一笔换汇", errFix: "请修改或取消勾选标红的行", posDate: "买入日期",
};
const EN = {
  title: "AI statement import", batches: "Import history",
  intro: "Upload a broker trade report or monthly statement. AI extracts trades, dividends and FX conversions; you review and import them in one click. Record your currency conversion once and every imported trade gets its FX cost automatically.",
  types: "Supported: text PDF, Excel (.xlsx), CSV", typesImg: ", screenshots / photos / scans (PNG, JPG)",
  pick: "Choose files", drop: "or drop them here (several at once is fine, e.g. daily + monthly statements)", maxMb: "Up to {n} MB each; PDFs up to {p} pages",
  consent: "I agree to send the file content (names, addresses, emails and phone numbers removed; account and order numbers replaced by codes) to a third-party AI service (possibly outside the EEA) for extraction. Files are not stored.",
  dedupHint: "No double counting: trades you already have (including manual ones) are reconciled per day, symbol and side and skipped automatically, so re-uploading or mixing daily and monthly statements imports each trade once.",
  tooMany: "Up to 10 files at a time", fileFailed: "{f}: {e}", continueRest: "Continue with the other files", merging: "Merging files and removing duplicates",
  skipped: "{n} record(s) you already have were skipped", showSkipped: "Show skipped", files: "Files", fileN: "File {n}",
  start: "Extract", used: "Used {u} of {n} today",
  needConsent: "Please tick the consent box", needFile: "Please choose a file", working: "Extracting", elapsed: "{s}s", cancel: "Cancel",
  broker: "Broker", period: "Period", stats: "{p} page(s) · {m} · {s}s", modeText: "text", modeVision: "image",
  fxTitle: "Where did these US dollars come from?", fxRecords: "Use my recorded conversions:", fxRecordsHint: "{n} record(s), average 1 USD = {r} {c} (weighted by conversions up to each trade date)",
  fxNone: "(no conversions recorded yet)", fxNew: "Record a conversion now:", fxNewDate: "Date", fxNewFrom: "Paid", fxNewTo: "Received USD",
  fxUsd: "Ignore FX (book everything in USD)", fxStmt: "Conversions in the statement are included in the average",
  trades: "Trades", cash: "Cash", positions: "Opening positions (can be imported as buys)", notes: "AI notes",
  colDate: "Date", colSym: "Symbol", colSide: "Side", colQty: "Qty", colPrice: "Price USD", colFee: "Fees USD", colRate: "FX cost", colCheck: "Checks",
  colType: "Type", colAmount: "Amount", buy: "Buy", sell: "Sell", all: "All", none: "None",
  planning: "Checking…", planOk: "{t} trades (buy {b} / sell {s}) and {c} cash records will be imported{n}", newSyms: "; new watchlist symbols: {s}",
  confirm: "Import", done: "Imported {t} trades and {c} cash records. You can undo them in Import history.",
  nothing: "Nothing importable was found", rawTip: "Source", undo: "Undo", undone: "Undone", undoConfirm: "Undo this import? All trades and cash records of this batch will be deleted.",
  noBatches: "No imports yet", typeNames: { deposit: "Deposit", withdrawal: "Withdrawal", dividend: "Dividend", interest: "Interest", fee: "Fee", tax: "Tax", fx: "FX", other: "Other" },
  borrowed: "before first conversion", errFix: "Fix or untick the rows marked red", posDate: "Buy date",
};
const L = () => (prefs.lang === "zh" ? ZH : EN);
const fill = (s, o) => s.replace(/\{(\w+)\}/g, (_, k) => (o[k] ?? ""));

function modal(title, wide = true) {
  const dlg = h("dialog", { class: `glass pf-dialog${wide ? " imp-dialog" : ""}` });
  const body = h("div", { class: "dialog-form" });
  dlg.append(h("div", { class: "dialog-form" }, h("div", { class: "row" }, h("h2", {}, title), h("span", { class: "spacer" }),
    h("button", { class: "btn", onclick: () => dlg.close() }, prefs.lang === "zh" ? "关闭" : "Close")), body));
  dlg.addEventListener("close", () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
  return { dlg, body };
}

/** ctx: { reload(), ccyLabel(c) } */
export async function openImport(ctx) {
  const l = L();
  let cfg;
  try { cfg = await api("/api/portfolio/import/config"); } catch (e) { toast(e.message); return; }
  if (!cfg.enabled) { toast(prefs.lang === "zh" ? "网站暂未开启 AI 导入" : "AI import is not enabled"); return; }
  if (cfg.members_only && !cfg.allowed) { ui.onLocked?.(); return; }
  const { dlg, body } = modal(l.title);
  let polling = true;
  dlg.addEventListener("close", () => { polling = false; });

  /* ---------- 第一步：上传 ---------- */
  const file = h("input", { type: "file", multiple: true, accept: [".pdf", ".xlsx", ".csv", ".txt", ".htm", ".html", ...(cfg.vision ? [".png", ".jpg", ".jpeg", ".webp"] : [])].join(","), style: { display: "none" } });
  const fname = h("span", { class: "muted small" });
  const agree = h("input", { type: "checkbox" });
  const err = h("div", { class: "err", role: "alert" });
  let chosen = [];
  const choose = (list) => {
    chosen = [...list].slice(0, 10);
    fname.textContent = chosen.map((f) => `${f.name}（${fmt(f.size / 1024, 0)} KB）`).join("、");
    err.textContent = list.length > 10 ? l.tooMany : "";
  };
  file.addEventListener("change", () => choose(file.files));
  const drop = h("div", { class: "imp-drop", onclick: () => file.click() },
    h("button", { class: "btn primary", type: "button" }, l.pick), h("span", { class: "muted small" }, l.drop), fname);
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); choose(e.dataTransfer.files); });
  const startBtn = h("button", { class: "btn primary", type: "button", onclick: () => upload() }, l.start);
  body.append(...[
    h("p", { class: "muted small", style: { margin: 0 } }, l.intro),
    h("p", { class: "small", style: { margin: 0 } }, l.types + (cfg.vision ? l.typesImg : ""), "。", fill(l.maxMb, { n: cfg.max_mb, p: cfg.max_pages })),
    drop, file,
    h("p", { class: "muted small", style: { margin: 0 } }, l.dedupHint),
    h("label", { class: "imp-consent small" }, agree, h("span", {}, l.consent)),
    cfg.daily_limit ? h("p", { class: "muted small", style: { margin: 0 } }, fill(l.used, { u: cfg.used_today, n: cfg.daily_limit })) : null,
    err,
    h("div", { class: "row" }, h("span", { class: "spacer" }), startBtn)].filter(Boolean));

  async function uploadOne(f) {
    let res;
    try {
      res = await fetch(`/api/portfolio/import/upload?consent=1&name=${encodeURIComponent(f.name.slice(0, 80))}`, { method: "POST", credentials: "same-origin", body: f,
        headers: { "X-Requested-With": "zyll", "Content-Type": f.type || "application/octet-stream" } });
    } catch { return { error: prefs.lang === "zh" ? "网络连接失败，请稍后重试" : "Network error" }; }
    const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
    if (res.status === 403 && data?.detail === "members_only") return { locked: true };
    if (!res.ok) return { error: data?.detail || (res.status === 413 ? (prefs.lang === "zh" ? "文件太大：超过了服务器（或反向代理）允许的上传大小" : "File too large for the server or its proxy") : `HTTP ${res.status}`) };
    return { job: data.job };
  }

  async function upload() {
    if (!chosen.length) { err.textContent = l.needFile; return; }
    if (!agree.checked) { err.textContent = l.needConsent; return; }
    const big = chosen.find((f) => f.size > cfg.max_mb * 1048576);
    if (big) { err.textContent = `${big.name}：${fill(l.maxMb, { n: cfg.max_mb, p: cfg.max_pages })}`; return; }
    startBtn.disabled = true; err.textContent = "";
    // 服务器同时最多识别 3 个文件：分批上传，前一批开始后再传下一批
    const items = chosen.map((f) => ({ name: f.name, file: f, job: null, error: null, status: "queued", step: "" }));
    waitJobs(items);
  }

  /* ---------- 第二步：等待识别 ---------- */
  async function waitJobs(items) {
    const t0 = Date.now();
    const list = h("div", { class: "imp-wait-list small" });
    const timeEl = h("span", { class: "muted small" });
    body.replaceChildren(h("div", { class: "imp-wait" }, h("div", { class: "spinner", "aria-hidden": "true" }), h("div", {}, h("div", {}, `${l.working}`), timeEl)), list,
      h("div", { class: "row" }, h("span", { class: "spacer" }), h("button", { class: "btn", onclick: () => dlg.close() }, l.cancel)));
    const draw = () => {
      timeEl.textContent = fill(l.elapsed, { s: Math.round((Date.now() - t0) / 1000) });
      list.replaceChildren(...items.map((it) => h("div", { class: `imp-wait-item ${it.status}` },
        h("span", {}, it.name), " — ", h("b", {}, it.error ? it.error : it.status === "done" ? "✓" : it.step || "…"))));
    };
    while (polling) {
      const running = items.filter((it) => it.status === "running").length;
      for (const it of items.filter((x) => x.status === "queued").slice(0, Math.max(0, 3 - running))) {
        it.status = "running"; it.step = prefs.lang === "zh" ? "上传中" : "uploading"; draw();
        const r = await uploadOne(it.file);
        if (r.locked) { dlg.close(); ui.onLocked?.(); return; }
        if (r.error) { it.status = "failed"; it.error = r.error; } else it.job = r.job;
      }
      for (const it of items.filter((x) => x.status === "running" && x.job)) {
        try {
          const j = await api(`/api/portfolio/import/job/${encodeURIComponent(it.job)}`);
          it.step = j.step;
          if (j.status === "done") { it.status = "done"; it.result = j.result; }
          if (j.status === "failed") { it.status = "failed"; it.error = j.error; }
        } catch (e) { it.status = "failed"; it.error = e.message; }
      }
      draw();
      if (items.every((it) => it.status === "done" || it.status === "failed")) break;
      await new Promise((r) => setTimeout(r, 1500));
    }
    if (!polling) return;
    const ok = items.filter((it) => it.status === "done");
    const bad = items.filter((it) => it.status === "failed");
    const proceed = async () => {
      if (ok.length === 1) { review(ok[0].result, ok[0].job); return; }
      body.replaceChildren(h("div", { class: "imp-wait" }, h("div", { class: "spinner", "aria-hidden": "true" }), h("div", {}, l.merging)));
      try {
        const m = await api("/api/portfolio/import/merge", { method: "POST", body: { jobs: ok.map((it) => it.job) } });
        review(m.result, m.job);
      } catch (e) { body.replaceChildren(h("div", { class: "err" }, e.message)); }
    };
    if (!bad.length) { proceed(); return; }
    body.replaceChildren(...bad.map((it) => h("div", { class: "err" }, fill(l.fileFailed, { f: it.name, e: it.error }))),
      h("div", { class: "row" }, h("span", { class: "spacer" }),
        h("button", { class: "btn", onclick: () => { dlg.close(); openImport(ctx); } }, prefs.lang === "zh" ? "重新上传" : "Try again"),
        ok.length ? h("button", { class: "btn primary", onclick: proceed }, l.continueRest) : null));
  }

  /* ---------- 第三步：核对 ---------- */
  function review(r, job) {
    const trades = r.trades.map((x) => ({ ...x }));
    const cash = r.cash.map((x) => ({ ...x }));
    const positions = r.positions.map((x) => ({ ...x, date: x.as_of || dayBefore(r.period_start) || "" }));
    if (!trades.length && !cash.length && !positions.length) {
      body.replaceChildren(h("p", {}, l.nothing), ...(r.notes || []).map((n) => h("p", { class: "muted small" }, n)));
      return;
    }
    // —— 美元来源 ——
    const pools = cfg.fx_pools || {};
    const stmtFxFrom = [...new Set(cash.filter((c) => c.type === "fx" && c.to_currency === "USD" && c.selected).map((c) => c.from_currency))];
    const poolCcys = [...new Set([...Object.keys(pools), ...stmtFxFrom])];
    const fx = {
      mode: cfg.base === "USD" ? "usd" : poolCcys.length ? "records" : "new",
      ccy: poolCcys.includes(cfg.base) ? cfg.base : poolCcys[0] || (cfg.base !== "USD" ? cfg.base : "CNY"),
      new: { date: firstTradeDate(trades) || new Date().toISOString().slice(0, 10), from_amount: "", to_amount: "" },
    };
    const ccySel = (v, on) => h("select", { onchange: (e) => on(e.target.value) }, cfg.currencies.filter((c) => c !== "USD").map((c) => h("option", { value: c, selected: c === v }, ctx.ccyLabel(c))));
    const radio = (mode, ...kids) => h("label", { class: "imp-fx-opt" }, h("input", { type: "radio", name: "fxmode", checked: fx.mode === mode, onchange: () => { fx.mode = mode; drawFx(); replan(); } }), h("span", {}, ...kids));
    const fxBox = h("div", { class: "imp-fx" });
    function drawFx() {
      const p = pools[fx.ccy];
      const recHint = p ? fill(l.fxRecordsHint, { n: p.records, r: fmt(p.rate, 4), c: fx.ccy }) : l.fxNone;
      const num = (k, ph) => h("input", { type: "number", step: "any", min: 0, value: fx.new[k], placeholder: ph, oninput: (e) => { fx.new[k] = e.target.value; replan(); } });
      fxBox.replaceChildren(h("b", {}, l.fxTitle),
        radio("records", l.fxRecords, " ", ccySel(fx.ccy, (c) => { fx.ccy = c; drawFx(); replan(); }), h("span", { class: "muted small" }, " ", recHint, stmtFxFrom.length ? `；${l.fxStmt}` : "")),
        radio("new", l.fxNew, " ", h("span", { class: "imp-inline" }, l.fxNewDate, h("input", { type: "date", value: fx.new.date, oninput: (e) => { fx.new.date = e.target.value; replan(); } }),
          l.fxNewFrom, ccySel(fx.ccy, (c) => { fx.ccy = c; drawFx(); replan(); }), num("from_amount", "71000"), l.fxNewTo, num("to_amount", "10000"),
          fx.new.from_amount > 0 && fx.new.to_amount > 0 ? h("span", { class: "muted small" }, `1 USD = ${fmt(fx.new.from_amount / fx.new.to_amount, 4)} ${fx.ccy}`) : null)),
        radio("usd", l.fxUsd));
    }
    drawFx();

    // —— 表格 ——
    const planEl = h("div", { class: "imp-plan small" });
    const commitBtn = h("button", { class: "btn primary", disabled: true, onclick: () => commit() }, l.confirm);
    let lastPlan = null;
    const rateCells = new Map(), errCells = new Map();
    const inp = (row, k, type = "text", w = 90) => h("input", { type, step: "any", value: row[k] ?? "", style: { width: `${w}px` },
      oninput: (e) => { row[k] = type === "number" ? Number(e.target.value) : type === "date" ? e.target.value : e.target.value.trim().toUpperCase(); replan(); } });
    const issueList = (row) => h("div", { class: "imp-issues" }, ...(row.issues || []).map((x) => h("div", { class: `issue ${x.level}` }, x.msg)));
    const check = (row) => h("input", { type: "checkbox", checked: !!row.selected, onchange: (e) => { row.selected = e.target.checked; replan(); } });
    const rawTip = (row) => (row.raw || multi ? h("span", { class: "imp-raw", title: `${multi ? `${fill(l.fileN, { n: (row.file || 0) + 1 })} ${r.files[row.file || 0]?.name || ""}\n` : ""}${row.raw ? `${l.rawTip}：${row.raw}` : ""}` }, "ⓘ") : null);

    const multi = (r.files || []).length > 1;
    const skippedRow = (x) => x.dup && (x.issues || []).some((i) => i.code === "duplicate" || i.code === "dup_file");
    const tradeRows = trades.map((t) => {
      const rate = h("td", { class: "num small" }), errc = h("div", { class: "issue error" });
      rateCells.set(t.key, rate); errCells.set(t.key, errc);
      return h("tr", { class: `${t.issues.some((x) => x.level === "error") ? "imp-bad" : ""}${skippedRow(t) ? " imp-skipped" : ""}` },
        h("td", {}, check(t)), h("td", {}, inp(t, "date", "date", 130)), h("td", {}, inp(t, "symbol", "text", 70), rawTip(t)),
        h("td", {}, h("select", { onchange: (e) => { t.side = e.target.value; replan(); } }, ["buy", "sell"].map((s) => h("option", { value: s, selected: t.side === s }, l[s])))),
        h("td", {}, inp(t, "shares", "number", 80)), h("td", {}, inp(t, "price", "number", 90)), h("td", {}, inp(t, "fee", "number", 70)),
        rate, h("td", {}, issueList(t), errc));
    });
    const allBox = (list) => h("span", { class: "row small" }, h("button", { class: "linkbtn", type: "button", onclick: () => { list.forEach((x) => { if (!x.dup && !(x.issues || []).some((i) => i.level === "error")) x.selected = true; }); review2(); } }, l.all), " / ",
      h("button", { class: "linkbtn", type: "button", onclick: () => { list.forEach((x) => (x.selected = false)); review2(); } }, l.none));
    function review2() { // 全选 / 全不选后同步勾选框
      body.querySelectorAll("input[type=checkbox][data-k]").forEach((cb) => { const row = [...trades, ...cash, ...positions].find((x) => x.key === cb.dataset.k); if (row) cb.checked = !!row.selected; });
      replan();
    }
    const cashRows = cash.map((c) => {
      const errc = h("div", { class: "issue error" });
      errCells.set(c.key, errc);
      const what = c.type === "fx" ? `${fmt(c.from_amount, 2)} ${c.from_currency} → ${fmt(c.to_amount, 2)} ${c.to_currency}` : `${fmt(c.amount, 2)} ${c.currency}`;
      return h("tr", { class: skippedRow(c) ? "imp-skipped" : "" }, h("td", {}, check(c)), h("td", {}, c.date), h("td", {}, l.typeNames[c.type] || c.type, rawTip(c)), h("td", { class: "num" }, what), h("td", {}, issueList(c), errc));
    });
    const posRows = positions.map((p) => {
      const errc = h("div", { class: "issue error" });
      errCells.set(p.key, errc);
      return h("tr", {}, h("td", {}, check(p)), h("td", {}, inp(p, "date", "date", 130)), h("td", {}, p.symbol), h("td", { class: "num" }, fmt(p.shares, 4)),
        h("td", { class: "num" }, p.price ? `$${fmt(p.price, 4)}` : "—"), h("td", {}, issueList(p), errc));
    });
    // 给勾选框打标记，便于全选
    [...tradeRows, ...cashRows, ...posRows].forEach((tr, i) => { const row = [...trades, ...cash, ...positions][i]; tr.querySelector("input[type=checkbox]").dataset.k = row.key; });

    const table = (head, rows) => h("div", { class: "table-wrap" }, h("table", { class: "imp-table" }, h("thead", {}, h("tr", {}, head.map((x) => h("th", {}, x)))), h("tbody", {}, rows)));
    const s = r.stats || {};
    const wrap = h("div", { class: "imp-tables hide-skipped" });
    const nSkip = [...trades, ...cash].filter(skippedRow).length;
    const skipBar = nSkip ? h("label", { class: "imp-skipbar small" }, h("input", { type: "checkbox", onchange: (e) => wrap.classList.toggle("hide-skipped", !e.target.checked) }),
      h("span", {}, fill(l.skipped, { n: nSkip }), "　", l.showSkipped)) : null;
    wrap.append(...[
      trades.length ? h("div", { class: "row" }, h("b", {}, `${l.trades}（${trades.length}）`), allBox(trades)) : null,
      trades.length ? table(["", l.colDate, l.colSym, l.colSide, l.colQty, l.colPrice, l.colFee, l.colRate, l.colCheck], tradeRows) : null,
      cash.length ? h("div", { class: "row" }, h("b", {}, `${l.cash}（${cash.length}）`), allBox(cash)) : null,
      cash.length ? table(["", l.colDate, l.colType, l.colAmount, l.colCheck], cashRows) : null,
      positions.length ? h("b", {}, l.positions) : null,
      positions.length ? table(["", l.posDate, l.colSym, l.colQty, `${l.colPrice}`, l.colCheck], posRows) : null].filter(Boolean));
    const modeName = (m) => (m || "text").split("+").map((x) => (x === "vision" ? l.modeVision : l.modeText)).join(" + ");
    body.replaceChildren(...[
      h("div", { class: "row small muted" }, r.broker ? `${l.broker}：${r.broker}` : "", r.period_start || r.period_end ? `　${l.period}：${r.period_start || "?"} ~ ${r.period_end || "?"}` : "",
        h("span", { class: "spacer" }), fill(l.stats, { p: s.pages || 1, m: modeName(s.mode), s: s.seconds })),
      multi ? h("div", { class: "small muted" }, `${l.files}：`, r.files.map((f, i) => `${i + 1}. ${f.name || "?"}${f.period_start ? `（${f.period_start} ~ ${f.period_end || "?"}）` : ""}`).join("　")) : null,
      fxBox,
      skipBar,
      wrap,
      r.notes?.length ? h("div", { class: "imp-notes" }, h("b", { class: "small" }, l.notes), ...r.notes.map((n) => h("div", { class: "muted small" }, `· ${n}`))) : null,
      planEl,
      h("div", { class: "row" }, h("span", { class: "spacer" }), commitBtn)].filter(Boolean));

    function payload() {
      return {
        source: r.broker || "", job,
        // 预览判为重复 / 对不上的行由用户自己勾选 = 确认导入
        trades: [...trades.filter((t) => t.selected).map((t) => ({ key: t.key, date: t.date, symbol: t.symbol, side: t.side, shares: t.shares, price: t.price, fee: t.fee || 0,
          ext_id: t.ext_id || "", time: t.time || "", confirm_dup: !!t.dup })),
          ...positions.filter((p) => p.selected).map((p) => ({ key: p.key, date: p.date, symbol: p.symbol, side: "buy", shares: p.shares, price: p.price, fee: 0, note: prefs.lang === "zh" ? "期初持仓" : "opening position" }))],
        cash: cash.filter((c) => c.selected).map((c) => ({ key: c.key, date: c.date, type: c.type, currency: c.currency, amount: c.amount,
          from_currency: c.from_currency, from_amount: c.from_amount, to_currency: c.to_currency, to_amount: c.to_amount, confirm_dup: !!c.dup, note: r.broker ? `${l.typeNames[c.type] || ""}（${r.broker}）` : "" })),
        fx: { mode: fx.mode, ccy: fx.ccy, new: fx.new },
      };
    }
    let timer = null, seq = 0;
    function replan() {
      clearTimeout(timer);
      commitBtn.disabled = true;
      planEl.className = "imp-plan small muted"; planEl.textContent = l.planning;
      timer = setTimeout(async () => {
        const my = ++seq;
        errCells.forEach((c) => (c.textContent = "")); rateCells.forEach((c) => (c.textContent = ""));
        let p;
        try {
          p = await api("/api/portfolio/import/plan", { method: "POST", body: payload() });
        } catch (e) {
          if (my !== seq) return;
          planEl.className = "imp-plan small err"; planEl.textContent = e.message;
          for (const [k, msg] of Object.entries(e.data?.errors || {})) errCells.get(k) && (errCells.get(k).textContent = msg);
          return;
        }
        if (my !== seq) return;
        lastPlan = p;
        for (const t of p.trades) {
          const c = rateCells.get(t.key);
          if (c) c.textContent = t.ccy === "USD" ? "—" : `${fmt(t.fx, 4)}${t.rate_note ? `（${l.borrowed}）` : ""}`;
        }
        for (const [k, msg] of Object.entries(p.errors || {})) errCells.get(k) && (errCells.get(k).textContent = msg);
        const sm = p.summary;
        const lines = [fill(l.planOk, { t: sm.trades, b: sm.buys, s: sm.sells, c: sm.cash, n: p.new_symbols.length ? fill(l.newSyms, { s: p.new_symbols.join("、") }) : "" })];
        planEl.className = `imp-plan small ${p.ok ? "" : "err"}`;
        planEl.replaceChildren(...lines.map((x) => h("div", {}, x)), ...(p.ok ? [] : [h("div", {}, l.errFix)]), ...p.notes.map((n) => h("div", { class: "muted" }, `⚠ ${n}`)));
        commitBtn.disabled = !p.ok || !(sm.trades + sm.cash);
        commitBtn.textContent = `${l.confirm}（${sm.trades + sm.cash}）`;
      }, 500);
    }
    async function commit() {
      commitBtn.disabled = true;
      try {
        const res = await api("/api/portfolio/import/commit", { method: "POST", body: payload() });
        toast(fill(l.done, { t: res.summary.trades, c: res.summary.cash }), 6000);
        dlg.close();
        ctx.reload();
      } catch (e) {
        planEl.className = "imp-plan small err"; planEl.textContent = e.message;
        for (const [k, msg] of Object.entries(e.data?.errors || {})) errCells.get(k) && (errCells.get(k).textContent = msg);
      }
    }
    replan();
  }
}

export async function openBatches(ctx) {
  const l = L();
  const { body } = modal(l.batches, false);
  async function draw() {
    let d;
    try { d = await api("/api/portfolio/import/batches"); } catch (e) { body.replaceChildren(h("div", { class: "err" }, e.message)); return; }
    body.replaceChildren(d.batches.length ? h("div", { class: "table-wrap" }, h("table", {}, h("tbody", {}, d.batches.map((b) => h("tr", {},
      h("td", { class: "small muted" }, new Date(b.created_at * 1000).toLocaleString(prefs.lang === "zh" ? "zh-CN" : "en-US", { hour12: false })),
      h("td", {}, b.source || "—", b.period_start ? h("div", { class: "muted small" }, `${b.period_start} ~ ${b.period_end}`) : null),
      h("td", { class: "small" }, `${b.trades} / ${b.cash}`, b.skipped ? h("div", { class: "muted small" }, prefs.lang === "zh" ? `跳过重复 ${b.skipped}` : `${b.skipped} skipped`) : null),
      h("td", {}, b.undone ? h("span", { class: "muted small" }, l.undone) : h("button", { class: "btn danger", onclick: async () => {
        if (!confirm(l.undoConfirm)) return;
        try { await api(`/api/portfolio/import/batches/${encodeURIComponent(b.id)}`, { method: "DELETE" }); toast(l.undone); ctx.reload(); draw(); } catch (e) { toast(e.message, 6000); }
      } }, l.undo))))))) : h("p", { class: "muted" }, l.noBatches));
  }
  draw();
}

function dayBefore(d) {
  if (!d) return "";
  const t = new Date(`${d}T12:00:00Z`);
  t.setUTCDate(t.getUTCDate() - 1);
  return t.toISOString().slice(0, 10);
}
function firstTradeDate(trades) {
  return trades.map((t) => t.date).filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d)).sort()[0];
}

