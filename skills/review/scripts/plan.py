#!/usr/bin/env python3
"""Plans a review round from a PR's paths and the repo's policy: its depth, its lenses in order and each lens's effort.

  plan.py [--pr <n>] [--depth none|light|focused|full] [--owner "<the owner's words>"] [--json]
      the lead's preview: what verdict.sh will require of the round it records for PR <n> (the current branch's
      open PR when --pr is left out); --depth raises the depth, never lowers it below the floor, unless --owner
      quotes the owner's instruction that set it (an owner override: light, focused or full, on any path).
  plan.py record --pr <n> [--depth <d>] [--owner "<words>"] --reviewers <names> --lens "<name> ... effort=<e> ..."...
      what verdict.sh runs: the same plan, then refuses a reviewer set missing a planned lens or the verifier, or a
      planned lens run below its planned effort; prints the marker's depth and the round line's pairs.
  plan.py floor --base <ref> --head <ref>
      what the merge guard runs, like tier.sh: the tier and the depth floor of the paths, from a local clone.

The preview and the record read the same inputs the same way, and neither takes a base, a head, a reviewed commit
or a prior output from the lead: no option can change what verdict.sh records except to raise it.

Inputs, where each is read from, who controls it, and how a lead-controlled one can only raise the plan:

| Input | Read from | Controlled by | Enforcement |
|---|---|---|---|
| PR head | `gh api repos/<r>/pulls/<n>`, `.head.sha` | GitHub's PR API | fetched by that sha; the checkout, `HEAD` and local branches are never read |
| Default branch name | the same answer, `.base.repo.default_branch` | GitHub's PR API | `origin/HEAD` and local branch names are never read |
| Default branch tip | `gh api repos/<r>/branches/<name>`, `.commit.sha`; then `git fetch --force origin +refs/heads/<name>:refs/remotes/origin/<name>` | GitHub (the sha), the remote (the objects) | the forced fetch overwrites a locally moved ref; a fetched tip other than GitHub's sha refuses |
| Changed paths | `git diff --name-only --no-renames $(git merge-base <tip> <head>) <head>` | the two shas above | computed from content-addressed commits only |
| Policy | `REVIEW.md` at the tip, parsed by tiers.py (tier.sh's parser), and the tip's instruction imports | the default branch on the remote | the change's own `REVIEW.md` is never read; an unparsable one rates every path sensitive; no line lowers a path below the built-in floor or below `## Sensitive` |
| Previous round | `gh api repos/<r>/issues/<n>/comments`, paged by hand: the newest review-marker comment by the owner, a member or a collaborator | a trusted record on the PR | used only when unedited, in verdict.sh's exact shape, at or above the change's tier and this round's depth, its raw output's first `Reviewed:` naming its `reviewed=`, its `Blocking:` line readable, and `reviewed=` an ancestor of the head and not of the merge-base; else a first review (the widest plan); an older record is never used in its place; untrusted authors are ignored |
| Answered lenses | that record's `Blocking:` ids, by their first part | a trusted record | a part that names no lens plans correctness-reviewer; the record narrows only when its depth is at least this round's |
| `--depth` | the lead's argument | the lead | the depth is the higher of it and the floor; one below the floor refuses |
| `--owner` | the lead's argument, quoting the owner's instruction | the owner, by the review skill's rule | sets the depth to `--depth` exactly (light at least), recorded as `override=` with the quote; a later round narrows from it only at no greater depth |
| `--reviewers`, `--lens` | the lead's arguments to verdict.sh | the lead | must cover every planned lens and the verifier, each planned lens at its planned effort or above; extra lenses are accepted |
| `--pr` | the lead's argument | the lead | names the PR the record is posted on, so it can only describe that PR |
| Repo (`REVIEW_REPO`, else `origin`'s URL) and the object store | the local clone | the lead | every object is read by a sha GitHub named; the code these scripts run from is stamped as `kit=` on the round line |
| Current branch name | `git symbolic-ref HEAD`, in the preview without `--pr` only | the local clone | used only to find that branch's open PR; `record` always takes `--pr` |

Depths, ranked none < light < focused < full; the floor is the highest depth among the changed paths:
  routine path    none;
  standard path   light, or the `Depth:` line of REVIEW.md;
  sensitive path  focused, or that `Depth:` when higher (tiers.py's built-in floor and REVIEW.md's `## Sensitive`).
  A REVIEW.md line's `; depth: <d>` sets its paths' depth: higher anywhere, lower only on a path that is not
  sensitive (no line lowers a sensitive path, and a `## Sensitive` line below focused makes REVIEW.md unparsable).
Lenses by depth (the tier's set: routine claims-auditor; standard correctness-reviewer; sensitive correctness-reviewer,
guardrail-reviewer and the lenses REVIEW.md names for the changed paths):
  none     no reviewer: gates only.
  light    one lens and the verifier: correctness-reviewer, or claims-auditor when the tier is routine.
  focused  the tier's set, correctness-reviewer first and alone (`first`), then the rest (`then`) with its findings in
           their briefs.
  full     the tier's set at once.
A fix round is a round after the PR's newest trusted review record (the table's "Previous round") whose tier and
depth are at least this round's (a round below either, such as one the owner overrode lighter, never narrows a deeper
one); its paths are those changed since that record's `reviewed=` commit that the change still changes. In focused it
runs each lens a must-fix on the record's `Blocking:` line came from (by its id's first part, PREFIX, so a promoted
dismissal `COR-RO-1` is correctness-reviewer's; a part that names no lens, correctness-reviewer), the lenses REVIEW.md
names for its paths, and the sensitive set when one of its paths is sensitive.
In light it reruns the one lens; in full, the whole set. The verifier runs on every round with a lens.
Effort per lens, the highest over the round's paths: a REVIEW.md `; effort: <lens>=<level>` on a line matching the
path (raising or lowering it), else high for correctness-reviewer and control-prober at depth full on a sensitive path
that is not prose (*.md, *.txt, licence files), else medium. The verifier is medium unless a line sets it. A lens may
run above its planned effort, never below; the merge guard never reads effort.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import blocking  # noqa: E402  (the verifier's `Blocking:` line)
import record  # noqa: E402  (the round's --lens shape)
import tiers  # noqa: E402  (the paths' tiers and REVIEW.md, as tier.sh reads them)

COR, CLM, GRD, CTL, LEAK = ("correctness-reviewer", "claims-auditor", "guardrail-reviewer", "control-prober",
                            "leak-hunter")
VERIFIER = "finding-verifier"
LENSES = [COR, CLM, GRD, CTL, LEAK]
PREFIX = {"COR": COR, "CLM": CLM, "GRD": GRD, "CTL": CTL, "LEAK": LEAK}
TIER_SET = {"routine": [CLM], "standard": [COR], "sensitive": [COR, GRD]}
DEPTHS = tiers.DEPTHS
DRANK = {d: i for i, d in enumerate(DEPTHS)}
ERANK = {e: i for i, e in enumerate(tiers.EFFORTS)}
HIGH_ON_CODE = {COR, CTL}
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
MARKER = re.compile(r"<!-- loadout:review((?: [a-z]+=[^\s=]+)+) -->")
TITLE = re.compile(r"🤖 Review: (pass|fail) \((routine|standard|sensitive) tier\)")
FIELDS = {"sha", "state", "tier", "reviewed", "depth", "override"}
ROUND = re.compile("<!-- loadout" r":round((?: [a-z]+=[A-Za-z0-9._,:-]+)+) -->")
RAW = re.compile(r"<details><summary>[^<\n]*</summary>\n\n(?:Clipped[^\n]*\n\n)?(`{3,})text\n(.*?)\1\n\n</details>",
                 re.S)
SHA = re.compile(r"[0-9a-f]{40}")
REVIEWED_SHA = re.compile(r"^[ \t\v\f\r]*Reviewed:[ \t\v\f\r]*`?([0-9a-f]{7,40})`?[ \t\v\f\r]*$")
PROSE = [tiers.glob_re(g) for g in tiers.DEFAULT_ROUTINE]
MAX_PAGES = 30


class Refused(Exception):
    """The plan cannot be made, or a round does not cover it: the reason."""


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), capture_output=True, text=True)


def git(*args: str) -> str:
    done = run("git", *args)
    if done.returncode:
        raise Refused(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout.strip()


def is_ancestor(a: str, b: str) -> bool:
    return run("git", "merge-base", "--is-ancestor", a, b).returncode == 0


def gh(endpoint: str) -> object:
    done = run("gh", "api", endpoint)
    if done.returncode:
        why = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no output"]
        raise Refused(f"cannot read `{endpoint}` from GitHub: {why[0]}")
    try:
        return json.loads(done.stdout)
    except ValueError:
        raise Refused(f"`{endpoint}` answered something that is not JSON") from None


def repo_name() -> str:
    if os.environ.get("REVIEW_REPO"):
        return os.environ["REVIEW_REPO"]
    url = run("git", "remote", "get-url", "origin").stdout.strip()
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/*$", url)
    if not m:
        raise Refused("no origin remote: set REVIEW_REPO=owner/name")
    return m.group(1)


def current_pr(repo: str) -> str:
    branch = run("git", "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    got = gh(f"repos/{repo}/pulls?head={repo.split('/')[0]}:{branch}&state=open&per_page=1") if branch else []
    if not isinstance(got, list) or not got or not isinstance(got[0], dict):
        raise Refused("no open PR for the current branch: pass --pr <n>")
    return str(got[0].get("number"))


# The change: its paths and the policy at the default branch's tip.


class Change:
    def __init__(self, base: str, head: str) -> None:
        try:
            self.mb, self.paths = tiers.changed(base, head)
        except RuntimeError as exc:
            raise Refused(str(exc)) from None
        if not self.paths:
            raise Refused(f"{head} changes nothing against {base}")
        self.base, self.head = base, head
        self.rules, self.broken = tiers.load_rules(base, prog="plan.py")
        try:
            imported = tiers.imports(base)
        except RuntimeError as exc:
            raise Refused(str(exc)) from None
        self.rated = tiers.rate(self.paths, self.rules, self.broken, imported)
        self.tier = tiers.top_tier(self.rated)
        self.floor = max((self.depth_of(p) for p in self.paths), key=DRANK.get)

    def depth_of(self, path: str) -> str:
        r, default = self.rated[path], self.rules["depth"]
        if r["tier"] == "routine":
            base = "none"
        elif r["tier"] == "standard":
            base = default or "light"
        else:
            base = max("focused", default or "focused", key=DRANK.get)
        if not r["depths"]:
            return base
        line = max(r["depths"], key=DRANK.get)
        if r["tier"] == "sensitive":  # raise only: the built-in floor and `## Sensitive` hold
            return max(base, line, key=DRANK.get)
        return line

    def tier_of(self, paths: list[str]) -> str:
        return max((self.rated[p]["tier"] for p in paths), key=tiers.RANK.get)

    def named(self, paths: list[str]) -> set[str]:
        return {x for p in paths for x in self.rated[p]["lenses"]}

    def tier_set(self, paths: list[str]) -> set[str]:
        top = self.tier_of(paths)
        return set(TIER_SET[top]) | (self.named(paths) if top == "sensitive" else set())

    def effort(self, lens: str, paths: list[str], depth: str) -> str:
        def one(p: str) -> str:
            r = self.rated[p]
            set_by = [e[lens] for e in r["efforts"] if lens in e]
            if set_by:
                return max(set_by, key=ERANK.get)
            code = not any(g.match(p) for g in PROSE)
            deep = depth == "full" and lens in HIGH_ON_CODE and r["tier"] == "sensitive" and code
            return "high" if deep else "medium"
        return max((one(p) for p in paths), key=ERANK.get)


# The PR's newest trusted review record.


def body_lines(c: dict) -> list[str]:
    return (c.get("body") or "").replace("\r\n", "\n").split("\n")


def newest_review(comments: list[dict]) -> dict | None:
    """The newest comment whose second line opens a review marker, by the owner, a member or a collaborator."""
    newest = None
    for c in sorted(comments, key=lambda c: (str(c.get("created_at")), c.get("id") or 0)):
        lines = body_lines(c)
        if (len(lines) > 1 and re.match(r"\s*<!-- loadout:review\b", lines[1])
                and c.get("author_association") in TRUSTED):
            newest = c
    return newest


def record_fields(c: dict) -> dict | None:
    """The marker's fields, and `round` (the round line's), of a record in verdict.sh's exact shape; else None."""
    if c.get("updated_at") != c.get("created_at"):
        return None
    lines = body_lines(c)
    m = MARKER.fullmatch(lines[1].strip()) if len(lines) > 1 else None
    title = TITLE.fullmatch(lines[0].strip())
    if not m or not title:
        return None
    pairs = [kv.split("=", 1) for kv in m.group(1).split()]
    f = dict(pairs)
    if (len(f) != len(pairs) or not {"sha", "state", "tier", "reviewed"} <= set(f) <= FIELDS
            or not SHA.fullmatch(f["sha"]) or not SHA.fullmatch(f["reviewed"]) or f["tier"] not in tiers.RANK
            or f.get("depth", "none") not in DEPTHS or f["state"] not in ("success", "failure")
            or {"pass": "success", "fail": "failure"}[title.group(1)] != f["state"] or title.group(2) != f["tier"]):
        return None
    rl = ROUND.fullmatch(lines[2].strip()) if len(lines) > 2 else None
    f["round"] = dict(kv.split("=", 1) for kv in rl.group(1).split() if not kv.startswith("lens=")) if rl else {}
    return f


