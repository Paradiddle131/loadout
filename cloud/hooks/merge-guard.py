#!/usr/bin/env python3
"""PreToolUse hook: a PR merges through the review path, and a commit keeps its hooks.

A reminder for an agent that forgets the review path, not a wall against a determined or dishonest one: by
design it reads two things and stops nothing else.

The merge tool: any MCP server's `merge_pull_request` may merge a PR only when its newest gates record
(skills/review/scripts/gate_stamp.sh) and newest review record (skills/review/scripts/verdict.sh), PR comments
by the owner, a member or a collaborator whose first line is `🤖 Gates: <state>` or `🤖 Review: <result>
(<tier> tier)` and second the marker `<!-- loadout:<gates|review> sha=<head> state=success|failure [tier=..]
[reviewed=..] -->`, are unedited, well formed, agree with their first line and name the PR's current head as
a success. In a local clone holding the head and the default branch GitHub names, tier.sh runs with `--base
origin/<that branch>` and a review below the paths' tier refuses, as does a tier.sh that fails or runs out of
time; with no such clone the tier check is skipped. The merge must name the head checked (`expectedHeadSha`),
so GitHub refuses it if a push lands in between. A PR labelled `owner-merges` is refused whatever its records
(the merge is the owner's), here and in `--check`. `enable_pr_auto_merge` is refused.

Bash: the command is read as text, never as shell. A command whose text holds one of the five MENTIONS
patterns (`pr merge`, `pulls/<n>/merge`, a GraphQL merge mutation, `--no-verify`, `hooksPath=`) is refused,
wherever the words sit, a quoted message or a search included; the refusal says how to
merge (the MCP merge tool, or the autopilot's merge.sh, which runs `--check` below itself) and how to search or
write such words without them in a command. Anything else passes, with no network call.
Not read, by design: a merge spelled so the words do not appear (a variable, an encoded path, another client),
`git commit -n`, `git config core.hooksPath`, a script or program that merges, the web UI. Hooks never see the
commands a hook or script runs (save-work's push, merge.sh's merge).

Each refusal in hook mode is noted in the friction log (bin/friction): the guard's name and the rule, never the
command. Bounds: one 30 s budget per merge-tool decision, under the hook's 45 s timeout (a timed-out hook does
not block); a merge it cannot check (GitHub unreadable, a guard failure, input nested too deep to read) is
refused; a guard failure on a Bash command passes it.

Hook mode (no arguments): the hook's JSON on stdin, a deny decision or nothing on stdout, exit 0. Check
mode, for scripts: `merge-guard.py --check <owner>/<repo>#<n>` (or `<n>`, the repo from the origin) runs the
record checks and prints the head it checked (exit 0) or the reason on stderr (exit 1; 2 for usage).
"""

from __future__ import annotations

import json
import os
import re
import runpy
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCER = {
    "gates": "skills/review/scripts/gate_stamp.sh -- <the repo's gate command>",
    "review": "skills/review/scripts/verdict.sh <pr> --tier ... --result pass --reviewed <head> ...",
}
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
OWNER_MERGES = "owner-merges"  # a PR label: the merge is the owner's alone
MARKER = re.compile(r"<!-- loadout:(gates|review)((?: [a-z]+=[^\s=]+)+) -->")
TITLE = {"gates": re.compile(r"🤖 Gates: (success|failure)"),
         "review": re.compile(r"🤖 Review: (pass|fail) \((routine|standard|sensitive) tier\)")}
FIELDS = {"gates": {"sha", "state"}, "review": {"sha", "state", "tier", "reviewed"}}
RANK = {"routine": 0, "standard": 1, "sensitive": 2}
TIER_SH = ROOT / "skills/review/scripts/tier.sh"
MERGE_SH = ROOT / "cloud/skills/autopilot/scripts/merge.sh"
FRICTION = ROOT / "bin/friction"
MAX_PAGES = 30
TIMEOUT = 10  # any one call
try:  # tests shrink it; nothing raises it
    BUDGET = min(30.0, float(os.environ.get("MERGE_GUARD_BUDGET_S") or 30))
