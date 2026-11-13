#!/usr/bin/env python3
"""PreToolUse hook: refuse a PR merge whose head commit carries no recorded gates and review.

A change may be merged only when its PR carries two records for its current head commit, each the newest
of its kind: a gates record (skills/review/scripts/gate_stamp.sh, the gate command's result) and a review
record (skills/review/scripts/verdict.sh, a verdict posted with the reviewers' output). A record is a PR
comment whose first line is `🤖 Gates: <state>` or `🤖 Review: <result> (<tier> tier)` and whose second line
is the marker `<!-- loadout:<gates|review> sha=<head> state=success|failure [tier=..] [reviewed=..] -->`.
Only comments by the repo's owner, a member or a collaborator count (`author_association`); of those, the
newest marker of each kind must be unedited, well formed, agree with its first line, name the PR's
current head and say `state=success`. A record for an older head does not count. When the guard can run
skills/review/scripts/tier.sh in a local clone holding the head, a review whose tier is below the one the
paths give refuses too, and so does a tier check that cannot finish there (tier.sh failing, or the time
budget running out); only with no local clone holding the head is that check skipped. The merge must also
name the head the
guard checked (`expectedHeadSha`, `--match-head-commit`, `-f sha=`), so GitHub itself refuses it if a push
lands between this check and the merge.

Caught: the GitHub MCP merge tool (any server's `merge_pull_request`, owner, repo and number from its
input); `gh pr merge` (a number, URL or branch; `-R`/`--repo` anywhere in the command, `GH_REPO`, or the
origin of the directory it runs in); `gh api` writes to `repos/<o>/<r>/pulls/<n>/merge` (any write method
anywhere among repeated ones, every flag spelling pflag takes, a full URL, an encoded or dotted path,
`{owner}`/`{repo}` placeholders); and the same behind shell keywords (`if … then`, `do`, `!`, `{`), through
a shell (options with values, `+` options, options after `-c`, a here-string, stdin, `busybox sh`), `eval`,
`env -S`, a backtick or `$(…)` substitution, a heredoc fed to a shell, `cd <dir> &&`, wrappers with their
own option values (`sudo -u`, `timeout -s`, `nice -n`), or a runner (`setsid`, `flock`, `find -exec`, `su
-c`). Refused outright: auto-merge (`gh pr merge --auto`, the MCP `enable_pr_auto_merge`), which merges
later at a head nobody checked; a GraphQL call that names a merge mutation, or whose query the guard
cannot read (`--input`, a `query` field from a file, an HTTP body from a file); and an HTTP client's write
to a merge URL (curl, wget, httpie, xh): use the MCP tool or `gh`. Also refused, typed by the agent: `git commit`
or `git push` with `--no-verify` (or an abbreviation git accepts, `--no-veri`), `git commit -n`, and
core.hooksPath overridden (`-c`, `--config-env`, `GIT_CONFIG_KEY_<n>`, `GIT_CONFIG_PARAMETERS`): fix what
the hook reports instead.

Not caught (out of scope): `git push` of a merge commit to the default branch, a merge through the web
UI, code calling the API from a script, or a command built at run time (`x=merge; gh pr $x`). Hooks see
only the agent's tool calls, never commands a hook runs, so the save-work hook's own `git push
--no-verify` is unaffected.

Honest limits: the records guard against forgetting, not against a dishonest author; the same account
posts them and could type a marker by hand. The guard fails closed on a merge: when it cannot read the PR
or its comments, or the guard itself fails on a command that looks like a merge, it refuses and says why.
All the calls of one decision share a 30 s budget, under the hook's 45 s timeout (a timed-out hook does not
block), and a merge whose reads run past it is refused. Any other command passes untouched and costs no
network call.

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
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote

# The shell parsing is the GCP guard's (cloud/gcp/guard.py). Should it fail to load, every call that looks like
# a merge is refused (below) and every other call passes.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gcp"))
try:
    from guard import KEYWORDS, WRAPPERS, segments, split_heredocs, tokenize
except Exception as _exc:  # noqa: BLE001
    IMPORT_ERROR: Exception | None = _exc
else:
    IMPORT_ERROR = None

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
# All calls of one decision together stay inside this budget, well under the hook's 45 s timeout: a hook that
# times out does not block the tool call, so the guard refuses as unreadable before that can happen.
try:  # tests shrink it; nothing raises it
    BUDGET = min(30.0, float(os.environ.get("MERGE_GUARD_BUDGET_S") or 30))
except ValueError:
    BUDGET = 30.0
_deadline = [time.monotonic() + BUDGET]
MERGE_ENDPOINT = re.compile(r"(?:^|/)repos/([^/\s]+)/([^/\s]+)/pulls/(\d+)/merge/?(?:\?|$)", re.IGNORECASE)
MERGE_URL = re.compile(r"api\.github\.com/+repos/+[^/\s]+/+[^/\s]+/+pulls/+\d+/+merge\b", re.IGNORECASE)
MERGE_MUTATION = re.compile(r"(mergePullRequest|enablePullRequestAutoMerge)", re.IGNORECASE)
# Text that looks like a merge, for the fail-closed path when parsing fails.
MERGE_HINT = re.compile(
    r"pr\s+merge|pulls/\S*/merge|merge_pull_request|mergePullRequest|--no-verify"
)
# gh's flags as pflag reads them. Every spelling (`-X PUT`, `-XPUT`, `-X=PUT`, `--method PUT`,
# `--method=PUT`, a cluster such as `-iXPUT`) goes through parse_flags, so every check sees the same words.
# The api and pr-merge flag sets are merged: no letter takes a value in one and not in the other.
GH_SHORT_VALUE = {"X": "method", "f": "raw-field", "F": "field", "H": "header", "q": "jq", "t": "template",
                  "p": "preview", "R": "repo", "b": "body", "A": "author-email"}
GH_LONG_VALUE = {"method", "raw-field", "field", "header", "jq", "template", "input", "preview", "hostname",
                 "cache", "repo", "body", "body-file", "subject", "author-email", "match-head-commit"}
CURL_SHORT_VALUE = {"X": "request", "d": "data", "F": "form", "T": "upload-file", "H": "header", "u": "user",
                    "o": "output", "A": "user-agent", "e": "referer", "b": "cookie", "x": "proxy", "m": "max-time",
                    "w": "write-out", "K": "config", "E": "cert", "r": "range", "c": "cookie-jar", "D": "dump-header",
                    "Y": "speed-limit", "y": "speed-time", "z": "time-cond", "C": "continue-at", "P": "ftp-port",
                    "Q": "quote", "U": "proxy-user"}
CURL_LONG_VALUE = {"request", "data", "data-raw", "data-binary", "data-ascii", "data-urlencode", "json", "form",
                   "form-string", "upload-file", "header", "user", "output", "url", "user-agent", "referer", "cookie",
                   "proxy", "max-time", "connect-timeout", "write-out", "config", "retry", "cacert", "cert",
                   "method", "body-data", "body-file", "post-data", "post-file", "output-document", "header-file"}
# Options whose value is the request body (curl, wget); from a file when it starts with `@` (or `<` in a form).
BODY_FLAGS = {"data", "data-raw", "data-binary", "data-ascii", "data-urlencode", "json", "form", "form-string",
              "upload-file", "body-data", "body-file", "post-data", "post-file", "d", "F", "T"}
HTTP_TOOLS = {"curl", "wget", "http", "https", "xh", "xhs", "curlie"}
WRITE_METHOD = re.compile(r"(?i)put|post|patch|delete")
# Shells, and how their options take values (bash, sh, zsh, dash, ksh, ash, mksh, fish, busybox's sh).
SHELL_NAMES = {"bash", "sh", "zsh", "dash", "ksh", "ash", "mksh", "fish", "yash", "posh"}
SHELL_VALUE_SHORT = set("oO")
SHELL_VALUE_LONG = {"--rcfile", "--init-file"}
# Programs that run their arguments as a command (`setsid gh …`, `find . -exec gh … \;`, `su -c '…'`): their
# joined arguments, and each argument alone, are checked as commands.
RUNNERS = {"su", "runuser", "script", "flock", "watch", "parallel", "find", "setsid", "chroot", "unbuffer",
           "strace", "ltrace", "nsenter", "unshare", "doas", "firejail", "systemd-run", "caffeinate", "chronic",
           "ts", "pv", "torsocks", "proxychains", "proxychains4", "catchsegv", "valgrind", "faketime", "tini",
           "dumb-init", "su-exec", "gosu", "chpst", "ssh-agent", "dbus-run-session", "xvfb-run", "busybox"}
# Wrappers (`sudo`, `timeout`, ...) and the options of theirs that take a separate value.
WRAPPER_VALUE = {
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T", "--user", "--group", "--chdir",
             "--host", "--prompt", "--role", "--type", "--other-user", "--command-timeout", "--close-from"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "-n", "-p", "--class", "--classdata", "--pid"},
    "env": {"-u", "-C", "--unset", "--chdir"},
    "xargs": {"-I", "-i", "-n", "-P", "-L", "-l", "-d", "-E", "-e", "-s", "-a", "--max-args", "--max-procs",
              "--max-lines", "--delimiter", "--eof", "--max-chars", "--arg-file", "--replace"},
    "exec": {"-a"},
    "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
    "time": {"-f", "-o", "--format", "--output"},
    "nohup": set(),
    "command": set(),
}
COMMIT_VALUE_SHORT = set("mFcCt")  # short options of `git commit` that take a value
COMMIT_ATTACHED = set("uS")  # ones whose optional value is attached (`-uno`)
GIT_GLOBAL_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}

AUTO_MERGE = ("auto-merge merges later, at a head nobody checked; merge by hand once both records are "
              "on the PR's head")
NO_VERIFY = ("skipping the repo's commit or push hooks. A hook that fails is reporting something: fix "
             "what it names (or ask the owner about a deliberate exception) instead of bypassing it")


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


def origin_repo(cwd: str) -> str | None:
    try:
        url = subprocess.run(["git", "-C", cwd, "remote", "get-url", "origin"], capture_output=True,
                             text=True, timeout=max(0.1, left()), check=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/*$", url)
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


def paths_tier(repo: str, head: str, cwd: str) -> str | None:
    """The tier tier.sh gives the head's paths, from a local clone of `repo` holding it.

    None only when no such clone holds the head (the check cannot run, and is skipped). Once a local clone
    holds the head, the check must finish: running out of time, or tier.sh failing, refuses as unreadable.
    """
    try:
        top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, timeout=max(0.1, left()), check=False).stdout.strip()
        if not top or origin_repo(top) != repo or not TIER_SH.is_file():
            return None
        if subprocess.run(["git", "-C", top, "cat-file", "-e", f"{head}^{{commit}}"], capture_output=True,
                          timeout=max(0.1, left()), check=False).returncode:
            return None
    except OSError:
        return None
    except subprocess.TimeoutExpired as exc:
        raise Unreadable("it ran out of time looking for the head in the local clone, so it cannot rule out a "
                         "review below the head's tier") from exc
    budget = left()
    if budget < 1:
        raise Unreadable("no time was left to run tier.sh on the head, which this clone holds")
    try:
        done = subprocess.run(["bash", str(TIER_SH), "--head", head], cwd=top, capture_output=True,
                              text=True, timeout=budget, check=False)
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
    head = (pr.get("head") or {}).get("sha") if isinstance(pr, dict) else None
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
        tier = paths_tier(repo, head, cwd)
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


def parse_flags(args: list[str], short_value: dict[str, str],
                long_value: set[str]) -> tuple[list[str], list[tuple[str, str | None]]]:
    """(positional words, [(flag name, value or None)]) the way pflag and curl read a command line.

    `--name=value`, `--name value` (for a flag that takes one), `-Xvalue`, `-X=value`, `-X value`, and a
    cluster of short flags ending in one that takes a value (`-iXPUT`) all give the same (name, value).
    A short flag keeps its letter as its name unless the table names it.
    """
    pos: list[str] = []
    flags: list[tuple[str, str | None]] = []
    i = 0
    while i < len(args):
        a = args[i]
        i += 1
        if a == "--":
            pos += args[i:]
            break
        if a.startswith("--") and len(a) > 2:
            name, eq, val = a[2:].partition("=")
            if eq:
                flags.append((name, val))
            elif name in long_value:
                flags.append((name, args[i] if i < len(args) else ""))
                i += 1
            else:
                flags.append((name, None))
        elif a.startswith("-") and len(a) > 1:
            for j in range(1, len(a)):
                ch = a[j]
                if ch in short_value:
                    val = a[j + 1:]
                    if val.startswith("="):
                        val = val[1:]
                    elif not val:
                        val = args[i] if i < len(args) else ""
                        i += 1
                    flags.append((short_value[ch], val))
                    break
                flags.append((ch, None))
        else:
            pos.append(a)
    return pos, flags


def values(flags: list[tuple[str, str | None]], *names: str) -> list[str]:
    return [v if v is not None else "" for n, v in flags if n in names]


def shell_commands(args: list[str]) -> list[str]:
    """The command strings a shell would run from its arguments (`bash [options] -c <cmd> [name args]`).

    Options as bash reads them: clusters with `-` or `+`, `-o`/`-O`/`+o`/`+O` taking a value, `--rcfile` and
    `--init-file` taking one, `--` ending them; the command string is the first word after the options once
    a `c` was seen in any cluster. A here-string (`<<< 'cmd'`) is a command too. When the options cannot be
    read for sure and a `c` is among them, every word is returned as a candidate: over-refusing a word that
    looks like a merge is the safe side.
    """
    out = [args[k + 1] for k, a in enumerate(args[:-1]) if a == "<<<"]
    saw_c = unsure = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            i += 1
            break
        if a in SHELL_VALUE_LONG:
            i += 2
            continue
        if a.startswith("--"):
            i += 1
            continue
        if len(a) > 1 and a[0] in "-+" and a[1:].isalpha():
            letters = a[1:]
            saw_c |= "c" in letters
            takes = sum(ch in SHELL_VALUE_SHORT for ch in letters)
            if takes > 1 or (takes == 1 and letters[-1] not in SHELL_VALUE_SHORT):
                unsure = True
            i += 1 + takes
            continue
        if a[:1] in "-+":
            unsure = True  # `-c1`, `-o=x`: not a form bash takes; read every word
            saw_c |= "c" in a
            i += 1
            continue
        break
    if i > len(args):
        unsure = True  # a value-taking option with no value
    if not saw_c:
        return out
    if unsure:
        return out + [a for a in args if a not in ("--", "<<<")]
    return out + args[i:i + 1]


def gh_repo(seg_env: dict[str, str], cwd: str) -> str | None:
    return seg_env.get("GH_REPO") or os.environ.get("GH_REPO") or origin_repo(cwd)


def check_gh(args: list[str], env: dict[str, str], cwd: str) -> str:
    pos, flags = parse_flags(args, GH_SHORT_VALUE, GH_LONG_VALUE)
    names = {n for n, _ in flags}
    repos = values(flags, "repo")
    repo_flag = repos[-1] if repos else None
    if pos[:2] == ["pr", "merge"]:
        if "auto" in names:
            return "refused `gh pr merge --auto`: " + AUTO_MERGE
        if "disable-auto" in names:
            return ""
        repo = repo_flag or gh_repo(env, cwd)
        ref = pos[2] if len(pos) > 2 else None
        if ref:
            m = re.search(r"github\.com/+([^/]+)/+([^/]+)/+pull/+(\d+)", ref, re.IGNORECASE)
            if m:
                repo, ref = f"{m.group(1)}/{m.group(2)}", m.group(3)
            ref = ref.lstrip("#") if ref.lstrip("#").isdigit() else ref
        else:
            ref = current_branch(cwd)
        heads = values(flags, "match-head-commit")
        return check_merge(repo, ref, heads[-1] if heads else None, cwd)[0]
    if pos[:1] == ["api"]:
        endpoint = pos[1] if len(pos) > 1 else ""
        typed = values(flags, "field")
        fields = values(flags, "raw-field") + typed
        has_input = "input" in names
        path = posixpath.normpath(unquote(re.sub(r"^https?://[^/]+", "", endpoint)).split("?", 1)[0] or "/")
        if path.strip("/").lower() == "graphql":
            if any(MERGE_MUTATION.search(f) for f in fields):
                return ("refused a GraphQL merge mutation: the guard checks merges through REST only; use "
                        "the MCP merge tool or `gh api -X PUT repos/<o>/<r>/pulls/<n>/merge`")
            if has_input or any(f.startswith("query=@") for f in typed):
                return ("refused a GraphQL call whose query comes from a file, which the guard cannot check for a "
                        "merge mutation: pass the query inline with `-f query='...'`")
            return ""
        m = MERGE_ENDPOINT.search(path)
        if not m:
            return ""
        methods = values(flags, "method")
        # gh sends the last method given; any write method anywhere counts as a write all the same.
        write = (any(x.strip().upper() not in ("GET", "HEAD") for x in methods)
                 or (not methods and (fields or has_input)))
        if not write:
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
    return ""


def current_branch(cwd: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", cwd, "symbolic-ref", "--short", "-q", "HEAD"],
                             capture_output=True, text=True, timeout=max(0.1, left()), check=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out or None


def no_verify(a: str) -> bool:
    """`--no-verify`, or an abbreviation git takes for it (`--no-veri`; `--no-ver` could be `--no-verbose`)."""
    return a == "--no-verify" or (len(a) >= 9 and "--no-verify".startswith(a))


def hooks_path(text: str) -> bool:
    return text.strip().lower().startswith("core.hookspath")


def check_git(args: list[str], env: dict[str, str]) -> str:
    i, hooks_off = 0, False
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if a == "-c" and i + 1 < len(args):
            hooks_off |= hooks_path(args[i + 1])
        elif a.startswith("-c") and len(a) > 2:
            hooks_off |= hooks_path(a[2:])
        elif a == "--config-env" and i + 1 < len(args):
            hooks_off |= hooks_path(args[i + 1])
        elif a.startswith("--config-env="):
            hooks_off |= hooks_path(a.split("=", 1)[1])
        i += 2 if a in GIT_GLOBAL_VALUE else 1
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
    pos, flags = parse_flags(args, CURL_SHORT_VALUE, CURL_LONG_VALUE)
    joined = " ".join(args)
    methods = values(flags, "request", "method")
    if name not in ("curl", "wget"):  # httpie, xh: `http PUT <url>`
        methods += [p for p in pos if WRITE_METHOD.fullmatch(p)]
    bodies = [(n, v if v is not None else "") for n, v in flags if n in BODY_FLAGS]
    items = [p for p in pos if not WRITE_METHOD.fullmatch(p) and "github.com" not in p.lower()]
    write = (any(x.strip().upper() not in ("GET", "HEAD") for x in methods) or bool(bodies)
             or (name not in ("curl", "wget") and any(re.search(r"=|@", p) for p in items)))
    if MERGE_URL.search(joined) and write:
        return ("refused a merge sent with an HTTP client, which this guard does not check: use the MCP merge "
                "tool or `gh`, after both records are on the head")
    if re.search(r"api\.github\.com/+graphql", joined, re.IGNORECASE):
        if MERGE_MUTATION.search(joined):
            return ("refused a GraphQL merge mutation: the guard checks merges through REST only; use the MCP "
                    "merge tool or `gh api -X PUT repos/<o>/<r>/pulls/<n>/merge`")
        from_file = any((v.startswith("@") and n != "data-raw") or n in ("upload-file", "T", "body-file", "post-file")
                        or (n in ("data-urlencode", "form", "F") and re.search(r"(^|=)[@<]", v))
                        for n, v in bodies)
        if from_file or (name not in ("curl", "wget") and any("@" in p for p in items)):
            return ("refused a GraphQL call whose body comes from a file, which the guard cannot check for a "
                    "merge mutation: send the query inline")
    return ""


ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", re.DOTALL)


def command_of(seg: list[str]) -> tuple[str, list[str], dict[str, str]] | None:
    """(program, its arguments, the variables set for it) of a segment, past assignments, shell keywords and
    wrappers with their own options and values (`sudo -u root`, `timeout -s KILL 5`, `env -i`, `xargs -n 1`).
    `env -S '<cmd>'` splits its string into a command: it comes back as `eval`."""
    env: dict[str, str] = {}
    i = 0
    while i < len(seg):
        t = seg[i]
        m = ASSIGNMENT.fullmatch(t)
        if m:
            env[m.group(1)] = m.group(2)
            i += 1
            continue
        if t in KEYWORDS:
            i += 1
            continue
        name = os.path.basename(t)
        if name in WRAPPER_VALUE or name in WRAPPERS:
            i += 1
            takes = WRAPPER_VALUE.get(name, set())
            while i < len(seg) and seg[i].startswith("-") and seg[i] != "-":
                o = seg[i]
                i += 1
                if o == "--":
                    break
                if name == "env" and (o in ("-S", "--split-string") or o.startswith(("-S", "--split-string="))):
                    text = o.split("=", 1)[1] if o.startswith("--split-string=") else o[2:] if o.startswith("-S") and len(o) > 2 else (seg[i] if i < len(seg) else "")
                    if o in ("-S", "--split-string"):
                        i += 1
                    return "eval", [text, *seg[i:]], env
                if o in takes:
                    i += 1
            if name == "timeout" and i < len(seg) and re.fullmatch(r"[\d.]+[smhd]?", seg[i]):
                i += 1  # the duration
            continue
        if t.isdigit():
            i += 1
            continue
        return name, seg[i + 1:], env
    return None


def verdict(command: str, cwd: str, depth: int = 0, exported: dict[str, str] | None = None) -> str:
    exported = {} if exported is None else exported
    # `$'…'` and `$"…"` quote as '…' and "…" for this purpose, and a backtick substitution runs its command.
    command = re.sub(r"\$(['\"])", r"\1", command).replace("`", " ; ")
    command, bodies = split_heredocs(command)
    for body in bodies if depth < 4 else []:
        reason = verdict(body, cwd, depth + 1, dict(exported))
        if reason:
            return reason
    tokens = tokenize(command)
    if tokens is None:
        return ("refused a command this guard cannot parse (unbalanced quotes) that looks like a merge or a "
                "hook bypass" if MERGE_HINT.search(command) else "")
    for seg in segments(tokens):
        found = command_of(seg)
        if not found:
            exported.update({k: v for k, v in (ASSIGNMENT.fullmatch(t).groups() for t in seg  # type: ignore[union-attr]
                                               if ASSIGNMENT.fullmatch(t))})
            continue
        name, args, own = found
        env = {**exported, **own}
        if name == "export":
            exported.update({k: v for k, v in (ASSIGNMENT.fullmatch(t).groups() for t in args  # type: ignore[union-attr]
                                               if ASSIGNMENT.fullmatch(t))})
            continue
        if name in ("cd", "pushd") and args:
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(args[0])))
            continue
        reason = ""
        if name == "gh":
            reason = check_gh(args, env, cwd)
        elif name == "git":
            reason = check_git(args, env)
        elif name in HTTP_TOOLS:
            reason = check_http(name, args)
        elif depth < 4 and (name in SHELL_NAMES or (name == "busybox" and args[:1] and args[0] in SHELL_NAMES)):
            shell_args = args[1:] if name == "busybox" else args
            candidates = shell_commands(shell_args)
            if not candidates and not any(a for a in shell_args if not a.startswith(("-", "+"))):
                # A shell reading its commands from stdin (`echo '…' | bash`): the other words of this command
                # line are what it may run.
                candidates = [t for t in tokens if " " in t.strip()]
            for inner in candidates:
                reason = verdict(inner, cwd, depth + 1, dict(env))
                if reason:
                    break
        elif depth < 4 and name == "eval":
            reason = verdict(" ".join(args), cwd, depth + 1, dict(env))
        elif depth < 4 and (name in RUNNERS or " " in name):
            # Where the command starts depends on the runner's own options (`flock <file> cmd`,
            # `find . -exec cmd \;`): every tail of its arguments is a candidate, and so is each spaced word.
            words = ([name] if " " in name else []) + args
            for inner in ([" ".join(words[k:]) for k in range(len(words))]
                          + [a for a in args if " " in a.strip()]):
                reason = verdict(inner, cwd, depth + 1, dict(env))
                if reason:
                    break
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
    if IMPORT_ERROR is not None and tool == "Bash":
        raise IMPORT_ERROR
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
