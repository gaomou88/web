import { computeSymbol, cashBalances, cpiFactor, deflator } from "../../../frontend/js/pnl.js";
import fs from "fs";
const cases = JSON.parse(fs.readFileSync("cases.json"));
let bad = 0;
const near = (a, b) => (a == null && b == null) || (a != null && b != null && Math.abs(a - b) <= 1e-6 * Math.max(1, Math.abs(a)));
for (const [i, c] of cases.entries()) {
  const js = computeSymbol(c.trades, c.q, { now: c.now, prev: c.prev, mode: c.mode }, c.base, "2026-10-20", c.cpi ? deflator(c.cpi, "2026-10-22") : null);
  for (const k of Object.keys(c.py)) if (!near(js[k], c.py[k])) { bad++; if (bad < 5) console.log("case", i, k, js[k], c.py[k]); }
  const cj = cashBalances(c.trades, c.moves, c.base);
  for (const k of new Set([...Object.keys(cj), ...Object.keys(c.pycash)])) if (!near(cj[k] ?? 0, c.pycash[k] ?? 0)) { bad++; if (bad < 5) console.log("cash", i, k, cj[k], c.pycash[k]); }
}
const cc = JSON.parse(fs.readFileSync("cpi_cases.json"));
for (const [d, n, f] of cc.factors) if (!near(cpiFactor(cc.table, d, n), f)) { bad++; console.log("cpi", d, n, cpiFactor(cc.table, d, n), f); }
console.log(bad ? `${bad} 处不一致` : `Python 与 JS 一致（${cases.length} 个随机用例）`);
