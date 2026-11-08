---
name: report-kit
description: "Use when building or restyling an HTML report page (a data report, an eval report, a decision write-up, an explainer, a pitch) in any repo: the house kit of tokens, components and checks for one standalone page. Not for architecture diagrams or slide decks."
---

A report page is **one standalone HTML file** that a reader understands at a glance: ink on a quiet ground, tables that sort, definitions on hover, small pictures on a shared 0-100 scale, charts in the same look, light and dark.
This skill is how such a page is built, not what it says: the page's content comes from its brief and its data.
It ships as a kit: components in [`kit/`](kit/) inlined by [`bin/build.cjs`](bin/build.cjs), checked by [`bin/check.cjs`](bin/check.cjs), with the defaults in [STANDARDS.md](STANDARDS.md) and every markup contract in [REFERENCE.md](REFERENCE.md).

## Steps

1. **Brief.** Write `PRODUCT.md` beside the page from [`templates/PRODUCT.md`](templates/PRODUCT.md): who reads it, the job it does for them, and what it must never do.
   Done when a stranger could hold the finished page against those three lines and say whether it passes.
2. **Direction.** Use the impeccable skill: its new-work flow for a new page, its refinement rules for a restyle (the incumbent look is kept unless the brief replaces it).
   Read its craft floor (`reference/craft-floor.md`) before the first edit, every time.
   A restyle onto the kit keeps each part's shape (its container, its controls, its order) unless the owner names that shape as the problem: a description of what a part is ("a table in its own scroll box") is not a complaint, and moving it to the kit's look is not a licence to rebuild it.
   A new shape is a redesign: show it to the owner as an option, beside the part as it is, before building it into the page.
3. **Compose** from the kit's components, following [STANDARDS.md](STANDARDS.md) and the contracts in [REFERENCE.md](REFERENCE.md).
   A generator (Python, Node, anything) writes the markup and the build markers; [`tests/build_fixture.py`](tests/build_fixture.py) is a worked example.
   Diagrams come from `loadout:draw-architecture`; charts are chosen with the dataviz skill and drawn with Observable Plot through `ReportKit.plot`, which gives them the kit's theme.
4. **Build:** `node bin/build.cjs <page.html>` inlines the kit and the pinned Plot and d3, checked against `kit/vendor/checksums.txt`; run it again after every kit or generator change.
5. **Check:** `node bin/check.cjs <page.html>` until it prints `0 problems`, then the impeccable skill's detector (`impeccable detect --json <page.html>`, empty) and its audit.
   Look at the page yourself in both themes and at a phone width (`--shots <dir>` saves them): the checker proves geometry, contrast and behaviour, not sense.
   Hold each changed part against its "before" shots as its reader would; if it reads worse, keep the before, whatever the checks say.
6. **Record** the page's design in `DESIGN.md` beside it, from [`templates/DESIGN.md`](templates/DESIGN.md): what it changes from the kit's defaults, and why.

The page is done when the checker and the detector are clean, the audit has no P0 or P1, and every brief line holds.

**Improve the kit as you use it.** When a page needs what the kit lacks, or a component, standard or check gets something wrong, build the page's own workaround in its own files, and propose the generic fix to this skill as a PR on the repo that holds it, with what you hit and the evidence (a screenshot, a checker line).
The PR waits for the owner's review before merge; the page re-vendors the kit once it lands.

Requirements: Node, and Playwright with Chromium (`require('playwright')` must resolve; `npx playwright install chromium` where it does not), and network access to Google Fonts for the page's face.