except ValueError:
    BUDGET = 30.0
_deadline = [time.monotonic() + BUDGET]

# (rule id, what the text mentions, pattern, kind). Each pattern is literals, one character class repeated and
# word boundaries, so a search is linear in the command's length.
MENTIONS = [
    ("pr-merge", "`pr merge`", re.compile(r"\bpr\s+merge\b", re.IGNORECASE), "merge"),
    ("merge-endpoint", "a `pulls/<n>/merge` endpoint", re.compile(r"pulls/[^/\s]+/merge", re.IGNORECASE), "merge"),
    ("merge-mutation", "a GraphQL merge mutation",
     re.compile(r"mergePullRequest|enablePullRequestAutoMerge", re.IGNORECASE), "merge"),
    ("no-verify", "`--no-verify`", re.compile(r"--no-verify", re.IGNORECASE), "hooks"),
    ("hooks-path", "a `hooksPath=` override", re.compile(r"hooksPath\s*=", re.IGNORECASE), "hooks"),
]
ADVICE = {
    "merge": ("To merge, use the MCP merge tool (`merge_pull_request` with `expectedHeadSha`), which this guard "
              "checks against the PR's gates and review records, or run `{merge_sh} <pr>` from the repo's root."),
    "hooks": ("A hook that fails is reporting something: fix what it names, or ask the owner about a deliberate "
              "exception, instead of bypassing it."),
}
MENTION_ONLY = ("If the command only mentions these words: search with the Grep tool, write the text with the "
                "Write tool, put a commit message in a file and run `git commit -F <file>`, and send a body as "
                "`gh api ... -F body=@<file>`.")
FRICTION_LINE = ("If this refusal got in your way, note it before working around it: write what you were doing "
                 "and what you did instead to a file with the Write tool, in generic words (no repo name, path, "
                 "data or secret: it is posted on this collection's tracker, which may be public), then run "
                 "`{friction} note --file <file> --part merge-guard`")
AUTO_MERGE = ("auto-merge merges later, at a head nobody checked; merge by hand once both records are "
              "on the PR's head")


class Unreadable(Exception):
    """GitHub could not be read: the merge is refused (fail closed)."""


def left() -> float:
    """Seconds left of this decision's budget, for the next call's timeout."""
    return min(TIMEOUT, _deadline[0] - time.monotonic())


def gh_json(endpoint: str) -> object:
    budget = left()
    if budget < 1:
        raise Unreadable(f"its {BUDGET:.0f} s budget for reading GitHub ran out before `gh api {endpoint}`")
    try:
        done = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True,
                              timeout=budget, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Unreadable(f"`gh api {endpoint}` did not run ({exc})") from exc
    if done.returncode != 0:
        why = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no output"]
        raise Unreadable(f"`gh api {endpoint}` failed: {why[0]}")
    try:
        return json.loads(done.stdout)
    except ValueError as exc:
        raise Unreadable(f"`gh api {endpoint}` answered something that is not JSON") from exc


