#!/usr/bin/env python3
"""Reads the verifier's `Blocking:` line: the must-fix findings of its output and the harm each names.

  blocking.py <file>   prints how many must-fix findings the line lists; exits 2 with the reason when the header is
                       refused (below), the line is missing or malformed, names an id no `###` heading outside a code
                       fence opens with, or a listed finding names no harm
  blocking.py --header <file>
                       prints the header's `VERDICT:` and `Reviewed:` lines (an empty line for one the output's first
                       lines lack), read as GitHub stores the output (record.py § stored); exits 2 with the reason when
                       the header is refused
  blocking.py --patched <file>
                       prints `<ids> <settled id>` for each finding block, outside a code fence, holding the verifier's
                       `- class: patched, not fixed (<settled id>)` line: a re-raise of a settled must-fix's class

The header is the output's first lines (agents/finding-verifier.md § Output): its first non-blank line `VERDICT:`,
the next `Reviewed:`, the next `Blocking:`, and every reader (verdict.sh through --header, plan.py's previous round,
the count here) takes it from there and nowhere else. Any other line that starts, after blanks, with `VERDICT:`,
`Reviewed:` or `Blocking:` refuses the output, wherever it stands and whatever fence surrounds it, so no fence is
parsed to find the header and no decoy can decide it:
  Blocking: none
  Blocking: [{"ids": "COR-1, CLM-2", "harm": "an operator trusts a total that drops rows"}, ...]
Lines are split on newlines only, and blanks are the C locale's [[:space:]] within a line, which `verdict.sh` sets.
A harm has at least two words, is not the template's unfilled `<...>` slot, and is not made only of the words
in FILLER below (`none`, `no harm`, `TBD` and the like); a short dismissal off that list, such as `wording only`,
passes, so the check catches a forgotten harm, not a weak or false one.
Each listed id must be one of the ids a `###` line outside a code fence below the header opens with; the line is
not otherwise compared with the finding blocks; a fence is read as GitHub reads it (record.py § fenced), and an
unclosed fence hides the headings after it (a refusal).
"""

from __future__ import annotations

import json
import re
import sys

from record import fenced, stored  # the text as GitHub stores it: a record's counts come from what it holds

WS = r"[ \t\v\f\r]"  # what grep's [[:space:]] matches inside a line in the C locale, which verdict.sh sets
LINE = re.compile(rf"^{WS}*Blocking:{WS}*(.*?){WS}*$")
FILLER = {"none", "n/a", "na", "tbd", "todo", "unknown", "nothing", "no", "harm", "at", "all", "yet", "identified",
          "stated", "concrete", "named", "-", "—", "see", "above", "below"}


def no_harm(harm: object) -> bool:
    if not isinstance(harm, str):
        return True
    text = harm.strip().strip("`*_ ").strip()
    if re.fullmatch(r"<[^<>]*>", text):  # the template's slot, left unfilled
        return True
    words = [w.strip("`*_.,;:()[]").lower() for w in text.split()]
    words = [w for w in words if w]
    return len(words) < 2 or all(w in FILLER for w in words)


HEADER = re.compile(rf"^{WS}*(VERDICT|Reviewed|Blocking):")
WORDS = ("VERDICT", "Reviewed", "Blocking")
SHAPE = "a `VERDICT: PASS|FAIL <sha>` line, then `Reviewed: <sha>`, then `Blocking:`"


def header(lines: list[str]) -> tuple[int, list[str]]:
    """The verifier's header, taken from the output's first lines and nowhere else: (the index of its first non-blank
    line, and that line and the two after it, kept while each starts with `VERDICT:`, `Reviewed:` and `Blocking:` in
    turn, '' for the first that does not and each after it).

    ValueError when any other line, anywhere, fenced or not and however indented, starts with one of those words: only
    the header starts a line so, and the verifier writes a quoted one after `> ` (agents/finding-verifier.md § Output),
    so no line but the header can decide the record, whatever fence surrounds it.
    """
    at = next((i for i, ln in enumerate(lines) if ln.strip(" \t\v\f\r")), 0)
    got: list[str] = []
    for k, word in enumerate(WORDS):
        m = HEADER.match(lines[at + k]) if at + k < len(lines) else None
        if not m or m.group(1) != word:
            break
        got.append(lines[at + k])
    for i, ln in enumerate(lines):
        if (m := HEADER.match(ln)) and not at <= i < at + len(got):
            word = m.group(1)
            many = sum(1 for x in lines if (h := HEADER.match(x)) and h.group(1) == word) > 1
            said = (f"the output holds more than one `{word}:` line (line {i + 1} is not in its header)" if many
                    else f"the output's line {i + 1} starts with `{word}:` outside its header")
            raise ValueError(f"{said}: a verifier's output opens with its header, {SHAPE}, and any other line that "
                             "starts with one of those words, a fenced one included, is written after `> `")
    return at, got + [""] * (len(WORDS) - len(got))


