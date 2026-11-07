# Report page standards

The defaults a report page gets from this kit.
Each is encouraged, not enforced: follow it unless the page's brief gives a reason, and record a departure in the page's `DESIGN.md`.
Each says when it does not apply.

## The first screen

- **The first screen answers the brief's question** before any detail, so the reader knows the outcome without scrolling; what leads depends on the kind of page.
  A data report leads with its three to five headline numbers.
  A decision page leads with the recommendation and the one reason that decides it, then compares only the real contenders on the same criteria, marks the chosen one, and names the riskiest assumption.
  An explainer leads with one overview diagram of the whole shape (`loadout:draw-architecture`), then one section per part.
  When not: a reference page read by lookup (a glossary, an index) leads with its search or its table.
- **A headline number stands beside what it is judged against:** a prior period, a target, or the best option; alone, it reads as neither good nor bad.
  When not: a count that only sets the scope (the number of runs a page covers).

## Reading

- **No muted text:** every word and number is set in full ink; rank is carried by weight, size and order, never by a paler grey.
  When not: never on the page's own text; a third-party picture keeps its colours.
- **One family, a fixed scale:** Atkinson Hyperlegible Next at 400, 600, 700 and 800; words at 1rem, numbers at 1.375rem bold, a finding's headline at 1.1875rem, section heads at 1.375rem, the title at 2rem, the bubble at .9375rem, chart text at .875rem; numerals tabular.
  When not: a code or identifier column may use a mono face, as data, never as decoration.
- **Headings rank by size, weight and space, never by a paler body:** a finding's headline is a size step above its sentence (1.1875rem over 1rem) and two weight steps heavier (700 over 400); a section head is a step above that; a headline sits closer to its own sentence (6px) than to the row above it; on a dark ground headings go one weight further (800) and words get a touch more tracking and leading, since light strokes on dark spread and close the gap between weights.
  Size alone or weight alone is too weak in a dense block of short text: the two together, plus space, make the rank readable at a glance in both themes.
  Grounds: Butterick, [Headings](https://practicaltypography.com/headings.html) (the smallest size step that shows, bold, space) and [Space above and below](https://practicaltypography.com/space-above-and-below.html) (a heading belongs to the text after it); impeccable's typeset reference (combine size, weight, space and tone rather than asking one cue to carry rank; on dark grounds compensate in weight, tracking and leading); Argyle, [Adjust perceived typeface weight for dark mode](https://nerdy.dev/adjust-perceived-typepace-weight-for-dark-mode-without-layout-shift) (the irradiation illusion).
  When not: a page whose headings are already far apart in size (a title over prose) needs no dark-ground step; lowering the body's colour or weight is never the fix.
- **Plain-language labels, definitions on hover:** a column, a mark or a term is named in the reader's words, and anything that needs explaining gets a definition in the bubble rather than a paragraph in the layout.
  When not: a term the reader's own field uses daily needs no definition.
- **No process metadata** on a reader-facing page: no hashes, versions, run dates, file names, issue or pull request numbers.
  When not: a page whose readers are the people who run the process, and whose brief says so.
- **No recommendation styling:** no winner highlight, crown, badge or "best" colour; the reader draws the conclusion.
  When not: the brief asks the page to recommend, and then the recommendation is stated in words as well.
- **No emoji as icons, no gradient text, no decorative eyebrows above headings:** icons are line drawings in `currentColor`, and emphasis comes from weight and size.
  When not: never.

## Colour and theme

- **Colours only as tokens**, defined in `:root` with their light and dark values; components read semantic tokens, never raw values.
  When not: a brand mark keeps its own colours, inside its own drawing.
- **Light and dark, both first-class**, in the triple pattern: light in `:root`, dark in `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }` and again in `:root[data-theme="dark"]`, so the system choice and a forced theme both work.
  When not: never; a page that cannot do dark is not finished.
- **Never colour alone:** each status (ok, no, warn, bad, info) is also a shape: a filled circle, a ring, a square, a diamond, a triangle.
  When not: a single-series chart, where there is nothing to tell apart.
- **A fixed status taxonomy:** ok, warn, bad, info and a neutral "no" ring, named for the page in its key and its definitions.
  When not: a page with no outcomes uses no status colour at all.

## Structure

- **Sections share one heading style:** the heading over a 2px ink rule, every section alike.
  When not: never; a section that needs to stand out says so in its heading's words.
- **A control sits beside the heading of the section it changes**, never in a page-wide bar.
  When not: a control that truly changes the whole page (the theme) may sit by the title.
- **A segmented switch has two to four segments**, for views of the same data.
  When not: more views, or views of different things, are tabs or a select.
- **Parts as tabs** when a page has more than one job; each part has its own URL, and an empty part drops out.
  When not: a short page reads top to bottom with no tabs.
- **Single file:** the kit, the charts' libraries and the data are inlined; the page opens from disk or a link with nothing beside it.
  When not: the web font loads from Google Fonts, with fallbacks; a page that must work offline drops the link and uses the fallbacks.
- **A report inside a larger page is scoped** (`scope=<selector>` in the build markers): the kit's look and scripts stay inside that element, and the host page keeps its own.
  When not: a page that is the report from top to bottom.

## Tables

- **A real `<table>`**, words left, numbers right-aligned in tabular numerals and the number size.
  When not: a list of one-word items is a list.
- **Tables sort from the whole header cell:** a table of numbers or comparable text sorts by every such column, showing `aria-sort` and a direction mark, with one column that restores the page's own order.
  When not: a table of two or three rows, or one whose order is its message.
- **Rows slide to their new places** when sorted, and do not under reduced motion.
  When not: a table long enough that the slide hides where a row went.
- **Narrow tables stack** each row into a block whose values carry their column's label and mark; set the width where a table stacks (`data-rk-stack-at`) from its own columns, and use the compact stack (each number beside its column's mark alone, the header as a sort bar) when every number column has a mark.
  When not: a table of two or three narrow columns fits as it is.
