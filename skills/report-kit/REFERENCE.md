# The kit's contracts

Every component is a CSS file in [`kit/`](kit/) and, where it acts, a JS file whose `init(root)` wires it from `data-*` attributes inside `root`; the build's boot step runs every component's `init` on DOMContentLoaded, on the whole document or on each element the scope names.
Classes start with `rk-`; scripts add one global, `window.ReportKit`.
A generator writes the markup below; the build inlines the rest.

## Build markers

A page names what it uses in three opening markers; `node bin/build.cjs <page.html>` writes the kit's current files after each, up to the closing marker, which it adds when missing.
Running it again replaces what it wrote, so a page is rebuilt in place after a kit change.

```html
<style>
/* report-kit:css tokens base section table-sort tip */
</style>
...
<!-- report-kit:vendor plot -->
<script>
/* report-kit:js table-sort tip */
</script>
```

- `all` names every component; a component brings what it needs (`dots`, `slope` and `highlight` bring `marks`); the CSS list must name `tokens`.
- `node bin/build.cjs --list` prints the components: `tokens base section marks dots bar range grade slope tabs switch table-sort tip highlight plot-theme`.
- `scope=<selector>` in the css and the js marker runs the kit inside part of a page, as in `/* report-kit:css all scope=#report */`: the CSS nests under the selector (`:root` and `body` rules land on the scoped element, so the tokens, the ground and the type stop there), and the scripts wire only what sits inside each match, each with its own bubble.
  The page's own theme switch (`data-theme` on `<html>`) still reaches the scope; `@keyframes` stay global, under their `rk-` names.
  `ReportKit.init(el)` wires an element added later (each element once).
