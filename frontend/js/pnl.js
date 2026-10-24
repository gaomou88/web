/**
 * 连汇盈亏计算（纯函数，无副作用）。
 *
 * 约定：
 * - 股价、手续费以美元计；汇率 fx 表示“1 美元 = 多少本币”。
 * - 成本采用加权平均法：每次买入把（股数×价格+手续费）按当时汇率折成本币计入成本；
 *   卖出时按平均成本结转，差额计入已实现盈亏。
 * - 持仓盈亏拆分：
 *     股价部分 = (市值USD − 成本USD) × 平均成本汇率
 *     汇率部分 = 市值USD × (现汇率 − 平均成本汇率)
 *   两部分相加正好等于 市值本币 − 成本本币。
 * - 今日盈亏 = 现市值本币 + 今日卖出所得本币 − 今日买入花费本币 − 昨收市值本币；
 *   其中汇率部分 = 现市值USD × (现汇率 − 今日参考汇率)，参考汇率由“昨日收盘汇率”和“今日买入的成交汇率”按股数加权。
 * - 每笔交易有自己的货币对（USD/该笔资金的货币）。同一股票按货币分组各自计算（卖出只冲减同一货币买入的持股），
 *   再按当前交叉汇率折算成用户的本币汇总。
 * - 扣除通胀（可选）：每笔成本、卖出所得按付款货币所在地的物价指数折算成今天的购买力（见 cpiFactor），
 *   实际盈亏 = 市值 − 按今天购买力计算的成本。今日盈亏不受影响。
 * - 不计汇率（可选）：持仓盈亏取股价部分 unrealPrice，已实现取 realizedPrice（按平均成本汇率换算，不含汇率变化），今日取 todayPrice。
 */

const dayNum = (d) => Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10)) / 86400000;

/** 月度物价指数表 [[YYYY-MM, 指数], ...] 在某一天的值：每月 15 日为该月的值，之间按天线性插值，两端取端点。 */
export function cpiIndexAt(table, day) {
  if (!table || !table.length) return null;
  const x = dayNum(day);
  const pts = table.map(([m, v]) => [dayNum(`${m}-15`), Number(v)]);
  if (x <= pts[0][0]) return pts[0][1];
  if (x >= pts[pts.length - 1][0]) return pts[pts.length - 1][1];
  let lo = 0, hi = pts.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (pts[mid][0] <= x) lo = mid; else hi = mid; }
  const [x0, y0] = pts[lo], [x1, y1] = pts[hi];
  return y0 + ((y1 - y0) * (x - x0)) / (x1 - x0);
}

/** day 那天的 1 元相当于 nowDay 的多少元（物价上涨 → 大于 1）。没有数据时为 1。 */
export function cpiFactor(table, day, nowDay) {
  const a = cpiIndexAt(table, day), b = cpiIndexAt(table, nowDay);
  return a && b ? b / a : 1;
}

/** 按货币返回折算函数：deflator(tables, 今天)(货币)(日期)。tables: { 货币: { table } } */
export function deflator(tables, nowDay) {
  return (ccy) => {
    const t = tables?.[ccy];
    const table = Array.isArray(t) ? t : t?.table;
    if (!table || !table.length) return null;
    return (day) => cpiFactor(table, day, nowDay);
  };
}

/** 由人民币报价换算“1 美元 = 多少本币”。mode: mid 中间价 / bid 卖出美元可得价（更保守）。 */
export function usdTo(rates, ccy, mode = "mid") {
  if (!rates) return null;
  if (ccy === "USD") return 1;
  const usd = rates.USD, base = rates[ccy];
  if (!usd || !base) return null;
  if (mode === "bid") return usd.bid / base.ask;
  return ((usd.bid + usd.ask) / 2) / ((base.bid + base.ask) / 2);
}

