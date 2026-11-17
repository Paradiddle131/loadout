#!/usr/bin/env python3
"""Reads the verifier's `Blocking:` line: the must-fix findings of its output and the harm each names.

  blocking.py <file>   prints how many must-fix findings the line lists; exits 2 with the reason when the line
                       is missing or malformed, or a finding names no harm

The line is the one right after the output's first `Reviewed:` line (agents/finding-verifier.md § Output):
  Blocking: none
  Blocking: [{"ids": "COR-1, CLM-2", "harm": "an operator trusts a total that drops rows"}, ...]
Only that line is read, so quoted text anywhere else in the output cannot change it. A harm is a sentence: at least
three words, not a placeholder such as `none` or the template's `<...>` slot. The check guards against a
forgotten harm, not against a verifier that writes a false one.
"""

from __future__ import annotations

import json
import re
import sys

REVIEWED = re.compile(r"^\s*Reviewed:")
LINE = re.compile(r"^\s*Blocking:\s*(.*?)\s*$")
PLACEHOLDER = re.compile(r"(none|n/?a|tbd|todo|unknown|nothing|no harm|-+|—)", re.I)


def read(text: str) -> list[dict]:
    lines = text.splitlines()
    at = next((i for i, ln in enumerate(lines) if REVIEWED.match(ln)), None)
    if at is None or at + 1 >= len(lines) or not (m := LINE.match(lines[at + 1])):
        raise ValueError("the line after `Reviewed:` is not a `Blocking:` line")
    value = m.group(1)
    if value.lower() == "none":
        return []
    try:
        items = json.loads(value)
    except json.JSONDecodeError as e:
        raise ValueError(f"the `Blocking:` line is neither `none` nor a JSON list ({e.msg})") from None
    if not isinstance(items, list) or not items:
        raise ValueError("the `Blocking:` line is neither `none` nor a non-empty JSON list")
    for i, b in enumerate(items):
        ids = b.get("ids") if isinstance(b, dict) else None
        if not isinstance(ids, str) or not ids.strip():
            raise ValueError(f"blocking finding {i + 1} has no `ids`")
        harm = b.get("harm")
        words = harm.strip(" `*_.()").split() if isinstance(harm, str) else []
        if (len(words) < 3 or harm.strip().startswith("<")
                or PLACEHOLDER.fullmatch(harm.strip(" `*_.()"))):
            raise ValueError(f"must-fix {ids.strip()} names no harm: its `harm` says who acts wrongly or what "
                             "breaks once the change lands, in a sentence")
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
