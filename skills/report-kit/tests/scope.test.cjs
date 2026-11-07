#!/usr/bin/env node
// The kit inside part of a page (scope=#report, tests/scoped.html): the host keeps its own look, the scope gets the
// kit's, and the scripts wire what sits inside the scope. Prints each failed expectation; exit 1 on any.
const path = require('path');
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const page = await (await b.newContext({ viewport: { width: 1024, height: 900 } })).newPage();
  await page.goto('file://' + path.join(__dirname, 'scoped.html'));
  await page.evaluate(() => document.fonts.ready);
  const r = await page.evaluate(() => {
    const cs = s => getComputedStyle(document.querySelector(s));
    const report = document.querySelector('#report');
    return {
      hostFont: cs('body').fontFamily, hostH2: cs('#host-h').fontSize, hostGround: cs('body').backgroundColor,
      kitFont: cs('#report').fontFamily, kitGround: cs('#report').backgroundColor, kitH2: cs('#grid-h').fontWeight,
      rootPaper: getComputedStyle(document.documentElement).getPropertyValue('--paper').trim(),
      graded: report.querySelectorAll('.rk-fill[data-g]').length, fills: report.querySelectorAll('.rk-fill').length,
      bubbleInside: !!report.querySelector('.rk-tip'), bubbleOutside: !!document.querySelector('body > .rk-tip'),
    };
  });
  const fails = [];
  const want = (ok, what) => { if (!ok) fails.push(what); };
  want(/Georgia/.test(r.hostFont), `the host keeps its font (got ${r.hostFont})`);
  want(r.hostH2 === '28px', `the host's h2 keeps its size (got ${r.hostH2})`);
  want(r.hostGround === 'rgb(255, 255, 255)', `the host keeps its ground (got ${r.hostGround})`);
  want(/Atkinson/.test(r.kitFont), `the scope gets the kit's font (got ${r.kitFont})`);
  want(r.kitGround === 'rgb(244, 246, 250)', `the scope gets the kit's paper (got ${r.kitGround})`);
  want(r.rootPaper === '', `the tokens stay on the scope, not on :root (got --paper "${r.rootPaper}")`);
  want(r.fills > 0 && r.graded === r.fills, `every bar inside the scope is graded (${r.graded} of ${r.fills})`);
  want(r.bubbleInside && !r.bubbleOutside, 'the bubble lives inside the scope');
  await page.click('#report thead th:nth-child(2) button');
  const sorted = await page.$eval('#report thead th:nth-child(2)', h => h.getAttribute('aria-sort'));
  want(sorted === 'descending', `a sort inside the scope works (aria-sort ${sorted})`);
  await page.hover('#report thead th:nth-child(3) button');
  const tip = await page.$eval('#report .rk-tip', t => !t.hidden && getComputedStyle(t).backgroundColor);
  want(tip && tip !== 'rgba(0, 0, 0, 0)', 'the bubble opens inside the scope, in the kit\'s colours');
  await b.close();
  fails.forEach(f => console.log(`FAIL ${f}`));
  console.log(fails.length ? `${fails.length} problems` : '0 problems');
  process.exit(fails.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