export function computePosition(trades, quote, fxNow, fxPrev, sessionDate, deflate = null) {
  const list = [...trades].sort((a, b) => (a.trade_date < b.trade_date ? -1 : a.trade_date > b.trade_date ? 1 : a.id - b.id));
  let qty = 0, costUsd = 0, costBase = 0, costUsdR = 0, costBaseR = 0, realized = 0, realizedPrice = 0;
  let todayBuyQty = 0, todayBuyFxQty = 0, todayBuyCost = 0, todaySellProceeds = 0;
  let qtyAtPrevClose = 0;

  for (const t of list) {
    const today = t.trade_date >= sessionDate;
    if (!today) qtyAtPrevClose = qty;
    const d = deflate ? deflate(t.trade_date) : 1;
    if (t.side === "buy") {
      const usd = t.shares * t.price + (t.fee || 0);
      qty += t.shares; costUsd += usd; costBase += usd * t.fx;
      costUsdR += usd * d; costBaseR += usd * t.fx * d;
      if (today) { todayBuyQty += t.shares; todayBuyFxQty += t.shares * t.fx; todayBuyCost += usd * t.fx; }
    } else {
      if (qty <= 0) continue;
      const q = Math.min(t.shares, qty);
      const avgUsd = costUsd / qty, avgBase = costBase / qty, avgUsdR = costUsdR / qty, avgBaseR = costBaseR / qty;
      const avgFx = costUsd ? costBase / costUsd : t.fx;
      const proceedsUsd = q * t.price - (t.fee || 0);
      const proceedsBase = proceedsUsd * t.fx;
      realized += proceedsBase * d - q * avgBaseR;
      realizedPrice += (proceedsUsd * d - q * avgUsdR) * avgFx;
      costUsd -= q * avgUsd; costBase -= q * avgBase; qty -= q;
      costUsdR -= q * avgUsdR; costBaseR -= q * avgBaseR;
      if (today) todaySellProceeds += proceedsBase;
    }
    if (!today) qtyAtPrevClose = qty;
  }
  if (qty < 1e-9) { qty = 0; costUsd = 0; costBase = 0; costUsdR = 0; costBaseR = 0; }

  const price = quote?.price ?? null;
  const prevClose = quote?.prev_close ?? price;
  const fxP = fxPrev ?? fxNow;
  const out = {
    qty, costUsd, costBase, costReal: costBaseR, realized, realizedPrice,
    avgUsd: qty ? costUsd / qty : null,
    avgFx: costUsd ? costBase / costUsd : null,
    price, prevClose,
    dayChangePct: price != null && prevClose ? (price / prevClose - 1) * 100 : null,
    mvUsd: null, mvBase: null, unreal: null, unrealPct: null, unrealPrice: null, unrealFx: null,
    today: null, todayPrice: null, todayFx: null, fxPrevMissing: fxPrev == null,
  };
  if (price == null || fxNow == null) return out;

  out.mvUsd = qty * price;
  out.mvBase = out.mvUsd * fxNow;
  if (qty) {
    out.unreal = out.mvBase - costBaseR;
    out.unrealPct = costBaseR ? (out.unreal / costBaseR) * 100 : null;
    out.unrealPrice = (out.mvUsd - costUsdR) * out.avgFx;
    out.unrealFx = out.unreal - out.unrealPrice;
  } else {
    out.unreal = out.unrealPrice = out.unrealFx = 0;
  }

  const prevValue = qtyAtPrevClose * (prevClose ?? price) * fxP;
  out.today = out.mvBase + todaySellProceeds - todayBuyCost - prevValue;
  const keptFromPrev = Math.max(0, qty - todayBuyQty);
  const refFx = qty ? (keptFromPrev * fxP + Math.min(todayBuyQty, qty) * (todayBuyQty ? todayBuyFxQty / todayBuyQty : fxP)) / qty : fxP;
  out.todayFx = out.mvUsd * (fxNow - refFx);
  out.todayPrice = out.today - out.todayFx;
  return out;
}

const SUM_KEYS = ["qty", "costUsd", "costBase", "costReal", "realized", "realizedPrice", "mvUsd", "mvBase", "unreal", "unrealPrice", "unrealFx", "today", "todayPrice", "todayFx"];
const SCALE_KEYS = new Set(["costBase", "costReal", "realized", "realizedPrice", "mvBase", "unreal", "unrealPrice", "unrealFx", "today", "todayPrice", "todayFx"]);

/**
 * 一只股票的持仓（可能由多种货币买入）。
 * fx: { now, prev, mode } —— now/prev 为外汇交易中心报价表；base 为本币。
 * deflate：deflator(...) 的返回值（扣除通胀时传入），按每组的付款货币取折算函数。
 */
