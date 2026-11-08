#!/usr/bin/env node
// The glossary on the fixture (tests/fixture.html, "Glossary"): typing narrows the entries in place and says the count
// as a status, a type chip shows one group and each chip counts the matches in its type, a group with no match hides,
// nothing matching says so with a button that clears the box, and a link to an entry a search hides brings it back.
// The list runs in the page's flow: no box inside it scrolls. Prints each failed expectation; exit 1 on any.
const path = require('path');
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const page = await (await b.newContext({ viewport: { width: 400, height: 800 } })).newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  await page.goto('file://' + path.join(__dirname, 'fixture.html') + '#glossary');
  await page.evaluate(() => document.fonts.ready);
  const fails = [];
  const want = (ok, what) => { if (!ok) fails.push(what); };
  const state = () => page.evaluate(() => {
    const list = document.getElementById('glossary-list');
    const shown = [...list.querySelectorAll('[data-rk-find-item]')].filter(e => !e.hidden).map(e => e.id);
    const groups = [...list.querySelectorAll('[data-rk-find-group]')].filter(g => !g.hidden).map(g => g.dataset.rkFindGroup);
    const chips = Object.fromEntries([...document.querySelectorAll('.rk-chips button')].map(c => [c.dataset.value || 'all', { n: +c.querySelector('.rk-chip-n').textContent, on: c.getAttribute('aria-pressed') === 'true' }]));
    return { shown, groups, chips, count: document.querySelector('.rk-find-count').textContent, none: !list.querySelector('.rk-find-none').hidden,
      label: document.querySelector('.rk-find-box').checkVisibility(), nested: [...list.querySelectorAll('*'), list].some(e => /auto|scroll/.test(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 1) };
  });
  let s = await state();
  want(s.shown.length === 9 && s.groups.length === 2, `every entry shows at first (${s.shown.length}, ${s.groups.length} groups)`);
  want(s.count === '9 terms', `the count says the whole list ("${s.count}")`);
  want(s.label, 'the find box has its label in sight');
  want(!s.nested, 'no box in the list scrolls up and down');
  want(s.chips.all.on && s.chips.all.n === 9 && s.chips.option.n === 5 && s.chips.outcome.n === 4, 'each chip counts its type');

  await page.fill('.rk-find-box input', 'van');
  s = await state();
  want(s.shown.join() === 'term-own-van,term-shared-van', `typing narrows the list (${s.shown})`);
  want(s.groups.join() === 'option', 'a group with no match hides');
  want(s.count === '2 of 9 terms shown', `the count follows ("${s.count}")`);
  want(s.chips.option.n === 2 && s.chips.outcome.n === 0, 'each chip counts the matches in its type');

  await page.fill('.rk-find-box input', '');
  await page.click('.rk-chips button[data-value="outcome"]');
  s = await state();
  want(s.shown.length === 4 && s.groups.join() === 'outcome' && s.chips.outcome.on && !s.chips.all.on, 'a chip shows one type, pressed alone');

  await page.fill('.rk-find-box input', 'zzz');
  s = await state();
  want(s.none && s.shown.length === 0, 'nothing matching says so');
  await page.click('.rk-find-none button');
  s = await state();
  want(s.shown.length === 9 && s.chips.all.on && !s.none, 'its button clears the box and the type');
  want(await page.evaluate(() => document.activeElement && document.activeElement.matches('.rk-find-box input')), 'the focus goes back to the box');

  // a link to an entry the search hides brings it back
  await page.fill('.rk-find-box input', 'van');
  await page.evaluate(() => { location.hash = '#term-late'; });
  await page.waitForTimeout(150);
  want(await page.evaluate(() => { const e = document.getElementById('term-late'); return !e.hidden && e.checkVisibility(); }), 'a link to a hidden entry brings it back');

  want(!errs.length, `no page errors (${errs.join('; ')})`);
  await b.close();
  for (const f of fails) console.log(`FAIL ${f}`);
  console.log(fails.length ? `${fails.length} failed` : 'find: all passed');
  process.exit(fails.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