def prior_round(c: dict | None, change: Change) -> tuple[str, list[dict], str] | None:
    """(reviewed commit, its must-fix items, its depth) when `c` can start a fix round of `change`; else None.

    A record below the change's tier (a routine one included) never starts one: it reviewed less than the change now
    needs.
    """
    f = record_fields(c) if c else None
    if not f or tiers.RANK[f["tier"]] < tiers.RANK[change.tier] or f.get("depth") not in DRANK:
        return None
    raw = RAW.search("\n".join(body_lines(c)))
    if not raw:
        return None
    text = raw.group(2)
    first = next((ln for ln in text.split("\n") if blocking.REVIEWED.match(ln)), "")
    named = REVIEWED_SHA.match(first)
    if not named or not f["reviewed"].startswith(named.group(1)):
        return None
    try:
        items = blocking.read(text)
    except ValueError:
        return None
    reviewed = f["reviewed"]
    if (run("git", "cat-file", "-e", f"{reviewed}^{{commit}}").returncode or reviewed == change.head
            or not is_ancestor(reviewed, change.head) or is_ancestor(reviewed, change.mb)):
        return None
    return reviewed, items, f["depth"]


# The plan.


def ordered(lenses: set[str]) -> list[str]:
    return sorted(lenses, key=lambda x: (LENSES.index(x) if x in LENSES else len(LENSES), x))


