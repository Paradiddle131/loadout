#!/usr/bin/env python3
"""Reads the verifier's `Blocking:` line: the must-fix findings of its output and the harm each names.

  blocking.py <file>   prints how many must-fix findings the line lists; exits 2 with the reason when the line
                       is missing or malformed, names an id no `###` heading outside a code fence opens with, or a listed
                       finding names no harm
  blocking.py --patched <file>
                       prints `<ids> <settled id>` for each finding block, outside a code fence, holding the verifier's
                       `- class: patched, not fixed (<settled id>)` line: a re-raise of a settled must-fix's class

The line is the one right after the output's first `Reviewed:` line (agents/finding-verifier.md § Output):
  Blocking: none
  Blocking: [{"ids": "COR-1, CLM-2", "harm": "an operator trusts a total that drops rows"}, ...]
Lines are split on newlines only and leading blanks are grep's in the C locale, which `verdict.sh` sets, so both
read the same `Reviewed:` line.
A harm has at least two words, is not the template's unfilled `<...>` slot, and is not made only of the words
in FILLER below (`none`, `no harm`, `TBD` and the like); a short dismissal off that list, such as `wording only`,
passes, so the check catches a forgotten harm, not a weak or false one.
Each listed id must be one of the ids a `###` line outside a code fence below the header opens with; the line is
not otherwise compared with the finding blocks, and an unclosed fence hides the headings after it (a refusal).
"""

from __future__ import annotations

import json
import re
import sys

from record import stored  # the text as GitHub stores it: a record's counts come from what it holds

WS = r"[ \t\v\f\r]"  # what grep's [[:space:]] matches inside a line in the C locale, which verdict.sh sets
REVIEWED = re.compile(rf"^{WS}*Reviewed:")
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


def read(text: str) -> list[dict]:
    lines = text.split("\n")
    at = next((i for i, ln in enumerate(lines) if REVIEWED.match(ln)), None)
    if at is None or at + 1 >= len(lines) or not (m := LINE.match(lines[at + 1])):
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
    heads, fence = set(), None
    for n, ln in enumerate(lines):  # finding ids: the comma-separated ids of each `###` line outside a code fence
        mark = re.match(r"\s*(`{3,}|~{3,})", ln)
        if mark:
            fence = None if fence and mark.group(1)[0] == fence[0] else (fence or mark.group(1))
        elif n > at + 1 and fence is None and ln.startswith("###"):
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
    found, fence, ids = [], None, ""
    for ln in text.split("\n"):
        mark = re.match(r"\s*(`{3,}|~{3,})", ln)
        if mark:
            fence = None if fence and mark.group(1)[0] == fence[0] else (fence or mark.group(1))
        elif fence is None and ln.startswith("###"):
            ids = ln.lstrip("#").strip()
        elif fence is None and ids and (m := PATCHED.match(ln)):
            found.append((ids.replace(" ", ""), m.group(1)))
    return found


def main() -> int:
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
