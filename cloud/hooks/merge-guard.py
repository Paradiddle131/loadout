#!/usr/bin/env python3
"""PreToolUse hook: refuse a PR merge whose head commit carries no recorded gates and review.

A change may be merged only when its PR carries two records for its current head commit, each the newest
of its kind: a gates record (skills/review/scripts/gate_stamp.sh, the gate command's result) and a review
record (skills/review/scripts/verdict.sh, a verdict posted with the reviewers' output). A record is a PR
comment whose first line is `🤖 Gates: <state>` or `🤖 Review: <result> (<tier> tier)` and whose second line
is the marker `<!-- loadout:<gates|review> sha=<head> state=success|failure [tier=..] [reviewed=..] -->`.
Only comments by the repo's owner, a member or a collaborator count (`author_association`); of those, the
newest marker of each kind must be unedited, well formed, agree with its first line, name the PR's
current head and say `state=success`. A record for an older head does not count. In a local clone holding
the head and the repo's default branch as GitHub names it, skills/review/scripts/tier.sh runs with
`--base origin/<default branch>`, and a review below the tier the paths give refuses, as does a tier.sh that
fails or runs out of time; with no such clone the tier check is skipped. The merge must also name the head
the guard checked (`expectedHeadSha`, `--match-head-commit`, `-f sha=`), so GitHub itself refuses it if a
push lands between this check and the merge.

Covered (the guard is a guard against an agent forgetting the review path, not against a determined or
dishonest one, so it covers these forms exactly and no others):
- checked against the records: the MCP `merge_pull_request` tool of any server; `gh pr merge` (a number,
  `#n`, URL or branch; the repo from `-R`/`--repo`, the URL, `GH_REPO` or the origin); `gh api` writes to
  `repos/<o>/<r>/pulls/<n>/merge` (any write method, every flag spelling, a full URL, an encoded, dotted or
  upper-case path, `{owner}`/`{repo}` placeholders);
- refused outright: auto-merge (`gh pr merge --auto`, the MCP `enable_pr_auto_merge`); a GraphQL call that
  names a merge mutation or whose query comes from a file (`gh api graphql`, or an HTTP client); a write to a
  merge endpoint with `curl`, `wget`, `http`/`https` (httpie) or `xh`; `git commit` or `git push` with hooks
  bypassed (`--no-verify` or an abbreviation git takes, `commit -n`, core.hooksPath set with `-c`,
  `--config-env` or `GIT_CONFIG_*`): fix what the hook reports instead;
- each of these as the command itself, after `&&`, `||`, `;`, `|`, `&` or a newline, inside `( … )`,
  `{ …; }`, `$( … )` or backticks, after the shell keywords in KEYWORDS, variable assignments, `export` and
  `cd`, behind the wrappers in WRAPPERS with their options (`env`, `command`, `sudo`, `timeout`, `nice`,
  `time`, `exec`, `nohup`), and in the command string of `bash`/`sh`/`zsh`/`dash -c '<string>'`, `eval` or
  `env -S`, or a here-string or heredoc a shell reads its commands from, up to MAX_DEPTH levels deep.

Not covered (passed unchecked): any other program that runs a command for you (`find -exec`, `xargs`,
`parallel`, `strace`, `setsid`, `su -c`, `ssh`, `chrt`, `builtin`, …); a command piped into a shell
(`… | bash`); a command assembled at run time (`x=merge; gh pr $x`); aliases, functions and scripts; code
calling the API; a merge commit pushed to the default branch; the web UI. Hooks see only the agent's tool
calls, never commands a hook runs, so the save-work hook's own `git push --no-verify` is unaffected.

Bounds: all the work of one decision shares a 30 s budget, under the hook's 45 s timeout (a timed-out hook
does not block); parsing gets the first PARSE_BUDGET seconds of it, MAX_DEPTH levels and MAX_SEGMENTS
commands. A command it cannot parse within those bounds, or at all (unbalanced quotes), is refused when its
text holds a merge hint (MERGE_HINT), with a reason asking for the merge as a command of its own, and passed
otherwise. It fails closed on a merge: when it cannot read the PR or its comments, or it fails on a call that
looks like a merge, it refuses and says why. Any other command passes and costs no network call.

Hook mode (no arguments): reads the hook's JSON on stdin; prints a deny decision on stdout or nothing;
always exits 0. Check mode, for scripts that merge: `merge-guard.py --check <owner>/<repo>#<n>` (or `<n>`,
the repo from the current directory's origin) runs the same record checks; it prints the head sha it
checked and exits 0 when a merge naming that head would be allowed, else prints the reason on stderr and
exits 1 (2 for a usage error).
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote

PRODUCER = {
    "gates": "skills/review/scripts/gate_stamp.sh -- <the repo's gate command>",
    "review": "skills/review/scripts/verdict.sh <pr> --tier ... --result pass --reviewed <head> ...",
}
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
MARKER = re.compile(r"<!-- loadout:(gates|review)((?: [a-z]+=[^\s=]+)+) -->")
TITLE = {"gates": re.compile(r"🤖 Gates: (success|failure)"),
         "review": re.compile(r"🤖 Review: (pass|fail) \((routine|standard|sensitive) tier\)")}
FIELDS = {"gates": {"sha", "state"}, "review": {"sha", "state", "tier", "reviewed"}}
RANK = {"routine": 0, "standard": 1, "sensitive": 2}
TIER_SH = Path(__file__).resolve().parents[2] / "skills/review/scripts/tier.sh"
MAX_PAGES = 30
TIMEOUT = 10  # any one call
try:  # tests shrink it; nothing raises it
    BUDGET = min(30.0, float(os.environ.get("MERGE_GUARD_BUDGET_S") or 30))
except ValueError:
    BUDGET = 30.0
_deadline = [time.monotonic() + BUDGET]
PARSE_BUDGET, MAX_DEPTH, MAX_SEGMENTS, MAX_CHARS = 2.0, 4, 2000, 1_000_000
MERGE_ENDPOINT = re.compile(r"(?:^|/)repos/([^/\s]+)/([^/\s]+)/pulls/(\d+)/merge/?$", re.IGNORECASE)
MERGE_MUTATION = re.compile(r"mergePullRequest|enablePullRequestAutoMerge", re.IGNORECASE)
MERGE_HINT = re.compile(r"pulls\S*merge|pr\s+merge|mergePullRequest|enablePullRequestAutoMerge|--no-verify"
                        r"|hookspath", re.IGNORECASE)
GITHUB_API = re.compile(r"^(?:https?://)?api\.github\.com(?=/|$)", re.IGNORECASE)

# gh's flags as pflag reads them, curl's as curl does; parse_flags gives every spelling the same (name, value).
GH_SHORT_VALUE = {"X": "method", "f": "raw-field", "F": "field", "H": "header", "q": "jq", "t": "template",
                  "p": "preview", "R": "repo", "b": "body", "A": "author-email"}
GH_LONG_VALUE = {"method", "raw-field", "field", "header", "jq", "template", "input", "preview", "hostname",
                 "cache", "repo", "body", "body-file", "subject", "author-email", "match-head-commit"}
CURL_SHORT_VALUE = {"X": "request", "d": "data", "F": "form", "T": "upload-file", "H": "header", "u": "user",
                    "o": "output", "O": "output-document", "A": "user-agent", "e": "referer", "b": "cookie",
                    "x": "proxy", "m": "max-time", "w": "write-out", "K": "config", "E": "cert", "r": "range",
                    "c": "cookie-jar", "D": "dump-header", "Y": "speed-limit", "y": "speed-time",
                    "z": "time-cond", "C": "continue-at", "P": "ftp-port", "Q": "quote", "U": "proxy-user"}
CURL_LONG_VALUE = {"request", "data", "data-raw", "data-binary", "data-ascii", "data-urlencode", "json", "form",
                   "form-string", "upload-file", "header", "user", "output", "url", "user-agent", "referer", "cookie",
                   "proxy", "max-time", "connect-timeout", "write-out", "config", "retry", "cacert", "cert",
                   "method", "body-data", "body-file", "post-data", "post-file", "output-document", "header-file"}
BODY_FLAGS = {"data", "data-raw", "data-binary", "data-ascii", "data-urlencode", "json", "form", "form-string",
              "upload-file", "body-data", "body-file", "post-data", "post-file"}
HTTP_TOOLS = {"curl", "wget", "http", "https", "xh", "xhs"}
WRITE_METHOD = re.compile(r"(?i)put|post|patch|delete")
SHELLS = {"bash", "sh", "zsh", "dash"}
KEYWORDS = {"if", "then", "elif", "else", "do", "while", "until", "!", "{"}
# The wrappers, each with (its short options that take a value, its long ones, words before the command).
WRAPPERS = {
    "env": ("uCSa", {"unset", "chdir", "split-string", "argv0"}, 0),
    "command": ("", set(), 0),
    "sudo": ("ugCDhprtUTR", {"user", "group", "close-from", "chdir", "host", "prompt", "role", "type",
                             "other-user", "command-timeout", "chroot"}, 0),
    "timeout": ("sk", {"signal", "kill-after"}, 1),
    "nice": ("n", {"adjustment"}, 0),
    "time": ("fo", {"format", "output"}, 0),
    "exec": ("a", set(), 0),
    "nohup": ("", set(), 0),
}
COMMIT_VALUE_SHORT = set("mFcCt")  # short options of `git commit` that take a value
COMMIT_ATTACHED = set("uS")  # ones whose optional value is attached (`-uno`)
GIT_GLOBAL_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", re.DOTALL)
HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*\\?(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
PLACEHOLDER = re.compile("\x00(\\d+)\x00")
REDIRECT = re.compile(r"\d*(?:>>?|<>?|>\|)")
FD_DUP = re.compile(r"(?<![\w&])\d*[<>]&(?:\d+|-)")

AUTO_MERGE = ("auto-merge merges later, at a head nobody checked; merge by hand once both records are "
              "on the PR's head")
NO_VERIFY = ("skipping the repo's commit or push hooks. A hook that fails is reporting something: fix "
             "what it names (or ask the owner about a deliberate exception) instead of bypassing it")
GRAPHQL_MERGE = ("refused a GraphQL merge mutation: the guard checks merges through REST only; use the MCP "
                 "merge tool or `gh api -X PUT repos/<o>/<r>/pulls/<n>/merge`")


class Unreadable(Exception):
    """GitHub could not be read: the merge is refused (fail closed)."""


class TooComplex(Exception):
    """The command could not be parsed within the bounds: the hint rule decides."""


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


def current_branch(cwd: str) -> str | None:
    done = git_out("-C", cwd, "symbolic-ref", "--short", "-q", "HEAD")
    return (done.stdout.strip() or None) if done else None


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


def check_merge(repo: str | None, ref: str | None, expected: str | None, cwd: str = ".",
                require_named: bool = True) -> tuple[str, str]:
    """(deny reason, head checked) for merging PR `ref` (a number or a branch) of `repo`; no reason: allowed."""
    if not repo:
        return ("refused a PR merge whose repository it cannot tell (no `-R`, `GH_REPO` or origin remote "
                "here): name it, and the PR number"), ""
    if not ref:
        return "refused a PR merge that names no PR: pass the PR number", ""
    number = ref
    if not ref.isdigit():
        owner = repo.split("/")[0]
        found = gh_json(f"repos/{repo}/pulls?head={owner}:{ref}&state=open&per_page=1")
        if not isinstance(found, list) or not found:
            return (f"refused a merge of branch `{ref}`: no open PR in {repo} has it as head; pass the PR "
                    "number"), ""
        number = str(found[0]["number"])
    pr = gh_json(f"repos/{repo}/pulls/{number}")
    pr = pr if isinstance(pr, dict) else {}
    head = (pr.get("head") or {}).get("sha")
    if not head or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise Unreadable(f"PR {number} in {repo} shows no head commit")
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
        return (f"PR {number} of {repo} has both records on head {head}: repeat the merge naming that head "
                f"(MCP `expectedHeadSha: {head}`, `gh pr merge --match-head-commit {head}`, or "
                f"`gh api ... -f sha={head}`), so GitHub refuses it if the head moves first"), head
    return "", head


def parse_flags(args: list[str], short_value: dict[str, str], long_value: set[str],
                wrapper: bool = False) -> tuple[list[str], list[tuple[str, str | None]], int]:
    """(positional words, [(flag name, value or None)], index where parsing stopped) as pflag and curl read a
    command line: `--name=value`, `--name value` (for a flag that takes one), `-Xvalue`, `-X=value`, `-X value`
    and a cluster ending in a flag that takes a value (`-iXPUT`) all give the same (name, value). A short flag
    keeps its letter as its name unless the table names it. For a wrapper, as getopt reads it, `-X=value` is the
    value `=value`, a long option may be abbreviated, and the first other word ends the options."""
    pos: list[str] = []
    flags: list[tuple[str, str | None]] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos += args[i + 1:]
            return pos, flags, i + 1
        if a.startswith("--") and len(a) > 2:
            i += 1
            name, eq, val = a[2:].partition("=")
            if eq:
                flags.append((name, val))
            elif name in long_value or (wrapper and any(v.startswith(name) for v in long_value)):
                full = name if name in long_value else next(v for v in long_value if v.startswith(name))
                flags.append((full, args[i] if i < len(args) else ""))
                i += 1
            else:
                flags.append((name, None))
        elif a.startswith("-") and len(a) > 1:
            i += 1
            for j in range(1, len(a)):
                ch = a[j]
                if ch in short_value:
                    val = a[j + 1:]
                    if val.startswith("=") and not wrapper:
                        val = val[1:]
                    elif not val:
                        val = args[i] if i < len(args) else ""
                        i += 1
                    flags.append((short_value[ch], val))
                    break
                flags.append((ch, None))
        elif wrapper:
            return pos, flags, i
        else:
            pos.append(a)
            i += 1
    return pos, flags, i


def values(flags: list[tuple[str, str | None]], *names: str) -> list[str]:
    return [v if v is not None else "" for n, v in flags if n in names]


def api_path(url: str) -> str:
    """A GitHub API path as GitHub reads it: host dropped, percent-decoded, dot segments resolved, no query."""
    path = unquote(GITHUB_API.sub("", re.sub(r"(?i)^https?://[^/]+", "", url)))
    return posixpath.normpath(path.split("?", 1)[0].split("#", 1)[0] or "/")


def gh_repo(env: dict[str, str], cwd: str) -> str | None:
    return env.get("GH_REPO") or os.environ.get("GH_REPO") or origin_repo(cwd)


def check_gh(args: list[str], env: dict[str, str], cwd: str) -> str:
    pos, flags, _ = parse_flags(args, GH_SHORT_VALUE, GH_LONG_VALUE)
    names = {n for n, _ in flags}
    if names & {"help", "h"}:
        return ""
    repos = values(flags, "repo")
    if pos[:2] == ["pr", "merge"]:
        if "auto" in names:
            return "refused `gh pr merge --auto`: " + AUTO_MERGE
        if "disable-auto" in names:
            return ""
        repo = repos[-1] if repos else gh_repo(env, cwd)
        ref = pos[2] if len(pos) > 2 else current_branch(cwd)
        m = re.search(r"github\.com/+([^/]+)/+([^/]+)/+pull/+(\d+)", ref or "", re.IGNORECASE)
        if m:
            repo, ref = f"{m.group(1)}/{m.group(2)}", m.group(3)
        elif ref and ref.lstrip("#").isdigit():
            ref = ref.lstrip("#")
        heads = values(flags, "match-head-commit")
        return check_merge(repo, ref, heads[-1] if heads else None, cwd)[0]
    if pos[:1] != ["api"]:
        return ""
    typed = values(flags, "field")
    fields = values(flags, "raw-field") + typed
    has_input = "input" in names
    path = api_path(pos[1] if len(pos) > 1 else "")
    if path.strip("/").lower() == "graphql":
        if any(MERGE_MUTATION.search(f) for f in fields):
            return GRAPHQL_MERGE
        if has_input or any(f.startswith("query=@") for f in typed):
            return ("refused a GraphQL call whose query comes from a file, which the guard cannot check for a "
                    "merge mutation: pass the query inline with `-f query='...'`")
        return ""
    m = MERGE_ENDPOINT.search(path)
    methods = values(flags, "method")
    # gh sends the last method given; any write method anywhere counts as a write all the same.
    if not m or not (any(x.strip().upper() not in ("GET", "HEAD") for x in methods)
                     or (not methods and (fields or has_input))):
        return ""
    owner, name, number = m.groups()
    repo = f"{owner}/{name}"
    if "{" in repo:
        base = gh_repo(env, cwd)
        if not base:
            return check_merge(None, number, None)[0]
        o, n = base.split("/", 1)
        repo = repo.replace("{owner}", o).replace("{repo}", n)
    shas = [f.split("=", 1)[1] for f in fields if f.startswith("sha=")]
    return check_merge(repo, number, shas[-1] if shas else None, cwd)[0]


def no_verify(a: str) -> bool:
    """`--no-verify`, or an abbreviation git takes for it (`--no-veri`; `--no-ver` could be `--no-verbose`)."""
    return a == "--no-verify" or (len(a) >= 9 and "--no-verify".startswith(a))


def hooks_path(text: str) -> bool:
    return text.strip().lower().startswith("core.hookspath")


def check_git(args: list[str], env: dict[str, str]) -> str:
    i, hooks_off = 0, False
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if a in ("-c", "--config-env") and i + 1 < len(args):
            hooks_off |= hooks_path(args[i + 1])
        elif a.startswith("-c") and len(a) > 2:
            hooks_off |= hooks_path(a[2:])
        elif a.startswith("--config-env="):
            hooks_off |= hooks_path(a.split("=", 1)[1])
        i += 2 if a in GIT_GLOBAL_VALUE or a == "--config-env" else 1
    if i >= len(args) or args[i] not in ("commit", "push"):
        return ""
    sub, rest = args[i], args[i + 1:]
    # Config from the environment: GIT_CONFIG_COUNT with GIT_CONFIG_KEY_<n>, or GIT_CONFIG_PARAMETERS.
    hooks_off |= any(re.fullmatch(r"GIT_CONFIG_KEY_\d+", k) and hooks_path(v) for k, v in env.items())
    hooks_off |= "core.hookspath" in env.get("GIT_CONFIG_PARAMETERS", "").lower()
    if hooks_off:
        return f"refused `git {sub}` with core.hooksPath overridden: " + NO_VERIFY
    skip = False
    for a in rest:
        if skip:
            skip = False
            continue
        if a == "--":
            break
        if no_verify(a):
            return f"refused `git {sub} {a}` (`--no-verify`): " + NO_VERIFY
        if sub == "commit" and a.startswith("-") and not a.startswith("--"):
            for ch in a[1:]:
                if ch == "n":
                    return "refused `git commit -n` (`--no-verify`): " + NO_VERIFY
                if ch in COMMIT_VALUE_SHORT:
                    skip = a.endswith(ch)  # `-m msg`: the next word is the value
                    break
                if ch in COMMIT_ATTACHED:
                    break  # `-uno`, `-Skey`: the rest of the word is the value
    return ""


def check_http(name: str, args: list[str]) -> str:
    pos, flags, _ = parse_flags(args, CURL_SHORT_VALUE, CURL_LONG_VALUE)
    httpie = name not in ("curl", "wget")
    methods = values(flags, "request", "method") + ([p for p in pos if WRITE_METHOD.fullmatch(p)] if httpie else [])
    bodies = [(n, v or "") for n, v in flags if n in BODY_FLAGS]
    items = [p for p in pos if not WRITE_METHOD.fullmatch(p) and not GITHUB_API.match(p)]
    write = (any(x.strip().upper() not in ("GET", "HEAD") for x in methods) or bool(bodies)
             or (httpie and any(re.search(r"=|@", p) for p in items)))
    paths = [api_path(u) for u in pos + values(flags, "url") if GITHUB_API.match(u)]
    if write and any(MERGE_ENDPOINT.search(p) for p in paths):
        return ("refused a merge sent with an HTTP client, which this guard does not check: use the MCP merge "
                "tool or `gh`, after both records are on the head")
    if any(p.strip("/").lower() == "graphql" for p in paths):
        if MERGE_MUTATION.search(" ".join(args)):
            return GRAPHQL_MERGE
        from_file = any((v.startswith("@") and n != "data-raw") or n in ("upload-file", "body-file", "post-file")
                        or (n in ("data-urlencode", "form") and re.search(r"(^|=)[@<]", v)) for n, v in bodies)
        if from_file or (httpie and any("@" in p for p in items)):
            return ("refused a GraphQL call whose body comes from a file, which the guard cannot check for a "
                    "merge mutation: send the query inline")
    return ""


class Parse:
    """One command line's parse: the gh, git and HTTP-client commands it runs, found within the bounds."""

    def __init__(self) -> None:
        self.deadline = min(_deadline[0], time.monotonic() + PARSE_BUDGET)
        self.segments = 0
        self.bodies: list[str] = []
        self.hits: list[tuple[str, list[str], dict[str, str], str]] = []

    def tick(self) -> None:
        if time.monotonic() > self.deadline:
            raise TooComplex(f"it took more than {PARSE_BUDGET:.0f} s to read")

    def heredocs(self, text: str) -> str:
        """The text with each heredoc body cut out, kept in `bodies`, and its `<<EOF` turned into a here-string
        of a placeholder, so a shell reading it gets the body as its commands and any other program text."""
        lines, kept, i = text.split("\n"), [], 0
        while i < len(lines):
            line, parts, last = lines[i], [], 0
            i += 1
            for m in HEREDOC.finditer(line):
                self.tick()
                strip, delim = m.group(1) == "-", m.group(3)
                end = next((j for j in range(i, len(lines))
                            if (lines[j].lstrip("\t") if strip else lines[j]) == delim), None)
                if end is None:
                    break  # not a heredoc after all (a quoted `<<`): leave the text as it is
                self.bodies.append("\n".join(lines[i:end]))
                parts.append(f"{line[last:m.start()]} <<< \x00{len(self.bodies) - 1}\x00 ")
                last, i = m.end(), end + 1
            kept.append("".join(parts) + line[last:])
        return "\n".join(kept)

    def tokens(self, text: str) -> list[str]:
        lex = shlex.shlex(text, posix=True, punctuation_chars=";&|()\n")
        lex.whitespace, lex.whitespace_split, lex.commenters = " \t\r", True, ""
        out = []
        try:
            for t in lex:
                out.append(t)
                if len(out) % 512 == 0:
                    self.tick()
        except ValueError as exc:
            raise TooComplex("its quotes do not balance") from exc
        return out

    def scan(self, text: str, cwd: str, env: dict[str, str], depth: int = 0) -> None:
        if depth > MAX_DEPTH:
            raise TooComplex(f"it nests shells more than {MAX_DEPTH} deep")
        if len(text) > MAX_CHARS:
            raise TooComplex(f"it is longer than {MAX_CHARS} characters")
        # `$'…'` and `$"…"` quote as '…' and "…" here, and a file descriptor copy (`2>&1`, `&>`) is a
        # redirection, not a separator.
        text = FD_DUP.sub(" ", re.sub(r"\$(['\"])", r"\1", text).replace("&>", " >"))
        text, substitutions = prepare(self.heredocs(text))
        for inner in substitutions:
            self.scan(inner, cwd, dict(env), depth + 1)
        seg: list[str] = []
        for t in [*self.tokens(text), ";"]:
            if t and set(t) <= set(";&|()\n"):
                if seg:
                    self.segments += 1
                    if self.segments > MAX_SEGMENTS:
                        raise TooComplex(f"it holds more than {MAX_SEGMENTS} commands")
                    self.tick()
                    cwd = self.command(seg, cwd, env, depth)
                seg = []
            else:
                seg.append(t)

    def command(self, seg: list[str], cwd: str, env: dict[str, str], depth: int) -> str:
        """Read one simple command; return the directory the next one runs in."""
        words, here = [], []
        i = 0
        while i < len(seg):
            t = seg[i]
            if t.startswith("<<<"):
                here.append(t[3:] or (seg[i + 1] if i + 1 < len(seg) else ""))
                i += 1 if t[3:] else 2
            elif REDIRECT.fullmatch(t):
                i += 2
            elif REDIRECT.match(t):
                i += 1
            else:
                words.append(t)
                i += 1
        here = [self.bodies[int(m.group(1))] if (m := PLACEHOLDER.fullmatch(h)) else h for h in here]
        name, args, own = command_of(words)
        if not name:
            env.update(own)  # `X=1` alone sets a shell variable for what follows
            return cwd
        sub_env = {**env, **own}
        if name == "export":
            env.update(dict(m.groups() for a in args if (m := ASSIGNMENT.fullmatch(a))))  # type: ignore[misc]
        elif name in ("cd", "pushd") and args:
            return os.path.normpath(os.path.join(cwd, os.path.expanduser(args[0])))
        elif name in ("gh", "git") or name in HTTP_TOOLS:
            self.hits.append((name, args, sub_env, cwd))
        elif name == "eval":
            self.scan(" ".join(args), cwd, dict(sub_env), depth + 1)
        elif name in SHELLS:
            for inner in shell_commands(args, here):
                self.scan(inner, cwd, dict(sub_env), depth + 1)
        return cwd