def owner_quote(quote: str | None, want: str | None) -> str | None:
    """The owner's words for an override, checked: one line, light or deeper; None when there is no override."""
    if quote is None:
        return None
    if not quote.strip() or "\n" in quote or "\r" in quote or "-->" in quote or len(quote) > 300:
        raise Refused("--owner quotes the owner's instruction: one line of at most 300 characters, without `-->`")
    if want not in ("light", "focused", "full"):
        raise Refused("--owner sets the depth --depth names: light, focused or full (an override never skips review)")
    return quote


def make_plan(change: Change, prior: tuple[str, list[dict], str] | None, want: str | None,
              owner: str | None = None) -> dict:
    if want is not None and want not in DEPTHS:
        raise Refused(f"--depth is one of {', '.join(DEPTHS)} (got {want!r})")
    owner = owner_quote(owner, want)
    if owner is None and want is not None and DRANK[want] < DRANK[change.floor]:
        raise Refused(f"--depth {want} is below the floor the paths set, {change.floor}: a depth may be raised, never "
                      "lowered, except by the owner's override (--owner)")
    depth = want if owner is not None else max(change.floor, want or "none", key=DRANK.get)
    why = [f"the paths make it {change.tier} with depth floor {change.floor}"]
    if owner is not None:
        why.append(f"set to {depth} by the owner's override")
    elif want and want != change.floor:
        why.append(f"raised to {depth}")
    whole = change.tier_set(change.paths)
    light = {CLM} if change.tier == "routine" else {COR}
    paths, since, kind = change.paths, None, "first"
    if prior and DRANK[prior[2]] < DRANK[depth]:
        why.append(f"the previous round ran at {prior[2]}, below {depth}, so this round reviews the whole change")
        prior = None
    if prior:
        fix = [p for p in git("diff", "--name-only", "--no-renames", prior[0], change.head).splitlines()
               if p in change.rated]
        if fix:
            paths, since, kind = fix, prior[0], "fix"
    if depth == "none":
        lenses: set[str] = set()
        why.append("none: gates only")
    elif depth == "light":
        lenses = light
    elif kind == "first" or depth == "full":
        lenses = whole
        if kind == "fix":
            why.append("full: a fix round reruns the whole set")
    else:
        prefixes = {x.strip().split("-", 1)[0] for b in prior[1] for x in b["ids"].split(",") if x.strip()}
        lenses = {PREFIX.get(x, COR) for x in prefixes} | change.named(paths) or {COR}
        why.append("a fix round: the lenses whose must-fix it answers and those REVIEW.md names for its paths")
        if change.tier_of(paths) == "sensitive":
            lenses |= set(TIER_SET["sensitive"])
            why.append("a fix path is sensitive, so the sensitive set runs too")
    run_ = ordered(lenses)
    first = [COR] if depth == "focused" and COR in run_ and len(run_) > 1 else []
    then = [x for x in run_ if x not in first]
    effort = {x: change.effort(x, paths, depth) for x in run_}
    if run_:
        set_by = [e[VERIFIER] for p in paths for e in change.rated[p]["efforts"] if VERIFIER in e]
        effort[VERIFIER] = max(set_by, key=ERANK.get) if set_by else "medium"
    return {"head": change.head, "tier": change.tier, "floor": change.floor, "depth": depth, "round": kind,
            "since": since, "first": first, "then": then, "verifier": VERIFIER if run_ else "", "effort": effort,
            "planned": run_ + ([VERIFIER] if run_ else []), "override": depth if owner is not None else None,
            "why": why}


