#!/usr/bin/env python3
"""Reads the verifier's `Blocking:` line: the must-fix findings of its output and the harm each names.

  blocking.py <file>   prints how many must-fix findings the line lists; exits 2 with the reason when the line
                       is missing or malformed, names an id the output holds nowhere else, or a listed finding
                       names no harm

The line is the one right after the output's first `Reviewed:` line (agents/finding-verifier.md § Output):
  Blocking: none
  Blocking: [{"ids": "COR-1, CLM-2", "harm": "an operator trusts a total that drops rows"}, ...]
Lines are split on newlines only, as `verdict.sh`'s grep splits them, so both read the same `Reviewed:` line.
A harm has at least two words, is not the template's bare `<...>` slot, and is not made only of filler words
such as `none`, `no harm` or `TBD`.
The check refuses a listed must-fix with no harm; it does not compare the line with the finding blocks below it,
and it cannot tell a real harm from a false one.
"""

from __future__ import annotations

import json
import re
import sys

REVIEWED = re.compile(r"^\s*Reviewed:")
LINE = re.compile(r"^\s*Blocking:\s*(.*?)\s*$")
FILLER = {"none", "n/a", "na", "tbd", "todo", "unknown", "nothing", "no", "harm", "at", "all", "yet", "identified",
          "stated", "concrete", "named", "-", "—", "see", "above", "below"}


def no_harm(harm: object) -> bool:
    if not isinstance(harm, str):
        return True
    text = harm.strip().strip("`*_ ").strip()
    if text.startswith("<") and text.endswith(">"):
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
    rest = "\n".join(lines[at + 2:])
    for i, b in enumerate(items):
        ids = b.get("ids") if isinstance(b, dict) else None
        names = [x.strip() for x in ids.split(",") if x.strip()] if isinstance(ids, str) else []
        if not names:
            raise ValueError(f"blocking finding {i + 1} has no `ids`")
        if missing := [x for x in names if x not in rest]:
            raise ValueError(f"the `Blocking:` line names {', '.join(missing)}, which the output holds nowhere else")
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