- The vendor marker takes `plot` (d3, then Plot) or `d3`; it sits before the `report-kit:js` script, and the page's own chart code runs after both.
- The page links the face in its `<head>`: `https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;600;700;800&display=swap` (800 is the headings' weight on a dark ground).
- From Python: write the page with the markers, then `subprocess.run(["node", "<skill>/bin/build.cjs", page], check=True)`; [`tests/build_fixture.py`](tests/build_fixture.py) does exactly this.

## Components

| Component | Files | What it does |
|---|---|---|
| `tokens` | css | primitives and semantic tokens, light and dark |
| `base` | css | page ground, type, themed selection, focus ring, scrollbar and links; `.rk-wrap`, `.rk-title`, `.rk-lede`, `.rk-sr` |
| `section` | css | section head (heading over a 2px ink rule, a control beside it), finding rows, glossary; parts, a side column beside a stage, a figure with its key and caption |
| `marks` | css | the five status shapes on `data-k`, and the `.rk-key` legend |
| `dots` | css | a share of 100 as 100 marks |
| `bar`, `range`, `slope` | css | small pictures on the 0-100 scale; `bar` also holds the meter (a number over a thin bar) |
| `grade` | css, js | opt-in: a bar or span coloured by where its value falls on its scale |
| `tabs` | css, js | the page's parts, hash-routed; empty parts drop out |
| `switch` | css, js | a segmented control of two to four views of the same data |
| `table-sort` | css, js | sortable columns, aria-sort, a restorable order, optional row slide, a stacked narrow layout |
| `tip` | css, js | the one definition bubble; optional pin, drag and "more" link |
| `highlight` | css, js | pointing at a category lights its marks; leaving resets them |
| `plot-theme` | css, js | Observable Plot defaults from the tokens, redrawn on theme and width changes |

### Page and section

```html
<main class="rk-wrap">
  <h1 class="rk-title">Delivery options, a twelve-week trial</h1>
  <p class="rk-lede">One sentence on what the page shows.</p>
  <section class="rk-section" aria-labelledby="options-h">
    <div class="rk-head"><h2 id="options-h">Options</h2> <!-- the section's one control, if any; two (a switch and a filter) sit in <div class="rk-head-tools"> --></div>
    ...
  </section>
</main>
```

Finding rows (text left, one picture right, the picture dropping under the text in a narrow container): `<ul class="rk-rows"><li><div><h3>Headline</h3><p>One sentence.</p></div><div class="rk-pic">...</div></li></ul>`.
The headline is `--t-find` at `--w-head`, a size step and two weight steps over its sentence; right under a `.rk-head`, the first row adds no space of its own.
A glossary: `<dl class="rk-glossary"><div id="term-late"><dt>Late</dt><dd>...</dd></div></dl>`; the ids are what a bubble's "more" link points at.

### Levels inside a section

A section holds parts, and a part holds items (STANDARDS.md, Inside a section); each level is set off by its own space token and head:

| Level | Head | Set off by |
|---|---|---|
| section | `h2` in `.rk-head`, `--t-head` | the 2px ink rule under its head; `--gap-section` above |
| part | `h3` at `--t-find`; `h4` at 1rem bold inside a stage | a 1px ink rule above it (`.rk-part`); `--gap-part` above |
| item | `h4` (or a bold lead word), 1rem bold | `--gap-item` above; no rule |

A head sits 6px over its own text, and a paragraph or list right under it adds no space of its own.
A part right under a section head drops its rule (the head's rule is its own).

```html
<div class="rk-split">
  <nav class="rk-aside" aria-labelledby="pick-h"><h3 id="pick-h">Cheapest first</h3>
    <ul><li><a href="#own-van">Own van</a></li><li><a href="#bike" aria-current="true">Bike courier</a></li> ...</ul></nav>
  <div class="rk-stage">
    <h3>Bike courier</h3>
    <p>One sentence on what it is.</p>
    <figure class="rk-fig">(the drawing) <ul class="rk-key">...</ul><figcaption>What the drawing cannot say.</figcaption></figure>
    <div class="rk-parts">
      <div class="rk-part"><h4>What changes from Own van</h4>...</div>
      <div class="rk-part"><h4>On one order</h4>...</div>
    </div>
  </div>
</div>
```

- `.rk-split` lays a side column (`.rk-aside`, on `--panel`) beside a stage (`.rk-stage`, on the ground); the column wraps above the stage once the stage would fall under 60% of the row.
- In the column, a list's links are full-width rows; `aria-current="true"` (or `"page"`) makes the chosen one a reversed plate in bold.
  A picker that changes the stage in place uses buttons with `aria-pressed` or radios with `aria-checked`, styled the same way by the page.
- `.rk-parts` sets sibling parts side by side (each at least 18rem) and stacks them when narrow; each `.rk-part` keeps its own rule, broken by the column gap.
  A lone `.rk-part` anywhere in a section takes the same rule and `--gap-part`.
- `.rk-fig` holds a drawing, its key and its caption: the key and the caption sit `--s2` from what precedes them, the caption last, within the reading measure.
  A chart keeps `.rk-chart`, whose `figcaption` leads as its title with its units.

### Marks

`data-k` takes `ok` (filled circle), `no` (ring), `warn` (square), `bad` (diamond) or `info` (triangle), on `<i class="rk-mark">`, on a dot, on a slope point.
A key: `<ul class="rk-key"><li><span data-tip="..." data-lit="ok"><i class="rk-mark" data-k="ok" aria-hidden="true"></i>On time</span></li></ul>`.

### Dot array

```html
<span class="rk-dots" role="img" aria-label="78 on time, 14 late, 3 damaged, 5 not delivered, of 100 orders">
  <i data-k="ok"></i> ... <!-- exactly 100, in the columns' order -->
</span>
```

`--cols` (default 20) sets the grid width; in a container under 30rem the marks shrink to fit.

### Bar, range, slope

All three sit in a `.rk-pic`, label with `.rk-pl`, and take values from 0 to 100.

```html
<span class="rk-bar"><span class="rk-track" aria-hidden="true"><span class="rk-fill" data-k="warn" style="--v:22"></span></span><b>22</b><span class="rk-sr"> late in 100</span></span>
```

A meter is a number over a thin bar, for a cell in a dense grid: `<span class="rk-meter"><b>66</b><span class="rk-track" aria-hidden="true"><span class="rk-fill" style="--v:66"></span></span></span>`.

A range is the whole rail with a span from `--lo` to `--hi`, each end's number at `--p`; compute `--p` with a `spread(values, gap)` that pushes close labels apart (the fixture's generator has one).
`data-k` on `.rk-span` takes a status colour (`data-g`, a grade); in a range under 20rem wide the two numbers turn outward from their discs, so they cannot meet:

```html
<div class="rk-range"><span class="rk-pl">Weekdays</span>
  <span class="rk-ruler"><span aria-hidden="true">0</span>
    <span class="rk-scale" style="--lo:69;--hi:91"><span class="rk-span" aria-hidden="true"></span>
      <span class="rk-at" style="--p:69"><span class="rk-end rk-term" data-tip="Partner app">69</span></span>
      <span class="rk-at" style="--p:91"><span class="rk-end rk-term" data-tip="Collect in shop">91</span></span></span>
    <span aria-hidden="true">100</span></span></div>
```

A slope panel draws one line per kind in a stretched SVG (`viewBox="0 0 100 100" preserveAspectRatio="none"`, `y = 100 - value`, `vector-effect="non-scaling-stroke"`), and its points and numbers in HTML so text keeps the page's sizes; the panel is `aria-hidden`, so say its figures in an `.rk-sr` sentence beside it:

```html
<div class="rk-slopes"><div class="rk-slope"><span class="rk-pl" aria-hidden="true">Own van</span>
  <div class="rk-slope-plot" aria-hidden="true">
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" focusable="false"><line class="rk-ln" data-k="ok" x1="0" y1="22" x2="100" y2="30" vector-effect="non-scaling-stroke"/></svg>
    <i class="rk-pt" data-k="ok" style="--x:0;--y:78"></i><i class="rk-pt" data-k="ok" style="--x:100;--y:70"></i>
    <b class="rk-n rk-l" style="--y:78">78</b><b class="rk-n rk-r" style="--y:70">70</b></div>
  <div class="rk-xl" aria-hidden="true"><span>Weekdays</span><span>Weekends</span></div></div></div>
```

### Grade

Opt-in, for dense grids (STANDARDS.md says when).
A container with `data-rk-grade="60 80"` (two cut points on the 0-100 scale) gives each `.rk-fill` (by its `--v`) and `.rk-span` (by its `--hi`) inside it `data-g="lo"` under 60, `"mid"` from 60 to 79 and `"hi"` from 80; `data-rk-grade-dir="down"` swaps the ends where lower is better.
A `data-g` the generator wrote stays; `ReportKit.grade(root)` grades rows added later.
Name the cut points in a key, with `.rk-swatch` marks:

```html
<ul class="rk-key"><li><span data-tip="80 or more of 100 on time."><i class="rk-swatch" data-g="hi" aria-hidden="true"></i>80 and over</span></li> ...</ul>
```

The colours are `--grade-hi`, `--grade-mid` and `--grade-lo`, a blue to vermilion pair through a neutral grey, checked with the dataviz skill's validator on both grounds (colour-blind separation between every pair; the grey is neutral by design); a graded container lightens its tracks so every grade keeps 3:1 against its track.

### Tint

Opt-in, for a dense grid of numbers on one 0-100 scale where no cut point means anything to the reader (otherwise grade).
A block with class `rk-tint` and its value in `--v` takes one hue (`--tint`, the right-answer green unless the page sets another) from none at 0 to half strength at 100; `data-rk-tint="down"` on it or a container says lower is better.
The number stays in the cell, so the tint needs no key; ink keeps 4.5:1 on the strongest step on both grounds.

```html
<td class="rk-num" data-v="66"><span class="rk-tint" style="--v:66">66</span></td>
```

### Tabs

```html
<nav class="rk-tabs"><div role="tablist" aria-label="Parts of the page">
  <a role="tab" id="tab-options" href="#options" aria-controls="options">Options</a> ...
</div></nav>
<div id="options" role="tabpanel" aria-labelledby="tab-options">...</div>
<div id="glossary" role="tabpanel" aria-labelledby="tab-glossary" hidden>...</div>
```

- A part with no text loses its tab; with one part left the strip hides.
- The hash names the open part, or any element inside one, which opens that part, scrolls the element into view and flashes it; Back and Forward walk the parts; arrow keys, Home and End move along the strip.
- `ReportKit.tabs.open(id)`; every change fires `rk:tab` on `document` with the part's id.

### Switch

```html
<div class="rk-switch" role="group" aria-label="Days" data-rk-switch="days">
  <button type="button" data-value="weekday" aria-pressed="true">Weekdays</button>
  <button type="button" data-value="weekend" aria-pressed="false">Weekends</button>
</div>
<table ... data-rk-when="days=weekday">...</table>
<table ... data-rk-when="days=weekend" hidden>...</table>
```

Every element with `data-rk-when="<name>=<value>"` shows only while that value is chosen; `ReportKit.switches.set(name, value)`; each change fires `rk:switch` with `{name, value}`.

### Filter

Options a reader may never need, folded behind one button beside the section's head (in `.rk-head-tools` when a switch sits there too); its panel opens over the page, never pushing the content down.

```html
<details class="rk-filter" data-rk-filter><summary>Filter <span class="rk-filter-count"></span></summary>
  <div class="rk-filter-panel"><fieldset><legend>Family</legend>
    <label class="rk-check"><input type="checkbox" checked> Google's agents</label> ...</fieldset>
    <div class="rk-filter-foot"><button type="button" class="rk-filter-reset">Show all</button></div></div></details>
```

The count says how many boxes are off ("2 off"); "Show all" ticks every box and fires one change per box it ticked; Escape or a click outside closes the panel, focus back on its button.
The page filters its own rows on the boxes' `change` events: the component only folds the controls away.

### Sortable table

```html
<div class="rk-table-wrap">
<table class="rk-table rk-stack" data-rk-sort data-rk-flip>
  <caption class="rk-sr">What the table holds</caption>
  <thead><tr>
    <th scope="col" data-sort="default"><button type="button"><span class="rk-label">Option</span></button></th>
    <th scope="col" class="rk-wide">100 orders</th>
    <th scope="col" class="rk-num" data-sort="number"><button type="button" data-lit="ok" data-tip="Arrived within the hour.">
      <i class="rk-mark" data-k="ok"></i><span class="rk-label">On time</span></button></th>
  </tr></thead>
  <tbody><tr><th scope="row">Own van</th><td class="rk-wide">(dots)</td><td class="rk-num" data-v="78">78</td></tr></tbody>
</table></div>
```

- `data-sort`: `default` restores the page's own row order (exactly one column should carry it), `number` sorts highest first on the first press, `text` A to Z; a second press reverses; ties keep the page's order.
- `data-rk-sort="toggle"` makes a two-state table: every press flips its column, nothing resets to the page's order, and no default column is needed (one that is there flips the page's order and its reverse).
  A head may start sorted: write its `aria-sort` and the rows in that order.
