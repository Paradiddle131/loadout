#!/usr/bin/env node
// Adds (or replaces) a logo in logos/registry.json, in its brand colours and normalised so every logo
// reads at the same size and weight:
//  1. keep the colours: fills, strokes and gradients stay (a <style> block's class paints are inlined first) (gradient ids get the logo's id as a prefix,
//     so two logos on one page never share one); a single-colour mark takes its brand colour (--hex);
//     clip paths, masks, styles and metadata go. A one-ink copy is kept beside it (every paint becomes
//     currentColor) for the theme where the colours do not read;
//  2. fit: the drawing's bounding box is scaled to fill a 24-unit square, centred;
//  3. weigh: rasterised at 240 px, the share of the square the ink covers is measured; a mark denser
//     than the target is shrunk by sqrt(target / coverage) (never below MIN_SCALE), so a solid disc and
//     a thin outline carry about the same ink;
//  4. embolden: a mark lighter than the target keeps the full square and gets a thin stroke (at most
//     MAX_WEIGHT units of 24) until it reaches 80% of the target, as a typeface's optical size would, so an
//     outline does not fade to a hairline at 14 px: a single-colour mark in its colour, a multi-colour
//     mark each shape in its own fill;
//  5. contrast: on each theme's card, the share of its ink pixels at VISIBLE:1 or more against the card
//     is measured; under half, that theme draws the one-ink copy instead. The bar is visibility, not
//     WCAG's 3:1 for graphics: a sheet always prints the technology's name beside its logo, so the
//     logo carries no information of its own, and 3:1 would turn dbt's orange or BigQuery's blue grey.
// Usage: node bin/add-logo.cjs <id> <file.svg> --title "Name" --source <where> --license <licence>
//          [--hex RRGGBB] [--aliases "Name,Other name"]
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const TARGET = 0.36;
const MIN_SCALE = 0.7;
const MAX_WEIGHT = 1.2;
const VISIBLE = 2;
const CARDS = { light: '#ffffff', dark: '#1c1d20' }; // kit/sheet.css --card per theme
const regPath = path.join(__dirname, '..', 'logos', 'registry.json');