def git_out(*args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=max(0.1, left()),
                              check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def origin_repo(cwd: str) -> str | None:
    done = git_out("-C", cwd, "remote", "get-url", "origin")
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/*$", done.stdout.strip()) if done else None
    return f"{m.group(1)}/{m.group(2)}" if m else None


def comments(repo: str, number: str) -> list[dict]:
    """Every comment on the PR, paged by hand (`--paginate` follows links some proxies refuse)."""
    out: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        got = gh_json(f"repos/{repo}/issues/{number}/comments?per_page=100&page={page}")
        if not isinstance(got, list):
            raise Unreadable(f"the comments of PR {number} came back in an unknown shape")
        out += [c for c in got if isinstance(c, dict)]
        if len(got) < 100:
            return out
    raise Unreadable(f"PR {number} has more than {MAX_PAGES * 100} comments")


def body_lines(c: dict) -> list[str]:
    return (c.get("body") or "").replace("\r\n", "\n").split("\n")


def record_problem(kind: str, c: dict, head: str) -> tuple[str, dict]:
    """Why `c`, the newest trusted marker comment of `kind`, records no success on `head` ('' when it does)."""
    lines = body_lines(c)
    where = f"the newest {kind} record ({c.get('html_url') or 'comment ' + str(c.get('id'))})"
    if c.get("updated_at") != c.get("created_at"):
        return f"{where} was edited after it was posted, so it does not count", {}
    m = MARKER.fullmatch(lines[1].strip()) if len(lines) > 1 else None
    title = TITLE[kind].fullmatch(lines[0].strip())
    if not m or m.group(1) != kind or not title:
        return f"{where} has a malformed first line or marker", {}
    pairs = [kv.split("=", 1) for kv in m.group(2).split()]
    fields = dict(pairs)
    shas = [fields.get("sha", "")] + ([fields["reviewed"]] if "reviewed" in fields else [])
    if (len(fields) != len(pairs) or not {"sha", "state"} <= set(fields) <= FIELDS[kind]
            or not all(re.fullmatch(r"[0-9a-f]{40}", s) for s in shas)
            or (kind == "review" and fields.get("tier") not in RANK)):
        return f"{where} has a malformed marker", {}
    state = fields["state"]
    said = title.group(1) if kind == "gates" else {"pass": "success", "fail": "failure"}[title.group(1)]
    if state not in ("success", "failure") or said != state or (
            kind == "review" and title.group(2) != fields.get("tier")):
        return f"{where} has a marker that disagrees with its first line", {}
    if fields["sha"] != head:
        return (f"{where} is for {fields['sha']}, not the head {head}: a record for an older head does not "
                "count"), {}
    if state != "success":
        return f"{where} says {state}", {}
    return "", fields


def paths_tier(repo: str, head: str, base: object, cwd: str) -> str | None:
    """The tier tier.sh gives the head's paths against `origin/<base>`, from a local clone of `repo`.

    None when no local clone holds both the head and that branch (the check cannot run, and is skipped).
    Once one does, the check must finish: tier.sh failing, or running out of time, refuses as unreadable.
    """
    top_done = git_out("-C", cwd, "rev-parse", "--show-toplevel")
    top = top_done.stdout.strip() if top_done else ""
    if not top or origin_repo(top) != repo or not TIER_SH.is_file():
        return None
    held = git_out("-C", top, "cat-file", "-e", f"{head}^{{commit}}")
    if held is None:
        raise Unreadable("it ran out of time looking for the head in the local clone, so it cannot rule out a "
                         "review below the head's tier")
    if held.returncode:
        return None
    if not isinstance(base, str) or not base:
        raise Unreadable("GitHub named no default branch for the repo, so tier.sh has no base to compare with")
    ref = git_out("-C", top, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{base}^{{commit}}")
    if not ref or ref.returncode:
        return None  # this clone has no copy of the default branch: it cannot answer
    budget = left()
    if budget < 1:
        raise Unreadable("no time was left to run tier.sh on the head, which this clone holds")
    try:
        done = subprocess.run(["bash", str(TIER_SH), "--base", f"origin/{base}", "--head", head], cwd=top,
                              capture_output=True, text=True, timeout=budget, check=False)
    except subprocess.TimeoutExpired as exc:
        raise Unreadable(f"tier.sh did not finish on the head within {budget:.0f} s") from exc
    except OSError as exc:
        raise Unreadable(f"tier.sh did not run ({exc})") from exc
    tier = done.stdout.split("\n", 1)[0].strip()
    if done.returncode != 0 or tier not in RANK:
        why = (done.stderr.strip().splitlines() or ["no output"])[-1]
        raise Unreadable(f"tier.sh failed on the head: {why}")
    return tier


def check_merge(repo: str | None, number: str | None, expected: str | None, cwd: str = ".",
                require_named: bool = True) -> tuple[str, str]:
    """(deny reason, head checked) for merging PR `number` of `repo`; no reason: allowed."""
    if not repo:
        return "refused a PR merge that names no repository: pass its owner and name", ""
    if not number:
        return "refused a PR merge that names no PR: pass the PR number", ""
    pr = gh_json(f"repos/{repo}/pulls/{number}")
    pr = pr if isinstance(pr, dict) else {}
    head = (pr.get("head") or {}).get("sha")
    if not head or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise Unreadable(f"PR {number} in {repo} shows no head commit")
    if any(isinstance(lb, dict) and lb.get("name") == OWNER_MERGES for lb in pr.get("labels") or []):
        return (f"refused merging PR {number} of {repo}: it carries `{OWNER_MERGES}`, so the merge is the "
                "owner's: they merge it in GitHub, or remove the label themselves"), head
    if expected and expected != head:
        return (f"refused merging PR {number} of {repo}: the merge names head {expected}, but the PR's head "
                f"is now {head}. Check the new head's gates and review, then merge naming it"), head
    newest: dict[str, dict] = {}
    ignored: dict[str, set[str]] = {"gates": set(), "review": set()}
    for c in sorted(comments(repo, number), key=lambda c: (str(c.get("created_at")), c.get("id") or 0)):
        lines = body_lines(c)
        m = re.match(r"\s*<!-- loadout:(gates|review)\b", lines[1]) if len(lines) > 1 else None
        if not m:
            continue
        if c.get("author_association") in TRUSTED:
            newest[m.group(1)] = c
        else:
            ignored[m.group(1)].add(str(c.get("author_association")))
    problems, review = [], {}
    for kind in ("gates", "review"):
        if kind not in newest:
            extra = f" (markers by {', '.join(sorted(ignored[kind]))} do not count)" if ignored[kind] else ""
            problems.append(f"no {kind} record{extra}; record it with {PRODUCER[kind]}")
            continue
        why, fields = record_problem(kind, newest[kind], head)
        if why:
            problems.append(f"{why}; record it again with {PRODUCER[kind]}")
        elif kind == "review":
            review = fields
    if not problems and review:
        base = ((pr.get("base") or {}).get("repo") or {}).get("default_branch")
        tier = paths_tier(repo, head, base, cwd)
        if tier and RANK[review["tier"]] < RANK[tier]:
            problems.append(f"the review is {review['tier']} tier, but the head's paths make it {tier} "
                            "(skills/review/scripts/tier.sh); review it at that tier")
    if problems:
        return f"refused merging PR {number} of {repo} at head {head}: " + "; ".join(problems), head
    if require_named and not expected:
        return (f"PR {number} of {repo} has both records on head {head}: repeat the merge with "
                f"`expectedHeadSha: {head}`, so GitHub refuses it if the head moves first"), head
    return "", head


def text_rule(command: str) -> tuple[str, str]:
    """(deny reason, rule id) for a Bash command, from its text alone; ('', '') when it passes."""
    for rule, what, pattern, kind in MENTIONS:
        if pattern.search(command):
            return (f"refused a Bash command whose text mentions {what} (rule `{rule}`); it reads the text, not "
                    "the shell, so a mention counts as a call. " + ADVICE[kind].format(merge_sh=MERGE_SH) + " "
                    + MENTION_ONLY + " " + FRICTION_LINE.format(friction=FRICTION)), rule
    return "", ""


def tool_input(event: dict) -> dict:
    data = event.get("tool_input")
    return data if isinstance(data, dict) else {}


def decide(event: dict) -> tuple[str, str]:
    """(deny reason, rule id) for one tool call; ('', '') when it passes."""
    _deadline[0] = time.monotonic() + BUDGET
    tool = event.get("tool_name") or ""
    data = tool_input(event)
    if re.fullmatch(r"mcp__.+__enable_pr_auto_merge", tool):
        return "refused enabling auto-merge: " + AUTO_MERGE, "auto-merge"
    if re.fullmatch(r"mcp__.+__merge_pull_request", tool):
        owner, name, number = data.get("owner"), data.get("repo"), data.get("pullNumber")
        repo = f"{owner}/{name}" if isinstance(owner, str) and isinstance(name, str) and owner and name else None
        ref = (str(int(number)) if isinstance(number, (int, float)) and not isinstance(number, bool)
               else number if isinstance(number, str) and number.isdigit() else None)
        expected = data.get("expectedHeadSha")
        reason = check_merge(repo, ref, expected if isinstance(expected, str) and expected else None,
                             event.get("cwd") or os.getcwd())[0]
        return reason, "merge-records" if reason else ""
    if tool == "Bash":
        command = data.get("command")
        return text_rule(command if isinstance(command, str) else "")
    return "", ""


def note_refusal(rule: str) -> None:
    """Note the refusal in the friction log: the guard and the rule only. Never fails, never reaches the network."""
    try:
        runpy.run_path(str(FRICTION), run_name="friction")["record_refusal"]("merge-guard", rule)
    except Exception:  # noqa: BLE001 -- the log is a courtesy; the decision stands without it
        pass


def check_mode(argv: list[str]) -> int:
    """`--check <owner>/<repo>#<n>` or `--check <n>`: 0 and the head on stdout when a merge naming it may go."""
    m = re.fullmatch(r"(?:([^/\s#]+/[^/\s#]+)#)?(\d+)", argv[1]) if len(argv) == 2 else None
    if not m:
        print("usage: merge-guard.py --check <owner>/<repo>#<n> | <n>", file=sys.stderr)
        return 2
    _deadline[0] = time.monotonic() + BUDGET
    repo = m.group(1) or origin_repo(os.getcwd())
    try:
        reason, head = check_merge(repo, m.group(2), None, os.getcwd(), require_named=False)
    except Unreadable as exc:
        reason, head = f"refused: it cannot read the PR's head or comments, so it fails closed ({exc})", ""
    except Exception as exc:  # noqa: BLE001 -- fail closed
        reason, head = f"refused: the merge guard failed ({exc!r}), so it fails closed", ""
    if reason:
        print(f"merge-guard: {reason}.", file=sys.stderr)
        return 1
    print(head)
    return 0


def main() -> int:
    if sys.argv[1:2] == ["--check"]:
        return check_mode(sys.argv[1:])
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except ValueError:
        return 0
    except RecursionError:  # nested past what json reads: refuse a merge-tool call, pass a command
        if re.search(r'"tool_name"\s*:\s*"mcp__[^"]*__(?:merge_pull_request|enable_pr_auto_merge)"', raw):
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": "Merge guard: refused: the call's input is nested too deep to read, "
                                            "so it fails closed."}}))
            note_refusal("guard-error")
        return 0
    if not isinstance(event, dict):
        return 0
    if not isinstance(event.get("cwd"), str):
        event["cwd"] = os.getcwd()
    try:
        reason, rule = decide(event)
    except Unreadable as exc:
        reason, rule = (f"refused the merge: it cannot read the PR's head or comments, so it fails closed "
                        f"({exc}). Retry once GitHub answers"), "unreadable"
    except Exception as exc:  # noqa: BLE001 -- a guard bug must not wave a merge through, nor block a command
        failed = (event.get("tool_name") or "") != "Bash"
        reason = f"refused: the merge guard failed on this call ({exc!r}), so it fails closed" if failed else ""
        rule = "guard-error"
    if reason:
        note_refusal(rule)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"Merge guard: {reason}.",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