- A cell's sort value is its `data-v`, else its text; the direction mark is added when the button has none; a polite live region says what changed, and `data-rk-sort-restored="..."` on the table sets what it says when the page's order comes back.
- The label flows inline in its button: the column's mark stays with the first word and the direction mark with the last, however the label wraps.
- `data-rk-sort-group="name"` links tables (a switch's views of the same rows): a sort on one sorts the others by the same column and direction.
- `data-rk-flip` slides rows to their new places, except under reduced motion.
- `rk-stack` turns each row into a block when the table's wrap is narrower than `data-rk-stack-at` (default `56rem`; rem, em or px): the row head and `.rk-wide` cells span the row, every other value gets its column's label and mark.
  `rk-stack-compact` keeps only the mark beside each number (the words stay for screen readers and for columns without a mark) and lays the header out as a two-column sort bar.
- Each sort fires `rk:sort` on the table with `{table, key, dir}`; `ReportKit.tableSort.apply(table, col, kind, dir)` sorts a table from a page's own script.

### Definition bubble

Any element with `data-tip="..."` gets the bubble on hover, keyboard focus and tap, an `aria-describedby` copy for screen readers when it has none, and `tabindex="0"` when it is not a control.
Words that carry a definition take `class="rk-term"` (a dotted underline in the line colour).
The bubble is one element, made when absent; write it to set options:

```html
<div class="rk-tip" id="rk-tip" data-pin hidden></div>
```

- `data-pin`: a click or Enter on a non-control element pins its definition, with a handle (drag it, or focus it and use the arrow keys; Shift moves further), a close button, and Escape to close; Tab from the element moves into the bubble.
- `data-tip-more="#id"` and `data-tip-more-label="In the glossary"` on the element add a link to a fuller entry, which may sit in another tab.
- `data-tip-title` sets the pinned bubble's title (default: the element's text).
- A bubble opened by the keyboard stays on its element through a scroll (the browser scrolls a focused element into view) and follows it; the pointer's bubble closes on a scroll.
- `ReportKit.tip.show(el)`, `.hide()`, `.pin(el)`, `.unpin()`.

