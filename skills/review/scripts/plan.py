#!/usr/bin/env python3
"""Prints which reviewers a review round runs, in which order, from the change's paths: the lead may add a lens,
never drop one, so the author does not choose who reviews it.

  plan.py [--base <ref>] [--head <ref>] [--mode light|focused|full] [--add <lens>[,<lens>...]]
          [--since <reviewed sha> --prior <the verifier output of that round>] [--json]

A first review (no --since) runs the tier's lenses:
  routine    none: gates only.
  standard   correctness-reviewer.
  sensitive  correctness-reviewer, claims-auditor and guardrail-reviewer.
  Both add the lenses REVIEW.md names for the changed paths (tier.sh prints them) and every --add.
A fix round (--since and --prior) runs only what the fix needs:
  every lens a must-fix on the prior round's `Blocking:` line came from (by its id's prefix, see PREFIX);
  correctness-reviewer when the fix changes a path tier.sh does not rank routine;
  claims-auditor when every path the fix changes is routine;
  the sensitive set (correctness-reviewer, claims-auditor, guardrail-reviewer) when the fix changes a sensitive path;
  the lenses REVIEW.md names for the paths the fix changed, and every --add (pass the first review's again).
  --prior's `Reviewed:` line must name --since, and --since must not be the change's merge-base with --base.
  A `Blocking:` id whose prefix names no lens runs the first review's whole set instead.
Modes (default focused):
  focused  correctness-reviewer first, alone; the other lenses then start in parallel with its findings in their
           briefs as raised this round (templates.md).
  full     every lens of the first review's set at once, on a fix round too.
  light    the planned lenses at once, with no first phase; refused on a sensitive change's first review.
Prints `mode`, `tier`, `first`, `then` and `verifier` lines (`--json`: one object with those keys and `why`), or
exits 2 with the reason.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import blocking  # noqa: E402


def die(why: str) -> None:
    sys.stderr.write(f"plan.py: {why}\n")
    sys.exit(2)

LENSES = ["correctness-reviewer", "claims-auditor", "guardrail-reviewer", "control-prober", "leak-hunter"]
PREFIX = {"COR": "correctness-reviewer", "CLM": "claims-auditor", "GRD": "guardrail-reviewer",
          "CTL": "control-prober", "LEAK": "leak-hunter"}
BASE = {"routine": [], "standard": ["correctness-reviewer"],
        "sensitive": ["correctness-reviewer", "claims-auditor", "guardrail-reviewer"]}
VERIFIER = "finding-verifier"
REVIEWED = re.compile(r"^[ \t]*Reviewed:[ \t]*`?([0-9a-f]{7,40})`?[ \t]*$")


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True)
    if done.returncode:
        die(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout.strip()


def default_base() -> str:
    for ref in ("origin/HEAD", "origin/main", "origin/master"):
        if subprocess.run(["git", "rev-parse", "-q", "--verify", ref], capture_output=True).returncode == 0:
            return ref
    die("cannot tell the default branch: pass --base")
    return ""


def tier(args: list[str]) -> tuple[str, set[str]]:
    done = subprocess.run(["bash", str(HERE / "tier.sh"), *args], capture_output=True, text=True)
    if done.returncode:
        die(f"tier.sh {' '.join(args)}: {done.stderr.strip() or done.returncode}")
    lines = done.stdout.splitlines()
    named = set()
    for line in lines[1:]:
        if "lenses: " in line:
            named.update(x.strip(" )") for x in line.split("lenses: ", 1)[1].split(";")[0].split(","))
    return lines[0], {x for x in named if x}


def ordered(lenses: set[str]) -> list[str]:
    return sorted(lenses, key=lambda x: (LENSES.index(x) if x in LENSES else len(LENSES), x))


def main() -> int:
    p = argparse.ArgumentParser(prog="plan.py")
    p.add_argument("--base")
    p.add_argument("--head", default="HEAD")
    p.add_argument("--mode", choices=["light", "focused", "full"], default="focused")
    p.add_argument("--add", default="")
    p.add_argument("--since")
    p.add_argument("--prior")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    if bool(a.since) != bool(a.prior):
        die("a fix round takes both --since <reviewed sha> and --prior <that round's verifier output>")
    common = (["--base", a.base] if a.base else []) + ["--head", a.head]
    added = {x.strip() for x in a.add.split(",") if x.strip()}
    if unknown := added - set(LENSES):
        die(f"--add names no lens: {', '.join(sorted(unknown))} (lenses: {', '.join(LENSES)})")
    top, named = tier(common)
    whole = set(BASE[top]) | named | added if top != "routine" else set()
    why = [f"the change's paths make it {top}"]
    if top == "routine":
        lenses = set()
        why.append("routine needs gates only")
    elif a.since and a.mode != "full":
        try:
            text = open(a.prior, encoding="utf-8", errors="replace", newline="").read()
            items = blocking.read(text)
        except (OSError, ValueError) as e:
            die(f"--prior is not a verifier output this script can read: {e}")
        since = git("rev-parse", "--verify", a.since + "^{commit}")
        named_sha = next((m.group(1) for m in (REVIEWED.match(ln) for ln in text.split("\n")) if m), "")
        if not named_sha or not since.startswith(named_sha) or len(named_sha) < 7:
            die(f"--prior reviewed {named_sha or 'no commit'}, not --since {since}: give the verifier output of the "
                "round that reviewed --since")
        if since == git("merge-base", a.base or default_base(), a.head):
            die("--since is the change's merge-base, so this is a first review: drop --since and --prior")
        prefixes = {x.strip().rsplit("-", 1)[0] for b in items for x in b["ids"].split(",") if x.strip()}
        fix_top, fix_named = tier(common + ["--since", a.since])
        if prefixes - set(PREFIX):
            lenses = whole
            why.append(f"a blocking id's prefix ({', '.join(sorted(prefixes - set(PREFIX)))}) names no lens, so the "
                       "whole set runs")
        else:
            lenses = {PREFIX[x] for x in prefixes} | fix_named | added
            why.append("the lenses whose must-fix the fix answers" if prefixes else "no must-fix was open")
            if fix_top == "routine":
                lenses.add("claims-auditor")
                why.append("the fix changes documentation only, so claims-auditor reads it")
            else:
                lenses.add("correctness-reviewer")
                why.append("the fix changes code, tests, configuration or rules, so correctness-reviewer reads it")
            if fix_top == "sensitive":
                lenses |= set(BASE["sensitive"])
                why.append("the fix changes a sensitive path, so the sensitive set reads it")
            if fix_named:
                why.append("REVIEW.md names lenses for the paths the fix changed")
    else:
        lenses = whole
        if a.since:
            why.append("full mode reruns the first review's whole set")
    if a.mode == "light" and top == "sensitive" and not a.since:
        die("light mode cannot run a sensitive change's first review: use focused or full")
    run = ordered(lenses)
    first, then = ([], run) if a.mode != "focused" or "correctness-reviewer" not in run or len(run) == 1 else \
        (["correctness-reviewer"], [x for x in run if x != "correctness-reviewer"])
    if a.mode == "focused" and first:
        why.append("focused: correctness-reviewer runs first and the others get its findings")
    out = {"mode": a.mode, "tier": top, "first": first, "then": then, "verifier": VERIFIER if run else "", "why": why}
    if a.json:
        print(json.dumps(out))
    else:
        for k in ("mode", "tier"):
            print(f"{k}: {out[k]}")
        for k in ("first", "then"):
            print(f"{k}: {', '.join(out[k]) or 'none'}")
        print(f"verifier: {out['verifier'] or 'none'}")
        print(f"why: {'; '.join(why)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