- **Three states by default, two for a comparison grid:** a table that has an order of its own (a sequence, a ranking the page argues from) keeps the default: the page's order, highest first, lowest first, with one column that brings the page's order back.
  A grid whose rows have no meaningful order of their own, read by comparing columns (options by kinds of question), takes `data-rk-sort="toggle"`: each press flips its column between highest first and lowest first, with no reset state to press through.
  When not: a toggle table whose page order still matters gives that order a default column, which then flips between the page's order and its reverse.
- **Tables that show the same rows in different views share one sort** (`data-rk-sort-group`), so switching views keeps the order the reader chose.
  When not: tables of different rows.

## Marks and pictures

- **Proportions out of 100 as dot arrays**: 100 marks, shape-coded by status, in the order of the columns that count them.
  When not: shares that are not counts of like things (a budget split) are bars.
- **Pointing at a category lights its marks** across every row in its section and steps the rest back; leaving resets them, and a sort or a tap never leaves them lit.
  When not: a section with one row has nothing to compare.
- **Small inline pictures are HTML, CSS and SVG** on the same 0-100 scale as the table: a bar (the whole track is 100), a meter (a number over a thin bar, for a grid cell), a range (lowest to highest), a slope (one value to another).
  When not: a picture that needs axes, many points or interaction is a chart.
- **Consider grading values where dense comparisons sit side by side:** in a grid of many numbers over bars (options by kinds of question), every bar in one colour makes the reader read each number to find the strong and weak cells.
  Grading (`grade`) colours each bar by where its value falls on its scale (blue for the good end, a neutral middle, vermilion for the poor end; checked for colour-blind separation on both grounds), so the pattern shows before the numbers are read; the number and the bar's length still carry the value, and a key names the cut points.
  Choose cut points that mean something to the reader (a pass mark, a target), the same for every cell in the grid, and say which end is good when lower is better (`data-rk-grade-dir="down"`).
  This is guidance, not a rule: weigh it per picture.
  When not: a main table already carrying dot arrays (their marks colour the outcomes; a second colour code competes with them); a handful of numbers with one bar each, which read at a glance anyway; a picture whose colour already means a status (the green of "on time").
- **Charts through Observable Plot** with the kit's theme (`ReportKit.plot`), chart type chosen with the dataviz skill, a key in HTML, shapes as well as colours for series.
  When not: an architecture or system diagram is drawn with `loadout:draw-architecture`.

## Behaviour

- **A clipped label keeps its full text** within reach (the definition bubble, or a `title`), and a name gets its own line before any tag that could crowd it.
  When not: never.
- **A control that names a count shows what it counts** ("12 more" expands them) and offers the way back.
  When not: never.
- **Explain a mechanic once,** in the key or the section's lead, not again in every row or card.
  When not: a page printed in parts that may be read apart.
- **One definition bubble** for the whole page, on hover, keyboard focus and tap (a tap shows it for a moment), kept inside the viewport, kept on its element through a scroll while the keyboard rests there, closed by Escape, read by screen readers through `aria-describedby`.
  When not: never a second tooltip style.
- **Pinning is an option**: a click or Enter pins a definition, which can be dragged by its handle or moved with the arrow keys, closed, and can link on to a fuller entry ("more").
  When not: a page whose definitions are one line each leaves pinning off.
- **Visible focus on every focusable element**, in the line colour.
  When not: never.
- **A modal dialog traps focus and Escape closes it**; the pinned bubble is not modal: it traps nothing, Tab moves into it from its element, and Escape closes it.
  When not: never.