A control (a sort button, a switch segment) may carry a `data-tip`; its click keeps doing its own job and never pins.

### Highlight

A trigger carries `data-lit="<mark kind>"`; its scope is the nearest `data-rk-lit-scope` ancestor, else the nearest table.
Pointing at the trigger, or focusing it from the keyboard, sets `data-rk-lit` on the scope and steps every other mark in it back to 14%; leaving, blurring, Escape, the pointer leaving the window, a switch or a tab change resets it.
A tap lights nothing, so a sort by touch leaves no marks lit; `ReportKit.highlight.off()`.

### Charts

```html
<figure class="rk-chart" id="trend">
  <figcaption>On-time orders in 100, three options over twelve weeks</figcaption>
  <ul class="rk-key">...</ul>
  <div class="rk-chart-plot"></div>
</figure>
<script>
ReportKit.plot(document.getElementById("trend"), (t, width) => ({
  ariaLabel: "One sentence that says the chart",
  height: Math.max(240, t.fontPx * 18),
  y: { domain: [0, 100], label: null },
  marks: [Plot.line(DATA, { x: "week", y: "v", stroke: "name" }), Plot.dot(DATA, { x: "week", y: "v", symbol: "name", fill: "name" })],
}));
</script>
```

- `ReportKit.plotTheme(el)` returns the resolved tokens (`ink`, `paper`, `line`, `ok`, `warn`, `bad`, `info`, `viz` as a list, `font`, `fontPx`) and `options`: the font, ink axes, a light y grid, the series colours as the colour range, and margins scaled to the text size.
- `ReportKit.plot(el, spec)` calls `spec(theme, width)` and merges its options over the defaults (`style`, `x`, `y`, `color` one level deep), draws into `.rk-chart-plot`, and redraws when the theme flips or the width changes; a chart in a hidden tab is drawn once shown.
- Plot cannot read CSS variables: pass colours from `t`, never `var(--...)`, and size anything textual from `t.fontPx`, so a 200% text size still fits.
- Put the units in the caption and the series in an HTML key with the same shapes as the marks; axis labels inside the drawing crowd at large text sizes.

