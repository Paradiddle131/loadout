#!/usr/bin/env python3
"""Build the report-kit fixture: an invented bakery's delivery trial on one page that uses every component.

It is the checker's test page and a worked example of a generator: Python writes the markup each component's
contract asks for (REFERENCE.md), leaves the kit's markers in place, and calls bin/build.cjs to inline the kit.

    python3 tests/build_fixture.py            # writes tests/fixture.html and tests/scoped.html, then inlines the kit
"""

import html
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
esc = html.escape

# column key, head, mark kind, definition
COLUMNS = [
    ("ok", "On time", "ok", "Arrived within the hour the customer chose."),
    ("late", "Late", "warn", "Arrived, but after the hour the customer chose."),
    ("damaged", "Damaged", "bad", "Arrived with something squashed, cold or missing."),
    ("lost", "Not delivered", "no", "Never arrived; the bakery refunded the order."),
]
# name, definition, 100 weekday orders, 100 weekend orders (on time, late, damaged, not delivered)
OPTIONS = [
    ("Own van", "The bakery's own van and driver.", (78, 14, 3, 5), (70, 22, 3, 5)),
    ("Bike courier", "A local courier on a cargo bike.", (84, 9, 5, 2), (75, 15, 7, 3)),
    ("Partner app", "A delivery app that sends whichever driver is free.", (69, 20, 2, 9), (58, 28, 4, 10)),
    ("Shared van", "A van shared with two other shops on the street.", (72, 17, 6, 5), (66, 21, 6, 7)),
    ("Collect in shop", "The customer collects the order at the counter.", (91, 4, 1, 4), (88, 6, 1, 5)),
]
DAYS = [
    ("weekday", "Weekdays", "Monday to Friday, 100 orders per option."),
    ("weekend", "Weekends", "Saturday and Sunday, 100 orders per option."),
]
GLOSSARY = [(f"term-{n.lower().replace(' ', '-')}", n, d) for n, d, *_ in OPTIONS] + [
    (f"term-{k}", h, d) for k, h, _, d in COLUMNS
]


def slug(name):
    return f"#term-{name.lower().replace(' ', '-')}"


def tipped(text, inner, more=None, cls="rk-term", attrs=""):
    """A word that shows its definition in the bubble; more names a fuller entry the pinned bubble links to."""
    link = f' data-tip-more="{esc(more)}" data-tip-more-label="In the glossary"' if more else ""
    return f'<span class="{cls}" data-tip="{esc(text)}"{link}{attrs}>{inner}</span>'


def dots(counts):
    """100 marks in the columns' order, read out as one sentence."""
    marks = "".join(f'<i data-k="{k}"></i>' * c for (_, _, k, _), c in zip(COLUMNS, counts, strict=True))
    said = ", ".join(f"{c} {h.lower()}" for (_, h, _, _), c in zip(COLUMNS, counts, strict=True))
    return f'<span class="rk-dots" role="img" aria-label="{said}, of 100 orders">{marks}</span>'


def table(day, hidden):
    heads = "".join(
        f'<th scope="col" class="rk-num" data-sort="number"><button type="button" data-lit="{k}" data-tip="{esc(d)}">'
        f'<i class="rk-mark" data-k="{k}"></i><span class="rk-label">{esc(h)}</span></button></th>'
        for _, h, k, d in COLUMNS
    )
    rows = []
    for name, desc, weekday, weekend in OPTIONS:
        counts = weekday if day == "weekday" else weekend
        cells = "".join(f'<td class="rk-num" data-v="{c}">{c}</td>' for c in counts)
        rows.append(
            f'<tr><th scope="row">{tipped(desc, esc(name), slug(name))}</th><td class="rk-wide">{dots(counts)}</td>{cells}</tr>'
        )
    return (
        f'<table class="rk-table rk-stack rk-stack-compact" data-rk-sort data-rk-flip data-rk-sort-group="days" data-rk-stack-at="48rem" '
        'data-rk-sort-restored="Back in the trial\'s order, from the bakery\'s own van to the counter." '
        f'data-rk-when="days={day}"{" hidden" if hidden else ""}>'
        f'<caption class="rk-sr">Delivery options, {day}s: 100 orders each</caption><thead><tr>'
        '<th scope="col" data-sort="default"><button type="button" data-tip="From the bakery\'s own van to the counter.">'
        '<span class="rk-label">Option</span></button></th>'
        f'<th scope="col" class="rk-wide">100 orders</th>{heads}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
    )


