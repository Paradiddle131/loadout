#!/usr/bin/env python3
"""Reads the verifier's `Blocking:` line: the must-fix findings of its output and the harm each names.

  blocking.py <file>   prints how many must-fix findings the line lists; exits 2 with the reason when the line
                       is missing or malformed, names an id that heads no `###` finding below it, or a listed
                       finding names no harm

The line is the one right after the output's first `Reviewed:` line (agents/finding-verifier.md § Output):
  Blocking: none
  Blocking: [{"ids": "COR-1, CLM-2", "harm": "an operator trusts a total that drops rows"}, ...]
Lines are split on newlines only and leading blanks are grep's, so both read the same `Reviewed:` line.
A harm has at least two words, is not the template's unfilled `<...>` slot, and is not made only of the words
in FILLER below (`none`, `no harm`, `TBD` and the like); a short dismissal off that list, such as `wording only`,
passes, so the check catches a forgotten harm, not a weak or false one.
Each listed id must head a `###` line below the header (as a whole id); the line is not otherwise compared with
the finding blocks.
"""

from __future__ import annotations

import json
import re
import sys

WS = r"[ \t\v\f\r]"  # what grep's [[:space:]] matches inside a line, so both read the same `Reviewed:` line
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
    heads = [ln for ln in lines[at + 2:] if ln.startswith("###")]
    for i, b in enumerate(items):
        ids = b.get("ids") if isinstance(b, dict) else None
        names = [x.strip() for x in ids.split(",") if x.strip()] if isinstance(ids, str) else []
        if not names:
            raise ValueError(f"blocking finding {i + 1} has no `ids`")
        if missing := [x for x in names
                       if not any(re.search(rf"(?<![\w-]){re.escape(x)}(?![\w-])", h) for h in heads)]:
            raise ValueError(f"the `Blocking:` line names {', '.join(missing)}, which heads no `###` finding below it")
        if no_harm(b.get("harm")):
            raise ValueError(f"must-fix {', '.join(names)} names no harm: its `harm` says who acts wrongly or what "
                             "breaks once the change lands")
    return items


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: blocking.py <verifier output>\n")
        return 2
    try:
        items = read(open(sys.argv[1], encoding="utf-8", errors="replace").read())
    except (OSError, ValueError) as e:
        sys.stderr.write(f"{e}\n")
        return 2
    print(len(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
