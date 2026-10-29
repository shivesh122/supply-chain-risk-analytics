/* Supply Chain Risk Analytics dashboard (vanilla JS + D3 v7). Reads data/dashboard.json built by the Python pipeline. */
(() => {
  'use strict';

  const COLORS = {
    blue: '#2563eb', teal: '#0d9488', cyan: '#22d3ee', amber: '#f59e0b', red: '#ef4444', green: '#10b981',
    violet: '#7c3aed', slate: '#94a3b8', navy: '#143a5a',
  };
  const TIER_COLOR = { Preferred: COLORS.green, Watch: COLORS.amber, 'At Risk': COLORS.red, High: COLORS.red, Medium: COLORS.amber, Low: COLORS.green };
  const REGION_COLOR = { Domestic: COLORS.teal, Asia: COLORS.amber, Europe: COLORS.violet };

  // ---------- formatting ----------
  const nfIN = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
  const inr = (v) => {
    const a = Math.abs(v);
    if (a >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
    if (a >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`;
    if (a >= 1e3) return `₹${(v / 1e3).toFixed(1)}K`;
    return `₹${nfIN.format(v)}`;
  };
  const num = (v) => nfIN.format(v ?? 0);
  const pct = (v, d = 1) => (v == null ? '—' : `${(+v).toFixed(d)}%`);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const monthLabel = (ym) => d3.timeFormat('%b %y')(d3.timeParse('%Y-%m')(ym));
  const dayLabel = d3.timeFormat('%d %b');
  const parseDay = d3.timeParse('%Y-%m-%d');

  // ---------- tooltip ----------
  const tip = document.getElementById('tip');
  function showTip(html, event) {
    tip.innerHTML = html;
    tip.style.opacity = 1;
    const pad = 14;
    const { innerWidth: W, innerHeight: H } = window;
    const r = tip.getBoundingClientRect();
    let x = event.clientX + pad;
    let y = event.clientY + pad;
    if (x + r.width > W - 8) x = event.clientX - r.width - pad;
    if (y + r.height > H - 8) y = event.clientY - r.height - pad;
    tip.style.left = `${x}px`;
    tip.style.top = `${y}px`;
  }
  const hideTip = () => { tip.style.opacity = 0; };

  // ---------- chart registry (re-render on resize / tab switch) ----------
  const charts = new Map();
  function register(id, fn) {
    charts.set(id, fn);
    const el = document.getElementById(id);
    if (el && el.offsetParent !== null) fn(el);
  }
  function renderVisible() {
    charts.forEach((fn, id) => {
      const el = document.getElementById(id);
      if (el && el.offsetParent !== null) fn(el);
    });
  }
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(renderVisible, 150);
  });

  function frame(el, margin) {
    el.innerHTML = '';
    const width = Math.max(el.clientWidth, 280);
    const height = el.clientHeight || 280;
    const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${width} ${height}`);
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);
    return { svg, g, w: width - margin.left - margin.right, h: height - margin.top - margin.bottom, width, height };
  }

  function legend(svg, items, x, y) {
    const lg = svg.append('g').attr('class', 'legend').attr('transform', `translate(${x},${y})`);
    let off = 0;
    items.forEach((it) => {
      const gi = lg.append('g').attr('transform', `translate(${off},0)`);
      if (it.line) gi.append('line').attr('x1', 0).attr('x2', 16).attr('y1', 0).attr('y2', 0).attr('stroke', it.color).attr('stroke-width', 2.5).attr('stroke-dasharray', it.dash || null);
      else gi.append('rect').attr('x', 0).attr('y', -6).attr('width', 12).attr('height', 12).attr('rx', 3).attr('fill', it.color).attr('opacity', it.opacity || 1);
      gi.append('text').attr('x', it.line ? 21 : 17).attr('y', 4).text(it.label);
      off += (it.line ? 26 : 22) + it.label.length * 6.4 + 12;
    });
  }

  // ---------- generic charts ----------
  function comboChart(el, data) {
    const m = { top: 30, right: 48, bottom: 30, left: 58 };
    const { svg, g, w, h } = frame(el, m);
    const x = d3.scaleBand().domain(data.map((d) => d.year_month)).range([0, w]).padding(0.3);
    const yL = d3.scaleLinear().domain([0, d3.max(data, (d) => d.lost_revenue) * 1.15 || 1]).nice().range([h, 0]);
    const lo = Math.floor(d3.min(data, (d) => d.fill_rate_pct) - 3);
    const yR = d3.scaleLinear().domain([Math.max(lo, 0), 100]).range([h, 0]);
    g.append('g').attr('class', 'grid-line').call(d3.axisLeft(yL).ticks(5).tickSize(-w).tickFormat(''));
    const every = Math.ceil(data.length / 9);
    g.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`)
      .call(d3.axisBottom(x).tickValues(x.domain().filter((_, i) => i % every === 0)).tickFormat(monthLabel));
    g.append('g').attr('class', 'axis').call(d3.axisLeft(yL).ticks(5).tickFormat(inr));
    g.append('g').attr('class', 'axis').attr('transform', `translate(${w},0)`).call(d3.axisRight(yR).ticks(5).tickFormat((v) => `${v}%`));
    g.selectAll('rect.bar').data(data).join('rect').attr('class', 'bar')
      .attr('x', (d) => x(d.year_month)).attr('width', x.bandwidth())
      .attr('y', (d) => yL(d.lost_revenue)).attr('height', (d) => h - yL(d.lost_revenue))
      .attr('rx', 3).attr('fill', COLORS.red).attr('opacity', 0.28);
    const line = d3.line().x((d) => x(d.year_month) + x.bandwidth() / 2).y((d) => yR(d.fill_rate_pct)).curve(d3.curveMonotoneX);
    g.append('path').datum(data).attr('fill', 'none').attr('stroke', COLORS.blue).attr('stroke-width', 2.5).attr('d', line);
    g.selectAll('circle').data(data).join('circle').attr('cx', (d) => x(d.year_month) + x.bandwidth() / 2).attr('cy', (d) => yR(d.fill_rate_pct)).attr('r', 3.5).attr('fill', COLORS.blue);
    g.selectAll('rect.hover').data(data).join('rect').attr('class', 'hover').attr('x', (d) => x(d.year_month)).attr('width', x.bandwidth()).attr('y', 0).attr('height', h).attr('fill', 'transparent')
      .on('mousemove', (e, d) => showTip(`<b>${monthLabel(d.year_month)}</b><br>Fill rate: ${pct(d.fill_rate_pct, 2)}<br>Lost revenue: ${inr(d.lost_revenue)}<br>Revenue: ${inr(d.revenue)}`, e))
      .on('mouseleave', hideTip);
    legend(svg, [{ label: 'Fill rate %', color: COLORS.blue, line: true }, { label: 'Lost revenue (stockouts)', color: COLORS.red, opacity: 0.35 }], m.left, 12);
  }

  function heatmap(el, rows) {
    const cats = [...new Set(rows.map((r) => r.category))].sort();
    const whs = [...new Set(rows.map((r) => r.warehouse_name))].sort();
    const m = { top: 8, right: 8, bottom: 28, left: 84 };
    const { g, w, h } = frame(el, m);
    const x = d3.scaleBand().domain(whs).range([0, w]).padding(0.06);
    const y = d3.scaleBand().domain(cats).range([0, h]).padding(0.06);
    const color = d3.scaleSequential(d3.interpolateRdYlGn).domain([70, 100]);
    g.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x).tickSize(0).tickFormat((d) => d.replace(' DC', ''))).select('.domain').remove();
    g.append('g').attr('class', 'axis').call(d3.axisLeft(y).tickSize(0)).select('.domain').remove();
    const cell = g.selectAll('g.cell').data(rows).join('g').attr('class', 'cell');
    cell.append('rect').attr('x', (d) => x(d.warehouse_name)).attr('y', (d) => y(d.category)).attr('width', x.bandwidth()).attr('height', y.bandwidth()).attr('rx', 6)
      .attr('fill', (d) => color(d.fill_rate_pct))
      .on('mousemove', (e, d) => showTip(`<b>${esc(d.category)} · ${esc(d.warehouse_name)}</b><br>Fill rate: ${pct(d.fill_rate_pct, 2)}<br>Lost revenue: ${inr(d.lost_revenue)}`, e))
      .on('mouseleave', hideTip);
    cell.append('text').attr('x', (d) => x(d.warehouse_name) + x.bandwidth() / 2).attr('y', (d) => y(d.category) + y.bandwidth() / 2 + 4)
      .attr('text-anchor', 'middle').attr('font-size', 12).attr('font-weight', 600).attr('pointer-events', 'none')
      .attr('fill', (d) => (d.fill_rate_pct < 80 ? '#fff' : '#0f1d2e')).text((d) => `${d.fill_rate_pct.toFixed(0)}%`);
  }

  function hbar(el, data, { value, label, color, format, tipHtml, domainMax }) {
    const m = { top: 6, right: 54, bottom: 22, left: 160 };
    el.style.height = `${Math.max(220, data.length * 26 + 40)}px`;
    const { g, w, h } = frame(el, m);
    const y = d3.scaleBand().domain(data.map(label)).range([0, h]).padding(0.25);
    const x = d3.scaleLinear().domain([0, domainMax ?? (d3.max(data, value) * 1.05 || 1)]).nice().range([0, w]);
    g.append('g').attr('class', 'grid-line').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x).ticks(5).tickSize(-h).tickFormat(''));
    g.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x).ticks(5).tickFormat(format));
    g.append('g').attr('class', 'axis').call(d3.axisLeft(y).tickSize(0).tickPadding(8)).select('.domain').remove();
    g.selectAll('rect').data(data).join('rect').attr('y', (d) => y(label(d))).attr('height', y.bandwidth()).attr('x', 0)
      .attr('width', (d) => x(value(d))).attr('rx', 4).attr('fill', color)
      .on('mousemove', (e, d) => tipHtml && showTip(tipHtml(d), e)).on('mouseleave', hideTip);
    g.selectAll('text.v').data(data).join('text').attr('class', 'v').attr('x', (d) => x(value(d)) + 6).attr('y', (d) => y(label(d)) + y.bandwidth() / 2 + 4)
      .attr('font-size', 11.5).attr('fill', '#334155').attr('font-weight', 600).text((d) => format(value(d)));
  }

  function vbars(el, data, { color, format }) {
    const m = { top: 16, right: 10, bottom: 46, left: 44 };
    const { g, w, h } = frame(el, m);
    const x = d3.scaleBand().domain(data.map((d) => d.label)).range([0, w]).padding(0.25);
    const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d.value) * 1.15 || 1]).nice().range([h, 0]);
    g.append('g').attr('class', 'grid-line').call(d3.axisLeft(y).ticks(4).tickSize(-w).tickFormat(''));
    const xa = g.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x).tickSize(0).tickPadding(8));
    xa.selectAll('text').attr('transform', 'rotate(-20)').attr('text-anchor', 'end');
    g.append('g').attr('class', 'axis').call(d3.axisLeft(y).ticks(4).tickFormat(format));
    g.selectAll('rect').data(data).join('rect').attr('x', (d) => x(d.label)).attr('width', x.bandwidth()).attr('y', (d) => y(d.value)).attr('height', (d) => h - y(d.value))
      .attr('rx', 4).attr('fill', color)
      .on('mousemove', (e, d) => showTip(`<b>${esc(d.label)}</b><br>${esc(d.tip)}`, e)).on('mouseleave', hideTip);
    g.selectAll('text.v').data(data).join('text').attr('class', 'v').attr('x', (d) => x(d.label) + x.bandwidth() / 2).attr('y', (d) => y(d.value) - 5)
      .attr('text-anchor', 'middle').attr('font-size', 11).attr('font-weight', 600).attr('fill', '#334155').text((d) => format(d.value));
  }

  function multiLine(el, data, series, { yFormat, xKey, xFormat, yDomain }) {
    const m = { top: 30, right: 16, bottom: 30, left: 44 };
    const { svg, g, w, h } = frame(el, m);
    const x = d3.scalePoint().domain(data.map((d) => d[xKey])).range([0, w]).padding(0.3);
    const vals = data.flatMap((d) => series.map((s) => d[s.key]).filter((v) => v != null));
    const y = d3.scaleLinear().domain(yDomain || [Math.max(0, d3.min(vals) - 5), Math.min(100, d3.max(vals) + 3)]).nice().range([h, 0]);
    g.append('g').attr('class', 'grid-line').call(d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(''));
    const every = Math.ceil(data.length / 9);
    g.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x).tickValues(x.domain().filter((_, i) => i % every === 0)).tickFormat(xFormat));
    g.append('g').attr('class', 'axis').call(d3.axisLeft(y).ticks(5).tickFormat(yFormat));
    series.forEach((s) => {
      const line = d3.line().defined((d) => d[s.key] != null).x((d) => x(d[xKey])).y((d) => y(d[s.key])).curve(d3.curveMonotoneX);
      g.append('path').datum(data).attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', s.width || 2).attr('stroke-dasharray', s.dash || null).attr('d', line);
    });
    const focus = g.append('line').attr('y1', 0).attr('y2', h).attr('stroke', '#94a3b8').attr('stroke-dasharray', '3 3').attr('opacity', 0);
    g.append('rect').attr('width', w).attr('height', h).attr('fill', 'transparent')
      .on('mousemove', (e) => {
        const [mx] = d3.pointer(e);
        const idx = Math.max(0, Math.min(data.length - 1, Math.round((mx - x(data[0][xKey])) / (x.step() || 1))));
        const d = data[idx];
        focus.attr('x1', x(d[xKey])).attr('x2', x(d[xKey])).attr('opacity', 1);
        showTip(`<b>${xFormat(d[xKey])}</b><br>${series.map((s) => `${esc(s.label)}: ${d[s.key] == null ? '—' : yFormat(d[s.key])}`).join('<br>')}`, e);
      })
      .on('mouseleave', () => { focus.attr('opacity', 0); hideTip(); });
    legend(svg, series.map((s) => ({ label: s.label, color: s.color, line: true, dash: s.dash })), m.left, 12);
  }

  function scatter(el, rows) {
    const m = { top: 16, right: 24, bottom: 42, left: 52 };
    const { g, w, h } = frame(el, m);
    const x = d3.scaleLinear().domain([d3.min(rows, (d) => d.otif_pct) - 5, 100]).nice().range([0, w]);
    const y = d3.scaleLinear().domain([0, d3.max(rows, (d) => d.defect_rate_pct) * 1.2]).nice().range([h, 0]);
    const r = d3.scaleSqrt().domain([0, d3.max(rows, (d) => d.total_spend)]).range([4, 24]);
    g.append('g').attr('class', 'grid-line').call(d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(''));
    g.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x).ticks(6).tickFormat((v) => `${v}%`));
    g.append('g').attr('class', 'axis').call(d3.axisLeft(y).ticks(5).tickFormat((v) => `${v}%`));
    g.append('text').attr('x', w / 2).attr('y', h + 36).attr('text-anchor', 'middle').attr('class', 'legend').text('OTIF % (higher is better) →');
    g.append('text').attr('transform', `translate(-40,${h / 2}) rotate(-90)`).attr('text-anchor', 'middle').attr('class', 'legend').text('Defect rate % (lower is better)');
    const pts = g.selectAll('g.pt').data(rows).join('g').attr('class', 'pt').attr('transform', (d) => `translate(${x(d.otif_pct)},${y(d.defect_rate_pct)})`);
    pts.append('circle').attr('r', (d) => r(d.total_spend)).attr('fill', (d) => TIER_COLOR[d.tier]).attr('fill-opacity', 0.55).attr('stroke', (d) => TIER_COLOR[d.tier]).attr('stroke-width', 1.5)
      .on('mousemove', (e, d) => showTip(`<b>${esc(d.supplier_name)}</b> (${esc(d.country)})<br>OTIF: ${pct(d.otif_pct)} · Defects: ${pct(d.defect_rate_pct, 2)}<br>Spend: ${inr(d.total_spend)}<br>Score ${d.score} · ${esc(d.tier)}`, e))
      .on('mouseleave', hideTip);
    // Greedy label placement: try above, below, right, left of each bubble; skip a label if every spot collides
    const placed = [];
    const overlaps = (b) => placed.some((p) => b.x1 < p.x2 && b.x2 > p.x1 && b.y1 < p.y2 && b.y2 > p.y1);
    rows.slice().sort((a, b) => b.total_spend - a.total_spend).forEach((d) => {
      const name = d.supplier_name.split(' ')[0];
      const tw = name.length * 6.2;
      const cx = x(d.otif_pct);
      const cy = y(d.defect_rate_pct);
      const rr = r(d.total_spend);
      const spots = [[cx, cy - rr - 5, 'middle'], [cx, cy + rr + 13, 'middle'], [cx + rr + 4, cy + 4, 'start'], [cx - rr - 4, cy + 4, 'end']];
      for (const [lx, ly, anchor] of spots) {
        const x1 = anchor === 'middle' ? lx - tw / 2 : anchor === 'start' ? lx : lx - tw;
        const box = { x1, x2: x1 + tw, y1: ly - 10, y2: ly + 2 };
        if (box.x1 < -40 || box.x2 > w + 20 || overlaps(box)) continue;
        placed.push(box);
        g.append('text').attr('x', lx).attr('y', ly).attr('text-anchor', anchor).attr('font-size', 10.5).attr('fill', '#334155')
          .attr('pointer-events', 'none').text(name);
        break;
      }
    });
  }

  function invChart(el, rows) {
    const data = rows.map((d) => ({ ...d, dt: parseDay(d.date) }));
    const m = { top: 30, right: 44, bottom: 28, left: 58 };
    const { svg, g, w, h } = frame(el, m);
    const x = d3.scaleTime().domain(d3.extent(data, (d) => d.dt)).range([0, w]);
    const yL = d3.scaleLinear().domain([0, d3.max(data, (d) => d.inventory_value) * 1.1]).nice().range([h, 0]);
    const yR = d3.scaleLinear().domain([0, Math.max(10, d3.max(data, (d) => d.skus_out_of_stock) * 1.2)]).nice().range([h, 0]);
    g.append('g').attr('class', 'grid-line').call(d3.axisLeft(yL).ticks(5).tickSize(-w).tickFormat(''));
    g.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x).ticks(8).tickFormat(d3.timeFormat('%b %y')));
    g.append('g').attr('class', 'axis').call(d3.axisLeft(yL).ticks(5).tickFormat(inr));
    g.append('g').attr('class', 'axis').attr('transform', `translate(${w},0)`).call(d3.axisRight(yR).ticks(5));
    g.append('path').datum(data).attr('fill', COLORS.teal).attr('fill-opacity', 0.14)
      .attr('d', d3.area().x((d) => x(d.dt)).y0(h).y1((d) => yL(d.inventory_value)).curve(d3.curveMonotoneX));
    g.append('path').datum(data).attr('fill', 'none').attr('stroke', COLORS.teal).attr('stroke-width', 2)
      .attr('d', d3.line().x((d) => x(d.dt)).y((d) => yL(d.inventory_value)).curve(d3.curveMonotoneX));
    g.append('path').datum(data).attr('fill', 'none').attr('stroke', COLORS.red).attr('stroke-width', 1.8).attr('stroke-dasharray', '4 3')
      .attr('d', d3.line().x((d) => x(d.dt)).y((d) => yR(d.skus_out_of_stock)).curve(d3.curveMonotoneX));
    const bis = d3.bisector((d) => d.dt).center;
    const focus = g.append('line').attr('y1', 0).attr('y2', h).attr('stroke', '#94a3b8').attr('stroke-dasharray', '3 3').attr('opacity', 0);
    g.append('rect').attr('width', w).attr('height', h).attr('fill', 'transparent')
      .on('mousemove', (e) => {
        const d = data[bis(data, x.invert(d3.pointer(e)[0]))];
        focus.attr('x1', x(d.dt)).attr('x2', x(d.dt)).attr('opacity', 1);
        showTip(`<b>${dayLabel(d.dt)} ${d.dt.getFullYear()}</b><br>Inventory value: ${inr(d.inventory_value)}<br>Out-of-stock locations: ${d.skus_out_of_stock}`, e);
      })
      .on('mouseleave', () => { focus.attr('opacity', 0); hideTip(); });
    legend(svg, [{ label: 'Inventory value', color: COLORS.teal, line: true }, { label: 'Out-of-stock SKU-locations (right axis)', color: COLORS.red, line: true, dash: '4 3' }], m.left, 12);
  }

  function forecastChart(el, p) {
    const hist = p.history.map((d) => ({ dt: parseDay(d.date), v: d.actual }));
    const hold = p.holdout.map((d) => ({ dt: parseDay(d.date), v: d.forecast }));
    const fut = p.forecast.map((d) => ({ dt: parseDay(d.date), v: d.forecast, lo: d.lower, hi: d.upper }));
    const m = { top: 30, right: 18, bottom: 28, left: 46 };
    const { svg, g, w, h } = frame(el, m);
    const x = d3.scaleTime().domain([hist[0].dt, fut[fut.length - 1].dt]).range([0, w]);
    const y = d3.scaleLinear().domain([0, d3.max([...hist.map((d) => d.v), ...fut.map((d) => d.hi)]) * 1.08]).nice().range([h, 0]);
    g.append('g').attr('class', 'grid-line').call(d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(''));
    g.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x).ticks(8).tickFormat(dayLabel));
    g.append('g').attr('class', 'axis').call(d3.axisLeft(y).ticks(5));
    const today = hist[hist.length - 1].dt;
    g.append('rect').attr('x', x(today)).attr('width', w - x(today)).attr('y', 0).attr('height', h).attr('fill', '#eff6ff');
    g.append('text').attr('x', x(today) + 6).attr('y', 12).attr('font-size', 11).attr('fill', COLORS.blue).attr('font-weight', 600).text('Forecast →');
    g.append('path').datum(fut).attr('fill', COLORS.blue).attr('fill-opacity', 0.15)
      .attr('d', d3.area().x((d) => x(d.dt)).y0((d) => y(d.lo)).y1((d) => y(d.hi)).curve(d3.curveMonotoneX));
    g.append('path').datum(hist).attr('fill', 'none').attr('stroke', '#475569').attr('stroke-width', 1.4)
      .attr('d', d3.line().x((d) => x(d.dt)).y((d) => y(d.v)));
    g.append('path').datum(hold).attr('fill', 'none').attr('stroke', COLORS.amber).attr('stroke-width', 2).attr('stroke-dasharray', '5 3')
      .attr('d', d3.line().x((d) => x(d.dt)).y((d) => y(d.v)));
    g.append('path').datum(fut).attr('fill', 'none').attr('stroke', COLORS.blue).attr('stroke-width', 2.4)
      .attr('d', d3.line().x((d) => x(d.dt)).y((d) => y(d.v)).curve(d3.curveMonotoneX));
    const all = [...hist.map((d) => ({ ...d, kind: 'Actual demand' })), ...fut.map((d) => ({ ...d, kind: 'Forecast' }))];
    const holdMap = new Map(hold.map((d) => [+d.dt, d.v]));
    const bis = d3.bisector((d) => d.dt).center;
    const focus = g.append('line').attr('y1', 0).attr('y2', h).attr('stroke', '#94a3b8').attr('stroke-dasharray', '3 3').attr('opacity', 0);
    g.append('rect').attr('width', w).attr('height', h).attr('fill', 'transparent')
      .on('mousemove', (e) => {
        const d = all[bis(all, x.invert(d3.pointer(e)[0]))];
        focus.attr('x1', x(d.dt)).attr('x2', x(d.dt)).attr('opacity', 1);
        const extra = d.kind === 'Forecast' ? `<br>80% range: ${d.lo} – ${d.hi}` : holdMap.has(+d.dt) ? `<br>Backtest forecast: ${holdMap.get(+d.dt)}` : '';
        showTip(`<b>${d3.timeFormat('%a %d %b %Y')(d.dt)}</b><br>${d.kind}: ${d.kind === 'Forecast' ? d.v : num(d.v)} units${extra}`, e);
      })
      .on('mouseleave', () => { focus.attr('opacity', 0); hideTip(); });
    legend(svg, [
      { label: 'Actual demand', color: '#475569', line: true },
      { label: 'Backtest (last 28 days)', color: COLORS.amber, line: true, dash: '5 3' },
      { label: 'Forecast', color: COLORS.blue, line: true },
    ], m.left, 12);
  }

  // ---------- tables ----------
  function table(el, columns, rows, opts = {}) {
    const state = { key: opts.sortKey, asc: opts.asc ?? false };
    function draw() {
      let data = rows.slice();
      if (state.key) {
        const col = columns.find((c) => c.key === state.key);
        const acc = col.sortValue || ((r) => r[state.key]);
        data.sort((a, b) => {
          const va = acc(a);
          const vb = acc(b);
          const cmp = typeof va === 'string' ? va.localeCompare(vb) : (va ?? -Infinity) - (vb ?? -Infinity);
          return state.asc ? cmp : -cmp;
        });
      }
      if (opts.limit) data = data.slice(0, opts.limit);
      if (!data.length) {
        el.innerHTML = `<div class="empty">${opts.empty || 'No rows match the filters.'}</div>`;
        return;
      }
      const head = columns.map((c) => {
        const cls = [c.num ? 'num' : '', opts.sortable ? 'sortable' : '', state.key === c.key ? `sorted${state.asc ? ' asc' : ''}` : ''].join(' ');
        return `<th class="${cls}" data-key="${c.key}">${c.label}</th>`;
      }).join('');
      const body = data.map((r) => `<tr>${columns.map((c) => `<td class="${c.num ? 'num' : ''}">${c.render ? c.render(r) : esc(r[c.key])}</td>`).join('')}</tr>`).join('');
      el.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
      if (opts.sortable) {
        el.querySelectorAll('th').forEach((th) => th.addEventListener('click', () => {
          const k = th.dataset.key;
          state.asc = state.key === k ? !state.asc : false;
          state.key = k;
          draw();
        }));
      }
    }
    draw();
  }

  const pill = (t) => `<span class="pill ${String(t).replace(' ', '-')}">${esc(t)}</span>`;
  const minibar = (v, max, color, label) => `<span class="minibar"><span class="track"><span class="fill" style="width:${Math.min(100, (v / max) * 100)}%;background:${color}"></span></span>${label}</span>`;
  const probColor = (p) => (p >= 0.5 ? COLORS.red : p >= 0.2 ? COLORS.amber : COLORS.green);

  // ---------- pages ----------
  function renderOverview(D) {
    const k = D.kpis;
    const c = k.current;
    const p = k.previous;
    const delta = (cur, prev, { higherBetter = true, unit = 'pts', digits = 1, money = false } = {}) => {
      const d = cur - prev;
      if (Math.abs(d) < 1e-9) return '<span class="delta flat">No change vs prior 30d</span>';
      const good = higherBetter ? d > 0 : d < 0;
      const txt = money ? `${d > 0 ? '+' : '−'}${inr(Math.abs(d))}` : `${d > 0 ? '+' : ''}${d.toFixed(digits)} ${unit}`;
      return `<span class="delta ${good ? 'good' : 'bad'}">${d > 0 ? '▲' : '▼'} ${txt} vs prior 30d</span>`;
    };
    const cards = [
      { label: 'Fill rate (30d)', value: pct(c.fill_rate_pct, 1), sub: delta(c.fill_rate_pct, p.fill_rate_pct), accent: COLORS.blue },
      { label: 'Lost revenue from stockouts (30d)', value: inr(c.lost_revenue), sub: delta(c.lost_revenue, p.lost_revenue, { higherBetter: false, money: true }), accent: COLORS.red },
      { label: 'Supplier OTIF (30d)', value: pct(c.otif_pct), sub: delta(c.otif_pct, p.otif_pct), accent: COLORS.teal },
      { label: 'Avg delay per order (30d)', value: `${c.avg_delay_days.toFixed(1)} days`, sub: delta(c.avg_delay_days, p.avg_delay_days, { higherBetter: false, unit: 'days', digits: 2 }), accent: COLORS.amber },
      { label: 'High-risk SKU-locations', value: num(k.high_risk_locations), sub: `<span class="delta flat">${k.medium_risk_locations} medium · ${k.skus_out_of_stock} out of stock now</span>`, accent: COLORS.red },
      { label: 'Inventory value', value: inr(k.inventory_value), sub: `<span class="delta flat">${k.sku_locations} SKU-locations</span>`, accent: COLORS.violet },
      { label: 'Open purchase orders', value: num(k.open_pos), sub: `<span class="delta flat">${inr(k.open_po_value)} on order</span>`, accent: COLORS.navy },
      { label: 'Forecast accuracy (1 − WAPE)', value: pct(k.forecast_accuracy_pct), sub: `<span class="delta good">${D.forecast.summary.improvement_vs_naive_pct}% better than naive</span>`, accent: COLORS.green },
    ];
    document.getElementById('kpis').innerHTML = cards.map((x) => `<div class="kpi" style="--accent:${x.accent}"><div class="label">${x.label}</div><div class="value">${x.value}</div>${x.sub}</div>`).join('');

    register('ch-service', (el) => comboChart(el, D.monthly_service));
    register('ch-heat', (el) => heatmap(el, D.category_service));
    table(document.getElementById('tbl-toprisk'), riskColumns(true), D.inventory.risk.filter((r) => r.risk_tier === 'High').concat(D.inventory.risk.filter((r) => r.risk_tier !== 'High')), { limit: 6 });
  }

  function riskColumns(compact = false) {
    const cols = [
      { key: 'sku', label: 'SKU / Product', render: (r) => `<div class="main">${esc(r.product_name)}</div><div class="sub2">${esc(r.sku)} · ${esc(r.category)}</div>`, sortValue: (r) => r.product_name },
      { key: 'warehouse_name', label: 'Warehouse' },
      { key: 'on_hand_units', label: 'On hand', num: true, render: (r) => num(r.on_hand_units) },
      { key: 'inbound_units', label: 'Inbound', num: true, render: (r) => num(r.inbound_units) },
      { key: 'avg_daily_demand', label: 'Demand/day', num: true, render: (r) => r.avg_daily_demand.toFixed(1) },
      { key: 'days_of_cover', label: 'Cover (days)', num: true, render: (r) => `${r.days_of_cover.toFixed(1)}<div class="sub2">${r.days_of_cover_incl_inbound.toFixed(0)} incl. inbound</div>` },
      { key: 'lead_time_days', label: 'Lead time', num: true, render: (r) => `${r.lead_time_days} ± ${r.lead_time_sd} d` },
      { key: 'stockout_probability', label: 'Stockout probability', render: (r) => minibar(r.stockout_probability, 1, probColor(r.stockout_probability), `${(r.stockout_probability * 100).toFixed(0)}%`) },
      { key: 'risk_tier', label: 'Risk', render: (r) => pill(r.risk_tier), sortValue: (r) => r.risk_score },
    ];
    if (!compact) {
      cols.splice(1, 0, { key: 'criticality', label: 'Class', render: (r) => `<span class="pill crit">${r.criticality}</span>` });
      cols.push({ key: 'supplier_name', label: 'Supplier', render: (r) => `<span class="sub2">${esc(r.supplier_name)}</span>` });
      cols.push({ key: 'stockout_days_30d', label: 'Stockout days (30d)', num: true });
      cols.push({ key: 'recommended_order_qty', label: 'Suggested order', num: true, render: (r) => (r.recommended_order_qty ? `<b>${num(r.recommended_order_qty)}</b><div class="sub2">${inr(r.recommended_order_value)}</div>` : '—') });
    }
    return cols;
  }

  function renderSuppliers(D) {
    const S = D.suppliers;
    register('ch-scatter', (el) => scatter(el, S));
    register('ch-score', (el) => hbar(el, S, {
      value: (d) => d.score, label: (d) => d.supplier_name, color: (d) => TIER_COLOR[d.tier], format: (v) => v.toFixed(0), domainMax: 100,
      tipHtml: (d) => `<b>${esc(d.supplier_name)}</b><br>Score ${d.score} (${esc(d.tier)})<br>OTIF ${pct(d.otif_pct)} · Fill ${pct(d.fill_rate_pct)}<br>Defects ${pct(d.defect_rate_pct, 2)} · Lead time ${d.avg_lead_time_days} ± ${d.lead_time_sd} d`,
    }));
    table(document.getElementById('tbl-suppliers'), [
      { key: 'supplier_name', label: 'Supplier', render: (r) => `<div class="main">${esc(r.supplier_name)}</div><div class="sub2">${esc(r.country)} · ${esc(r.region)}</div>` },
      { key: 'score', label: 'Score', render: (r) => minibar(r.score, 100, TIER_COLOR[r.tier], `<b>${r.score.toFixed(1)}</b>`) },
      { key: 'tier', label: 'Tier', render: (r) => pill(r.tier), sortValue: (r) => r.score },
      { key: 'otif_pct', label: 'OTIF', num: true, render: (r) => pct(r.otif_pct) },
      { key: 'otif_trend', label: 'OTIF 90d vs all', num: true, render: (r) => (r.otif_trend == null ? '—' : `<span class="${r.otif_trend >= 0 ? 'trend-up' : 'trend-down'}">${r.otif_trend >= 0 ? '▲' : '▼'} ${Math.abs(r.otif_trend).toFixed(1)}</span>`) },
      { key: 'fill_rate_pct', label: 'Fill rate', num: true, render: (r) => pct(r.fill_rate_pct) },
      { key: 'defect_rate_pct', label: 'Defects', num: true, render: (r) => pct(r.defect_rate_pct, 2) },
      { key: 'avg_lead_time_days', label: 'Lead time', num: true, render: (r) => `${r.avg_lead_time_days} ± ${r.lead_time_sd} d<div class="sub2">contract ${r.contract_lead_time_days} d</div>` },
      { key: 'po_count', label: 'POs', num: true },
      { key: 'overdue_pos', label: 'Overdue', num: true, render: (r) => (r.overdue_pos ? `<b style="color:#b91c1c">${r.overdue_pos}</b>` : '0') },
      { key: 'total_spend', label: 'Spend', num: true, render: (r) => inr(r.total_spend) },
    ], S, { sortable: true, sortKey: 'score' });
  }

  function renderDelivery(D) {
    const M = D.delivery.monthly;
    const series = [{ key: 'otif_pct', label: 'All suppliers', color: COLORS.navy, width: 3 }];
    ['domestic', 'asia', 'europe'].forEach((r) => {
      if (M.some((d) => d[`otif_${r}`] != null)) series.push({ key: `otif_${r}`, label: r[0].toUpperCase() + r.slice(1), color: REGION_COLOR[r[0].toUpperCase() + r.slice(1)], dash: '5 3' });
    });
    register('ch-otif', (el) => multiLine(el, M, series, { xKey: 'year_month', xFormat: monthLabel, yFormat: (v) => `${(+v).toFixed(0)}%` }));
    const distColor = { Early: COLORS.green, 'On time': COLORS.teal };
    register('ch-dist', (el) => vbars(el, D.delivery.distribution.map((d) => ({ label: d.bucket, value: d.pct, tip: `${num(d.count)} orders (${d.pct}%)` })), {
      color: (d) => distColor[d.label] || COLORS.red, format: (v) => `${v.toFixed(0)}%`,
    }));
    register('ch-delay', (el) => hbar(el, D.delivery.by_supplier, {
      value: (d) => d.avg_delay_days, label: (d) => d.supplier_name, color: (d) => REGION_COLOR[d.region] || COLORS.slate, format: (v) => `${v.toFixed(1)}d`,
      tipHtml: (d) => `<b>${esc(d.supplier_name)}</b> (${esc(d.region)})<br>Avg delay: ${d.avg_delay_days} days/order<br>Late orders: ${pct(d.late_pct)}`,
    }));
    const O = D.delivery.overdue;
    document.getElementById('overdue-count').textContent = `${O.length} orders · ${inr(d3.sum(O, (d) => d.order_value))}`;
    table(document.getElementById('tbl-overdue'), [
      { key: 'po_id', label: 'PO' },
      { key: 'supplier_name', label: 'Supplier' },
      { key: 'sku', label: 'SKU', render: (r) => `${esc(r.sku)}<div class="sub2">${esc(r.warehouse_name)}</div>` },
      { key: 'qty_ordered', label: 'Qty', num: true, render: (r) => num(r.qty_ordered) },
      { key: 'days_overdue', label: 'Overdue', num: true, render: (r) => `<b style="color:#b91c1c">${r.days_overdue} d</b>` },
    ], O, { sortable: true, sortKey: 'days_overdue', empty: 'No overdue purchase orders 🎉' });
  }

  function renderInventory(D) {
    const R = D.inventory.risk;
    const fill = (id, vals) => {
      const sel = document.getElementById(id);
      vals.forEach((v) => sel.insertAdjacentHTML('beforeend', `<option>${esc(v)}</option>`));
    };
    fill('f-wh', [...new Set(R.map((r) => r.warehouse_name))].sort());
    fill('f-cat', [...new Set(R.map((r) => r.category))].sort());
    const el = document.getElementById('tbl-risk');
    const cols = riskColumns(false);
    function apply() {
      const wh = document.getElementById('f-wh').value;
      const cat = document.getElementById('f-cat').value;
      const t = document.getElementById('f-tier').value;
      const q = document.getElementById('f-q').value.trim().toLowerCase();
      const rows = R.filter((r) => (!wh || r.warehouse_name === wh) && (!cat || r.category === cat) && (!t || r.risk_tier === t)
        && (!q || `${r.sku} ${r.product_name} ${r.supplier_name}`.toLowerCase().includes(q)));
      const cnt = (tier) => rows.filter((r) => r.risk_tier === tier).length;
      const orderVal = d3.sum(rows.filter((r) => r.risk_tier !== 'Low'), (r) => r.recommended_order_value);
      document.getElementById('risk-chips').innerHTML = `
        <div class="chip"><b style="color:#b91c1c">${cnt('High')}</b>High risk</div>
        <div class="chip"><b style="color:#b45309">${cnt('Medium')}</b>Medium risk</div>
        <div class="chip"><b style="color:#047857">${cnt('Low')}</b>Low risk</div>
        <div class="chip"><b>${rows.filter((r) => r.on_hand_units === 0).length}</b>Out of stock now</div>
        <div class="chip"><b>${inr(orderVal)}</b>Suggested replenishment (high + medium)</div>
        <div class="chip"><b>${rows.filter((r) => r.excess_stock).length}</b>Excess stock (&gt; 90 days cover)</div>`;
      table(el, cols, rows, { sortable: true, sortKey: 'risk_tier' });
    }
    ['f-wh', 'f-cat', 'f-tier'].forEach((id) => document.getElementById(id).addEventListener('change', apply));
    document.getElementById('f-q').addEventListener('input', apply);
    apply();
    register('ch-inv', (el2) => invChart(el2, D.inventory.value_trend));
  }

  function renderForecast(D) {
    const P = D.forecast.products;
    const S = D.forecast.summary;
    const sel = document.getElementById('f-prod');
    d3.groups(P, (p) => p.category).forEach(([cat, items]) => {
      sel.insertAdjacentHTML('beforeend', `<optgroup label="${esc(cat)}">${items.map((p) => `<option value="${p.product_id}">${esc(p.product_name)} (${esc(p.sku)})</option>`).join('')}</optgroup>`);
    });
    function show() {
      const p = P.find((x) => x.product_id === sel.value) || P[0];
      document.getElementById('fc-title').textContent = `Daily demand forecast · ${p.product_name} (all warehouses)`;
      document.getElementById('fc-stats').innerHTML = `
        <div><b>${num(p.next_28d_total)}</b>units next 28 days</div>
        <div><b>${(100 * (1 - p.holdout_wape)).toFixed(1)}%</b>accuracy (1 − WAPE)</div>
        <div><b>${(100 * p.naive_wape).toFixed(1)}%</b>naive WAPE</div>
        <div><b>α ${p.params.alpha} · β ${p.params.beta} · γ ${p.params.gamma}</b>fitted parameters</div>`;
      register('ch-fc', (el) => forecastChart(el, p));
    }
    sel.addEventListener('change', show);
    const best = P.slice().sort((a, b) => b.next_28d_total - a.next_28d_total)[0];
    sel.value = best.product_id;
    show();
    document.getElementById('fc-method').textContent = `${S.method} · avg WAPE ${(S.avg_wape * 100).toFixed(1)}% vs naive ${(S.avg_naive_wape * 100).toFixed(1)}%`;
    const acc = P.map((p) => ({ name: `${p.product_name}`, model: 100 * (1 - p.holdout_wape), naive: 100 * (1 - p.naive_wape) })).sort((a, b) => b.model - a.model);
    register('ch-acc', (el) => hbar(el, acc, {
      value: (d) => d.model, label: (d) => d.name, color: (d) => (d.model >= d.naive ? COLORS.blue : COLORS.slate), format: (v) => `${v.toFixed(0)}%`, domainMax: 100,
      tipHtml: (d) => `<b>${esc(d.name)}</b><br>Holt-Winters accuracy: ${d.model.toFixed(1)}%<br>Seasonal-naive accuracy: ${d.naive.toFixed(1)}%`,
    }));
  }

  function renderPipeline(D) {
    const e = D.meta.etl;
    document.getElementById('etl-meta').textContent = `Last run ${new Date(D.meta.generated_at).toLocaleString('en-IN')} · ${e.duration_sec}s`;
    const steps = [
      ['1 · Extract', 'Raw CSV exports', 'Sales, inventory, purchase orders, suppliers, products, warehouses'],
      ['2 · Transform', 'Clean & validate', 'Trim, standardise, de-duplicate, business-rule checks, rejects quarantined'],
      ['3 · Model', 'Star schema', '4 dimensions + 3 fact tables with surrogate keys and OTIF / delay flags'],
      ['4 · Load', 'SQLite / SQL Server', 'Single-transaction full refresh, FK + data-quality checks'],
      ['5 · Analyse', 'Python models', 'Supplier scoring, stockout probability, Holt-Winters forecasts'],
      ['6 · Publish', 'Dashboard + Power BI', 'This web app, plus CSV exports for the Power BI model'],
    ];
    document.getElementById('flow').innerHTML = steps.map(([n, t, d], i) => `${i ? '<div class="arrow">→</div>' : ''}<div class="step"><div class="n">${n}</div><h3>${t}</h3><p>${d}</p></div>`).join('');
    const rejKey = { fact_sales: 'sales', fact_inventory: 'inventory', fact_purchase_orders: 'purchase_orders' };
    const rows = Object.entries(e.rows_loaded).map(([table_, rowsN]) => ({ table: table_, rows: rowsN, dupes: (e.table_stats?.[table_] || {}).duplicates_removed || 0, rejected: e.rejected_rows[rejKey[table_]] || 0 }));
    table(document.getElementById('tbl-etl'), [
      { key: 'table', label: 'Table', render: (r) => `<code>${esc(r.table)}</code>` },
      { key: 'rows', label: 'Rows loaded', num: true, render: (r) => num(r.rows) },
      { key: 'dupes', label: 'Duplicates removed', num: true, render: (r) => (r.dupes ? `<b style="color:#b45309">${r.dupes}</b>` : '0') },
      { key: 'rejected', label: 'Rejected', num: true, render: (r) => (r.rejected ? `<b style="color:#b45309">${r.rejected}</b>` : '0') },
    ], rows);
    document.getElementById('checks').innerHTML = e.quality_checks.map((c) => `<li class="${c.passed ? '' : 'fail'}">${c.passed ? '✔' : '✖'} ${esc(c.check)}</li>`).join('');
  }

  // ---------- tabs ----------
  function setupTabs() {
    const buttons = document.querySelectorAll('.tabs button');
    const go = (name, push = true) => {
      buttons.forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
      document.querySelectorAll('.page').forEach((p) => { p.hidden = p.id !== `tab-${name}`; });
      if (push) history.replaceState(null, '', `#${name}`);
      hideTip();
      renderVisible();
      window.scrollTo({ top: 0 });
    };
    buttons.forEach((b) => b.addEventListener('click', () => go(b.dataset.tab)));
    document.querySelectorAll('[data-goto]').forEach((b) => b.addEventListener('click', () => go(b.dataset.goto)));
    const initial = location.hash.slice(1);
    if ([...buttons].some((b) => b.dataset.tab === initial)) go(initial, false);
  }

  // ---------- boot ----------
  fetch('data/dashboard.json', { cache: 'no-cache' })
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then((D) => {
      const asOf = d3.timeFormat('%d %b %Y')(parseDay(D.meta.data_as_of));
      const nWh = new Set(D.inventory.risk.map((r) => r.warehouse_id)).size;
      document.getElementById('asof').textContent = `Data as of ${asOf} · ${D.forecast.products.length} SKUs · ${nWh} warehouses · ${D.suppliers.length} suppliers`;
      setupTabs();
      renderOverview(D);
      renderSuppliers(D);
      renderDelivery(D);
      renderInventory(D);
      renderForecast(D);
      renderPipeline(D);
      renderVisible();
      document.body.dataset.ready = 'true';
    })
    .catch((err) => {
      document.getElementById('app').innerHTML = `<div class="card empty">Could not load dashboard data (${esc(err.message)}). Run <code>python build_dashboard.py</code> first.</div>`;
    });
})();