const args = process.argv.slice(2);
const flag = name => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : undefined; };
const [id, file] = args;
if (!id || !file || !flag('title') || !flag('source') || !flag('license')) {
  console.error('usage: node bin/add-logo.cjs <id> <file.svg> --title "Name" --source <where> --license <licence> [--hex RRGGBB] [--aliases "A,B"]');
  process.exit(2);
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent('<!doctype html><body></body>');
  // a mask or a filter draws part of the mark (Gemini's full-colour sparkle is blurred shapes under a
  // mask); both are stripped below, so what is left may not be the mark: say so, and look at the proof
  if (/<(mask|filter)\b/.test(fs.readFileSync(file, 'utf8'))) console.warn(`${id}: the source draws with a mask or a filter, which are stripped: check the proof, and prefer a source without them`);
  const out = await page.evaluate(async ({ svgText, id, hex, TARGET, MIN_SCALE, MAX_WEIGHT, CARDS, VISIBLE }) => {
    const NS = 'http://www.w3.org/2000/svg';
    const parse = () => new DOMParser().parseFromString(svgText, 'image/svg+xml').documentElement;
    const strip = root => {
      // a product icon paints by class in a <style> block: inline each class's paint as attributes first
      const rules = {};
      for (const st of root.querySelectorAll('style')) for (const [, sel, body] of st.textContent.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
        const props = Object.fromEntries(body.split(';').map(p => p.split(':').map(v => v.trim())).filter(p => p.length === 2 && /^(fill|stroke|fill-rule|stroke-width)$/.test(p[0])));
        for (const c of sel.split(',')) Object.assign((rules[c.trim().replace(/^\./, '')] ??= {}), props);
      }
      for (const n of root.querySelectorAll('[class]')) for (const c of n.getAttribute('class').split(/\s+/)) for (const [k, v] of Object.entries(rules[c] ?? {})) if (!n.hasAttribute(k)) n.setAttribute(k, v);
      root.querySelectorAll('title, desc, metadata, style, script, clipPath, mask').forEach(n => n.remove());
      // an invisible shape (a product icon's bounding square) would pick up the emboldening stroke
      root.querySelectorAll('[fill="none"]:not([stroke]):not(g):not(svg)').forEach(n => n.remove());
      for (const n of root.querySelectorAll('*')) {
        for (const a of ['clip-path', 'mask', 'filter', 'style', 'class', 'opacity']) n.removeAttribute(a);
        for (const a of [...n.attributes]) if (a.name.includes(':') && a.name !== 'xlink:href') n.removeAttribute(a.name);
      }
      return root;
    };
    const inner = root => [...root.childNodes].map(n => new XMLSerializer().serializeToString(n)).join('').replace(/ xmlns="[^"]*"/g, '').replace(/\s+/g, ' ').trim();

    // 1. the colour copy: gradient ids prefixed; a single-colour mark painted in its brand colour
    const colour = strip(parse());
    if (colour.nodeName !== 'svg') throw new Error('not an SVG file');
    for (const n of colour.querySelectorAll('[id]')) n.id = `${id}-${n.id}`;
    for (const n of colour.querySelectorAll('*')) {
      for (const a of ['fill', 'stroke']) if (n.hasAttribute(a)) n.setAttribute(a, n.getAttribute(a).replace(/url\(#([^)]+)\)/, `url(#${id}-$1)`));
      for (const a of ['href', 'xlink:href']) if (n.getAttribute(a)?.startsWith('#')) n.setAttribute(a, `#${id}-${n.getAttribute(a).slice(1)}`);
    }
    const rootFill = colour.getAttribute('fill') === 'none' ? 'none' : hex ? `#${hex}` : 'currentColor';
    //    the one-ink copy
    const mono = strip(parse());
    mono.querySelectorAll('defs, linearGradient, radialGradient').forEach(n => n.remove());
    const paint = v => (v && v !== 'none' ? 'currentColor' : v);
    for (const n of mono.querySelectorAll('*')) {
      n.removeAttribute('id');
      if (n.hasAttribute('fill')) n.setAttribute('fill', paint(n.getAttribute('fill')));
      if (n.hasAttribute('stroke')) n.setAttribute('stroke', paint(n.getAttribute('stroke')));
    }
    const monoFill = mono.getAttribute('fill') === 'none' ? 'none' : 'currentColor';
    const vb = colour.getAttribute('viewBox') ?? `0 0 ${parseFloat(colour.getAttribute('width'))} ${parseFloat(colour.getAttribute('height'))}`;
    const colourInner = inner(colour), monoInner = inner(mono);
    //    the colour copy with each painted shape outlined in its own fill, for emboldening a multi-colour mark
    const outlined = colour.cloneNode(true);
    for (const n of outlined.querySelectorAll('path, rect, circle, ellipse, polygon, polyline')) {
      const f = n.getAttribute('fill');
      if (!n.hasAttribute('stroke') && f && f !== 'none') n.setAttribute('stroke', f);
    }
    const outlinedInner = inner(outlined);
    const multi = !hex && /fill="(?!none|currentColor)[^"]+"|stroke="(?!none|currentColor)[^"]+"|Gradient/.test(colourInner);

    // 2. fit the bounding box into the 24-unit square
    const probe = document.createElementNS(NS, 'svg');
    probe.setAttribute('viewBox', vb);
    const g = document.createElementNS(NS, 'g');
    g.innerHTML = monoInner;
    probe.appendChild(g); document.body.appendChild(probe);
    const b = g.getBBox();
    const r = v => Math.round(v * 1e4) / 1e4;
    const wrap = (s, w, fill, body, strokeColour) => {
      const k = ((24 - w) / Math.max(b.width, b.height)) * s; // a stroke of w units stays inside the square
      const tx = 12 - (b.x + b.width / 2) * k, ty = 12 - (b.y + b.height / 2) * k;
      const stroke = w ? `${strokeColour ? ` stroke="${strokeColour}"` : ''} stroke-width="${r(w / k)}" stroke-linejoin="round"` : '';
      return `<g fill="${fill}"${stroke} transform="matrix(${r(k)} 0 0 ${r(k)} ${r(tx)} ${r(ty)})">${body}</g>`;
    };
    const colourBody = (s, w) => (multi && w ? wrap(s, w, rootFill, outlinedInner, null) : wrap(s, w, rootFill, colourInner, hex ? `#${hex}` : 'currentColor'));
    const monoBody = (s, w) => wrap(s, w, monoFill, monoInner, 'currentColor');
    const raster = async (svgBody, bg) => {
      const svg = `<svg xmlns="${NS}" viewBox="0 0 24 24" width="240" height="240" style="color:black">${svgBody}</svg>`;
      const img = new Image();
      img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svg)));
      await img.decode();
      const c = document.createElement('canvas'); c.width = c.height = 240;
      const x = c.getContext('2d');
      if (bg) { x.fillStyle = bg; x.fillRect(0, 0, 240, 240); }
      x.drawImage(img, 0, 0);
      return x.getImageData(0, 0, 240, 240).data;
    };
    // 3. weigh: the share of the square the ink covers
    const coverage = async body => { const d = await raster(body); let ink = 0; for (let i = 3; i < d.length; i += 4) ink += d[i] / 255; return ink / (240 * 240); };
    const full = await coverage(colourBody(1, 0));
    const scale = Math.max(MIN_SCALE, Math.min(1, Math.sqrt(TARGET / full)));
    // 4. embolden a light mark in its own colours
    let weight = 0;
    if (full < 0.8 * TARGET) {
      for (let w = 0.2; w <= MAX_WEIGHT + 1e-9; w += 0.2) { weight = Math.round(w * 10) / 10; if (await coverage(colourBody(1, weight)) >= 0.8 * TARGET) break; }
    }
    // 5. contrast of the colours against each theme's card
    const lum = (r8, g8, b8) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r8) + 0.7152 * f(g8) + 0.0722 * f(b8); };
    const hexRgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
    const themes = {};
    const ink = await raster(colourBody(scale, weight));
    for (const [theme, bg] of Object.entries(CARDS)) {
      const Lb = lum(...hexRgb(bg));
      const d = await raster(colourBody(scale, weight), bg);
      let n = 0, ok = 0;
      for (let i = 0; i < d.length; i += 4) {
        if (ink[i + 3] < 128) continue;
        n++;
        const L = lum(d[i], d[i + 1], d[i + 2]);
        if ((Math.max(L, Lb) + 0.05) / (Math.min(L, Lb) + 0.05) >= VISIBLE) ok++;
      }
      themes[theme] = { share: ok / n, use: ok / n >= 0.5 ? 'colour' : 'mono' };
    }
    return { body: colourBody(scale, weight), mono: monoBody(scale, weight), full, scale, weight, coverage: await coverage(colourBody(scale, weight)), themes, multi };
  }, { svgText: fs.readFileSync(file, 'utf8'), id, hex: flag('hex'), TARGET, MIN_SCALE, MAX_WEIGHT, CARDS, VISIBLE });
  await browser.close();

  const reg = fs.existsSync(regPath) ? JSON.parse(fs.readFileSync(regPath, 'utf8')) : { logos: {} };
  // colours as rgb(): uniform notation, and a hex of digits alone reads as an issue number to the
  // repo's generic-content guard
  const rgb = svg => svg.replace(/#([0-9a-f]{6}|[0-9a-f]{3})(?![\w-])/gi, (_, h) => {
    const x = h.length === 3 ? [...h].map(c => c + c).join('') : h;
    return `rgb(${[0, 2, 4].map(i => parseInt(x.slice(i, i + 2), 16)).join(', ')})`;
  });
  out.body = rgb(out.body); out.mono = rgb(out.mono);
  reg.target_coverage = TARGET;
  reg.logos[id] = {
    title: flag('title'),
    aliases: (flag('aliases') ?? flag('title')).split(',').map(s => s.trim()).filter(Boolean),
    source: flag('source'), license: flag('license'),
    coverage: Math.round(out.coverage * 1000) / 1000, scale: Math.round(out.scale * 1000) / 1000, weight: out.weight,
    light: out.themes.light.use, dark: out.themes.dark.use,
    body: out.body, mono: out.mono,
  };
  reg.logos = Object.fromEntries(Object.entries(reg.logos).sort(([a], [b]) => a.localeCompare(b)));
  fs.writeFileSync(regPath, JSON.stringify(reg, null, 1) + '\n');
  const pct = v => `${Math.round(v * 100)}%`;
  console.log(`${id}: ${out.multi ? 'multi-colour' : 'one colour'}; ink ${pct(out.full)} at full size, scale ${out.scale.toFixed(2)}, weight ${out.weight}, ink now ${pct(out.coverage)}; reads at ${VISIBLE}:1 on light ${pct(out.themes.light.share)} (${out.themes.light.use}), on dark ${pct(out.themes.dark.share)} (${out.themes.dark.use})`);
})().catch(e => { console.error(e.message); process.exit(1); });