def prepare(text: str) -> tuple[str, list[str]]:
    """(the text as the tokenizer should read it, the commands of its substitutions).

    Out go comments (a `#` that starts a word, outside quotes, to the end of the line), line continuations, and
    the substitutions a quote would hide from the tokenizer: backticks outside single quotes and `$( … )` inside
    double quotes, whose commands come back to be read on their own. A `$( … )` outside quotes needs nothing:
    its parentheses split it into commands."""
    out, subs, quote, i = [], [], "", 0
    while i < len(text):
        c = text[i]
        if c == "\\" and quote != "'":
            out.append("" if text[i + 1:i + 2] == "\n" else text[i:i + 2])
            i += 2
            continue
        if c == "`" and quote != "'":
            end = closing(text, i + 1, "`")
            subs.append(text[i + 1:end])
            out.append(" ")
            i = end + 1
            continue
        if quote == '"' and text.startswith("$(", i):
            end = closing(text, i + 2, ")")
            subs.append(text[i + 2:end])
            i = end + 1
            continue
        if quote:
            quote = "" if c == quote else quote
        elif c in "'\"":
            quote = c
        elif c == "#" and (i == 0 or text[i - 1] in " \t\n;&|()"):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue
        out.append(c)
        i += 1
    return "".join(out), subs