def spread(values, gap=18):
    """Label positions on a 0-100 scale, pushed at least gap apart and kept inside 0-100, so close numbers never overlap."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    at = [float(values[i]) for i in order]
    for i in range(1, len(at)):
        at[i] = max(at[i], at[i - 1] + gap)
    if at and at[-1] > 100:
        at[-1] = 100.0
        for i in range(len(at) - 2, -1, -1):
            at[i] = min(at[i], at[i + 1] - gap)
    out = [0.0] * len(values)
    for i, v in zip(order, at, strict=True):
        out[i] = round(v, 1)
    return out


def rng(label, lo, hi, lo_name, hi_name, k=None):
    p_lo, p_hi = spread([lo, hi], gap=16)
    kind = f' data-k="{k}"' if k else ""
    return (
        f'<div class="rk-range"><span class="rk-pl">{esc(label)}</span>'
        '<span class="rk-ruler"><span aria-hidden="true">0</span>'
        f'<span class="rk-scale" style="--lo:{lo};--hi:{hi}"><span class="rk-span"{kind} aria-hidden="true"></span>'
        f'<span class="rk-sr"> from </span><span class="rk-at" style="--p:{p_lo}">{tipped(lo_name, str(lo), cls="rk-end rk-term")}</span>'
        f'<span class="rk-sr"> to </span><span class="rk-at" style="--p:{p_hi}">{tipped(hi_name, str(hi), cls="rk-end rk-term")}</span>'
        '<span class="rk-sr"> on time in 100</span></span><span aria-hidden="true">100</span></span></div>'
    )


def bar(label, v, k):
    return (
        f'<li><span class="rk-pl">{esc(label)}</span><span class="rk-bar"><span class="rk-track" aria-hidden="true">'
        f'<span class="rk-fill" data-k="{k}" style="--v:{v}"></span></span><b>{v}</b>'
        '<span class="rk-sr"> late in 100</span></span></li>'
    )


def slope(label, left, right):
    """left, right: {kind: value}; one line per kind from the left value to the right one."""
    kinds = list(left)
    ys_l, ys_r = spread([left[k] for k in kinds]), spread([right[k] for k in kinds])
    lines = "".join(
        f'<line class="rk-ln" data-k="{k}" x1="0" y1="{100 - left[k]}" x2="100" y2="{100 - right[k]}" '
        'vector-effect="non-scaling-stroke"/>'
        for k in kinds
    )
    marks = "".join(
        f'<i class="rk-pt" data-k="{k}" style="--x:{x};--y:{v[k]}"></i>' for k in kinds for x, v in ((0, left), (100, right))
    )
    nums = "".join(
        f'<b class="rk-n {side}" style="--y:{y}">{v[k]}</b>'
        for side, v, ys in (("rk-l", left, ys_l), ("rk-r", right, ys_r))
        for k, y in zip(kinds, ys, strict=True)
    )
    return (
        f'<div class="rk-slope"><span class="rk-pl" aria-hidden="true">{esc(label)}</span>'
        f'<div class="rk-slope-plot" aria-hidden="true"><svg viewBox="0 0 100 100" preserveAspectRatio="none" focusable="false">'
        f'{lines}</svg>{marks}{nums}</div><div class="rk-xl" aria-hidden="true"><span>Weekdays</span><span>Weekends</span></div></div>'
    )


def takeaways():
    by = {name: (wd, we) for name, _, wd, we in OPTIONS}
    on_wd = sorted(((wd[0], n) for n, (wd, _) in by.items()))
    on_we = sorted(((we[0], n) for n, (_, we) in by.items()))
    ranges = rng("Weekdays", on_wd[0][0], on_wd[-1][0], on_wd[0][1], on_wd[-1][1], "ok") + rng(
        "Weekends", on_we[0][0], on_we[-1][0], on_we[0][1], on_we[-1][1]
    )
    bars = "".join(bar(n, we[1], "warn") for n, (_, we) in by.items())
    pair = ("Own van", "Partner app")
    slopes = "".join(slope(n, {"ok": by[n][0][0], "bad": by[n][0][2]}, {"ok": by[n][1][0], "bad": by[n][1][2]}) for n in pair)
    key = "".join(
        f"<li>{tipped(d, f'<i class="rk-mark" data-k="{k}" aria-hidden="true"></i>{esc(h)}', attrs=f' data-lit="{k}"')}</li>"
        for _, h, k, d in COLUMNS
        if k in ("ok", "bad")
    )
    said = " ".join(
        f"{n}: on time {by[n][0][0]} on weekdays and {by[n][1][0]} on weekends; damaged {by[n][0][2]} and {by[n][1][2]}."
        for n in pair
    )
    items = [
        (
            "Weekends cost every option some on-time orders",
            (
                f"On weekdays the options ranged from {on_wd[0][0]} to {on_wd[-1][0]} on time in 100; "
                f"on weekends from {on_we[0][0]} to {on_we[-1][0]}."
            ),
            f'<div class="rk-pic">{ranges}</div>',
        ),
        (
            "Weekend lateness differs by option",
            "Late orders in 100 on weekends, in the table's order.",
            f'<div class="rk-pic"><ul>{bars}</ul></div>',
        ),
        (
            "Bread travels well, large orders do not",
            "On-time orders in 100 by kind of order, weekdays and weekends together; press a column to sort by it.",
            f'<div class="rk-pic">{grid()}</div>',
        ),
        (
            "Two options from weekday to weekend",
            "On time and damaged orders in 100, weekdays on the left and weekends on the right.",
            (
                f'<div class="rk-pic" data-rk-lit-scope><div class="rk-slopes">{slopes}</div><p class="rk-sr">{esc(said)}</p>'
                f'<ul class="rk-key">{key}</ul></div>'
            ),
        ),
    ]
    return "".join(f"<li><div><h3>{esc(h)}</h3><p>{esc(b)}</p></div>{pic}</li>" for h, b, pic in items)


# kind of order, its definition; then each option's on-time orders in 100 per kind (invented)
KINDS = [
    ("Bread", "Loaves and rolls, packed flat in a paper bag."),
    ("Cakes", "Whole cakes in a box that must stay level."),
    ("Large", "Orders of twenty items or more, often for an event."),
    ("Early", "Orders due before eight in the morning."),
]
BY_KIND = {
    "Own van": (88, 71, 52, 79),
    "Bike courier": (93, 64, 38, 90),
    "Partner app": (81, 49, 44, 58),
    "Shared van": (84, 66, 61, 63),
    "Collect in shop": (97, 92, 85, 89),
}
GRADE = (60, 80)


def grid():
    """A dense comparison: options by kinds of order, each cell a number over a thin bar coloured by its grade."""
    lo, hi = GRADE
    heads = "".join(
        f'<th scope="col" class="rk-num" data-sort="number"><button type="button" data-tip="{esc(d)}"><span class="rk-label">{esc(k)}</span></button></th>'
        for k, d in KINDS
    )
    rows = "".join(
        f'<tr><th scope="row">{esc(name)}</th>'
        + "".join(
            f'<td class="rk-num" data-v="{v}"><span class="rk-meter"><b>{v}</b><span class="rk-track" aria-hidden="true">'
            f'<span class="rk-fill" style="--v:{v}"></span></span></span></td>'
            for v in vals
        )
        + "</tr>"
        for name, vals in BY_KIND.items()
    )
    bands = [("hi", f"{hi} and over", f"{hi} or more of 100 on time."), ("mid", f"{lo} to {hi - 1}", f"From {lo} to {hi - 1} of 100 on time."),
             ("lo", f"under {lo}", f"Fewer than {lo} of 100 on time.")]
    key = "".join(
        f'<li>{tipped(d, f"<i class=\"rk-swatch\" data-g=\"{g}\" aria-hidden=\"true\"></i>{esc(t)}", cls="")}</li>' for g, t, d in bands
    )
    return (
        f'<div class="rk-table-wrap" data-rk-grade="{lo} {hi}"><table class="rk-table rk-stack rk-grid" data-rk-sort="toggle" data-rk-stack-at="26rem">'
        '<caption class="rk-sr">On-time orders in 100 by option and kind of order</caption><thead><tr>'
        '<th scope="col" data-sort="default"><button type="button" data-tip="In the trial\'s order; press again to reverse it.">'
        f'<span class="rk-label">Option</span></button></th>{heads}</tr></thead><tbody>{rows}</tbody></table></div>'
        f'<ul class="rk-key">{key}</ul>'
    )


def one_at_a_time():
    """A side column to choose from beside a stage that shows the choice: the levels inside a section (a stage head,
    a figure with its key and caption, two parts side by side), each fact said once. Static: the second option is
    the chosen one."""
    chosen, before = "Bike courier", "Own van"
    picks = "".join(
        f'<li><a href="#one-at-a-time" data-rk-fold-pick{" aria-current=\"true\"" if n == chosen else ""}>{esc(n)}</a></li>'
        for n, *_ in OPTIONS
    )
    wd = dict((n, w) for n, _, w, _ in OPTIONS)[chosen]
    bars = "".join(
        f'<li><span class="rk-pl">{esc(h)}</span><span class="rk-bar"><span class="rk-track" aria-hidden="true">'
        f'<span class="rk-fill" data-k="{k}" style="--v:{v}"></span></span><b>{v}</b><span class="rk-sr"> in 100</span></span></li>'
        for (_, h, k, _), v in zip(COLUMNS, wd, strict=True)
    )
    key = "".join(
        f'<li><span data-tip="{esc(d)}"><i class="rk-mark" data-k="{k}" aria-hidden="true"></i>{esc(h)}</span></li>' for _, h, k, d in COLUMNS
    )
    return f"""<section class="rk-section" aria-labelledby="one-h" id="one-at-a-time">
      <div class="rk-head"><h2 id="one-h">One option at a time</h2></div>
      <div class="rk-split">
        <nav class="rk-aside" aria-labelledby="one-pick-h"><h3 id="one-pick-h">Cheapest first</h3>
          <button type="button" class="rk-fold" aria-controls="one-picks" hidden>All options<span class="rk-fold-cur">{esc(chosen)}</span></button>
          <ul id="one-picks">{picks}</ul></nav>
        <div class="rk-stage">
          <h3>{esc(chosen)}</h3>
          <p>A local courier on a cargo bike, booked by the hour.</p>
          <figure class="rk-fig"><div class="rk-pic"><ul>{bars}</ul></div>
            <ul class="rk-key">{key}</ul>
            <figcaption>Weekday orders, 100 in all.</figcaption></figure>
          <div class="rk-parts">
            <div class="rk-part"><h4>What changes from {esc(before)}</h4>
              <p>The van gives way to a bike that skips the traffic but carries less.</p>
              <ul><li>Six more on time</li><li>Two more damaged, mostly cakes</li></ul></div>
            <div class="rk-part"><h4>On one Saturday order</h4>
              <ol><li>The shop books the 9 o'clock slot.</li><li>The rider collects at 8:40.</li><li>The order arrives at 8:55.</li></ol></div>
          </div>
        </div>
      </div>
    </section>"""


# standing orders, each sent three Saturdays by three options: an outcome per Saturday ("" = not sent that week)
STANDING = [
    ("Café on the corner", "Forty croissants before seven.", {"Own van": "ok ok warn", "Bike courier": "ok ok ok", "Partner app": "warn no "}),
    ("Wedding cake", "A three-tier cake, collected by nobody.", {"Own van": "ok  ", "Bike courier": "bad  ", "Partner app": "  "}),
    ("School fair", "Two hundred buns in four crates.", {"Own van": "ok warn ok", "Bike courier": "warn warn bad", "Partner app": "ok no warn"}),
    ("Night shift", "Sandwiches for a hospital ward at ten at night.", {"Own van": "warn ok ok", "Bike courier": "ok ok ok", "Partner app": "no no ok"}),
]
WORD = {"ok": "on time", "warn": "late", "bad": "damaged", "no": "not delivered", "": "not sent"}


def runs(text):
    """Three Saturdays as a run of marks, said in words."""
    ks = (text.split(" ") + ["", "", ""])[:3]
    marks = "".join(f'<i class="rk-mark" data-k="{k}"></i>' if k else '<i class="rk-mark"></i>' for k in ks)
    return f'<span class="rk-marks" role="img" aria-label="{esc(", ".join(WORD[k] for k in ks))}">{marks}</span>'


def order_card(i):
    name, about, by = STANDING[i]
    rows = "".join(f'<tr><th scope="row">{esc(o)}</th><td>{runs(r)}</td></tr>' for o, r in by.items())
    return (f'<h3 id="order-name">{esc(name)}</h3><p>{esc(about)}</p>'
            f'<table class="rk-table"><caption class="rk-sr">Three Saturdays by option</caption>'
            f'<thead><tr><th scope="col">Option</th><th scope="col">Three Saturdays</th></tr></thead><tbody>{rows}</tbody></table>')


def order_by_order():
    """One item of a list at a time: Previous and Next above the item, the position after them, a dialog for the
    method; each item's outcomes as runs of marks. The page's own script steps (STEP_JS)."""
    key = "".join(
        f'<li><span data-tip="{esc(d)}"><i class="rk-mark" data-k="{k}" aria-hidden="true"></i>{esc(h)}</span></li>' for _, h, k, d in COLUMNS
    ) + '<li><span data-tip="The option was not tried that Saturday."><i class="rk-mark" aria-hidden="true"></i>Not sent</span></li>'
    prev = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    nxt = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M4.5 2.5 8 6 4.5 9.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    cross = '<svg viewBox="0 0 14 14" width="14" height="14" aria-hidden="true"><path d="M2 2 12 12M12 2 2 12" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>'
    return f"""<section class="rk-section" aria-labelledby="orders-h" id="orders">
      <div class="rk-head"><h2 id="orders-h">Standing orders</h2></div>
      <ul class="rk-key">{key}</ul>
      <div class="rk-step" id="order-step">
        <span class="rk-step-pair"><button type="button" data-step="-1" aria-label="Previous order" disabled>{prev}Previous</button>
          <button type="button" data-step="1" aria-label="Next order">Next{nxt}</button></span>
        <span class="rk-step-pos" aria-live="polite">Order 1 of {len(STANDING)}</span>
        <button type="button" class="rk-step-end" data-rk-open="how-scored">How a Saturday is scored</button></div>
      <article id="order-card" aria-labelledby="order-name">{order_card(0)}</article>
      <dialog class="rk-dialog" id="how-scored" aria-labelledby="how-h">
        <div class="rk-dialog-top"><h2 id="how-h">How a Saturday is scored</h2>
          <button type="button" class="rk-dialog-close" aria-label="Close">{cross}</button></div>
        <p>Each Saturday counts once, by what the customer found at the door.</p>
        <h3>On time</h3><p>The order arrived within <span class="rk-term" data-tip="The hour the customer chose when ordering.">the hour</span>.</p>
        <h3>Not sent</h3><p>The option was not tried that Saturday, so it has no outcome.</p>
      </dialog>
    </section>"""


def weekly():
    """Twelve invented weeks of on-time orders in 100 for three options."""
    base = {"Own van": 74, "Bike courier": 80, "Partner app": 63}
    wobble = [0, 2, -1, 3, 1, -2, 2, 4, 1, 3, 5, 4]
    return [
        {"name": n, "week": w + 1, "v": b + wobble[(w + i * 3) % 12] + (w // 4) * (1 - i)}
        for i, (n, b) in enumerate(base.items())
        for w in range(12)
    ]


def page():
    switch = "".join(
        f'<button type="button" data-value="{v}" data-tip="{esc(t)}" aria-pressed="{str(i == 0).lower()}">{esc(label)}</button>'
        for i, (v, label, t) in enumerate(DAYS)
    )
    tables = "".join(table(v, i > 0) for i, (v, *_) in enumerate(DAYS))
    glossary = "".join(f'<div id="{i}"><dt>{esc(t)}</dt><dd>{esc(d)}</dd></div>' for i, t, d in GLOSSARY)
    data = weekly()
    names = list(dict.fromkeys(d["name"] for d in data))
    key = "".join(
        f'<li><svg width="18" height="12" viewBox="0 0 18 12" aria-hidden="true" style="color:var(--viz-{i + 1})">'
        f'<path d="M1 6h16" stroke="currentColor" stroke-width="2.5"/>{sym}</svg>{esc(n)}</li>'
        for i, (n, sym) in enumerate(
            zip(
                names,
                [
                    '<circle cx="9" cy="6" r="3.5" fill="currentColor"/>',
                    '<rect x="5.5" y="2.5" width="7" height="7" fill="currentColor"/>',
                    '<path d="M9 1.5 13.5 6 9 10.5 4.5 6z" fill="currentColor"/>',
                ],
                strict=True,
            )
        )
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Delivery trial</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;600;700;800&display=swap">
<style>
/* report-kit:css all */
</style>
</head>
<body>
<main class="rk-wrap">
  <h1 class="rk-title">Delivery options, a twelve-week trial</h1>
  <p class="rk-lede">A neighbourhood bakery sent its orders five ways. Each row shows 100 orders and what became of them.</p>
  <nav class="rk-tabs"><div role="tablist" aria-label="Parts of the page">
    <a role="tab" id="tab-options" href="#options" aria-controls="options">Options</a>
    <a role="tab" id="tab-trends" href="#trends" aria-controls="trends">Week by week</a>
    <a role="tab" id="tab-notes" href="#notes" aria-controls="notes">Notes</a>
    <a role="tab" id="tab-glossary" href="#glossary" aria-controls="glossary">Glossary</a>
  </div></nav>
  <div id="options" role="tabpanel" aria-labelledby="tab-options">
    <section class="rk-section" aria-labelledby="options-h" data-rk-lit-scope>
      <div class="rk-head"><h2 id="options-h">Options</h2>
        <div class="rk-switch" role="group" aria-label="Days" data-rk-switch="days">{switch}</div></div>
      <div class="rk-table-wrap">{tables}</div>
    </section>
    <section class="rk-section" aria-labelledby="takeaways-h">
      <div class="rk-head"><h2 id="takeaways-h">Takeaways</h2></div>
      <ul class="rk-rows">{takeaways()}</ul>
    </section>
    {one_at_a_time()}
    {order_by_order()}
  </div>
  <div id="trends" role="tabpanel" aria-labelledby="tab-trends" hidden>
    <section class="rk-section" aria-labelledby="trends-h">
      <div class="rk-head"><h2 id="trends-h">On time, week by week</h2></div>
      <figure class="rk-chart" id="trend">
        <figcaption>On-time orders in 100, three options over twelve weeks</figcaption>
        <ul class="rk-key">{key}</ul>
        <div class="rk-chart-plot"></div>
      </figure>
    </section>
  </div>
  <div id="notes" role="tabpanel" aria-labelledby="tab-notes" hidden></div>
  <div id="glossary" role="tabpanel" aria-labelledby="tab-glossary" hidden>
    <section class="rk-section" aria-labelledby="glossary-h">
      <div class="rk-head"><h2 id="glossary-h">Glossary</h2></div>
      <dl class="rk-glossary">{glossary}</dl>
    </section>
  </div>
</main>
<div class="rk-tip" id="rk-tip" data-pin hidden></div>
<!-- report-kit:vendor plot -->
<script>
/* report-kit:js all */
</script>
<script>
const ORDERS = {json.dumps([order_card(i) for i in range(len(STANDING))])};
(() => {{ // the page's own stepping: Previous and Next keep their places; the item takes its own height
  const step = document.getElementById("order-step"), card = document.getElementById("order-card");
  const [back, fwd] = step.querySelectorAll("[data-step]"), pos = step.querySelector(".rk-step-pos");
  let at = 0;
  const go = d => {{
    at = Math.max(0, Math.min(ORDERS.length - 1, at + d));
    card.innerHTML = ORDERS[at];
    pos.textContent = "Order " + (at + 1) + " of " + ORDERS.length;
    back.disabled = at === 0; fwd.disabled = at === ORDERS.length - 1;
    const f = document.activeElement; // the pressed button went to an end and lost the focus: give it to the other
    if (!f || f === document.body || f.disabled) (d < 0 ? fwd : back).focus();
  }};
  back.addEventListener("click", () => go(-1)); fwd.addEventListener("click", () => go(1));
}})();
const WEEKS = {json.dumps(data, separators=(",", ":"))};
const NAMES = {json.dumps(names)};
ReportKit.plot(document.getElementById("trend"), (t, width) => ({{
  ariaLabel: "On-time orders in 100 per week for " + NAMES.join(", ") + ", weeks 1 to 12, all between 60 and 90.",
  height: Math.round(Math.max(240, t.fontPx * 18)),
  x: {{ domain: [1, 12], ticks: width < t.fontPx * 36 ? [1, 4, 8, 12] : [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], label: "Week", tickFormat: d => d }},
  y: {{ domain: [0, 100], ticks: [0, 25, 50, 75, 100], label: null }},
  color: {{ domain: NAMES }},
  symbol: {{ domain: NAMES, range: ["circle", "square", "diamond"] }},
  marks: [
    Plot.ruleY([0], {{ stroke: t.ink }}),
    Plot.line(WEEKS, {{ x: "week", y: "v", stroke: "name", strokeWidth: 2.5 }}),
    Plot.dot(WEEKS, {{ x: "week", y: "v", symbol: "name", fill: "name", r: 3.5, tip: false }}),
  ],
}}));
</script>
</body>
</html>
"""


