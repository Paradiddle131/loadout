# The sheet's API

`Sheet(svg, options)` draws on an `<svg class="sheet">`; the template wires it up after `Sheet.ready()`, which loads the three faces first, so text widths are measured in the real fonts (`document.fonts.ready` alone resolves before a lazily loaded face is used).
Any text, and any logo id, may be a value per mode: `{lab: '…', gcp: '…'}`.

## Options

| Option | Meaning |
|---|---|
| `style` | `'sheet'` (default) or `'board'` ([SKILL.md](SKILL.md#two-styles)); only the stylesheet changes |
| `headline` | the sheet's one line above the drawing: the question it answers or its takeaway, at most 60 characters, no full stop; the kit sets it at the top left and the drawing starts at `S.TOP` (64) or below |
| `logos` | `LOGOS`, which `bin/build.cjs` inlines with every id the sheet passes to `logo:` |
| `modes` | `[{id, label}, …]`, the first is the default and the PNG's; omit for one world |
| `solidIn` | the mode id where chain lines turn solid (the thing is real there) |
| `bar`, `storageKey` | the element the switch goes in, and the `localStorage` key that remembers the choice (`?mode=<id>` overrides, `?static` hides the switch) |

## Calls

| Call | Draws |
|---|---|
| `S.frame({x, y, w, h, title, note, logo, edge})` | a boundary: no fill, `[logo] title note` knocked into its top line, or its bottom line with `edge: 'bottom'` (a title block, when edges enter from above) |
| `S.card({x, y, w, h, title, lines, pkg, hatch, cls, tcls, logo})` | a card; `lines` are sans strings or `{mono: '…'}`; `pkg: 'name'` makes it a grey package card with the name above the title; `hatch: true` hatches it (the model); `cls: 'phantom'` gives it a chain outline, `'quiet'` a grey one; `tcls: 'mono'` sets the title as an identifier; `accent: 'teal' \| 'violet' \| 'amber'` marks its role with a bar in the board style |
| `S.phantom({x, y, w, h, label})` | a chain-line outline round a group, its label knocked into the top line at the right |
| `S.region({x, y, w, h, tone, title, role, edge})` | a role or trust region: a cobalt or vermilion outline (grey without `tone`), title left and role right in its top line, or its bottom line with `edge: 'bottom'` |
| `S.edge(d, {reads, tone, thin, both, noEnd, label, labels})` | a path (`M…H…V…`, right angles); `reads` dashes it, `tone: 'cobalt' \| 'vermilion'` colours it, `thin` greys it; a label is `{text, at: [x, y], anchor, mono}` |
| `S.tick(x, y)`, `S.equal(x, y)` | a check on a hop; a parity mark |
| `S.step(x, y, n)` | a numbered badge on an edge of the main path, raised above every edge (a filled cobalt dot in the board, an ink ring in the sheet) |
| `S.text(parent, x, y, s, cls, attrs)` | loose text (classes: `title`, `sub`, `mono`, `mono dim`, `elabel`) |
| `S.legend(x, y, [[kind, label], …], {column})` | a legend laid out left to right, or top to bottom with `column: true` (for a margin beside a tall sheet); kinds: `card`, `pkg`, `hatch`, `phantom`, `calls`, `reads`, `cobalt`, `vermilion`, `tick`, `equal`, `step`, `teal`, `violet`, `amber` |
| `S.done({unmarked})` | bands the frames by depth, bridges crossing edges, builds the switch, applies a saved or requested mode, and tells the checker the sheet is drawn: call it last; `unmarked: {id: 'why'}` lists a registry technology the sheet names without its logo, with the reason |

## Layout habits that pass the checker first time

- The headline holds the top 64 units: the first frame line or card sits at y 64 or a little below, and the viewBox is that much taller.
- Cards on a 4-unit grid, 32 between columns, 12 to 16 inside a frame's edge (8 at the least, which the checker holds); a card is 44 high with one line, 56 to 64 with two, plus 15 per further line.
- A label beside a vertical edge starts 8 right of it (`anchor: 'start'`); above a horizontal one, 6 above it, centred; never across a frame line, which is where knock-outs alone may sit.
- An edge between two frames crosses each frame line once, at a right angle; two edges cross only at right angles, at least 6 units from a segment's end, so the kit can bridge them.
- Leave a card's top-right 30 units clear when it carries a logo.
- A step badge (radius 9) sits on a straight run of its edge, at least 12 from a card, a frame line or another badge.