def closing(text: str, i: int, close: str) -> int:
    """Where the substitution opened just before `i` closes (a backtick, or the `)` of `$(`, past nested
    parentheses and quotes); the end of the text when it does not."""
    depth, quote = 1, ""
    while i < len(text):
        c = text[i]
        if c == "\\" and quote != "'":
            i += 2
            continue
        if quote:
            quote = "" if c == quote else quote
        elif c == close and close == "`":
            return i
        elif c in "'\"" and close == ")":
            quote = c
        elif close == ")" and c in "()":
            depth += 1 if c == "(" else -1
            if not depth:
                return i
        i += 1
    return len(text)


def command_of(words: list[str]) -> tuple[str, list[str], dict[str, str]]:
    """(program, its arguments, the variables set for it) of a simple command, past assignments, keywords and
    the wrappers with their options; `env -S '<cmd>'` comes back as `eval`. No program: ('', [], vars)."""
    env: dict[str, str] = {}
    i = 0
    while i < len(words):
        t = words[i]
        name = os.path.basename(t)
        if m := ASSIGNMENT.fullmatch(t):
            env[m.group(1)] = m.group(2)
            i += 1
        elif t in KEYWORDS:
            i += 1
        elif name in WRAPPERS:
            short, long, positional = WRAPPERS[name]
            rest = words[i + 1:]
            if name == "env" and rest[:1] == ["-"]:
                rest = rest[1:]  # `env -` is `env -i`
            _, flags, k = parse_flags(rest, {c: c for c in short}, long, wrapper=True)
            split = values(flags, "S", "split-string")
            if name == "env" and split:
                return "eval", [split[-1], *rest[k:]], env
            words, i = rest[k + positional:], 0
        else:
            return name, words[i + 1:], env
    return "", [], env