export function computeSymbol(trades, quote, fx, base, sessionDate, deflate = null) {
  const groups = new Map();
  for (const t of trades) {
    const c = t.ccy || base;
    if (!groups.has(c)) groups.set(c, []);
    groups.get(c).push(t);
  }
  const toBaseNow = usdTo(fx.now, base, fx.mode);
  const parts = [];
  for (const [c, list] of groups) {
    const now = usdTo(fx.now, c, fx.mode);
    const prev = usdTo(fx.prev, c, fx.mode);
    const p = computePosition(list, quote, now, prev, sessionDate, deflate ? deflate(c) : null);
    const k = now && toBaseNow ? toBaseNow / now : (c === base ? 1 : null);  // 该货币 → 本币
    parts.push({ ccy: c, p, k });
  }
  const price = quote?.price ?? null;
  const prevClose = quote?.prev_close ?? price;
  const out = {
    price, prevClose, ccys: parts.map((x) => x.ccy), parts,
    dayChangePct: price != null && prevClose ? (price / prevClose - 1) * 100 : null,
    fxPrevMissing: fx.prev == null,
  };
  for (const key of SUM_KEYS) {
    let sum = 0, any = false;
    for (const { p, k } of parts) {
      const v = p[key];
      if (v == null) continue;
      if (SCALE_KEYS.has(key)) { if (k == null) continue; sum += v * k; } else sum += v;
      any = true;
    }
    out[key] = any ? sum : (parts.length ? null : 0);
  }
  if (!parts.length) Object.assign(out, { qty: 0, costUsd: 0, costBase: 0, costReal: 0, realized: 0, realizedPrice: 0, mvUsd: price != null ? 0 : null, mvBase: price != null ? 0 : null });
  out.avgUsd = out.qty ? out.costUsd / out.qty : null;
  out.unrealPct = out.qty && out.costReal ? (out.unreal / out.costReal) * 100 : null;
  // 只有一种货币时显示平均成交汇率
  out.avgFx = parts.length === 1 ? parts[0].p.avgFx : null;
  return out;
}

export function totals(positions) {
  const sum = (k) => positions.reduce((a, p) => a + (p[k] ?? 0), 0);
  const cost = sum("costBase"), costReal = sum("costReal");
  const unreal = sum("unreal");
  return {
    mvBase: sum("mvBase"), costBase: cost, costReal, unreal, unrealPct: costReal ? (unreal / costReal) * 100 : null,
    unrealPrice: sum("unrealPrice"), unrealFx: sum("unrealFx"),
    today: sum("today"), todayPrice: sum("todayPrice"), todayFx: sum("todayFx"), realized: sum("realized"), realizedPrice: sum("realizedPrice"),
  };
}

/** 按“是否计入汇率”取要显示的盈亏：fx = true 用含汇率的数，false 用只含股价的数。 */
export function pick(p, includeFx) {
  if (!p) return { unreal: null, realized: null, today: null, total: null };
  const unreal = includeFx ? p.unreal : p.unrealPrice;
  const realized = includeFx ? p.realized : p.realizedPrice;
  const today = includeFx ? p.today : p.todayPrice;
  return { unreal, realized, today, total: unreal == null && realized == null ? null : (unreal ?? 0) + (realized ?? 0) };
}

/** 各币种现金：资金记录 + 买卖自动联动（买入从该笔货币对的现金扣除，卖出加回）。与后端 pnl.cash_balances 一致。 */
export function cashBalances(trades, moves, base, until = null) {
  const bal = {};
  for (const m of moves) {
    if (until && m.trade_date > until) continue;
    bal[m.ccy] = (bal[m.ccy] || 0) + m.amount;
  }
  for (const t of trades) {
    if (until && t.trade_date > until) continue;
    const fee = t.fee || 0;
    const usd = t.side === "buy" ? t.shares * t.price + fee : -(t.shares * t.price - fee);
    // funding = "usd"：用之前换好的美元，从美元现金扣（汇率只用于计算成本）；否则按成交汇率从该笔交易的货币扣
    const c = t.funding === "usd" ? "USD" : t.ccy || base;
    const amt = t.funding === "usd" ? usd : usd * t.fx;
    bal[c] = (bal[c] || 0) - amt;
  }
  for (const c of Object.keys(bal)) if (Math.abs(bal[c]) < 1e-9) delete bal[c];
  return bal;
}

/**
 * 总资本：各币种现金（按当前汇率折合本币）+ 美股持仓市值。
 * 占比按“资产合计”（正值之和）计算，现金为负（可能漏记入金）时单独标出，不会出现超过 100% 的占比。
 */
export function capital(trades, moves, rates, base, mode, stockValueBase) {
  const cash = cashBalances(trades, moves, base);
  const toBase = usdTo(rates, base, mode);
  const items = [];
  for (const [ccy, amount] of Object.entries(cash)) {
    const r = usdTo(rates, ccy, mode);
    const value = r && toBase ? (amount * toBase) / r : null;
    items.push({ kind: "cash", ccy, amount, value });
  }
  if (stockValueBase) items.push({ kind: "stocks", ccy: "USD", amount: null, value: stockValueBase });
  const gross = items.reduce((a, x) => a + (x.value > 0 ? x.value : 0), 0);
  const net = items.reduce((a, x) => a + (x.value ?? 0), 0);
  for (const x of items) x.pct = gross > 0 && x.value > 0 ? (x.value / gross) * 100 : null;
  items.sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity));
  return { items, gross, net, negative: items.filter((x) => x.value != null && x.value < 0), missingRate: items.filter((x) => x.value == null).map((x) => x.ccy) };
}
