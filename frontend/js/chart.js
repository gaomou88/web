/** 轻量 Canvas 图表：柱（左轴）+ 折线（右轴），无第三方依赖。 */
export function drawChart(canvas, { labels, bars = null, line = null, lineFmt = (v) => v, barFmt = (v) => v, barColor = "rgba(127,216,255,.35)", lineColor = "#47c6c0" }) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  const pad = { l: bars ? 54 : 12, r: line ? 52 : 12, t: 12, b: 24 };
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const n = labels.length;
  if (!n) return;
  const x = (i) => pad.l + (n === 1 ? iw / 2 : (i * iw) / (n - 1));
  ctx.font = "11px system-ui, sans-serif";
  ctx.fillStyle = "#6b7d9c";

  // 网格
  ctx.strokeStyle = "rgba(200,220,255,.07)";
  for (let g = 0; g <= 4; g++) {
    const y = pad.t + (ih * g) / 4;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
  }

  if (bars) {
    const max = Math.max(...bars, 1);
    const bw = Math.max(1, (iw / n) * 0.62);
    ctx.fillStyle = barColor;
    bars.forEach((v, i) => {
      const bh = (v / max) * ih;
      ctx.fillRect(x(i) - bw / 2, pad.t + ih - bh, bw, bh);
    });
    ctx.fillStyle = "#6b7d9c"; ctx.textAlign = "right";
    for (let g = 0; g <= 4; g++) ctx.fillText(barFmt((max * (4 - g)) / 4), pad.l - 6, pad.t + (ih * g) / 4 + 4);
  }

  if (line) {
    const vals = line.filter((v) => v != null);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (lo === hi) { lo -= 1; hi += 1; }
    const span = hi - lo; lo -= span * 0.08; hi += span * 0.08;
    const y = (v) => pad.t + ih - ((v - lo) / (hi - lo)) * ih;
    const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + ih);
    grad.addColorStop(0, lineColor + "55"); grad.addColorStop(1, lineColor + "00");
    ctx.beginPath();
    line.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
    ctx.strokeStyle = lineColor; ctx.lineWidth = 1.8; ctx.stroke();
    ctx.lineTo(x(n - 1), pad.t + ih); ctx.lineTo(x(0), pad.t + ih); ctx.closePath();
    ctx.fillStyle = grad; ctx.fill();
    ctx.fillStyle = "#6b7d9c"; ctx.textAlign = "left";
    for (let g = 0; g <= 4; g++) ctx.fillText(lineFmt(hi - ((hi - lo) * g) / 4), w - pad.r + 6, pad.t + (ih * g) / 4 + 4);
  }

  // X 轴：首、中、尾
  ctx.fillStyle = "#6b7d9c"; ctx.textAlign = "center";
  [0, Math.floor((n - 1) / 2), n - 1].forEach((i) => ctx.fillText(labels[i], x(i), h - 6));
}