## Tokens

Components read the semantic tokens; primitives (`--porcelain`, `--navy`, `--cobalt` and their dark partners) only feed them.

| Token | Light | Dark | Job |
|---|---|---|---|
| `--paper` | `#f4f6fa` | `#0a1430` | page ground |
| `--ink` | `#0d1b3e` | `#edf1f8` | every word and number, rules, axes |
| `--line` | `#2447c9` | `#86a4ff` | the accent line: focus ring, selection, underlines, the first chart series |
| `--hair` | ink at 16% | ink at 16% | hairlines between rows, tracks |
| `--row` | line at 6% | line at 6% | row hover |
| `--ok`, `--warn`, `--bad`, `--info` | `#0b7d4b`, `#a35f00`, `#cf2a1f`, `#1d6f8c` | `#3fcf8e`, `#f2b23e`, `#ff6a5c`, `#6cc4e0` | status marks, each also a shape |
| `--viz-1` to `--viz-4` | line, `#b83d16`, `#0f7480`, `#7a3b69` | line, `#ff8f6b`, `#4fd1c5`, `#e39ad0` | chart series |
| `--tip`, `--tip-ink` | ink, paper | ink, paper | the bubble, a reversed plate |
| `--shadow` | a soft navy shadow | none | the bubble's lift (a shadow on a dark ground reads as a glow) |
| `--sans` | Atkinson Hyperlegible Next | | the one family |
| `--t-word`, `--t-num`, `--t-find`, `--t-head`, `--t-title`, `--t-tip`, `--t-chart` | 1, 1.375, 1.1875, 1.375, 2, .9375, .875rem | | the type scale |
| `--w-head` | 700 | 800 | heading weight: one step further on a dark ground, where light strokes spread |
| `--lh-word`, `--track-word` | 1.45, 0 | 1.5, .01em | the words' leading and tracking, opened a touch on a dark ground |
| `--grade-hi`, `--grade-mid`, `--grade-lo` | `#2447c9`, `#6f778a`, `#b83d16` | `#5b7de8`, `#666e82`, `#e0663c` | value grades (opt-in) |
| `--s1` to `--s7` | 4, 8, 12, 16, 24, 32, 48px | | space |
| `--gap-section`, `--gap-part`, `--gap-item` | 64, 32, 12px | | the space above a section, a part, an item |
| `--panel` | `#ffffff` | `#1c2640` | the one raised surface, for a side column: a step lighter than the ground in both themes |

