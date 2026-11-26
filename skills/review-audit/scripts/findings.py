#!/usr/bin/env python3
"""Reads a finding-verifier output (agents/finding-verifier.md § Output) into its parts, leniently, for counting.

The review gate reads only the `Blocking:` line (the review skill's blocking.py); this reader is for audits of
past records, where a misread block shifts a count, never a verdict.

  findings.py parse <file>          prints the output as JSON: verdict, reviewed, steering, settled and findings
  findings.py missing-harm <file>   prints the ids of each must-fix finding that names no harm, `;`-separated
  findings.py must-fix <file>       prints how many must-fix findings the output holds

A finding is a `### <id>[, <id>...]` block (an id such as `COR-1`) at the start of a line outside a code fence;
its fields are `- <name>: <value>` lines at the start of a line; its section is the verifier's `## ` heading
above it (Must-fix, Nits, Pre-existing, Settled, Dropped, Unverified, Not checked); other headings are quoted text.
It is a must-fix when its `rank:` line says so, or, with no rank line, when its section is the must-fix one;
a must-fix needs a `harm:` line with a real value (text that may wrap onto the next indented lines).
Lines inside a fence (```, ~~~, indented at most three spaces) are quoted material, so a heading or a field there
counts for nothing; containers (list items, HTML blocks) are not modelled, so a count may shift, never a verdict.
"""

from __future__ import annotations

import json
import re
import sys

FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")  # four spaces in, a run is indented code, not a fence
H2 = re.compile(r"^##\s+(\S.*?)\s*$")
H3 = re.compile(r"^###\s+(\S.*?)\s*$")
SECTION = re.compile(r"(must[\s_-]*fix|nits?|pre-?existing|settled|dropped|unverified|not checked)\b", re.I)
FINDING_ID = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+")
FIELD = re.compile(r"^[-*]\s*(?:\*\*|__)?([a-z][a-z -]*?)\s*:(?:\*\*|__)?\s*(.*)$", re.I)
CONT = re.compile(r"^\s{2,}(\S.*)$")
TOP = re.compile(r"^\s*(VERDICT|Reviewed|Steering from the brief|Settled in the brief|Lens heads)\s*:\s*(.*)$")
PLACEHOLDER = re.compile(r"^[\s`*_.]*(none|n/?a|-+|tbd|todo|unknown|nothing|no harm)?[\s`*_.]*$", re.I)


def must_fix_words(text: str) -> bool:
    return re.sub(r"[\s_-]+", "", text.lower()).startswith("mustfix")


def parse(text: str) -> dict:
    out: dict = {"verdict": None, "reviewed": None, "steering": [], "settled": [], "lens_heads": None,
                 "findings": []}
    fence, section, block, last = None, "", None, None
    for line in text.splitlines():
        m = FENCE.match(line)
        if m:
            mark = m.group(1)
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence) and not line.strip()[len(mark):].strip():
                fence = None
            continue
        if fence is not None:
            continue
        if (h := H3.match(line)) and FINDING_ID.match(h.group(1)):
            block = {"ids": [i.strip() for i in h.group(1).split(",") if i.strip()], "section": section,
                     "fields": {}}
            out["findings"].append(block)
            last = None
        elif (h := H2.match(line)) and SECTION.match(h.group(1)):
            section, block, last = h.group(1), None, None
        elif block is not None and (f := FIELD.match(line)):
            last = f.group(1).strip().lower()
            block["fields"][last] = f.group(2).strip()
        elif block is not None and last and (c := CONT.match(line)):
            block["fields"][last] = (block["fields"][last] + " " + c.group(1)).strip()
        elif block is None and (t := TOP.match(line)):
            key, val = t.group(1), t.group(2).strip()
            last = None
            if key == "VERDICT" and out["verdict"] is None:
                out["verdict"] = val
            elif key == "Reviewed" and out["reviewed"] is None:
                out["reviewed"] = val
            elif key == "Steering from the brief":
                out["steering"].append(val)
            elif key == "Settled in the brief":
                out["settled"].append(val)
            elif key == "Lens heads":
                out["lens_heads"] = val
        else:
            last = None if not line.strip() else last
    for b in out["findings"]:
        rank = b["fields"].get("rank", "")
        b["rank"] = rank or None
        b["must_fix"] = must_fix_words(rank) if rank else must_fix_words(b["section"])
        harm = b["fields"].get("harm", "")
        b["harm"] = None if PLACEHOLDER.fullmatch(harm) else harm
    return out


def missing_harm(text: str) -> list[str]:
    return [", ".join(b["ids"]) for b in parse(text)["findings"] if b["must_fix"] and not b["harm"]]


def must_fix_count(text: str) -> int:
    return sum(b["must_fix"] for b in parse(text)["findings"])


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ("parse", "missing-harm", "must-fix"):
        sys.stderr.write("usage: findings.py parse|missing-harm|must-fix <file>\n")
        return 2
    text = open(sys.argv[2], encoding="utf-8", errors="replace").read()
    if sys.argv[1] == "parse":
        json.dump(parse(text), sys.stdout, indent=1)
        sys.stdout.write("\n")
    elif sys.argv[1] == "must-fix":
        print(must_fix_count(text))
    else:
        print("; ".join(missing_harm(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
