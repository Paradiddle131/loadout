#!/usr/bin/env node
// Refreshes the kit inside draw-architecture diagrams, so each stays one standalone HTML file:
// the sheet's CSS between /* sheet:css */ and /* /sheet:css */, its API between /* sheet:js */ and
// /* /sheet:js */, and between /* sheet:logos */ and /* /sheet:logos */ the registry entries of every
// logo id the diagram quotes ('kubernetes', "dbt"). Usage: node bin/build.cjs <diagram.html>...
const fs = require('fs');
const path = require('path');

const kit = path.join(__dirname, '..');
const css = fs.readFileSync(path.join(kit, 'kit/sheet.css'), 'utf8').trim();
const js = fs.readFileSync(path.join(kit, 'kit/sheet.js'), 'utf8').trim();
const registry = JSON.parse(fs.readFileSync(path.join(kit, 'logos/registry.json'), 'utf8'));

const esc = t => t.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
const region = name => new RegExp(`(${esc(`/* sheet:${name} */`)})[\\s\\S]*?(${esc(`/* /sheet:${name} */`)})`);
const replaceRegion = (src, name, body, file) => {
  const re = region(name);
  if (!re.test(src)) throw new Error(`${file}: no /* sheet:${name} */ ... /* /sheet:${name} */ markers (start from the kit's template.html)`);
  return src.replace(re, (_, a, b) => `${a}\n${body}\n${b}`);
};

const files = process.argv.slice(2);
if (!files.length) { console.error('usage: node bin/build.cjs <diagram.html>...'); process.exit(2); }
for (const file of files) {
  let src = fs.readFileSync(file, 'utf8');
  // Logos the diagram itself quotes, outside the regions the build owns.
  const own = src.replace(region('logos'), '').replace(region('js'), '');
  const quoted = [...own.matchAll(/logo:\s*(\{[^}]*\}|'[^']*'|"[^"]*")/g)].flatMap(m => [...m[1].matchAll(/['"]([\w-]+)['"]/g)].map(q => q[1]));
  const used = [...new Set(quoted.filter(id => registry.logos[id]))];
  const unknown = [...new Set(quoted.filter(id => !registry.logos[id]))];
  if (unknown.length) throw new Error(`${file}: logo ${unknown.map(id => `"${id}"`).join(', ')} not in the registry (bin/add-logo.cjs adds one)`);
  const entries = Object.fromEntries(used.map(id => { const { title, coverage, light, dark, body, mono } = registry.logos[id]; return [id, { title, coverage, light, dark, body, mono }]; }));
  src = replaceRegion(src, 'css', css, file);
  src = replaceRegion(src, 'js', js, file);
  src = replaceRegion(src, 'logos', `const LOGOS = window.LOGOS = ${JSON.stringify(entries, null, 1)};`, file);
  fs.writeFileSync(file, src);
  console.log(`${file}: kit inlined; logos: ${used.join(', ') || 'none'}`);
}