Every status and series colour reaches 4.5:1 on its ground, so it can also colour text.

### Beside draw-architecture

A report and a diagram from `loadout:draw-architecture` share their names where they share a job, so one page can hold both:

| report-kit | draw-architecture `kit/sheet.css` | Note |
|---|---|---|
| `--paper` | `--paper` | page ground; the sheet's is a warmer off-white, and an embedded diagram keeps its own |
| `--ink` | `--ink` | words and lines |
| `--line` | `--cobalt` | the one accent pencil; the report names it by job, since its meaning is fixed |
| `--viz-2` | `--vermilion` | the second pencil, a chart series here |
| `--hair` | `--hair` | hairlines |
| `--sans` | `--sans` | Atkinson Hyperlegible Next |
| none | `--muted`, `--mono` | a report has no muted text and no mono face |

Embed a diagram as the light and dark PNGs its checker exports, in a `<picture>`, or inline the sheet; either keeps the diagram's own paper.

## The checker

`node bin/check.cjs <page.html>` loads the page in Chromium at 360, 400, 768, 1024, 1280 and 1440 pixels, light and dark, and again at a 200% browser text size (light), in every tab and every switch view, and reports:

- page-level sideways scroll; text clipped by a box, outside the page, overflowing a hidden box, outside an SVG's viewBox, or on top of other text;
- text under 4.5:1 against what is behind it (3:1 for large text);
- a focusable element whose focus changes nothing visible (at 1280);
- tabs that do not open only their part or leave the URL behind, a switch that shows the wrong views, a sort that disagrees with its `aria-sort` or cannot return to the page's order, a highlight that stays lit after the pointer leaves or a click, a bubble that does not open, close, pin, drag or follow its "more" link;
- a sort whose presses do not go first direction, reverse, and (two-state) reverse again, or that leaves a table in its sort group sorted another way;
- a control it cannot reach or press in time (it scrolls each target into view and lets it settle before pointing at it);
- console and page errors, a web font that did not load, a switch with more than four segments;
- a heading (`h1` to `h4`) paler than the text around it, by its colour or its opacity;
- in the source (the vendored libraries left out): a raw colour outside a `:root` token block (a drawing's own colours inside an `<svg>`, such as a brand mark, are exempt), gradient text, emoji, a banned first font (Inter, Roboto, Arial, Helvetica), dark tokens missing one of the three blocks.

Visibility is judged with `checkVisibility({visibilityProperty: true})`, so a part hidden by `visibility` is not measured.
[`tests/scope.test.cjs`](tests/scope.test.cjs) checks a scoped page ([`tests/scoped.html`](tests/scoped.html)): the host keeps its look and the kit works inside its scope.
`--quick` checks 400 and 1280 only; `--shots <dir>` saves a full-page PNG per width and theme; `--selftest <page.html>` plants one case of each geometry kind in the page and fails unless each is found.

## Vendored libraries

[`kit/vendor/`](kit/vendor/) holds Observable Plot 0.6.17 (`package/dist/plot.umd.min.js`) and d3 7.9.0 (`package/dist/d3.min.js`), each the unmodified file from its npm tarball, stored gzipped, with their ISC licences.
`kit/vendor/checksums.txt` holds the sha256 of each file as published; the build decompresses, refuses a file whose sha256 differs, and inlines it.
To update: download the tarball from the npm registry, check its sha512 against the registry's `dist.integrity`, gzip the UMD build here under a versioned name (`gzip -9n`), replace its line in `checksums.txt` with the plain file's `sha256sum`, and update `VENDOR` in [`bin/build.cjs`](bin/build.cjs).
Pin a release at least two weeks old.
