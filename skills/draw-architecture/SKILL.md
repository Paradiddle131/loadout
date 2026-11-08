---
name: draw-architecture
description: "Use when drawing an architecture or system diagram (components, boundaries, flows) for a README, PR, issue or doc, in any repo: the house diagram style, with its kit, logos and checks. Not for charts."
---

A diagram is a **sheet**: black ink on paper, drawn the way a draughtsman would, where every mark means one thing and the legend says what.
This is the house style for architecture and system diagrams: reach for it first, and for another style only when the repo's own `DESIGN.md` asks.
It ships as a kit: one standalone HTML file per diagram, built from [`kit/`](kit/), checked by [`bin/check.cjs`](bin/check.cjs), exported to the light and dark PNGs a README embeds.
The kit draws in two styles, the **sheet** (the default, below) and the **board** ([Two styles](#two-styles)); the drawing, its words and every check are the same in both.

## Steps

1. **Read the system before drawing it.** Every box and arrow comes from the code, its deployment files or its plan, not from memory; note where each fact came from, for the PR.
2. **Pick the one story** the sheet tells (a question's path, a deployment, a data flow) and lay it out in that order, top to bottom or left to right. A second story is a second sheet, one level up or down.
   The **headline** states that story: one line above the drawing, the question the sheet answers or its takeaway (`How a data agent is built, configured and deployed`), at most 60 characters, never a sentence.
3. **Start from [`template.html`](template.html)**: copy it beside the repo's other assets, give it a `<title>`, a `headline`, and an `aria-label` that says the whole picture in prose, then `node bin/build.cjs <file>`.
4. **Draw** with the API ([`REFERENCE.md`](REFERENCE.md)), on a 1200-unit-wide viewBox, coordinates on a 4-unit grid, from y 64 down: the top is the headline's.
5. **Check and export:** `node bin/check.cjs <file>` until it reports 0 problems in every theme and mode; it writes `<name>.png` and `<name>-dark.png` (2x) beside the file.
6. **Look at both PNGs yourself.** The checker proves geometry, not sense: read the sheet as a stranger would, and fix what reads wrong.
7. **Embed** with the `<picture>` snippet `bin/check.cjs` prints: the dark PNG as the `prefers-color-scheme: dark` source, `width` set to the sheet's 1x width (the PNG is 2x) and no `height`, since GitHub scales an image's width down to fit and keeps an explicit height, which stretches it; alt text is the `aria-label`.

The sheet is done when the checker is clean in every theme and mode and every mark on it is in the legend or says what it is.

## The language

- **Paper and ink.** Everything is ink on paper; a card is white with an ink outline (this repo's code, a service), a grey card, outlined like every other, is a package's code (its name in mono above the title).
- **Frames, not panels.** A boundary (a cluster, a namespace, a network, "outside the cluster") is a frame, its title knocked into its top line (or its bottom line, a title block, where edges enter from above), a note after it in muted sans.
- **Depth by banding.** Nesting alone draws two grey lines a few units apart that read as one doubled border, so depth gets one treatment, the same at every level: a frame at an even level (second, fourth, ...) is screened with a fine dot pattern and the levels between go back to paper, the way a drafter screens an area (a flat grey fill stays the package card's alone, so the two never read alike); the outermost frames keep no fill, since whitespace already separates them. The kit decides this from the geometry in `S.done()`; a drawing never sets it. Regions and chain outlines are overlays, not levels: they never band.
- **Nesting keeps its margin.** A box inside another keeps at least 8 units on every side, and two boxes either nest or stay apart; a border never lies on its container's.
- **Two pencils.** Colour on the drawing is reserved: cobalt and vermilion, each with one meaning per sheet (a trust path, a role), stated in the legend or on the region it outlines; everything else is ink. The one exception is a logo's own brand colours, inside its 14-unit slot and nowhere else.
- **Drafting conventions carry the rest:** a chain (dash-dot) line, the drafting _phantom_ line, marks what is replaced elsewhere (at work, in the cloud); hatching marks the one part that is not code (a model); a dashed edge reads, a solid edge calls or writes; a tick on a hop is a check, `=` is parity.
- **Bridges where edges cross.** Lay edges out to avoid crossings first; where two still cross at right angles, the kit bridges one over the other with a small arc, as a circuit drawing shows wires that do not join (the horizontal one hops, or the vertical one when the crossing sits near the horizontal's ends). Edges meeting a frame line cross it plainly.
- **Type.** Atkinson Hyperlegible Next and Mono, nothing under 11 px: a card's title is the only bold word; its second line is sans for what runs it and mono for an identifier; an edge carries a word only where the arrow alone would not say it.
  The headline is the one larger line, 17 px in regular ink: no bold, box, rule or badge, and no full stop.
- **Spare.** No icons as decoration, no badges, pills, gradients or shadows, no `·`-joined lists or arrows inside text: a list is commas, an alternative is `/`.
- **Modes, when the picture has two worlds.** A switch above the sheet relabels each stand-in with its counterpart (`{lab: '…', gcp: '…'}` on any text or logo); chain lines go solid in the mode where the thing is real.

## Two styles

Pick the style by the reader; `Sheet(svg, {style: 'board'})` switches a drawing, nothing else changes.

- **Sheet** (default): black ink on paper, for a README, a PR or an issue, read by the people who work on the system.
- **Board**: soft white panels on a cool canvas, rounded cards with a hairline and a faint lift, for a pitch, a deck or a reader outside the work, where a modern look earns attention.
  - A card's **accent** (`accent: 'teal' | 'violet' | 'amber'`) is a bar on its left edge naming its role (this repo's code, the cloud's services, the org's platform), one meaning per hue, stated in the legend; the sheet draws no bar, so its two pencils stay.
  - **Steps** (`S.step(x, y, n)`) number the main path in order on its edges, so the edges need no words; the legend says what the numbers follow. The sheet draws them as ink rings.
  - Logos are 20 units, not 14, and more of them earn a place: a board names the cloud services around the core (the database, logging, the identity proxy) by their marks too.
  - Frames, the chain line, hatching, cobalt and vermilion keep their meanings; the headline is set bold, one size up.
- Both hold the same word budget: a card says what a thing is in at most 12 words (its package overline aside); a configuration list, a plugin list or a sentence goes in the doc beside the sheet, never on a card.

## Logos

A logo names a **technology the sheet shows** at a glance: the platform, the orchestrator, the transformation tool, the agent framework, the warehouse, the services around them.
A swappable detail gets none: a model provider, a library choice, anything the picture would not change for; the registry holds only marks worth showing, so every one it knows that a sheet names appears on it.
The mechanics keep logos coherent, so place them only through the API:

- **One size, two slots.** Every logo is 14 units square (20 on the board), either in a card's slot (8 in from its right edge, centred on its first text row) or before a frame's title in its top line; never beside a title in running text, never scaled to the space.
- **Brand colour, normalised.** The registry ([`logos/`](logos/)) holds each mark as its owner draws it, masks and gradients included, in its brand colours (a single-colour mark in its brand colour), fitted to a 24-unit square with its ink coverage equalised (dense marks shrink, thin single-colour marks get a hairline of their own colour), so a solid disc and an outline read at the same weight. Recognition is the point of a logo, and colour carries most of it: one ink loses marks whose shapes are drawn by colour (Cloud Run's chevrons, Airflow's pinwheel).
- **One-ink fallback per theme, measured.** Beside the colour copy the registry keeps a one-ink copy; a theme draws it where under half the mark's pixels reach 2:1 against that theme's card (GitHub and Helm on dark, Google's pale blue on light). The bar is visibility, not WCAG's 3:1 for graphics: the name is always printed beside the logo, so the logo carries no information of its own.
- **Once each, every one named.** A technology's logo appears once, on its most representative element; the checker fails a repeat, a hand-placed logo, a logo crowding text, more than twelve, and a technology the registry knows that the sheet names (its title or an alias, in any text) without showing its logo. A name that only says what something stands in for, or what replaces it elsewhere, may stay unmarked: say why in `S.done({unmarked: {id: 'why'}})`.
- **A mark that does not read is left out.** Add one with `bin/add-logo.cjs`, regenerate the proof beside the registry (`node bin/check.cjs --proof logos/proof.png`) and look at it, and record its source, licence, or why it was left out, in [`logos/SOURCES.md`](logos/SOURCES.md).

## What the checker proves

For every theme and mode, in either style: exactly one headline, not empty, at most 60 characters (read in one glance, about half the sheet's width), with no full stop at its end, no second sentence, not the `<title>` again, and nothing drawn beside or above it; no text under 11 px; text inside its card, off other cards, off edges, off frame lines except where knocked out, and clear of other text; every box at least 8 units inside the box around it, and no two boxes half overlapping; no edge through a card it does not start or end at, along a card's border, or through a logo; every edge crossing bridged (the count is reported); text contrast at least 4.5:1 against what is behind it (a step badge, its card, its band, or the paper); at most 12 words on a card; the palette itself: a package card at least 6 CIELAB lightness from a plain card (light's step is 7.4; a luminance ratio flattens dark steps), and ink and muted text at least 4.5:1 on it, whether or not the sheet draws one; the logo rules above; the web fonts loaded (widths measured in a fallback font are wrong); no console error.

Requirements: Node and Playwright with Chromium (`require('playwright')` must resolve; `npx playwright install chromium` where it does not), and network access to Google Fonts.
