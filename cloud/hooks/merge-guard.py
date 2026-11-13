#!/usr/bin/env python3
"""PreToolUse hook: refuse a PR merge whose head commit carries no recorded gates and review.

A change may be merged only when its PR's current head commit carries two GitHub commit statuses, both
`success`: `loadout/gates` (skills/review/scripts/gate_stamp.sh, the gate command's result) and
`loadout/review` (skills/review/scripts/verdict.sh, a verdict posted on the PR). Statuses on an older head
do not count: the guard reads the PR's head now. It also asks the merge to name that head
(`expectedHeadSha`, `--match-head-commit`, `-f sha=`), so GitHub itself refuses the merge if a push lands
between this check and the merge.

Caught: the GitHub MCP merge tool (any server's `merge_pull_request`, owner, repo and number from its
input); `gh pr merge` (a number, URL or branch; `-R`, `GH_REPO`, or the origin of the directory it runs
in); `gh api` writes to `repos/<o>/<r>/pulls/<n>/merge` (`{owner}`/`{repo}` placeholders included);
and the same through `bash -c`, `eval`, a heredoc fed to a shell, `cd <dir> &&`, or wrappers such as
`timeout`. Refused outright: auto-merge (`gh pr merge --auto`, the MCP `enable_pr_auto_merge`), which
merges later at a head nobody checked; GraphQL merge mutations and curl/wget writes to a merge URL,
which the guard does not parse: use the MCP tool or `gh`. Also refused: `--no-verify` (or `-n`) on
`git commit`, `--no-verify` on `git push`, and `-c core.hooksPath=` on either, typed by the agent: fix
what the hook reports instead.

Not caught (out of scope): `git push` of a merge commit to the default branch, a merge through the web
UI, code calling the API from a script, or a command built at run time (`x=merge; gh pr $x`). Hooks see
only the agent's tool calls, never commands a hook runs, so the save-work hook's own `git push
--no-verify` is unaffected.

Honest limits: the statuses guard against forgetting, not against a dishonest author; the same account
posts them. The guard fails closed on a merge: when it cannot read the PR or its statuses, or the guard
itself fails on a command that looks like a merge, it refuses and says why. Any other command passes
untouched and costs no network call.

Reads the hook's JSON on stdin; prints a deny decision on stdout or nothing; always exits 0.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# The shell parsing is the GCP guard's (cloud/gcp/guard.py). Should it fail to load, every call that looks like
# a merge is refused (below) and every other call passes.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gcp"))
try:
    from guard import SHELLS, program, segments, split_heredocs, tokenize
except Exception as _exc:  # noqa: BLE001
    IMPORT_ERROR: Exception | None = _exc
else:
    IMPORT_ERROR = None

GATES, REVIEW = "loadout/gates", "loadout/review"
PRODUCER = {
    GATES: "skills/review/scripts/gate_stamp.sh -- <the repo's gate command>",
    REVIEW: "skills/review/scripts/verdict.sh <pr> --tier ... --result pass ...",
}
TIMEOUT = 10
MERGE_ENDPOINT = re.compile(r"(?:^|/)repos/([^/\s]+)/([^/\s]+)/pulls/(\d+)/merge/?(?:\?|$)")
MERGE_URL = re.compile(r"api\.github\.com/repos/[^/\s]+/[^/\s]+/pulls/\d+/merge\b")
MERGE_MUTATION = re.compile(r"\b(mergePullRequest|enablePullRequestAutoMerge)\b")
# Text that looks like a merge, for the fail-closed path when parsing fails.
MERGE_HINT = re.compile(
    r"pr\s+merge|pulls/\S*/merge|merge_pull_request|mergePullRequest|--no-verify"
)
GH_API_VALUE_FLAGS = {"-X", "--method", "-f", "--raw-field", "-F", "--field", "-H", "--header",
                      "-q", "--jq", "-t", "--template", "--input", "-p", "--preview",
                      "--hostname", "--cache"}
GH_MERGE_VALUE_FLAGS = {"-b", "--body", "-F", "--body-file", "-t", "--subject", "-A",
                        "--author-email", "-R", "--repo", "--match-head-commit"}
COMMIT_VALUE_SHORT = set("mFcCt")  # short options of `git commit` that take a value
GIT_GLOBAL_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}

AUTO_MERGE = ("auto-merge merges later, at a head nobody checked; merge by hand once both statuses are "
              "`success` on the PR's head")
NO_VERIFY = ("skipping the repo's commit or push hooks. A hook that fails is reporting something: fix "
             "what it names (or ask the owner about a deliberate exception) instead of bypassing it")


class Unreadable(Exception):
    """GitHub could not be read: the merge is refused (fail closed)."""


def gh_json(endpoint: str) -> object:
    try:
        done = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True,
                              timeout=TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Unreadable(f"`gh api {endpoint}` did not run ({exc})") from exc
    if done.returncode != 0:
        why = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no output"]
        raise Unreadable(f"`gh api {endpoint}` failed: {why[0]}")
    try:
        return json.loads(done.stdout)
    except ValueError as exc:
        raise Unreadable(f"`gh api {endpoint}` answered something that is not JSON") from exc


def origin_repo(cwd: str) -> str | None:
    try:
        url = subprocess.run(["git", "-C", cwd, "remote", "get-url", "origin"], capture_output=True,
                             text=True, timeout=TIMEOUT, check=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/*$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def check_merge(repo: str | None, ref: str | None, expected: str | None) -> str:
    """The deny reason for merging PR `ref` (a number or a branch) of `repo`; empty when it may merge."""
    if not repo:
        return ("refused a PR merge whose repository it cannot tell (no `-R`, `GH_REPO` or origin remote "
                "here): name it, and the PR number")
    if not ref:
        return "refused a PR merge that names no PR: pass the PR number"
    number = ref
    if not ref.isdigit():
        owner = repo.split("/")[0]
        found = gh_json(f"repos/{repo}/pulls?head={owner}:{ref}&state=open&per_page=1")
        if not isinstance(found, list) or not found:
            return f"refused a merge of branch `{ref}`: no open PR in {repo} has it as head; pass the PR number"
        number = str(found[0]["number"])
    pr = gh_json(f"repos/{repo}/pulls/{number}")
    head = (pr.get("head") or {}).get("sha") if isinstance(pr, dict) else None
    if not head or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise Unreadable(f"PR {number} in {repo} shows no head commit")
    if expected and expected != head:
        return (f"refused merging PR {number} of {repo}: the merge names head {expected}, but the PR's head "
                f"is now {head}. Check the new head's gates and review, then merge naming it")
    combined = gh_json(f"repos/{repo}/commits/{head}/status?per_page=100")
    if not isinstance(combined, dict) or not isinstance(combined.get("statuses"), list):
        raise Unreadable(f"the statuses of {head} came back in an unknown shape")
    states = {s.get("context"): s.get("state") for s in combined["statuses"] if isinstance(s, dict)}
    missing = [c for c in (GATES, REVIEW) if states.get(c) != "success"]
    if missing:
        told = "; ".join(f"`{c}` is {states.get(c) or 'absent'} (record it with {PRODUCER[c]})"
                         for c in missing)
        return (f"refused merging PR {number} of {repo}: its head {head} lacks a recorded success: {told}. "
                "Statuses on an older head do not count")
    if not expected:
        return (f"PR {number} of {repo} has both statuses on head {head}: repeat the merge naming that head "
                f"(MCP `expectedHeadSha: {head}`, `gh pr merge --match-head-commit {head}`, or "
                f"`gh api ... -f sha={head}`), so GitHub refuses it if the head moves first")
    return ""


def flag_value(args: list[str], names: set[str]) -> str | None:
    for i, a in enumerate(args):
        if a in names and i + 1 < len(args):
            return args[i + 1]
        for n in names:
            if n.startswith("--") and a.startswith(n + "="):
                return a.split("=", 1)[1]
    return None


def positionals(args: list[str], value_flags: set[str]) -> list[str]:
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in value_flags:
            skip = True
        elif not a.startswith("-"):
            out.append(a)
    return out


def gh_repo(seg_env: dict[str, str], cwd: str) -> str | None:
    return seg_env.get("GH_REPO") or os.environ.get("GH_REPO") or origin_repo(cwd)


def check_gh(args: list[str], env: dict[str, str], cwd: str) -> str:
    if args[:2] == ["pr", "merge"]:
        rest = args[2:]
        if "--auto" in rest:
            return "refused `gh pr merge --auto`: " + AUTO_MERGE
        if "--disable-auto" in rest:
            return ""
        repo = flag_value(rest, {"-R", "--repo"}) or gh_repo(env, cwd)
        pos = positionals(rest, GH_MERGE_VALUE_FLAGS)
        ref = pos[0] if pos else None
        if ref:
            m = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", ref)
            if m:
                repo, ref = f"{m.group(1)}/{m.group(2)}", m.group(3)
        else:
            ref = current_branch(cwd)
        return check_merge(repo, ref, flag_value(rest, {"--match-head-commit"}))
    if args[:1] == ["api"]:
        rest = args[1:]
        pos = positionals(rest, GH_API_VALUE_FLAGS)
        endpoint = pos[0] if pos else ""
        fields = [v for i, a in enumerate(rest) if a in {"-f", "-F", "--field", "--raw-field"}
                  and i + 1 < len(rest) for v in [rest[i + 1]]]
        if endpoint.lstrip("/") == "graphql":
            if any(MERGE_MUTATION.search(f) for f in fields):
                return ("refused a GraphQL merge mutation: the guard checks merges through REST only; use "
                        "the MCP merge tool or `gh api -X PUT repos/<o>/<r>/pulls/<n>/merge`")
            return ""
        m = MERGE_ENDPOINT.search(endpoint)
        if not m:
            return ""
        method = (flag_value(rest, {"-X", "--method"}) or ("POST" if fields or "--input" in rest else "GET"))
        if method.upper() == "GET":
            return ""
        owner, name, number = m.groups()
        repo = f"{owner}/{name}"
        if "{" in repo:
            base = gh_repo(env, cwd)
            if not base:
                return check_merge(None, number, None)
            o, n = base.split("/", 1)
            repo = repo.replace("{owner}", o).replace("{repo}", n)
        sha = next((f.split("=", 1)[1] for f in fields if f.startswith("sha=")), None)
        return check_merge(repo, number, sha)
    return ""


def current_branch(cwd: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", cwd, "symbolic-ref", "--short", "-q", "HEAD"],
                             capture_output=True, text=True, timeout=TIMEOUT, check=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out or None


def check_git(args: list[str]) -> str:
    i, hooks_off = 0, False
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if a == "-c" and i + 1 < len(args):
            hooks_off |= args[i + 1].lower().startswith("core.hookspath")
        elif a.startswith("-c") and len(a) > 2:
            hooks_off |= a[2:].lower().startswith("core.hookspath")
        i += 2 if a in GIT_GLOBAL_VALUE else 1
    if i >= len(args) or args[i] not in ("commit", "push"):
        return ""
    sub, rest = args[i], args[i + 1:]
    if hooks_off:
        return f"refused `git -c core.hooksPath=... {sub}`: " + NO_VERIFY
    skip = False
    for a in rest:
        if skip:
            skip = False
            continue
        if a == "--":
            break
        if a == "--no-verify":
            return f"refused `git {sub} --no-verify`: " + NO_VERIFY
        if sub == "commit" and a.startswith("-") and not a.startswith("--"):
            for ch in a[1:]:
                if ch == "n":
                    return "refused `git commit -n` (`--no-verify`): " + NO_VERIFY
                if ch in COMMIT_VALUE_SHORT:
                    skip = a.endswith(ch)  # `-m msg`: the next word is the value
                    break
    return ""


def check_http(args: list[str]) -> str:
    joined = " ".join(args)
    method = (flag_value(args, {"-X", "--request", "--method"}) or "").upper()
    sends = any(a.startswith(("-d", "--data", "--json", "-F", "--form", "--post-")) for a in args)
    if MERGE_URL.search(joined) and (method not in ("", "GET", "HEAD") or sends):
        return ("refused a merge sent with curl or wget, which this guard does not check: use the MCP merge "
                "tool or `gh`, after both statuses are on the head")
    if "api.github.com/graphql" in joined and MERGE_MUTATION.search(joined):
        return ("refused a GraphQL merge mutation: the guard checks merges through REST only; use the MCP merge "
                "tool or `gh api -X PUT repos/<o>/<r>/pulls/<n>/merge`")
    return ""


def verdict(command: str, cwd: str, depth: int = 0) -> str:
    command, bodies = split_heredocs(command)
    for body in bodies if depth < 3 else []:
        reason = verdict(body, cwd, depth + 1)
        if reason:
            return reason
    tokens = tokenize(command)
    if tokens is None:
        return ("refused a command this guard cannot parse (unbalanced quotes) that looks like a merge or a "
                "hook bypass" if MERGE_HINT.search(command) else "")
    for seg in segments(tokens):
        env = {}
        for t in seg:
            m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", t)
            if not m:
                break
            env[m.group(1)] = m.group(2)
        prog = program(seg)
        if not prog:
            continue
        name, args = prog
        if name in ("cd", "pushd") and args:
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(args[0])))
            continue
        reason = ""
        if name == "gh":
            reason = check_gh(args, env, cwd)
        elif name == "git":
            reason = check_git(args)
        elif name in ("curl", "wget", "http"):
            reason = check_http(args)
        elif depth < 3 and (name in SHELLS and "-c" in args or name == "eval"):
            inner = (args[args.index("-c") + 1] if name in SHELLS and args.index("-c") + 1 < len(args)
                     else " ".join(args))
            reason = verdict(inner, cwd, depth + 1)
        if reason:
            return reason
    return ""


def decide(event: dict) -> str:
    tool = event.get("tool_name") or ""
    data = event.get("tool_input") or {}
    if IMPORT_ERROR is not None and tool == "Bash":
        raise IMPORT_ERROR
    if re.fullmatch(r"mcp__.+__enable_pr_auto_merge", tool):
        return "refused enabling auto-merge: " + AUTO_MERGE
    if re.fullmatch(r"mcp__.+__merge_pull_request", tool):
        owner, name, number = data.get("owner"), data.get("repo"), data.get("pullNumber")
        repo = f"{owner}/{name}" if owner and name else None
        ref = str(int(number)) if isinstance(number, (int, float)) or str(number or "").isdigit() else None
        return check_merge(repo, ref, data.get("expectedHeadSha") or None)
    if tool == "Bash":
        return verdict(data.get("command") or "", event.get("cwd") or os.getcwd())
    return ""


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(event, dict):
        return 0
    tool = event.get("tool_name") or ""
    try:
        reason = decide(event)
    except Unreadable as exc:
        reason = (f"refused the merge: it cannot read the PR's head or statuses, so it fails closed ({exc}). "
                  "Retry once GitHub answers")
    except Exception as exc:  # noqa: BLE001 -- a guard bug must not wave a merge through, nor block other tools
        looks = tool != "Bash" or MERGE_HINT.search((event.get("tool_input") or {}).get("command") or "")
        reason = f"refused: the merge guard failed on this call ({exc!r}), so it fails closed" if looks else ""
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"Merge guard: {reason}.",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