def scoped():
    """A host page that keeps its own look, with the kit running inside one element of it (scope=#report)."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Bakery newsletter</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;600;700;800&display=swap">
<style>
:root {{ --host-ground: #ffffff; --host-ink: #1f2328; --host-rule: #8a5a2b }}
body {{ margin: 0; background: var(--host-ground); color: var(--host-ink); font: 400 1.0625rem/1.6 Georgia, serif }}
.host {{ max-width: 46rem; margin: 0 auto; padding: 2rem 16px }}
.host h2 {{ font-size: 1.75rem; font-weight: 400; border-bottom: 1px solid var(--host-rule) }}
#report {{ border-radius: 12px; padding: 24px 16px }}
/* report-kit:css tokens base section bar grade table-sort tip scope=#report */
</style>
</head>
<body>
<div class="host">
  <h2 id="host-h">News from the counter</h2>
  <p>The host page keeps its own type and colours; the report below brings the kit's.</p>
  <div id="report">
    <section class="rk-section" aria-labelledby="grid-h">
      <div class="rk-head"><h2 id="grid-h">On time by kind of order</h2></div>
      <ul class="rk-rows"><li><div><h3>Bread travels well, large orders do not</h3>
        <p>On-time orders in 100 by kind of order; press a column to sort by it.</p></div></li></ul>
      {grid()}
    </section>
  </div>
  <p>More news next week.</p>
</div>
<script>
/* report-kit:js table-sort tip grade scope=#report */
</script>
</body>
</html>
"""


def main():
    for name, text in (("fixture.html", page()), ("scoped.html", scoped())):
        out = HERE / name
        out.write_text(text)
        subprocess.run(["node", str(KIT / "bin" / "build.cjs"), str(out)], check=True)


if __name__ == "__main__":
    main()
