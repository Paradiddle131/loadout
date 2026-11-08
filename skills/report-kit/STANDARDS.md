# Report page standards

The defaults a report page gets from this kit.
Each is encouraged, not enforced: follow it unless the page's brief gives a reason, and record a departure in the page's `DESIGN.md` (or wherever the page keeps its design record).
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
  It holds while the reader points too: pointing at an item lights what it names (a band, a bolder weight, an ink edge) and leaves every other word in full ink, never fading the rest to a grey or an opacity.
  When not: never on the page's own text; a third-party picture keeps its colours; a chart's or diagram's marks may step back while one is lit (Highlight), its words included only where they belong to those marks.
- **One family, a fixed scale:** Atkinson Hyperlegible Next at 400, 600, 700 and 800; words at 1rem, numbers at 1.375rem bold (a number that stands on its own, or in a short table; a count on a list row or in a dense table is at 1rem bold, so a column of numbers does not outshout the names it counts), a finding's headline at 1.1875rem, section heads at 1.5rem, the title at 2rem, the bubble at .9375rem, chart text at .875rem; numerals tabular.
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
  When not: more views, or views of different things, are tabs or a select; five or more types to filter a list by are chips (below).
- **Parts as tabs** when a page has more than one job; each part has its own URL, and an empty part drops out.
  When not: a short page reads top to bottom with no tabs.
