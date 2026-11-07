/* draw-architecture: the drawing API. bin/build.cjs inlines this file into each diagram between the
   sheet:js markers; edit it here, never in a copy. SKILL.md documents the calls. */
function Sheet(svg, opt = {}) {
  const NS = 'http://www.w3.org/2000/svg';
  const LOGO = 14; // the one logo size on every sheet, in user units
  const INSET = 8; // a card's logo slot: this far in from its right edge, centred on its first text row
  const modes = opt.modes ?? [];
  const ids = modes.map(m => m.id);
  let mode = ids[0] ?? null;
  const logos = opt.logos ?? {};
  const swaps = []; // run in creation order on every mode change
  const phantoms = []; // chain-line outlines that go solid in opt.solidIn
  const frames = []; // every frame, for the depth banding done() applies
  const knocks = []; // every knock-out, painted by done() to match what lies behind each half
  const edges = []; // every edge, for the bridges done() draws where two cross
  const HOP = 4; // a bridge's radius
  const HEAD = [24, 32]; // the headline's baseline start; the drawing starts at TOP or below
  const TOP = 64;

  const isModal = v => v !== null && typeof v === 'object' && !Array.isArray(v) && ids.some(i => i in v);
  const pick = v => (isModal(v) ? v[mode] : v);
  const el = (tag, attrs = {}, parent = svg) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) n.setAttribute(k, v);
    (parent ?? svg).appendChild(n);
    return n;
  };
  const text = (parent, x, y, s, cls, attrs = {}) => {
    const t = el('text', { x, y, class: cls, ...attrs }, parent);
    const set = () => { t.textContent = pick(s) ?? ''; };
    set();
    if (isModal(s)) swaps.push(set);
    return t;
  };
  const len = t => (t.textContent ? t.getBBox().width : 0); // the glyphs' box, wider than the advance in some fonts
  // A knock-out: the patch of a line a title sits on, in two halves (above and below the line), so each
  // half takes the fill of whatever surrounds it once done() knows the banding.
  const knock = (y, parent = svg, before = null) => {
    const g = document.createElementNS(NS, 'g');
    parent.insertBefore(g, before);
    const halves = [el('rect', { y: y - 8, height: 8, class: 'knock' }, g), el('rect', { y, height: 8, class: 'knock' }, g)];
    knocks.push(...halves);
    return { set: (x, w) => halves.forEach(r => { r.setAttribute('x', x); r.setAttribute('width', w); }) };
  };

  // A logo: a registry mark in a fixed 14-unit box, drawn only through a card's or a frame's slot.
  const logo = (parent, id, slot) => {
    const box = el('svg', { width: LOGO, height: LOGO, viewBox: '0 0 24 24', class: 'logo', 'data-slot': slot }, parent);
    const set = () => {
      const now = pick(id);
      if (now && !logos[now]) throw new Error(`draw-architecture: no logo "${now}" in the registry`);
      // both copies are drawn; the sheet's CSS shows the colour one, or the one-ink copy in a theme where
      // the registry measured the colours as not reading against the card
      box.innerHTML = now ? `<g class="lc">${logos[now].body}</g><g class="lm">${logos[now].mono}</g>` : '';
      if (now) Object.assign(box.dataset, { logo: now, light: logos[now].light, dark: logos[now].dark });
      else box.removeAttribute('data-logo');
      box.style.display = now ? '' : 'none';
    };
    set();
    if (isModal(id)) swaps.push(set);
    return { box, present: () => !!pick(id) };
  };

  const defs = el('defs');
  for (const [id, color] of [['ink', 'ink'], ['cobalt', 'cobalt'], ['vermilion', 'vermilion'], ['rule', 'rule']]) {
    const m = el('marker', { id: `arrow-${id}`, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' }, defs);
    el('path', { d: 'M1,1.5 L9,5 L1,8.5 z' }, m).style.fill = `var(--${color})`;
  }
  const hatch = el('pattern', { id: 'hatch', patternUnits: 'userSpaceOnUse', width: 7, height: 7, patternTransform: 'rotate(45)' }, defs);
  el('line', { x1: 0, y1: 0, x2: 0, y2: 7, class: 'hatch-line' }, hatch);
  // the depth screen: a fine dot on paper, tiled in the sheet's own units so every screened area and
  // every knock-out half on one lines up dot for dot
  const screen = el('pattern', { id: 'screen', patternUnits: 'userSpaceOnUse', width: 6, height: 6 }, defs);
  el('rect', { width: 6, height: 6, class: 'screen-bg' }, screen);
  el('circle', { cx: 3, cy: 3, r: 0.75, class: 'screen-dot' }, screen);

  // The headline: the one line above the drawing that says the question the sheet answers, or its
  // takeaway; drawn first, at the top left, so the drawing starts below it (the checker holds the rest).
  if (opt.headline !== undefined) text(svg, HEAD[0], HEAD[1], opt.headline, 'headline');

  // A frame: no fill; [logo] title and note knocked into its top line, or its bottom line with
  // edge: 'bottom' (a title block, for a frame that edges enter from above).
  const frame = ({ x, y: top, w, h, title, note, logo: id, edge: side = 'top' }) => {
    const y = side === 'bottom' ? top + h : top;
    frames.push({ x, y: top, w, h, rect: el('rect', { x, y: top, width: w, height: h, rx: 2, class: 'frame' }) });
    const k = knock(y);
    const g = el('g');
    const lg = id ? logo(g, id, 'frame') : null;
    const t = text(g, 0, y + 4.5, title, 'ftitle');
    const n = note ? text(g, 0, y + 4, note, 'sub') : null;
    const fit = () => {
      let cx = x + 16;
      if (lg?.present()) { lg.box.setAttribute('x', cx); lg.box.setAttribute('y', y - LOGO / 2); cx += LOGO + 6; }
      t.setAttribute('x', cx); cx += len(t);
      if (n) { n.setAttribute('x', cx + 10); cx += 10 + len(n); }
      k.set(x + 10, cx - x - 4);
    };
    fit(); swaps.push(fit);
  };

  // A card: an optional overline (the package a grey card is), a title, then lines: a string is sans,
  // {mono: '...'} is mono; any text may be {<mode>: '...'}. The logo sits in the top-right slot.
  const card = ({ x, y, w, h, title = '', lines = [], pkg, hatch: hatched, cls = '', tcls = 'title', logo: id }) => {
    const g = el('g');
    const r = el('rect', { x, y, width: w, height: h, rx: 2, class: `card ${pkg ? 'pkg' : ''} ${cls}` }, g);
    if (cls.includes('phantom')) phantoms.push(r);
    if (hatched) el('rect', { x: x + 0.5, y: y + 0.5, width: w - 1, height: h - 1, fill: 'url(#hatch)' }, g);
    const halo = hatched ? ' halo' : '';
    let ty = lines.length || pkg ? y + 19 : y + h / 2 + 4.5;
    const row = pkg ? y + 13 : ty - 4.5; // the optical middle of the first text row
    if (pkg) { text(g, x + 12, y + 17, pkg, 'over' + halo); ty = y + 34; }
    text(g, x + 12, ty, title, tcls + halo);
    lines.forEach((line, i) => {
      const y1 = ty + 16 + i * 15;
      const mono = line !== null && typeof line === 'object' && 'mono' in line;
      text(g, x + 12, y1, mono ? line.mono : line, (mono ? 'mono dim' : 'sub') + halo);
    });
    if (id) { const lg = logo(g, id, 'card'); lg.box.setAttribute('x', x + w - INSET - LOGO); lg.box.setAttribute('y', row - LOGO / 2); }
    return r;
  };

  // A chain-line outline round a group of cards, its label knocked into the top line at the right.
  const phantom = ({ x, y, w, h, label }) => {
    const r = el('rect', { x, y, width: w, height: h, rx: 2, class: 'outline phantom' }); // solid in solidIn: 'outline' alone
    phantoms.push(r);
    if (label) {
      const k = knock(y);
      const t = text(svg, x + w - 16, y + 4.5, label, 'mono', { 'text-anchor': 'end' });
      const fit = () => { const l = len(t); k.set(x + w - 22 - l, l + 12); };
      fit(); swaps.push(fit);
    }
    return r;
  };

  // A role or trust region: one coloured outline; its title left and its role right, knocked into its
  // top line, or its bottom line with edge: 'bottom' (when the top line sits close under a frame title).
  const region = ({ x, y: top, w, h, tone = '', title, role, edge: side = 'top' }) => {
    const y = side === 'bottom' ? top + h : top;
    el('rect', { x, y: top, width: w, height: h, rx: 2, class: `region ${tone}` });
    const g = el('g');
    const tc = tone ? ` ${tone}-text` : '';
    const parts = [];
    if (title) parts.push([text(g, x + 12, y + 4.5, title, 'title' + tc), 'start']);
    if (role) parts.push([text(g, x + w - 12, y + 4, role, 'mono' + tc, { 'text-anchor': 'end' }), 'end']);
    for (const [t, side] of parts) {
      const k = knock(y, svg, g);
      const fit = () => { const l = len(t); k.set(side === 'start' ? x + 6 : x + w - 18 - l, l + 12); };
      fit(); swaps.push(fit);
    }
  };

  // An edge: an SVG path; tone colours it, reads dashes it, thin greys it; labels sit where `at` says.
  const edge = (d, o = {}) => {
    const tone = o.tone ?? (o.thin ? 'rule' : 'ink');
    const cls = ['edge', o.reads ? 'reads' : '', o.thin ? 'thin' : '', o.tone ?? ''].join(' ');
    const marker = `url(#arrow-${tone})`;
    edges.push({ d, path: el('path', { d, class: cls, 'marker-end': o.noEnd ? null : marker, 'marker-start': o.both ? marker : null }) });
    for (const l of o.labels ?? (o.label ? [o.label] : [])) {
      const t = text(svg, l.at[0], l.at[1], l.text, `elabel${l.mono ? ' mono' : ''}${o.tone ? ` ${o.tone}-text` : ''}`, { 'text-anchor': l.anchor ?? 'middle' });
      t.dataset.edgeLabel = '1';
    }
  };

  // Marks: a check that runs on every build, drawn on the hop it checks; an equality (parity) mark.
  const tick = (x, y, parent = svg) => {
    el('circle', { cx: x, cy: y, r: 6, class: 'mark' }, parent);
    el('path', { d: `M${x - 3},${y} l2,2.2 l4,-4.4`, class: 'mark-ink' }, parent);
  };
  const equal = (x, y, parent = svg) => {
    el('circle', { cx: x, cy: y, r: 6.5, class: 'mark' }, parent);
    text(parent, x, y + 4, '=', 'mono', { 'text-anchor': 'middle' });
  };

  // A legend that lays itself out from (x, y), left to right, or top to bottom with {column: true} (in a
  // margin beside the sheet); each item is [kind, label].
  const legend = (x, y0, items, { column = false } = {}) => {
    let y = y0;
    const g = el('g', { class: 'legend' });
    const sw = {
      card: cx => el('rect', { x: cx, y: y - 8, width: 30, height: 16, rx: 2, class: 'card' }, g),
      pkg: cx => el('rect', { x: cx, y: y - 8, width: 30, height: 16, rx: 2, class: 'card pkg' }, g),
      hatch: cx => { el('rect', { x: cx, y: y - 8, width: 30, height: 16, rx: 2, class: 'card' }, g); el('rect', { x: cx + 0.5, y: y - 7.5, width: 29, height: 15, fill: 'url(#hatch)' }, g); },
      phantom: cx => el('path', { d: `M${cx},${y} H${cx + 30}`, class: 'phantom' }, g),
      calls: cx => el('path', { d: `M${cx},${y} H${cx + 30}`, class: 'edge', 'marker-end': 'url(#arrow-ink)' }, g),
      reads: cx => el('path', { d: `M${cx},${y} H${cx + 30}`, class: 'edge reads', 'marker-end': 'url(#arrow-ink)' }, g),
      cobalt: cx => el('rect', { x: cx, y: y - 8, width: 30, height: 16, rx: 2, class: 'region cobalt' }, g),
      vermilion: cx => el('rect', { x: cx, y: y - 8, width: 30, height: 16, rx: 2, class: 'region vermilion' }, g),
      tick: cx => tick(cx + 15, y, g),
      equal: cx => equal(cx + 15, y, g),
    };
    let cx = x;
    for (const [kind, label] of items) {
      sw[kind](cx);
      const t = text(g, cx + 40, y + 4, label, 'sub');
      if (column) y += 28; else cx += 40 + len(t) + 32;
    }
    return column ? y : cx;
  };

  // The mode switch: buttons in `bar`, remembered per page, overridden by ?mode=<id>; ?static hides it.
  const setMode = m => {
    mode = m;
    swaps.forEach(f => f());
    phantoms.forEach(r => r.classList.toggle('phantom', m !== opt.solidIn));
    opt.bar?.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === m)));
    try { if (opt.storageKey) localStorage.setItem(opt.storageKey, m); } catch (e) { /* storage off */ }
  };
  // Depth banding: a frame inside an odd number of frames (a second, fourth, ... level) is screened with
  // a fine dot pattern, the levels between stay paper, the outermost have no fill. Frames move beneath
  // everything, outermost first, and each knock-out half takes the fill of the frame it sits in.
  const inside = (a, b) => a !== b && a.x >= b.x && a.y >= b.y && a.x + a.w <= b.x + b.w && a.y + a.h <= b.y + b.h;
  const band = () => {
    for (const f of frames) f.depth = frames.filter(o => inside(f, o)).length;
    for (const f of frames) f.rect.classList.add(f.depth === 0 ? 'band-open' : f.depth % 2 ? 'band-tint' : 'band-paper');
    const first = svg.querySelector('defs')?.nextSibling ?? svg.firstChild;
    for (const f of [...frames].sort((a, b) => a.depth - b.depth)) svg.insertBefore(f.rect, first);
    for (const r of knocks) {
      const c = { x: +r.getAttribute('x') + 1, y: +r.getAttribute('y') + 4, w: 0, h: 0 };
      const home = frames.filter(f => inside(c, f) || (c.x >= f.x && c.x <= f.x + f.w && c.y > f.y && c.y < f.y + f.h)).sort((a, b) => b.depth - a.depth)[0];
      r.classList.toggle('tint', !!home && home.depth % 2 === 1);
    }
  };

  // Bridges: where two edges cross at right angles, one hops over the other with a small arc, the way a
  // circuit drawing shows wires that do not join. The horizontal one hops, unless the crossing sits too
  // close to its ends, then the vertical one; a crossing neither can take is reported to the checker.
  const bridge = () => {
    const polys = edges.map(e => {
      const out = []; let cur = null, x = 0, y = 0;
      for (const [, c, a] of e.d.matchAll(/([MLHV])\s*([-\d.,\s]+)/gi)) {
        const n = a.trim().split(/[\s,]+/).map(Number);
        if (/m/i.test(c)) { x = n[0]; y = n[1]; cur = [[x, y]]; out.push(cur); continue; }
        if (/h/i.test(c)) x = n[0]; else if (/v/i.test(c)) y = n[0]; else { x = n[0]; y = n[1]; }
        cur.push([x, y]);
      }
      return out;
    });
    const segs = [];
    polys.forEach((ps, ei) => ps.forEach((p, pi) => p.slice(1).forEach((b, si) => {
      const a = p[si];
      const o = a[1] === b[1] ? 'h' : a[0] === b[0] ? 'v' : 'o';
      segs.push({ ei, pi, si, a, b, o, hops: [] });
    })));
    const between = (v, a, b, m) => v > Math.min(a, b) + m && v < Math.max(a, b) - m;
    let unbridged = 0;
    for (const s1 of segs) for (const s2 of segs) {
      if (s1.ei >= s2.ei || s1.o === s2.o || s1.o === 'o' || s2.o === 'o') continue;
      const [h, v] = s1.o === 'h' ? [s1, s2] : [s2, s1];
      const px = v.a[0], py = h.a[1];
      if (!between(px, h.a[0], h.b[0], 0.5) || !between(py, v.a[1], v.b[1], 0.5)) continue;
      if (between(px, h.a[0], h.b[0], HOP + 2)) h.hops.push(px);
      else if (between(py, v.a[1], v.b[1], HOP + 2)) v.hops.push(py);
      else unbridged++;
    }
    edges.forEach((e, ei) => {
      let d = '', hops = 0;
      polys[ei].forEach((p, pi) => {
        d += `M${p[0][0]},${p[0][1]}`;
        p.slice(1).forEach((b, si) => {
          const sg = segs.find(q => q.ei === ei && q.pi === pi && q.si === si);
          const a = p[si], dir = sg.o === 'h' ? Math.sign(b[0] - a[0]) : Math.sign(b[1] - a[1]);
          for (const at of [...sg.hops].sort((m, n) => (m - n) * dir)) {
            hops++;
            if (sg.o === 'h') d += ` L${at - HOP * dir},${a[1]} A${HOP},${HOP} 0 0 ${dir > 0 ? 1 : 0} ${at + HOP * dir},${a[1]}`;
            else d += ` L${a[0]},${at - HOP * dir} A${HOP},${HOP} 0 0 ${dir > 0 ? 1 : 0} ${a[0]},${at + HOP * dir}`;
          }
          d += ` L${b[0]},${b[1]}`;
        });
      });
      e.path.setAttribute('d', d);
      e.path.dataset.hops = hops;
    });
    svg.dataset.unbridged = unbridged;
  };

  // done({unmarked: {id: 'why'}}): a technology the sheet names without its logo, and why.
  const done = ({ unmarked = {} } = {}) => {
    band();
    bridge();
    const params = new URLSearchParams(location.search);
    if (opt.bar && modes.length > 1) {
      if (params.has('static')) opt.bar.hidden = true;
      const seg = document.createElement('div');
      seg.className = 'seg'; seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', opt.switchLabel ?? 'Which names to show');
      for (const m of modes) {
        const b = document.createElement('button');
        b.type = 'button'; b.dataset.mode = m.id; b.textContent = m.label; b.setAttribute('aria-pressed', String(m.id === mode));
        b.addEventListener('click', () => setMode(m.id));
        seg.appendChild(b);
      }
      opt.bar.appendChild(seg);
      let saved = null;
      try { saved = opt.storageKey ? localStorage.getItem(opt.storageKey) : null; } catch (e) { /* storage off */ }
      const want = params.get('mode') ?? saved;
      if (want && ids.includes(want) && want !== mode) setMode(want);
    }
    window.__sheet = { modes: ids, setMode, mode: () => mode, unmarked };
  };

  return { el, text, frame, card, phantom, region, edge, tick, equal, legend, done, setMode, LOGO, TOP };
}

// Resolves once the sheet's three faces are loaded. document.fonts.ready alone is not enough: a face
// loads lazily, on first use, so text drawn before any mono text exists is measured in a fallback font.
Sheet.ready = () => Promise.all([
  '700 13px "Atkinson Hyperlegible Next"', '400 11px "Atkinson Hyperlegible Next"', '400 11px "Atkinson Hyperlegible Mono"',
].map(f => document.fonts.load(f))).then(() => document.fonts.ready);