def read_pr(repo: str, number: str) -> tuple[Change, list[dict], str]:
    """The change PR `number` holds, rated against its default branch's tip as GitHub names it, and its comments."""
    pr = gh(f"repos/{repo}/pulls/{number}")
    pr = pr if isinstance(pr, dict) else {}
    head = (pr.get("head") or {}).get("sha")
    default = ((pr.get("base") or {}).get("repo") or {}).get("default_branch")
    if not isinstance(head, str) or not SHA.fullmatch(head):
        raise Refused(f"PR {number} in {repo} shows no head commit")
    if not isinstance(default, str) or not re.fullmatch(r"[A-Za-z0-9._/-]+", default) or ".." in default:
        raise Refused(f"PR {number} in {repo} names no default branch")
    branch = gh(f"repos/{repo}/branches/{default}")
    tip = ((branch if isinstance(branch, dict) else {}).get("commit") or {}).get("sha")
    if not isinstance(tip, str) or not SHA.fullmatch(tip):
        raise Refused(f"GitHub names no tip for {default}")
    ref = f"refs/remotes/origin/{default}"
    if run("git", "fetch", "-q", "--force", "origin", f"+refs/heads/{default}:{ref}").returncode:
        raise Refused(f"cannot fetch {default} from origin")
    got = run("git", "rev-parse", "-q", "--verify", f"{ref}^{{commit}}").stdout.strip()
    if got != tip:
        raise Refused(f"origin's {default} is {got or 'missing'} after a forced fetch, but GitHub names {tip}: run "
                      "again, from a clone whose origin is the PR's repo")
    if run("git", "cat-file", "-e", f"{head}^{{commit}}").returncode and run("git", "fetch", "-q", "origin",
                                                                             head).returncode:
        raise Refused(f"the PR's head {head} is not in this clone and cannot be fetched")
    comments: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        got_page = gh(f"repos/{repo}/issues/{number}/comments?per_page=100&page={page}")
        if not isinstance(got_page, list):
            raise Refused(f"the comments of PR {number} came back in an unknown shape")
        comments += [c for c in got_page if isinstance(c, dict)]
        if len(got_page) < 100:
            break
    else:
        raise Refused(f"PR {number} has more than {MAX_PAGES * 100} comments")
    return Change(tip, head), comments, default