- **Headings step down one level at a time, a dialog's included:** under an h2 comes an h3, never an h4 or an h5; the number follows the outline, and the look follows the kit's levels (section, part, item), so a heading that should look smaller takes a smaller level's style, never a deeper heading number.
  A modal dialog is an outline of its own that opens at its h2, whatever level the button that opened it sits under.
  A skipped level tells a screen-reader user, who moves by headings, that a level is missing, and leaves the page's look and its outline telling two stories.
  Grounds: W3C WAI, [Headings](https://www.w3.org/WAI/tutorials/page-structure/headings/) ("Skipping heading ranks can be confusing and should be avoided where possible"; an h2 is never followed directly by an h4); WCAG 2.2, [Info and Relationships](https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html).
  When not: going back up may jump a level (an h4 closing its part, then the next h2).
- **Single file:** the kit, the charts' libraries and the data are inlined; the page opens from disk or a link with nothing beside it.
  When not: the web font loads from Google Fonts, with fallbacks; a page that must work offline drops the link and uses the fallbacks.
- **A report inside a larger page is scoped** (`scope=<selector>` in the build markers): the kit's look and scripts stay inside that element, and the host page keeps its own.
  When not: a page that is the report from top to bottom.

## Inside a section

- **Three levels inside a section, each with its own cues:** the section (its head at `--t-head` over the 2px ink rule, `--gap-section` above), a part (its head at `--t-find`, or 1rem bold inside a stage, over a 1px ink rule, `--gap-part` above), an item (a 1rem bold head, `--gap-item` above, no rule).
  Each step down in rank is a step down in space and in rule weight, and what sits inside a level is never looser than the space around it, so the eye groups by distance before it reads a word.
  With no paler grey to rank by, size, weight, space and the rule must carry the level together; a 1rem bold head alone looks like a bold sentence.
  Grounds: NN/g, [Proximity](https://www.nngroup.com/articles/gestalt-proximity/) (varying whitespace to unite or separate is how groups are read) and [Visual hierarchy](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/) (no more than three sizes; less space binds a heading to its content); the inner-and-outer spacing rule ([inner ≤ outer](https://cases.media/article/the-inner-and-outer-spacing-principle)).
  When not: a section of one block has no part level; a part of one paragraph needs no item level.
- **Space first, then one rule, then one surface:** group by the space steps above, add a part's rule where two parts meet, and keep the one raised surface (`--panel`) for a side column; never a box inside a box.
  A boundary overpowers proximity, so each extra line or tint spends the strongest grouping cue the page has, and a row of boxes reads as clutter.
  Grounds: NN/g, [Common region](https://www.nngroup.com/articles/common-region/) (a boundary is stronger than proximity; boxes added for decoration add clutter); Wathan and Schoger, *Refactoring UI* ("use fewer borders": space or a change of ground instead).
  When not: a dense grid whose cells must read apart (a table) keeps its hairlines.
- **A side column sits on the raised surface; the stage it drives stays on the ground:** a list to choose from (a picker, a contents, a ladder of options) beside what the choice shows goes in `.rk-aside` within `.rk-split`, with its own head at the stage head's level, and the chosen item is a reversed plate, marked by weight and plate as well as colour.
  The column's items are rows of it, never boxes inside its box: no border on a link, a chip or a button there, a hover band, the chosen one reversed.
  The surface tells controls from content without a border, and keeps the column one region however long it runs; the stage's parts keep their rules, so the two halves never share a device.
  On a narrow screen the column comes first: keep it short, folding a long one behind `.rk-fold` (one button naming the column and its current choice) so the stage starts on the first screen; a pick folds it again.
  Size the column to its longest item (`--aside`) rather than let ids wrap, and give a column that must leave its stage room the dense padding (`.rk-dense`).
  Grounds: IBM Carbon, [layering model](https://carbondesignsystem.com/elements/color/usage/) (a side panel is a layer: White on a Gray 10 ground, one step lighter on a dark one); Every Layout, [The Sidebar](https://every-layout.dev/layouts/sidebar/) (the column wraps above the content when the content would get too narrow).
  When not: two to four choices of one view are a switch beside the section's head.
- **Parts side by side each keep their own head and rule:** sibling parts in `.rk-parts` each start with a head over their own 1px ink rule, and the column gap breaks the rule between them; stacked, they keep the same rule and `--gap-part`.
  One hairline across both columns makes two parts read as one block with two columns of text.
  When not: two blocks that are one thing (a table and its note) are one part.
- **A figure holds its key and its caption:** one `<figure>` (`.rk-fig`, or `.rk-chart` for a chart) holds the drawing, its key right against it, and a reading note last, each a short step (`--s2`) from the drawing, with the next part a `--gap-part` away.
  The key decodes marks only, and the caption says only what the drawing cannot (its units, its sample, the one thing to see); a key or note that drifts past other blocks reads as belonging to them.
  Grounds: Caltech Hixon Writing Center, [figure captions](https://writing.caltech.edu/documents/27629/HWC-FigureCaptionHandout.1-2024.pdf) (a caption adds what the figure does not show, never repeats it); a figure with its caption should stand alone.
  When not: one key shared by several figures sits once above them, under the section's lead.
- **One item at a time: Previous and Next above it, in place:** a list read one item at a time (an example of each kind, one case per screen) steps with Previous and Next side by side above the item, then its position in words ("Order 3 of 12"), all in one control style (`.rk-step`); a further control in that row (a "See all 12") wears the same look.
  The item takes its own height: the reader pressed for the change, so what moves below the controls is expected, while fields that each reserve the tallest content any item gives them leave empty bands that read as a broken layout.
  At an end the button is disabled and stays in sight, dimmed (to no less than 4.5:1), so the other never moves under the pointer and the row never opens on an empty slot, and the focus passes to the other; the position is a polite live region, so a screen reader hears it without leaving the button.
  Grounds: web.dev, [Cumulative Layout Shift](https://web.dev/articles/cls) (a shift close to the reader's own press is expected, and shifts within 500 ms of input are left out); WCAG 2.2, [Status Messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html) (a change the focus does not move to is announced); GOV.UK Design System, [Pagination](https://design-system.service.gov.uk/components/pagination/) (Previous and Next through related content; no Previous on the first page).
  When not: a list of a screen or less shows whole; a list the reader searches rather than steps through is browsed (below).
- **A long list is browsed with a find box, in place where it can be:** a list too long to step through (dozens of items) is a side column beside the chosen item (`.rk-split`), with a find box over the list that narrows it as the reader types (a visible label over it, never a placeholder that carries its meaning: a placeholder is either paler than the words or mistaken for typed text), the count shown said as a status ("12 of 84 shown"), and, when nothing matches, a sentence that says so and a button that clears the box.
  A choice of scope over the list (this kind, every kind) is a switch.
  Prefer it in place: a browse is not a short exchange, and a modal covers the page the reader came from and repeats a stage the page already has.
  Where a compact view opens the browser on demand (a "See all" under one example), it may be the kit's dialog, holding the same split, full screen on a phone.
  Grounds: NN/g, [Modal and nonmodal dialogs](https://www.nngroup.com/articles/modal-nonmodal-dialog/) (modals for short, direct exchanges; not for decisions that need information outside them); WCAG 2.2, [Status Messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html) (its example: the count of search results announced without moving the focus); NN/g, [Placeholders in form fields are harmful](https://www.nngroup.com/articles/form-design-placeholders/) (a label that vanishes as the reader types, in text too faint to read).
  A reference list read whole rather than beside a stage (a glossary, an index) keeps the same find box, count and empty sentence over the list itself (`find`), marks the typed words in each entry shown (a tint with a line under it, so the mark is seen without its colour), and a link to one of its entries (a bubble's "more", a hash) clears whatever hides that entry before the page scrolls to it.
  When not: a list of a screen or less needs no find box.
- **A long list runs in the page's flow, never in a scroll box of its own:** the page keeps one scroll; a list, a glossary or a table gets no fixed height with its own vertical scroll inside the page, and so needs no sticky head or sticky group row inside it.
  A box inside the page takes the wheel and the thumb until its end and then hands them to the page, shows only a slice of the list so the reader holds the rest in memory, and pins its sticky rows over what the keyboard focuses; a find box and a type filter already make a long list short.
  Grounds: Baymard Institute, [Avoid inline scroll areas](https://baymard.com/blog/inline-scroll-areas) ("Inline scroll areas can hijack page scrolling"; "By design inline scroll areas make it impossible for the user to see all of the options at once"; on touch they can "trap" the user); MDN, [overscroll-behavior](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/overscroll-behavior) (once an inner box's scroll boundary is reached "the underlying page will then start to scroll", scroll chaining); WCAG 2.2, [Focus Not Obscured (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html) ("Typical types of content that can overlap focused items are sticky footers, sticky headers, and non-modal dialogs"); WCAG 2.2, [Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) (a scroll container is for content that needs "two-dimensional layout for usage or meaning", such as a data table, and only that section).
  The checker reports a box that scrolls up and down inside the page (`nest`).
  When not: a table wider than the page scrolls sideways in its own wrap (above); a dialog's content scrolls inside the dialog; a page whose brief keeps a box (a list that must stay in sight beside what it drives) marks it `data-rk-scroll` and records why in its `DESIGN.md`.
- **A glossary is a definition list, grouped under part heads:** each entry a `<div>` in `.rk-glossary` holding its term (`<dt>`) and meaning (`<dd>`), with an id that links and bubbles point at; terms grouped by type sit in one part per group (`.rk-part`, an h3 over its 1px ink rule), so the groups are in the page's outline and a screen-reader user moves between them by heading.
  An entry's extra lines (a count, an example) are labelled facts under its meaning (`.rk-facts-tight`), at the word size in full ink, a short step apart; numbers in bold, and their labels at 600, a weight under the term's heading weight (700, 800 on dark), so the term heads its entry rather than reading as one more label.
  A table's head row over a glossary ("Term", "What it means") only says what a glossary is, and its group rows are a second surface and a third size inside one table; a tinted band, a sticky group row or a fold that hides a group adds a way to lose an entry to a list the find box already narrows.
  Grounds: MDN, [`<dl>`](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dl) ("Common uses for this element are to implement a glossary or to display metadata"; a `<div>` may wrap each name-value group); W3C WAI, [Headings](https://www.w3.org/WAI/tutorials/page-structure/headings/) ("Web browsers, plug-ins, and assistive technologies can use them to provide in-page navigation"); NN/g, [Accordions on desktop](https://www.nngroup.com/articles/accordions-on-desktop/) (folds add clicks that "accumulate and can become burdensome for users").
  When not: a glossary of a dozen terms or fewer needs no groups and no find box; entries that each carry the same few values the reader compares across terms are a table; a page whose brief keeps folded groups gives each fold `hidden="until-found"`, so the browser's find and a link still open it ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/hidden): content in that state stays reachable by "Find in page" and fragment navigation), and records the choice in its `DESIGN.md`.
- **A filter of five or more types is a row of chips that wraps:** one choice among many types over a list (`.rk-chips` in `find`) is a row of buttons, the chosen one a reversed plate (as a switch's segment), each naming its type and how many entries it holds for what is typed, so the reader sees where the matches are before choosing; the row wraps onto as many lines as it needs, on a phone too.
  A strip that scrolls sideways with its scrollbar hidden leaves every type past its edge unseen, with nothing to say it is there; a wrapped row shows them all.
  Grounds: NN/g, [Horizontal scrolling](https://www.nngroup.com/articles/horizontal-scrolling/) ("People expect to scroll vertically for additional content, but they don't expect to scroll sideways"; "Use a scrollbar or pagination to show how much more content there is"); WCAG 2.2, [Non-text Contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html) (a control identified by its text needs no visible boundary; its selected state needs 3:1); GOV.UK Design System, [Select](https://design-system.service.gov.uk/components/select/) (a last resort; "try asking users questions which will allow you to present them with fewer options").
  The checker reports a strip that scrolls sideways with its scrollbar hidden (`strip`).
  When not: two to four types are a switch; a head row that scrolls sideways in step with a visible scrollbar under it (a wide table's frozen head) hides its own bar and is marked `data-rk-scroll`, with the reason in the page's design record; past about a dozen, regroup the types into fewer before reaching for a select; types a reader may never need fold behind the filter button (`.rk-filter`).
- **A short list of labelled facts sets the label beside its value:** a method note, a setup's settings or an entry's extra lines are a definition list (`.rk-facts`), each label bold at the word size in full ink, beside its value while the list has room and above it once narrow; the label column takes the longest label's width, never a fixed width in `rem` (the dark ground's extra tracking wraps a label that fits in light), and every value starts on one left edge.
  A label set smaller or paler than its value inverts the rank: it heads the row, so it is never the weaker of the two.
  Grounds: GOV.UK Design System, [Summary list](https://design-system.service.gov.uk/components/summary-list/) ("Use a summary list to show information as a list of key facts"; "only use it to present information that has a key and at least one value"; "Do not use it for tabular data"); MDN, [`<dl>`](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dl) (metadata as key-value pairs).
  When not: facts several items share, read by comparing them, are a table; a fact that runs past a few lines is a paragraph under an item head.
- **One statement per fact:** each fact has one home, by role: a name names; a tag line places it (a group, a rung) in words that repeat neither the name nor each other; a lead says once what it is; the figure shows; a list of changes lists without restating the lead; a caption adds what the figure cannot show, or is left out.
  A fact said three times in three styles (a tag line, a description, a caption) takes three reads to find it is one fact, and makes neighbouring blocks look alike.
  Test: hide each sentence in turn; if the reader loses nothing, delete it.
  When not: the first screen restates the findings below it by design, and a definition bubble may repeat a term's gloss.
- **Raised is lighter, in both themes:** the panel is a step lighter than the ground on light and on dark, about 1.1:1 against light ground and 1.2:1 against dark, since a dark step must be larger to be seen; rules are full ink in both, and nothing lifts by a shadow on a dark ground.
  One model (a raised layer is nearer the light) keeps the same region reading as the same thing when the theme flips, and a lighter panel keeps every status and series colour at 4.5:1 where a darker one would not.
  Grounds: Carbon's layering model (light layers alternate with White; dark layers go one step lighter each); Material's [dark theme](https://m2.material.io/design/color/dark-theme.html) (a surface higher in elevation is lighter).
  A page that keeps its own ground under the kit measures the step against that ground, not the kit's, in both themes, and records the ratios.
  When not: a page whose ground is already the lightest it can be (pure white) takes a ground one step darker instead, and records it.

## Tables

- **A real `<table>`**, words left, numbers right-aligned in tabular numerals and the number size.
  When not: a list of one-word items is a list.
- **Tables sort from the whole header cell:** a table of numbers or comparable text sorts by every such column, showing `aria-sort` and a direction mark, with one column that restores the page's own order.
  When not: a table of two or three rows, or one whose order is its message.
- **Rows slide to their new places** when sorted, and do not under reduced motion.
  When not: a table long enough that the slide hides where a row went.
- **Narrow tables stack** each row into a block whose values carry their column's label and mark; set the width where a table stacks (`data-rk-stack-at`) from its own columns, and use the compact stack (each number beside its column's mark alone, the header as a sort bar) when every number column has a mark.
  When not: a table of two or three narrow columns fits as it is.
- **A long table stays one table:** its rows are never split into two tables side by side to save height; split, the halves repeat their heads, sort apart, read as two groups, and at a large text size their columns squeeze into each other.
  Columns take their width from their content, never a fixed width in `em`; a long table shows its first rows and a control that names the rest ("12 more"), or scrolls inside its own wrap.
  Grounds: WCAG 2.2, [Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) (a data table keeps its two-dimensional layout and may scroll in its own container) and [Resize Text](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html) (text at 200% loses no content).
  When not: two tables of different rows are two tables.
- **Three states by default, two for a comparison grid:** a table that has an order of its own (a sequence, a ranking the page argues from) keeps the default: the page's order, highest first, lowest first, with one column that brings the page's order back.
  A grid whose rows have no meaningful order of their own, read by comparing columns (options by kinds of question), takes `data-rk-sort="toggle"`: each press flips its column between highest first and lowest first, with no reset state to press through.
  When not: a toggle table whose page order still matters gives that order a default column, which then flips between the page's order and its reverse.
- **Tables that show the same rows in different views share one sort** (`data-rk-sort-group`), so switching views keeps the order the reader chose.
  When not: tables of different rows.

## Marks and pictures

- **Proportions out of 100 as dot arrays**: 100 marks, shape-coded by status, in the order of the columns that count them.
  When not: shares that are not counts of like things (a budget split) are bars.
- **A run of outcomes is a row of marks:** a few outcomes of one thing (three tries, four weeks) sit in a cell as `.rk-marks`, one status mark per outcome in order, each in a slot of its own so runs line up from row to row; an outcome that does not exist (not run, no data) is a small ink dot, never a sixth status colour; the run says itself in words (its `aria-label`), and the key names the dot too.
  The same five shapes the rest of the page uses read the same in a small cell; a private set of squares for one table makes the reader learn a second code, and its tints fall apart on a dark ground.
  Grounds: WCAG 2.2, [Use of Color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html) (colour is never the only cue).
  When not: more than about ten outcomes are a count or a dot array.
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
- **A modal dialog is for a short, direct exchange** (a method note, a definition too long for the bubble), as `.rk-dialog`: a native `<dialog>` opened modal, named by its visible h2 (`aria-labelledby`), headed like a section (the h2 over the 2px ink rule, a close button beside it, no eyebrow above it).
  The focus starts on its heading, Tab stays inside it (and the browser's own controls), the first Escape closes the innermost thing (a bubble open in it, then the dialog), and closing gives the focus back to what opened it; definitions inside it show above it.
  The pinned bubble is not modal: it traps nothing, Tab moves into it from its element, and Escape closes it.
  Grounds: WAI-ARIA APG, [Dialog (Modal) pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) (a visible title by `aria-labelledby`; Escape closes; focus to a static element at the top when the content is long; focus back to the opener); NN/g, [Modal and nonmodal dialogs](https://www.nngroup.com/articles/modal-nonmodal-dialog/).
  When not: a long list is browsed in place where the page has room for it (the rule above); in a dialog it keeps the same split, find box and count.
