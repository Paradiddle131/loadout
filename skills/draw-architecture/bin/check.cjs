#!/usr/bin/env node
// Renders draw-architecture diagrams in Chromium, light and dark and in every mode, checks their geometry,
// type, contrast and logos, and exports the PNGs a README embeds (2x, the first mode, light and dark).
// Usage: node bin/check.cjs <diagram.html>... [--out <dir>] [--no-png] [--max-logos <n>]
//        node bin/check.cjs --proof <out.png>      (every registry logo at 14 px and 56 px, both themes)
// Exit 1 when any check fails; each finding names the text, edge or logo and the mode and theme.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const args = process.argv.slice(2);
const opt = name => { const i = args.indexOf(`--${name}`); return i >= 0 ? args.splice(i, 2)[1] : undefined; };
const has = name => { const i = args.indexOf(`--${name}`); return i >= 0 ? (args.splice(i, 1), true) : false; };
const kit = path.join(__dirname, '..');

const COVERAGE = [0.25, 0.4]; // the band add-logo.cjs normalises every mark into
// A headline is read in one glance: 60 characters, a title tag's or a commit subject's length, spans about
// half the sheet at its size and stays legible where a README scales the sheet down.
const HEADLINE_MAX = 60;
// A package card must read apart from a plain card in both themes: the CIELAB lightness step between
// --card and --pkg (light's #fff to #ebeae5 is 7.4; a luminance ratio flattens dark steps, so it is not used).
const PKG_STEP = 6;

// Runs in the page once per theme: the palette's own pairs, which hold whether or not a sheet uses them.
function palette({ pkgStep }) {
  const probe = document.createElement('i');
  document.body.append(probe);
  const rgb = v => { probe.style.color = `var(${v})`; return (getComputedStyle(probe).color.match(/[\d.]+/g) || []).slice(0, 3).map(Number); };
  const lin = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  const lstar = c => { const y = lum(c); return y > 216 / 24389 ? 116 * Math.cbrt(y) - 16 : (y * 24389) / 27; };
  const ratio = (a, b) => { const [l1, l2] = [lum(a), lum(b)].sort((p, q) => q - p); return (l1 + 0.05) / (l2 + 0.05); };
  const out = [];
  const [card, pkg] = [rgb('--card'), rgb('--pkg')];
  const step = Math.abs(lstar(card) - lstar(pkg));
  if (step < pkgStep) out.push(`palette: --pkg is ${step.toFixed(1)} lightness from --card, under ${pkgStep}: a package card reads as a plain one`);
  for (const t of ['--ink', '--muted']) {
    const r = ratio(rgb(t), pkg);
    if (r < 4.5) out.push(`palette: ${t} on --pkg is ${r.toFixed(2)}:1, under 4.5:1`);
  }
  probe.remove();
  return out;
}