# What verdict.sh records.


def check_round(p: dict, reviewers: str, lens_specs: list[str]) -> None:
    """Refuses a reviewer set missing a planned lens or the verifier, or a planned lens run below its effort."""
    try:
        ran = record.names(reviewers)
        specs = {x["name"]: x for x in (record.lens_spec(s) for s in lens_specs)}
    except ValueError as exc:
        raise Refused(str(exc)) from None
    if missing := [x for x in p["planned"] if x not in ran]:
        raise Refused(f"the round's plan ({p['depth']}, {p['round']} round) runs {', '.join(p['planned'])}; "
                      f"--reviewers lacks the planned {', '.join(missing)}: run it, or record no verdict")
    low = [f"{x} ran at {specs[x]['effort']}, planned {e}" for x, e in p["effort"].items()
           if x in specs and ERANK[specs[x]["effort"]] < ERANK[e]]
    if low:
        raise Refused(f"a planned lens ran below its planned effort ({'; '.join(low)}): an effort may be raised, "
                      "never lowered")


def record_main(a: argparse.Namespace) -> int:
    repo = repo_name()
    change, comments, _ = read_pr(repo, a.pr)
    if a.tier != "routine" and tiers.RANK[a.tier] < tiers.RANK[change.tier]:
        raise Refused(f"PR {a.pr}'s paths make it {change.tier}, so --tier {a.tier} is too low (tier.sh lists the "
                      "paths)")
    if a.routine:
        if a.owner is not None:
            raise Refused("--tier routine runs no reviewer, so it takes no --owner")
        if a.depth not in (None, "none"):
            raise Refused("--tier routine runs no reviewer, so its depth is none")
        if change.floor != "none":
            raise Refused(f"the paths set depth floor {change.floor}: a routine record is for a change whose floor is "
                          "none")
        pairs = ["depth=none", f"floor={change.floor}", "planned=none"]
        print(f"head {change.head}\ntier {change.tier}\ndepth none\npairs {' '.join(pairs)}")
        return 0
    if a.repost:
        f = record_fields(newest_review(comments) or {})
        planned = (f or {}).get("round", {}).get("planned")
        if not f or f["reviewed"] != a.reviewed or "depth" not in f or not planned:
            raise Refused("--repost posts the PR's newest trusted review record again, and that record must have "
                          "reviewed --reviewed and carry its depth and plan: record the round anew")
        if a.owner is not None:
            raise Refused("--repost carries the reposted record's own override, if it has one: pass no --owner")
        carried = f.get("override")
        if carried is not None and carried != f["depth"]:
            raise Refused("the reposted record's override= names another depth than its depth=: record the round anew")
        if DRANK[f["depth"]] < DRANK[change.floor] and carried is None:
            raise Refused(f"the reposted round ran depth {f['depth']}, below the floor {change.floor} at the head")
        p = {"planned": [] if planned == "none" else planned.split(","), "effort": {}, "depth": f["depth"],
             "round": "reposted"}
        check_round(p, a.reviewers, [])
        pairs = [f"depth={f['depth']}", f"floor={change.floor}", f"planned={planned}"]
        print(f"head {change.head}\ntier {change.tier}\ndepth {f['depth']}\npairs {' '.join(pairs)}")
        if carried is not None:
            print(f"override {carried}")
        return 0
    p = make_plan(change, prior_round(newest_review(comments), change), a.depth, a.owner)
    check_round(p, a.reviewers, a.lens)
    pairs = [f"depth={p['depth']}", f"floor={p['floor']}", f"planned={','.join(p['planned']) or 'none'}"]
    print(f"head {change.head}\ntier {change.tier}\ndepth {p['depth']}\npairs {' '.join(pairs)}")
    if p["override"]:
        print(f"override {p['override']}")
    return 0