def shell_commands(args: list[str], here: list[str]) -> list[str]:
    """The command strings a shell runs (`bash [options] -c <cmd> [name args]`, or its stdin).

    Options as bash reads them: clusters with `-` or `+`, `o`/`O` in a cluster taking the next word, `--rcfile`
    and `--init-file` taking one, `-`/`--` ending them; with a `c` among them the command string is the first
    word after the options. Without one, a here-string or heredoc is the commands when the shell reads stdin
    (no script named, or `-s`)."""
    saw_c = saw_s = False
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-", "--"):
            i += 1
            break
        if a in ("--rcfile", "--init-file"):
            i += 2
        elif a.startswith("--"):
            i += 1
        elif re.fullmatch(r"[-+][A-Za-z]+", a):
            saw_c |= "c" in a
            saw_s |= "s" in a
            i += 1 + sum(ch in "oO" for ch in a[1:])
        else:
            break
    if saw_c:
        return args[i:i + 1]
    return here if saw_s or i >= len(args) else []


def verdict(command: str, cwd: str) -> str:
    parse = Parse()
    try:
        parse.scan(command, cwd, {})
    except TooComplex as exc:
        if MERGE_HINT.search(command):
            return (f"refused a command it could not check ({exc}) whose text looks like a merge or a hook "
                    "bypass: run the merge, commit or push as a command of its own")
        return ""
    for name, args, env, where in parse.hits:
        reason = (check_gh(args, env, where) if name == "gh" else check_git(args, env) if name == "git"
                  else check_http(name, args))
        if reason:
            return reason
    return ""