def read(text: str) -> list[dict]:
    lines = text.split("\n")
    first, got = header(lines)
    if not got[1]:
        raise ValueError(f"the output does not open with the verifier's header: {SHAPE}")
    at = first + 1  # the `Reviewed:` line
    if not (m := LINE.match(got[2])):
        raise ValueError("the line after `Reviewed:` is not a `Blocking:` line")
    value = m.group(1).strip("`").strip()
    if value.lower() == "none":
        return []
    try:
        items = json.loads(value)
    except json.JSONDecodeError as e:
        raise ValueError(f"the `Blocking:` line is neither `none` nor a JSON list ({e.msg})") from None
    if not isinstance(items, list) or not items:
        raise ValueError("the `Blocking:` line is neither `none` nor a non-empty JSON list")
    heads = set()
    for n, (ln, in_fence) in enumerate(zip(lines, fenced(lines))):  # the ids of each `###` line outside a code fence
        if n > at + 1 and not in_fence and ln.startswith("###"):
            heads.update(p.strip(" `*_").split(" ")[0].strip("`*_") for p in ln.lstrip("#").split(","))
    for i, b in enumerate(items):
        ids = b.get("ids") if isinstance(b, dict) else None
        names = [x.strip() for x in ids.split(",") if x.strip()] if isinstance(ids, str) else []
        if not names:
            raise ValueError(f"blocking finding {i + 1} has no `ids`")
        if missing := [x for x in names if x not in heads]:
            raise ValueError(f"the `Blocking:` line names {', '.join(missing)}, which no `###` heading below it opens with")
        if no_harm(b.get("harm")):
            raise ValueError(f"must-fix {', '.join(names)} names no harm: its `harm` says who acts wrongly or what "
                             "breaks once the change lands")
    return items


PATCHED = re.compile(rf"^{WS}*-{WS}+class:{WS}*patched, not fixed{WS}*\(`?([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-[0-9]+)`?\){WS}*$")


def patched(text: str) -> list[tuple[str, str]]:
    """(the block's ids, the settled id) for each finding block outside a code fence marked `patched, not fixed`."""
    found, ids = [], ""
    lines = text.split("\n")
    for ln, in_fence in zip(lines, fenced(lines)):
        if in_fence:
            continue
        if ln.startswith("###"):
            ids = ln.lstrip("#").strip()
        elif ids and (m := PATCHED.match(ln)):
            found.append((ids.replace(" ", ""), m.group(1)))
    return found


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--header":  # the header lines verdict.sh reads, as every reader does
        try:
            _, got = header(stored(open(sys.argv[2], encoding="utf-8", errors="replace", newline="").read()).split("\n"))
        except (OSError, ValueError) as e:
            sys.stderr.write(f"{e}\n")
            return 2
        print(got[0])
        print(got[1])
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "--patched":
        try:
            text = stored(open(sys.argv[2], encoding="utf-8", errors="replace", newline="").read())
        except OSError as e:
            sys.stderr.write(f"{e}\n")
            return 2
        for ids, settled in patched(text):
            print(ids, settled)
        return 0
    if len(sys.argv) != 2:
        sys.stderr.write("usage: blocking.py [--patched] <verifier output>\n")
        return 2
    try:
        items = read(stored(open(sys.argv[1], encoding="utf-8", errors="replace", newline="").read()))
    except (OSError, ValueError) as e:
        sys.stderr.write(f"{e}\n")
        return 2
    print(len(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