def preview_main(a: argparse.Namespace) -> int:
    repo = repo_name()
    change, comments, default = read_pr(repo, a.pr or current_pr(repo))
    p = {"pr": int(a.pr) if a.pr else None, "base": default, "tip": change.base,
         **make_plan(change, prior_round(newest_review(comments), change), a.depth, a.owner)}
    if a.json:
        print(json.dumps(p))
        return 0
    for k in ("tier", "floor", "depth", "round"):
        print(f"{k}: {p[k]}")
    if p["override"]:
        print(f"override: depth {p['override']}, by the owner's words")
    print(f"since: {p['since'] or 'none (a first review)'}")
    for k in ("first", "then"):
        shown = ", ".join(f"{x} ({p['effort'][x]})" for x in p[k])
        print(f"{k}: {shown or 'none'}")
    print(f"verifier: {p['verifier'] + ' (' + p['effort'][VERIFIER] + ')' if p['verifier'] else 'none'}")
    print(f"why: {'; '.join(p['why'])}")
    return 0


def floor_main(a: argparse.Namespace) -> int:
    change = Change(a.base, a.head)
    print(f"{change.tier} {change.floor}")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] in (["record"], ["floor"]):
        p = argparse.ArgumentParser(prog=f"plan.py {argv[0]}")
        if argv[0] == "record":
            p.add_argument("--pr", required=True)
            p.add_argument("--depth")
            p.add_argument("--owner")
            p.add_argument("--reviewers", default="")
            p.add_argument("--lens", action="append", default=[])
            p.add_argument("--reviewed", default="")
            p.add_argument("--tier", choices=list(tiers.RANK), required=True)
            p.add_argument("--routine", action="store_true")
            p.add_argument("--repost", action="store_true")
        else:
            p.add_argument("--base", required=True)
            p.add_argument("--head", required=True)
        a = p.parse_args(argv[1:])
        handler = record_main if argv[0] == "record" else floor_main
    else:
        p = argparse.ArgumentParser(prog="plan.py")
        p.add_argument("--pr")
        p.add_argument("--depth")
        p.add_argument("--owner")
        p.add_argument("--json", action="store_true")
        a = p.parse_args(argv)
        handler = preview_main
    if getattr(a, "pr", None) is not None and not re.fullmatch(r"[0-9]+", a.pr):
        p.error("--pr is a PR number")
    try:
        return handler(a)
    except Refused as exc:
        print(f"plan.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