/** 迷你折线 */
export function sparkline(values, { w = 110, h = 28, color = "#47c6c0" } = {}) {
  const c = document.createElement("canvas");
  c.style.width = w + "px"; c.style.height = h + "px";
  requestAnimationFrame(() => {
    const dpr = window.devicePixelRatio || 1;
    c.width = w * dpr; c.height = h * dpr;
    const ctx = c.getContext("2d"); ctx.scale(dpr, dpr);
    const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
    ctx.beginPath();
    values.forEach((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * (w - 2) + 1;
      const y = h - 2 - ((v - lo) / span) * (h - 4);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke();
    if (lo < 0 && hi > 0) {
      const y0 = h - 2 - ((0 - lo) / span) * (h - 4);
      ctx.strokeStyle = "rgba(200,220,255,.2)"; ctx.setLineDash([2, 3]);
      ctx.beginPath(); ctx.moveTo(0, y0); ctx.lineTo(w, y0); ctx.stroke();
    }
  });
  return c;
}

/** 多条折线（共用一个 Y 轴），带圆点和图例；null 值断开。用于经济数据“预测值 vs 实际值”。 */
export function drawLines(canvas, { labels, series, fmt = (v) => v }) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  const n = labels.length;
  const vals = series.flatMap((s) => s.values.filter((v) => v != null));
  if (!n || !vals.length) return;
  ctx.font = "11px system-ui, sans-serif";
  const yl = (v) => String(fmt(v));
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (lo === hi) { lo -= Math.abs(lo) * 0.1 || 1; hi += Math.abs(hi) * 0.1 || 1; }
  const span = hi - lo; lo -= span * 0.12; hi += span * 0.12;
  const padL = Math.max(...[lo, hi].map((v) => ctx.measureText(yl(v)).width)) + 12;
  const pad = { l: padL, r: 12, t: 26, b: 22 };
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const x = (i) => pad.l + (n === 1 ? iw / 2 : (i * iw) / (n - 1));
  const y = (v) => pad.t + ih - ((v - lo) / (hi - lo)) * ih;
  ctx.strokeStyle = "rgba(200,220,255,.08)"; ctx.fillStyle = "#6b7d9c"; ctx.textAlign = "right";
  for (let g = 0; g <= 4; g++) {
    const yy = pad.t + (ih * g) / 4;
    ctx.beginPath(); ctx.moveTo(pad.l, yy); ctx.lineTo(w - pad.r, yy); ctx.stroke();
    ctx.fillText(yl(hi - ((hi - lo) * g) / 4), pad.l - 6, yy + 4);
  }
  if (lo < 0 && hi > 0) {  // 零轴
    ctx.strokeStyle = "rgba(200,220,255,.25)"; ctx.beginPath(); ctx.moveTo(pad.l, y(0)); ctx.lineTo(w - pad.r, y(0)); ctx.stroke();
  }
  for (const s of series) {
    ctx.strokeStyle = s.color; ctx.fillStyle = s.color; ctx.lineWidth = 2;
    ctx.setLineDash(s.dash || []);
    ctx.beginPath();
    let pen = false;
    s.values.forEach((v, i) => {
      if (v == null) { pen = false; return; }
      pen ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v));
      pen = true;
    });
    ctx.stroke();
    ctx.setLineDash([]);
    s.values.forEach((v, i) => { if (v != null) { ctx.beginPath(); ctx.arc(x(i), y(v), 2.8, 0, Math.PI * 2); ctx.fill(); } });
  }
  // 图例
  let lx = pad.l;
  ctx.textAlign = "left";
  for (const s of series) {
    ctx.fillStyle = s.color; ctx.fillRect(lx, 8, 14, 3);
    ctx.fillStyle = "#c9d4e8"; ctx.fillText(s.name, lx + 18, 13);
    lx += ctx.measureText(s.name).width + 36;
  }
  ctx.fillStyle = "#6b7d9c"; ctx.textAlign = "center";
  const ticks = n <= 6 ? [...Array(n).keys()] : [0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1];
  ticks.forEach((i) => {
    ctx.textAlign = i === 0 && n > 1 ? "left" : i === n - 1 && n > 1 ? "right" : "center";
    ctx.fillText(labels[i], x(i), h - 6);
  });
}

/**
 * 交互式图表：柱 / 线 / 面积，左右两个 Y 轴，鼠标或手指移动时显示十字线和数值提示。
 * series: [{ name, values, color, type: "line"|"bar"|"area", axis: "left"|"right", dash, hidden }]
 * 返回清理函数。
 */
