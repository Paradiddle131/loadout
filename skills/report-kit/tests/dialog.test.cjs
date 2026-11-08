#!/usr/bin/env node
// A modal dialog and the stepper on the fixture (tests/fixture.html, "Standing orders"): the dialog opens modal with
// the focus on its heading, a definition inside it shows above it and pins there, the first Escape closes the
// bubble and the second the dialog, and the focus goes back to its opener; Next and Previous keep their places
// while the item changes height. Prints each failed expectation; exit 1 on any.
const path = require('path');
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const page = await (await b.newContext({ viewport: { width: 1024, height: 800 } })).newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  await page.goto('file://' + path.join(__dirname, 'fixture.html'));
  await page.evaluate(() => document.fonts.ready);
  const fails = [];
  const want = (ok, what) => { if (!ok) fails.push(what); };
  const tip = () => page.evaluate(() => {
    const t = document.querySelector('.rk-tip'), r = t.getBoundingClientRect();
    const top = !t.hidden && document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return { shown: !t.hidden, inDialog: !!t.closest('dialog'), onTop: !!top && t.contains(top), pinned: t.classList.contains('is-pinned'),
      x: r.left, y: r.top, inView: r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight };
  });
  const open = () => page.evaluate(() => document.getElementById('how-scored').open);

  // the stepper: Next stays put while the item changes; Previous is disabled at the start and keeps its slot
  const btn = s => page.$eval(`#order-step [data-step="${s}"]`, e => { const r = e.getBoundingClientRect(); return { x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), disabled: e.disabled }; });
  const n0 = await btn(1), p0 = await btn(-1);
  want(p0.disabled, 'Previous is disabled on the first item');
  await page.click('#order-step [data-step="1"]');
  const n1 = await btn(1), p1 = await btn(-1);
  want(n1.x === n0.x && n1.y === n0.y, `Next keeps its place after a press (${n0.x},${n0.y} -> ${n1.x},${n1.y})`);
  want(!p1.disabled && p1.x === p0.x, 'Previous shows in the slot it kept');
  want(/Order 2 of/.test(await page.$eval('#order-step .rk-step-pos', e => e.textContent)), 'the position says the second item');
  for (let i = 0; i < 5; i++) if (!(await btn(1)).disabled) await page.click('#order-step [data-step="1"]');
  want((await btn(1)).disabled, 'Next is disabled on the last item');
  want(await page.evaluate(() => document.activeElement && document.activeElement.matches('#order-step [data-step="-1"]')), 'the focus moves to Previous when Next reaches the end');

  // the dialog
  await page.click('[data-rk-open="how-scored"]');
  want(await open(), 'the button opens the dialog');
  want(await page.evaluate(() => document.activeElement && document.activeElement.id === 'how-h'), 'the focus starts on the dialog\'s heading');
  want(await page.evaluate(() => !!document.querySelector('#how-scored:modal')), 'the dialog is modal');
  await page.hover('#how-scored .rk-term');
  let t = await tip();
  want(t.shown && t.inDialog && t.onTop, `a definition inside the dialog shows above it (shown ${t.shown}, in the dialog ${t.inDialog}, on top ${t.onTop})`);
  await page.keyboard.press('Escape');
  t = await tip();
  want(!t.shown && await open(), 'the first Escape closes the bubble and leaves the dialog open');
  await page.click('#how-scored .rk-term');
  t = await tip();
  want(t.pinned && t.onTop && t.inView, `a click pins the definition inside the dialog, in view (pinned ${t.pinned}, on top ${t.onTop}, in view ${t.inView})`);
  const term = await page.$eval('#how-scored .rk-term', e => { const r = e.getBoundingClientRect(); return { x: r.left, y: r.bottom }; });
  want(Math.abs(t.y - term.y) < 60 && Math.abs(t.x - term.x) < 400, `the pinned bubble sits by its term (bubble ${Math.round(t.x)},${Math.round(t.y)}, term ${Math.round(term.x)},${Math.round(term.y)})`);
  await page.keyboard.press('Escape');
  want(!(await tip()).shown && await open(), 'Escape closes the pinned bubble first');
  await page.keyboard.press('Escape');
  want(!(await open()), 'the next Escape closes the dialog');
  want(await page.waitForFunction(() => document.activeElement && document.activeElement.matches('[data-rk-open="how-scored"]'), null, { timeout: 2000 }).then(() => true, () => false),
    'the focus goes back to the opener');
  // the dialog's close event is queued as a task, so give it a moment
  want(await page.waitForFunction(() => document.querySelector('.rk-tip').parentElement === document.body, null, { timeout: 2000 }).then(() => true, () => false),
    'the bubble goes home when the dialog closes');
  await page.locator('#orders .rk-key [data-tip]').first().scrollIntoViewIfNeeded(); await page.waitForTimeout(100); // a scroll closes the pointer's bubble
  await page.hover('#orders .rk-key [data-tip]');
  t = await tip();
  want(t.shown && !t.inDialog, 'the page\'s definitions still show outside the dialog');
  await page.click('[data-rk-open="how-scored"]');
  await page.click('#how-scored .rk-dialog-close');
  want(!(await open()), 'the close button closes the dialog');
  await b.close();
  errs.forEach(e => fails.push(`page error: ${e}`));
  fails.forEach(f => console.log(`FAIL ${f}`));
  console.log(fails.length ? `${fails.length} problems` : '0 problems');
  process.exit(fails.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