// Runs in the page, after the sheet is drawn and set to one mode.
function inspect({ maxLogos, coverage, aliases, headlineMax }) {
  const svg = document.querySelector('svg.sheet');
  const visible = n => { for (let e = n; e && e !== svg; e = e.parentNode) { const s = getComputedStyle(e); if (s.display === 'none' || s.opacity === '0') return false; } return true; };
  const box = n => { const b = n.getBBox(); return { x: b.x, y: b.y, w: b.width, h: b.height }; };
  const userBox = n => { // a nested <svg> (a logo) in the sheet's user units
    const x = +n.getAttribute('x'), y = +n.getAttribute('y');
    return { x, y, w: +n.getAttribute('width'), h: +n.getAttribute('height') };
  };
  const inside = (p, r, pad = 0) => p.x >= r.x - pad && p.x <= r.x + r.w + pad && p.y >= r.y - pad && p.y <= r.y + r.h + pad;
  const overlap = (a, b, pad = 0) => a.x - pad < b.x + b.w && b.x - pad < a.x + a.w && a.y - pad < b.y + b.h && b.y - pad < a.y + a.h;
  const all = sel => [...svg.querySelectorAll(sel)].filter(visible);

  const texts = all('text').filter(t => t.textContent.trim()).map(t => ({ t, s: t.textContent, ...box(t), size: parseFloat(getComputedStyle(t).fontSize) }));
  const cards = all('rect.card:not(.behind)').map(n => ({ n, ...box(n) }));
  const knocks = all('rect.knock').map(n => ({ n, ...box(n) }));
  const outlines = all('rect.frame, rect.region, rect.outline').map(n => ({ n, ...box(n) }));
  const bands = all('rect.frame.band-tint, rect.frame.band-paper').map(n => ({ n, ...box(n) }));
  const edges = all('path.edge');
  const logos = all('svg.logo').filter(n => n.getAttribute('data-logo'));
  const out = [];

  for (const a of texts) {
    if (a.size < 11) out.push(`text under 11 px (${a.size}): "${a.s}"`);
    const anchor = { x: a.x + 1, y: a.y + a.h / 2 };
    const holder = cards.filter(r => inside(anchor, r)).sort((p, q) => p.w * p.h - q.w * q.h)[0];
    if (holder) {
      if (a.x < holder.x + 4 || a.x + a.w > holder.x + holder.w - 4 || a.y < holder.y + 1 || a.y + a.h > holder.y + holder.h - 1) out.push(`text past its card: "${a.s}"`);
    } else for (const r of cards) if (overlap(a, r)) out.push(`text over a card it is not in: "${a.s}"`);
    const core = { x: a.x + 1, y: a.y + 2, w: a.w - 2, h: a.h - 4 };
    for (const e of edges) {
      const L = e.getTotalLength();
      for (let d = 0; d <= L; d += 1.5) if (inside(e.getPointAtLength(d), core)) { out.push(`edge through text: "${a.s}"`); break; }
    }
    // a frame's, region's or chain line's border may pass a text only where a knockout covers it
    for (const f of outlines) {
      const segs = [[f.x, f.y, f.x + f.w, f.y], [f.x, f.y + f.h, f.x + f.w, f.y + f.h], [f.x, f.y, f.x, f.y + f.h], [f.x + f.w, f.y, f.x + f.w, f.y + f.h]];
      for (const [x1, y1, x2, y2] of segs) {
        const steps = Math.max(1, Math.hypot(x2 - x1, y2 - y1) / 2);
        for (let i = 0; i <= steps; i++) {
          const p = { x: x1 + ((x2 - x1) * i) / steps, y: y1 + ((y2 - y1) * i) / steps };
          if (inside(p, core) && !knocks.some(k => inside(p, k))) { out.push(`text on a frame line: "${a.s}"`); i = steps + 1; }
        }
      }
    }
    // contrast against what is behind it: its card's fill, or the paper
    const rgb = c => (c.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
    const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
    const fg = rgb(getComputedStyle(a.t).fill);
    // the band it sits on: the innermost frame with a fill (depth banding), or the paper
    const band = bands.filter(f => inside(anchor, f)).sort((p, q) => p.w * p.h - q.w * q.h)[0];
    // a screened band is paper under fine dots: measure against the paper
    const bandFill = band ? getComputedStyle(band.n).fill : '';
    const bg = rgb(holder ? getComputedStyle(holder.n).fill : band && !bandFill.startsWith('url') ? bandFill : getComputedStyle(document.body).backgroundColor);
    if (fg.length === 3 && bg.length === 3) {
      const [l1, l2] = [lum(fg), lum(bg)].sort((p, q) => q - p);
      const ratio = (l1 + 0.05) / (l2 + 0.05);
      if (ratio < 4.5) out.push(`contrast ${ratio.toFixed(2)}:1 under 4.5:1: "${a.s}"`);
    }
  }
  for (let i = 0; i < texts.length; i++) for (let j = i + 1; j < texts.length; j++) {
    const a = texts[i], b = texts[j];
    if (overlap({ x: a.x, y: a.y + 2, w: a.w, h: a.h - 4 }, { x: b.x, y: b.y + 2, w: b.w, h: b.h - 4 })) out.push(`texts overlap: "${a.s}" / "${b.s}"`);
  }
  // the headline: exactly one, one short line that is not the page title, above everything else
  const heads = all('text.headline');
  if (heads.length !== 1) out.push(heads.length ? `${heads.length} headlines: a sheet carries exactly one` : "no headline: pass Sheet(svg, {headline: '…'}), the question the sheet answers or its takeaway");
  for (const h of heads) {
    const s = h.textContent.trim();
    if (!s) { out.push('the headline is empty'); continue; }
    const n = [...s].length;
    if (n > headlineMax) out.push(`headline of ${n} characters, over ${headlineMax}: "${s}"`);
    if (/\.$/.test(s)) out.push(`headline ends in a full stop: "${s}"`);
    if (/[.!?;]\s/.test(s)) out.push(`headline holds a second sentence: "${s}"`);
    if (s.toLowerCase() === document.title.trim().toLowerCase()) out.push(`headline repeats the <title>: say the question or the takeaway instead: "${s}"`);
    const b = box(h), floor = b.y + b.h + 12;
    if (b.x + b.w > svg.viewBox.baseVal.width - 24) out.push(`headline runs past the sheet: "${s}"`);
    const rest = [...texts.filter(a => a.t !== h).map(a => [`text "${a.s}"`, a]), ...cards.map(c => ['a card', c]), ...outlines.map(f => ['a frame', f]),
      ...edges.map(e => [`edge ${e.getAttribute('d')}`, box(e)]), ...logos.map(l => [`logo "${l.getAttribute('data-logo')}"`, userBox(l)])];
    for (const [what, r] of rest) if (r.y < floor) out.push(`${what} at y ${Math.round(r.y)} reaches the headline: start the drawing at y ${Math.ceil(floor)} or below`);
  }
  // every shape is the kit's: a rect without its classes falls back to SVG's default black fill
  for (const r of all('rect')) if (!r.closest('pattern, marker') && !r.getAttribute('class') && !r.getAttribute('fill')) out.push(`a rect without a kit class at ${Math.round(+r.getAttribute('x'))},${Math.round(+r.getAttribute('y'))} (it would fill black)`);
  // nesting: a box inside another keeps MIN_INSET clear of it on every side (a border never sits on, or
  // a hair inside, its container's), and two boxes either nest or stay apart, never half overlap
  const MIN_INSET = 8;
  const boxes = [...cards.map(b => ({ ...b, kind: 'card' })), ...outlines.map(b => ({ ...b, kind: b.n.classList.contains('frame') ? 'frame' : b.n.classList.contains('region') ? 'region' : 'chain outline' }))];
  const name = b => `${b.kind} at ${Math.round(b.x)},${Math.round(b.y)}`;
  for (const a of boxes) for (const b of boxes) {
    if (a === b || !overlap(a, b)) continue;
    const aInB = a.x >= b.x && a.y >= b.y && a.x + a.w <= b.x + b.w && a.y + a.h <= b.y + b.h;
    const bInA = b.x >= a.x && b.y >= a.y && b.x + b.w <= a.x + a.w && b.y + b.h <= a.y + a.h;
    if (aInB) {
      const gaps = { left: a.x - b.x, right: b.x + b.w - a.x - a.w, top: a.y - b.y, bottom: b.y + b.h - a.y - a.h };
      for (const [side, g] of Object.entries(gaps)) if (g < MIN_INSET) out.push(`${name(a)} sits ${Math.round(g)} from the ${side} of the ${name(b)} around it (keep ${MIN_INSET})`);
    } else if (!bInA && a.x < b.x) out.push(`${name(a)} and ${name(b)} half overlap: nest one in the other or move them apart`);
  }
  // crossings: the kit bridges every one it can; one it could not (too near both ends) is a finding
  const unbridged = Number(svg.dataset.unbridged ?? 0);
  if (unbridged) out.push(`${unbridged} edge crossing(s) too near both segments' ends to bridge: move a lane`);
  let crossings = 0;
  const pts = edges.map(e => { const L = e.getTotalLength(), p = []; for (let d = 3; d <= L - 3; d += 2) p.push(e.getPointAtLength(d)); return p; });
  for (const [k, e] of edges.entries()) {
    const L = e.getTotalLength();
    const ends = [e.getPointAtLength(0), e.getPointAtLength(L)];
    for (const r of cards) {
      if (ends.some(p => inside(p, r, 1))) continue; // leaving a card nested in this one
      const hits = pts[k].filter(p => inside(p, { x: r.x + 3, y: r.y + 3, w: r.w - 6, h: r.h - 6 })).length;
      if (hits > 2) out.push(`edge ${e.getAttribute('d')} runs through a card at ${Math.round(r.x)},${Math.round(r.y)}`);
    }
    // an edge that rides a card's border for a stretch reads as a doubled line
    for (const r of cards) {
      const near = pts[k].filter(p => p.x > r.x + 2 && p.x < r.x + r.w - 2 && p.y > r.y + 2 && p.y < r.y + r.h - 2 ? false
        : (Math.abs(p.y - r.y) < 2 || Math.abs(p.y - r.y - r.h) < 2) && p.x > r.x + 2 && p.x < r.x + r.w - 2
        || (Math.abs(p.x - r.x) < 2 || Math.abs(p.x - r.x - r.w) < 2) && p.y > r.y + 2 && p.y < r.y + r.h - 2).length;
      if (near > 4) out.push(`edge ${e.getAttribute('d')} runs along the border of a card at ${Math.round(r.x)},${Math.round(r.y)}`);
    }
    for (const n of logos) {
      const b = userBox(n);
      if (pts[k].some(p => inside(p, b, 2)) || ends.some(p => inside(p, b, 8))) out.push(`edge ${e.getAttribute("d")} touches logo "${n.getAttribute('data-logo')}"`);
    }
    crossings += Number(e.dataset.hops ?? 0);
  }

  // logos: registry marks only, once each, one size, in a slot, clear of text, normalised ink
  const seen = {};
  for (const n of logos) {
    const id = n.getAttribute('data-logo');
    const b = userBox(n);
    if (seen[id]) out.push(`logo "${id}" appears more than once`);
    seen[id] = true;
    if (!window.LOGOS?.[id]) out.push(`logo "${id}" is not inlined (run bin/build.cjs)`);
    else if (window.LOGOS[id].coverage < coverage[0] || window.LOGOS[id].coverage > coverage[1]) out.push(`logo "${id}" ink ${window.LOGOS[id].coverage} outside ${coverage.join('-')} (re-import it)`);
    if (b.w !== 14 || b.h !== 14) out.push(`logo "${id}" is ${b.w}x${b.h}, not 14x14`);
    const slot = n.getAttribute('data-slot');
    if (slot === 'card') {
      if (!cards.some(r => Math.abs(r.x + r.w - 8 - 14 - b.x) < 0.6 && b.y >= r.y + 4 && b.y + 14 <= r.y + r.h - 4)) out.push(`logo "${id}" is not in a card's slot (8 in from its right edge, inside it)`);
    } else if (slot === 'frame') {
      if (!outlines.some(f => (Math.abs(f.y - (b.y + 7)) < 0.6 || Math.abs(f.y + f.h - (b.y + 7)) < 0.6) && b.x > f.x && b.x < f.x + f.w) || !knocks.some(k => inside({ x: b.x + 7, y: b.y + 7 }, k))) out.push(`logo "${id}" is not in a frame's title line`);
    } else out.push(`logo "${id}" placed by hand: use card({logo}) or frame({logo})`);
    for (const a of texts) if (overlap(a, b, 3)) out.push(`logo "${id}" crowds text "${a.s}"`);
  }
  if (Object.keys(seen).length > maxLogos) out.push(`${Object.keys(seen).length} logos, more than ${maxLogos}: keep the core ones`);
  // completeness: a technology the registry knows, named on the sheet, shows its logo once (or the sheet
  // says why not, in S.done({unmarked}))
  const unmarked = window.__sheet?.unmarked ?? {};
  for (const [id, names] of Object.entries(aliases)) {
    if (seen[id] || unmarked[id]) continue;
    const re = new RegExp(`(?<![\\w.-])(${names.map(n => n.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')).join('|')})(?![\\w-])`);
    const named = texts.find(a => re.test(a.s));
    if (named) out.push(`names ${id} ("${named.s}") without its logo: add it to one card or frame, or say why in S.done({unmarked})`);
  }
  return { problems: [...new Set(out)], crossings, logos: Object.keys(seen) };
}

async function proof(file) {
  const reg = JSON.parse(fs.readFileSync(path.join(kit, 'logos/registry.json'), 'utf8')).logos;
  const css = fs.readFileSync(path.join(kit, 'kit/sheet.css'), 'utf8');
  const logo = (l, n) => `<svg width=${n} height=${n} viewBox="0 0 24 24" class=logo data-light=${l.light} data-dark=${l.dark}><g class=lc>${l.body}</g><g class=lm>${l.mono}</g></svg>`;
  const cell = ([id, l]) => `<div class=c>${logo(l, 14)}${logo(l, 56)}<span class=s>${id}<br>${Math.round(l.coverage * 100)}% ink${l.light === 'mono' ? ', one ink on light' : ''}${l.dark === 'mono' ? ', one ink on dark' : ''}</span></div>`;
  const html = `<style>${css} .grid{display:flex;flex-wrap:wrap;gap:12px;padding:16px;background:var(--paper)} .c{display:flex;align-items:center;gap:12px;width:250px;background:var(--card);border:1px solid var(--hair);padding:8px} .s{font:11px var(--sans);color:var(--muted)}</style><div class=grid>${Object.entries(reg).map(cell).join('')}</div>`;
  const browser = await chromium.launch();
  for (const theme of ['light', 'dark']) {
    const page = await browser.newPage({ viewport: { width: 940, height: 300 }, deviceScaleFactor: 2, colorScheme: theme });
    await page.setContent(html);
    await page.screenshot({ path: theme === 'dark' ? file.replace(/\.png$/, '-dark.png') : file, fullPage: true });
  }
  await browser.close();
  console.log(`proof: ${file} (and -dark), ${Object.keys(reg).length} logos`);
}

(async () => {
  const proofOut = opt('proof');
  if (proofOut) return proof(proofOut);
  const outDir = opt('out');
  const maxLogos = Number(opt('max-logos') ?? 12);
  const aliases = Object.fromEntries(Object.entries(JSON.parse(fs.readFileSync(path.join(kit, 'logos/registry.json'), 'utf8')).logos).map(([id, l]) => [id, l.aliases ?? [l.title]]));
  const png = !has('no-png');
  if (!args.length) { console.error('usage: node bin/check.cjs <diagram.html>... [--out <dir>] [--no-png] [--max-logos <n>] | --proof <out.png>'); process.exit(2); }
  const browser = await chromium.launch();
  let failed = false;
  for (const file of args) {
    for (const theme of ['light', 'dark']) {
      const page = await browser.newPage({ viewport: { width: 1232, height: 900 }, deviceScaleFactor: 2, colorScheme: theme });
      const errors = [];
      page.on('pageerror', e => errors.push(String(e)));
      page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
      await page.goto('file://' + path.resolve(file));
      try { await page.waitForFunction(() => window.__sheet, null, { timeout: 15000 }); } catch { errors.push('the sheet never finished drawing (no S.done())'); }
      const fonts = await page.evaluate(() => [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family));
      if (!fonts.some(f => f.includes('Atkinson'))) errors.push('the Atkinson fonts did not load (offline?): widths would be wrong');
      const pal = await page.evaluate(palette, { pkgStep: PKG_STEP });
      pal.forEach(p => console.log(`    ${path.basename(file)} ${theme}: ${p}`));
      if (pal.length) failed = true;
      const modes = (await page.evaluate(() => window.__sheet?.modes ?? [null])).filter(m => m !== undefined);
      for (const m of modes.length ? modes : [null]) {
        if (m) await page.evaluate(id => window.__sheet.setMode(id), m);
        const r = await page.evaluate(inspect, { maxLogos, coverage: COVERAGE, aliases, headlineMax: HEADLINE_MAX });
        const where = `${path.basename(file)} ${theme}${m ? ` ${m}` : ''}`;
        console.log(`${where}: ${r.problems.length} problems; ${r.crossings} crossings, bridged; logos: ${r.logos.join(', ') || 'none'}`);
        r.problems.forEach(p => console.log('   ', p));
        if (r.problems.length) failed = true;
      }
      errors.forEach(e => console.log(`    error: ${e}`));
      if (errors.length) failed = true;
      if (png) {
        if (modes[0]) await page.evaluate(id => window.__sheet.setMode(id), modes[0]);
        const base = path.join(outDir ?? path.dirname(file), path.basename(file, '.html'));
        const fig = await page.$('figure');
        await fig.screenshot({ path: `${base}${theme === 'dark' ? '-dark' : ''}.png` });
        if (theme === 'dark') {
          // the embed, ready to paste: width only, the sheet's 1x width (the PNG is 2x). GitHub's
          // max-width: 100% scales the width down but keeps an explicit height, stretching the picture.
          const { w, label } = await page.evaluate(() => { const s = document.querySelector('svg.sheet'); return { w: s.viewBox.baseVal.width, label: s.getAttribute('aria-label') }; });
          const name = path.basename(base);
          console.log(`embed (src paths relative to the Markdown file):\n<picture>\n  <source media="(prefers-color-scheme: dark)" srcset="${name}-dark.png">\n  <img width="${w}" alt="${label.replace(/"/g, '&quot;')}" src="${name}.png">\n</picture>`);
        }
      }
      await page.close();
    }
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