export function interactiveChart(canvas, { labels, series, fmtLeft = (v) => v, fmtRight = (v) => v, tipTitle = (i) => labels[i], zeroLine = false }) {
  const n = labels.length;
  let hover = -1;
  const axes = { left: series.filter((s) => (s.axis || "left") === "left"), right: series.filter((s) => s.axis === "right") };
  const range = (ss, isBar) => {
    const vals = ss.flatMap((s) => s.values.filter((v) => v != null && Number.isFinite(v)));
    if (!vals.length) return null;
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (ss.some((s) => s.type === "bar") || isBar) lo = Math.min(0, lo), hi = Math.max(0, hi);
    if (lo === hi) { const d = Math.abs(lo) * 0.05 || 1; lo -= d; hi += d; }
    const pad = (hi - lo) * 0.08;
    return [ss.some((s) => s.type === "bar") && lo >= 0 ? 0 : lo - pad, hi + pad];
  };
  const rl = range(axes.left), rr = range(axes.right);

  function draw() {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h || !n) return;
    canvas.width = w * dpr; canvas.height = h * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.font = "11px system-ui, sans-serif";
    const tw = (r, f) => (r ? Math.max(ctx.measureText(String(f(r[0]))).width, ctx.measureText(String(f(r[1]))).width) + 10 : 8);
    const pad = { l: tw(rl, fmtLeft), r: tw(rr, fmtRight), t: 24, b: 20 };
    const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
    const slot = iw / n;
    const x = (i) => pad.l + slot * (i + 0.5);
    const yOf = (r) => (v) => pad.t + ih - ((v - r[0]) / (r[1] - r[0])) * ih;
    // 网格与刻度
    ctx.strokeStyle = "rgba(200,220,255,.07)";
    for (let g = 0; g <= 4; g++) {
      const yy = pad.t + (ih * g) / 4;
      ctx.beginPath(); ctx.moveTo(pad.l, yy); ctx.lineTo(w - pad.r, yy); ctx.stroke();
      ctx.fillStyle = "#6b7d9c";
      if (rl) { ctx.textAlign = "right"; ctx.fillText(String(fmtLeft(rl[1] - ((rl[1] - rl[0]) * g) / 4)), pad.l - 5, yy + 4); }
      if (rr) { ctx.textAlign = "left"; ctx.fillText(String(fmtRight(rr[1] - ((rr[1] - rr[0]) * g) / 4)), w - pad.r + 5, yy + 4); }
    }
    if (zeroLine && rl && rl[0] < 0 && rl[1] > 0) {
      ctx.strokeStyle = "rgba(200,220,255,.3)"; const y0 = yOf(rl)(0);
      ctx.beginPath(); ctx.moveTo(pad.l, y0); ctx.lineTo(w - pad.r, y0); ctx.stroke();
    }
    for (const s of series) {
      if (s.hidden) continue;
      const r = s.axis === "right" ? rr : rl;
      if (!r) continue;
      const y = yOf(r);
      if (s.type === "bar") {
        const bw = Math.min(28, Math.max(1, slot * 0.62));
        s.values.forEach((v, i) => {
          if (v == null) return;
          ctx.fillStyle = typeof s.color === "function" ? s.color(v, i) : s.color;
          const y0 = y(Math.max(r[0], 0)), y1 = y(v);
          ctx.fillRect(x(i) - bw / 2, Math.min(y0, y1), bw, Math.max(1, Math.abs(y1 - y0)));
        });
      } else {
        ctx.strokeStyle = s.color; ctx.lineWidth = s.width || 2; ctx.setLineDash(s.dash || []);
        ctx.beginPath();
        let pen = false, firstI = -1, lastI = -1;
        s.values.forEach((v, i) => {
          if (v == null) { pen = false; return; }
          pen ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v));
          pen = true; if (firstI < 0) firstI = i; lastI = i;
        });
        ctx.stroke(); ctx.setLineDash([]);
        if (s.type === "area" && firstI >= 0) {
          ctx.lineTo(x(lastI), pad.t + ih); ctx.lineTo(x(firstI), pad.t + ih); ctx.closePath();
          const g = ctx.createLinearGradient(0, pad.t, 0, pad.t + ih);
          g.addColorStop(0, s.color + "44"); g.addColorStop(1, s.color + "00");
          ctx.fillStyle = g; ctx.fill();
        }
        if (n <= 40 || s.dots) s.values.forEach((v, i) => { if (v != null) { ctx.fillStyle = s.color; ctx.beginPath(); ctx.arc(x(i), y(v), n <= 40 ? 2.4 : 1.6, 0, 7); ctx.fill(); } });
      }
    }
    // 图例
    let lx = pad.l; ctx.textAlign = "left";
    for (const s of series) {
      if (s.hidden || !s.name) continue;
      ctx.fillStyle = typeof s.color === "function" ? s.color(1, 0) : s.color;
      ctx.fillRect(lx, 8, 12, s.type === "bar" ? 8 : 3);
      ctx.fillStyle = "#c9d4e8"; ctx.fillText(s.name, lx + 16, 14);
      lx += ctx.measureText(s.name).width + 32;
    }
    // X 轴
    ctx.fillStyle = "#6b7d9c";
    const ticks = n <= 6 ? [...Array(n).keys()] : [0, Math.floor(n / 4), Math.floor(n / 2), Math.floor((3 * n) / 4), n - 1];
    ticks.forEach((i) => { ctx.textAlign = n > 1 && i === 0 ? "left" : n > 1 && i === n - 1 ? "right" : "center"; ctx.fillText(labels[i], i === 0 && n > 1 ? pad.l : i === n - 1 && n > 1 ? w - pad.r : x(i), h - 5); });
    // 十字线与提示
    if (hover >= 0) {
      ctx.strokeStyle = "rgba(200,220,255,.35)"; ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(x(hover), pad.t); ctx.lineTo(x(hover), pad.t + ih); ctx.stroke(); ctx.setLineDash([]);
      const lines = [String(tipTitle(hover))];
      const colors = [null];
      for (const s of series) {
        if (s.hidden || !s.name) continue;
        const v = s.values[hover];
        lines.push(`${s.name}：${v == null ? "—" : (s.axis === "right" ? fmtRight : fmtLeft)(v)}`);
        colors.push(typeof s.color === "function" ? s.color(v ?? 0, hover) : s.color);
      }
      ctx.font = "12px system-ui, sans-serif";
      const bw = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 20, bh = lines.length * 17 + 10;
      let bx = x(hover) + 12; if (bx + bw > w - 4) bx = x(hover) - bw - 12;
      const by = pad.t + 4;
      ctx.fillStyle = "rgba(10,16,30,.92)"; ctx.strokeStyle = "rgba(200,220,255,.2)";
      ctx.beginPath(); ctx.roundRect?.(bx, by, bw, bh, 8); if (!ctx.roundRect) ctx.rect(bx, by, bw, bh); ctx.fill(); ctx.stroke();
      lines.forEach((l, k) => {
        if (colors[k]) { ctx.fillStyle = colors[k]; ctx.fillRect(bx + 8, by + 9 + k * 17, 6, 6); }
        ctx.fillStyle = k ? "#dbe4f5" : "#9fb0cc"; ctx.textAlign = "left";
        ctx.fillText(l, bx + (colors[k] ? 18 : 10), by + 16 + k * 17);
      });
    }
    canvas._layout = { pad, slot, w };
  }

  const pick = (clientX) => {
    const L = canvas._layout; if (!L) return -1;
    const rect = canvas.getBoundingClientRect();
    const i = Math.floor((clientX - rect.left - L.pad.l) / L.slot);
    return i >= 0 && i < n ? i : -1;
  };
  const move = (e) => { const p = e.touches ? e.touches[0] : e; const i = pick(p.clientX); if (i !== hover) { hover = i; draw(); } };
  const out = () => { hover = -1; draw(); };
  canvas.addEventListener("mousemove", move);
  canvas.addEventListener("mouseleave", out);
  canvas.addEventListener("touchstart", move, { passive: true });
  canvas.addEventListener("touchmove", move, { passive: true });
  const ro = new ResizeObserver(() => draw());
  ro.observe(canvas);
  requestAnimationFrame(draw);
  return () => { ro.disconnect(); canvas.removeEventListener("mousemove", move); };
}

/** 移动平均（窗口不足时为 null）。 */
export function movingAvg(values, k) {
  return values.map((_, i) => {
    if (i + 1 < k) return null;
    const win = values.slice(i + 1 - k, i + 1).filter((v) => v != null);
    return win.length ? win.reduce((a, b) => a + b, 0) / win.length : null;
  });
}