def tool_input(event: dict) -> dict:
    data = event.get("tool_input")
    return data if isinstance(data, dict) else {}


def decide(event: dict) -> str:
    _deadline[0] = time.monotonic() + BUDGET
    tool = event.get("tool_name") or ""
    data = tool_input(event)
    if re.fullmatch(r"mcp__.+__enable_pr_auto_merge", tool):
        return "refused enabling auto-merge: " + AUTO_MERGE
    if re.fullmatch(r"mcp__.+__merge_pull_request", tool):
        owner, name, number = data.get("owner"), data.get("repo"), data.get("pullNumber")
        repo = f"{owner}/{name}" if isinstance(owner, str) and isinstance(name, str) and owner and name else None
        ref = (str(int(number)) if isinstance(number, (int, float)) and not isinstance(number, bool)
               else number if isinstance(number, str) and number.isdigit() else None)
        expected = data.get("expectedHeadSha")
        return check_merge(repo, ref, expected if isinstance(expected, str) and expected else None,
                           event.get("cwd") or os.getcwd())[0]
    if tool == "Bash":
        command = data.get("command")
        return verdict(command if isinstance(command, str) else "", event.get("cwd") or os.getcwd())
    return ""


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
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(event, dict):
        return 0
    tool = event.get("tool_name") or ""
    if not isinstance(event.get("cwd"), str):
        event["cwd"] = os.getcwd()
    try:
        reason = decide(event)
    except Unreadable as exc:
        reason = (f"refused the merge: it cannot read the PR's head or comments, so it fails closed ({exc}). "
                  "Retry once GitHub answers")
    except Exception as exc:  # noqa: BLE001 -- a guard bug must not wave a merge through, nor block other tools
        command = tool_input(event).get("command")
        looks = tool != "Bash" or MERGE_HINT.search(command if isinstance(command, str) else "")
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
