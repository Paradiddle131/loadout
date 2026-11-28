#!/usr/bin/env python3
"""PreToolUse hook for Bash: a tripwire for a review agent's slip into the cloud or past the repo's test selection.

A review agent's brief already forbids a live cloud call, a change to the project or proxy variables and a test run
wider than the repo's own; this hook refuses the forms of those that show in the command's own words, so an honest
reviewer's slip stops before it runs. It is a backstop for the brief, not a barrier against a reviewer working around
it: the brief stays the rule.

It applies only when the hook input's `agent_type` names one of this collection's review agents (`agents/*.md`), bare
(`correctness-reviewer`) or plugin-scoped (`<plugin>:correctness-reviewer`); every other call passes through untouched,
and the GCP spend guard (guard.py) keeps applying to everyone as before.

It reads the Bash command split into words the way the shell would (shlex), across `;`, `&&`, `||`, `|`, `&`, newlines,
`( )` subshells, `$( )` and backtick substitutions outside single quotes (double-quoted too), `bash -c`, `eval`, `env -S`, a heredoc fed to a
shell, and the wrappers `env`, `sudo`, `command`, `exec`, `timeout`, `nice`, `nohup`, `time`, `stdbuf`, `setsid`,
`ionice` and `xargs`. It never matches a substring over the whole text, so a command that only mentions a name (a
`grep`, `git log -S`, `cat`, an `echo`, a heredoc written to a file) passes.

It refuses:
- a cloud CLI as the command word: `gcloud`, `bq`, `gsutil`;
- a Google API host (`*.googleapis.com`) in a word given to any program but a text tool (grep, rg, git, cat, sed, echo,
  jq, gh, ...): `curl https://...`, `python3 -c "...urlopen('https://...')"`;
- a pytest run that widens the repo's selection: `-m`, `-o`/`--override-ini`, `-p no:<plugin>`, `-c`/`--config-file`
  or `--noconftest`, in any spelling (`-oaddopts=`, `--override-ini=addopts=`, `-qm live`), and setting
  `PYTEST_ADDOPTS`; and `make check` / `make test`;
- setting, emptying, unsetting or un-exporting a project or proxy variable (a name holding `GCP_PROJECT`, `CLOUDSDK_*`,
  `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, any case): `NAME=...` before a command or alone, `export`,
  `declare`/`typeset`/`local`/`readonly`, `unset`, `export -n`, `declare +x`, `read NAME`, `printf -v NAME`, `for NAME in`,
  `env -u NAME`, and clearing the whole environment (`env -i`, `exec -c`).

It does not catch, by design:
- a name built at run time: a variable (`$tool`), `eval` of one, encoded or concatenated text, a script written to a
  file and run later, `source`, text piped into a shell (`echo ... | bash`);
- a heredoc or stdin fed to a program other than a shell (`python3 - <<EOF` holding a host): a heredoc is read as text,
  so a reviewer can pipe sample hook JSON naming a host into a guard under review;
- a library call inside code the reviewer runs but did not write (a test, a repo script, `make lint`), and any program
  that reaches Google by another host or by an address it computes;
- a cloud CLI given as an argument to a program other than the wrappers above (`find -exec`, `docker run ... gcloud`);
- a reviewer that is not one of this collection's agents.

Reads the hook's JSON on stdin; prints a deny decision on stdout or nothing. It writes no log: the refusal goes only to
the reviewer, as the hook's message.
Tests: uvx --from pytest==8.4.2 pytest -q cloud/gcp/tests
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

# The `name:` of each agent under agents/; a test keeps this set equal to that folder.
REVIEW_AGENTS = frozenset(
    {
        "claims-auditor",
        "control-prober",
        "correctness-reviewer",
        "finding-auditor",
        "finding-verifier",
        "guardrail-reviewer",
        "handoff-auditor",
        "leak-hunter",
    }
)

CLOUD_CLIS = {"gcloud", "bq", "gsutil"}
HOST = re.compile(r"googleapis\.com", re.IGNORECASE)
# Programs that only read or write text: a Google API host in their words is a mention, not a request.
TEXT_TOOLS = {
    "grep", "egrep", "fgrep", "rg", "ag", "git", "cat", "bat", "less", "more", "head", "tail", "sed", "awk", "gawk",
    "cut", "sort", "uniq", "wc", "tr", "diff", "cmp", "comm", "paste", "column", "nl", "fold", "echo", "printf", "tee",
    "jq", "yq", "find", "ls", "file", "stat", "test", "[", "true", "false", ":", "gh", "basename", "dirname",
    "realpath", "printenv", "mkdir", "touch", "cp", "mv", "ln", "rm", "chmod",
}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
PYTHON = re.compile(r"python[0-9.]*")
RUNNERS = {"uv", "uvx", "poetry", "pdm", "hatch", "pipx", "rye", "coverage"}
PYTEST = {"pytest", "py.test"}
WATCHED = re.compile(r"[A-Za-z0-9_]*GCP_PROJECT[A-Za-z0-9_]*|CLOUDSDK_[A-Za-z0-9_]*|(?i:(?:https?|all|no)_proxy)")
ASSIGN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[[^]]*\])?\+?=.*", re.DOTALL)
KEYWORDS = {"if", "then", "elif", "else", "do", "while", "until", "!", "{", "}", "fi", "done"}
SEPARATORS = set(";&|()\n")
# Wrappers that run the command after their options, and the options of each that take a separate value.
WRAPPERS = {
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T", "--user", "--group"},
    "command": set(),
    "exec": {"-a"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "nice": {"-n", "--adjustment"},
    "nohup": set(),
    "time": {"-f", "-o", "--format", "--output"},
    "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
    "setsid": set(),
    "ionice": {"-c", "-n", "-p", "--class", "--classdata"},
    "xargs": {"-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a", "--max-args", "--max-procs", "--delimiter",
              "--arg-file", "--replace"},
}
HEREDOC = re.compile(r"<<(?!<)(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
# On text the guard cannot split into words: the names whose mention is refused.
UNPARSED = re.compile(r"\b(gcloud|bq|gsutil|pytest)\b")
MAX_DEPTH = 4

REFUSAL = (
    "Reviewer guard: refused {what}. Your brief forbids it: a reviewer makes no live cloud call, read or write, leaves"
    " the project and proxy variables as the session set them, and runs the repo's tests with the repo's own selection"
    " (`uv run pytest <paths>`, not `make check` or a flag that widens it). Report the check as `unverified`, naming"
    " this refusal; do not route around it."
)


def review_agent(event: dict) -> bool:
    """Whether the hook fired in one of this collection's review agents, named bare or plugin-scoped."""
    kind = event.get("agent_type")
    return isinstance(kind, str) and kind.rsplit(":", 1)[-1] in REVIEW_AGENTS


def tokenize(text: str) -> list[str] | None:
    lex = shlex.shlex(text, posix=True, punctuation_chars=";&|()\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = "#"
    try:
        return list(lex)
    except ValueError:
        return None


def segments(tokens: list[str]) -> list[list[str]]:
    out: list[list[str]] = []
    cur: list[str] = []
    for t in tokens:
        if set(t) <= SEPARATORS:
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        out.append(cur)
    return out


def substitutions(text: str) -> list[str]:
    """The bodies of `$( )` and backtick substitutions outside single quotes, double-quoted ones included."""
    out, i, quote, n = [], 0, None, len(text)
    while i < n:
        c = text[i]
        if quote == "'":
            quote = None if c == "'" else quote
            i += 1
        elif c == "\\":
            i += 2
        elif c == "'" and quote is None:
            quote, i = "'", i + 1
        elif c == '"':
            quote, i = (None if quote == '"' else '"'), i + 1
        elif c == "$" and text.startswith("(", i + 1) and not text.startswith("((", i + 1):
            depth, j = 1, i + 2
            while j < n and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            out.append(text[i + 2 : j - 1])
            i = j
        elif c == "`":
            j = text.find("`", i + 1)
            if j < 0:
                break
            out.append(text[i + 1 : j])
            i = j + 1
        else:
            i += 1
    return out


def split_heredocs(command: str) -> tuple[str, list[tuple[str, str, bool]]]:
    """The command without its heredoc bodies, and each body with the line that feeds it and whether the shell
    expands it (an unquoted delimiter: its `$( )` substitutions run)."""
    lines, kept, bodies, i = command.split("\n"), [], [], 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        for m in HEREDOC.finditer(line):
            strip, delim, body = m.group(1) == "-", m.group(3), []
            while i < len(lines) and (lines[i].lstrip("\t") if strip else lines[i]) != delim:
                body.append(lines[i])
                i += 1
            i += 1
            bodies.append((line, "\n".join(body), m.group(2) == ""))
    return "\n".join(kept), bodies


def watched(name: str) -> bool:
    return bool(WATCHED.fullmatch(name))


def resolve(seg: list[str], depth: int) -> tuple[str | None, str | None, list[str]]:
    """(a refusal found before the command word, the command word's name, its arguments)."""
    i = 0
    while i < len(seg):
        t = seg[i]
        m = ASSIGN.fullmatch(t)
        if m:
            if watched(m.group(1)):
                return f"setting `{m.group(1)}`", None, []
            if m.group(1) == "PYTEST_ADDOPTS":
                return "setting `PYTEST_ADDOPTS`, which widens the repo's test selection", None, []
            i += 1
            continue
        if t in KEYWORDS:
            i += 1
            continue
        name = os.path.basename(t.lstrip("`"))
        if name not in WRAPPERS:
            return None, name, seg[i + 1 :]
        takes_value = WRAPPERS[name]
        i += 1
        while i < len(seg) and (seg[i].startswith("-") and seg[i] != "-" or name == "env" and seg[i] == "-"):
            opt = seg[i]
            if opt == "--":
                i += 1
                break
            key, _, inline = opt.partition("=")
            value = inline if "=" in opt else None
            if value is None and key in takes_value:
                value = seg[i + 1] if i + 1 < len(seg) else ""
                i += 1
            elif value is None and len(key) > 2 and not key.startswith("--") and key[:2] in takes_value:
                value = key[2:]  # `-uNAME`
                key = key[:2]
            i += 1
            if name == "env":
                if key in ("-i", "-", "--ignore-environment"):
                    return "clearing the environment (`env -i`), which empties the project and proxy variables", None, []
                if key in ("-u", "--unset") and value and watched(value):
                    return f"unsetting `{value}`", None, []
                if key in ("-S", "--split-string") and value:
                    reason = check(value, depth + 1)
                    if reason:
                        return reason, None, []
            elif name == "exec" and "c" in key.lstrip("-") and not key.startswith("--"):
                return "clearing the environment (`exec -c`), which empties the project and proxy variables", None, []
            elif name == "command" and key in ("-v", "-V"):
                return None, None, []  # a lookup, not a run
        if name == "timeout" and i < len(seg):
            i += 1  # the duration
    return None, None, []


def pytest_args(name: str, args: list[str]) -> list[str] | None:
    """pytest's own arguments when this command runs pytest, else None."""
    if name in PYTEST:
        return args
    if PYTHON.fullmatch(name) or name in RUNNERS:
        for j, a in enumerate(args):
            if a in ("-m", "--module") and args[j + 1 : j + 2] and args[j + 1] in PYTEST:
                return args[j + 2 :]
            if os.path.basename(a) in PYTEST:
                return args[j + 1 :]
    return None


NOARG_SHORT = set("qvsxlh")


def widening(pargs: list[str]) -> str | None:
    """The pytest option that widens the repo's selection, if any."""
    for j, a in enumerate(pargs):
        if a == "--":
            break
        if a.startswith("--"):
            key = a.split("=", 1)[0]
            for prefix, full in (("--override", "--override-ini"), ("--config-f", "--config-file"),
                                 ("--noconf", "--noconftest")):
                if key.startswith(prefix):
                    return f"pytest's `{full}`"
            continue
        if not a.startswith("-") or a == "-":
            continue
        for k, c in enumerate(a[1:]):
            if c in "moc":
                return f"pytest's `-{c}`"
            if c == "p":
                value = a[k + 2 :] or (pargs[j + 1] if j + 1 < len(pargs) else "")
                if value.startswith("no:"):
                    return "pytest's `-p no:`"
                break
            if c not in NOARG_SHORT:
                break
    return None


MAKE_VALUE_OPTS = {"-C", "-f", "-j", "-I", "-o", "-W", "-l", "--directory", "--file", "--makefile"}


def make_target(args: list[str]) -> str | None:
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in MAKE_VALUE_OPTS:
            skip = True
            continue
        if a.startswith("-") or "=" in a:
            continue
        if a in ("check", "test"):
            return a
    return None


def variable_command(name: str, args: list[str]) -> str | None:
    """A builtin that sets, empties, unsets or un-exports a watched variable."""
    if name == "unset":
        hit = next((a for a in args if not a.startswith("-") and watched(a)), None)
        return f"unsetting `{hit}`" if hit else None
    if name in ("export", "declare", "typeset", "local", "readonly"):
        unexport = any(a.startswith("-") and "n" in a for a in args) if name == "export" else any(
            a.startswith("+") and "x" in a for a in args
        )
        for a in args:
            m = ASSIGN.fullmatch(a)
            if m and watched(m.group(1)):
                return f"setting `{m.group(1)}`"
            if m and m.group(1) == "PYTEST_ADDOPTS":
                return "setting `PYTEST_ADDOPTS`, which widens the repo's test selection"
            if unexport and watched(a):
                return f"un-exporting `{a}`"
        return None
    if name == "for" and args and watched(args[0]):
        return f"setting `{args[0]}` as a loop variable"
    if name == "read":
        hit = next((a for a in args if watched(a)), None)
        return f"setting `{hit}` with `read`" if hit else None
    if name == "printf":
        for j, a in enumerate(args):
            if a == "-v" and j + 1 < len(args) and watched(args[j + 1]):
                return f"setting `{args[j + 1]}` with `printf -v`"
            if a.startswith("-v") and len(a) > 2 and watched(a[2:]):
                return f"setting `{a[2:]}` with `printf -v`"
    return None


def shell_script(args: list[str]) -> str | None:
    """The command string a shell is given with `-c` (`bash -c`, `bash -lc`, `sh -ec`)."""
    seen_c = False
    for a in args:
        if not seen_c:
            if a.startswith("-") and not a.startswith("--") and "c" in a[1:]:
                seen_c = True
            elif not a.startswith("-"):
                return None  # a script file
        elif not a.startswith("-"):
            return a
    return None


def check_segment(seg: list[str], depth: int) -> str | None:
    reason, name, args = resolve(seg, depth)
    if reason or not name:
        return reason
    if name in CLOUD_CLIS:
        return f"a `{name}` command"
    if reason := variable_command(name, args):
        return reason
    pargs = pytest_args(name, args)
    if pargs is not None and (reason := widening(pargs)):
        return f"{reason}, which widens the repo's test selection"
    if name in ("make", "gmake") and (target := make_target(args)):
        return f"`make {target}`, which runs the repo's whole suite with its live tests' settings"
    if name in SHELLS and (script := shell_script(args)) is not None:
        return check(script, depth + 1)
    if name == "eval":
        return check(" ".join(args), depth + 1)
    if name not in TEXT_TOOLS and any(HOST.search(w) for w in [name, *args]):
        return f"a Google API host in a `{name}` command"
    return None


def heredoc_program(line: str) -> str | None:
    """The command word of the segment on `line` that holds a heredoc's `<<`."""
    tokens = tokenize(line)
    if tokens is None:
        return None
    for seg in segments(tokens):
        if any(t.startswith("<<") and not t.startswith("<<<") for t in seg):
            _, name, _ = resolve(seg, MAX_DEPTH)
            return name
    return None


def check(command: str, depth: int = 0) -> str | None:
    """Why a review agent may not run `command`, or None."""
    if depth > MAX_DEPTH:
        return None
    text, bodies = split_heredocs(command)
    for line, body, expands in bodies:
        for inner in substitutions(body) if expands else []:
            if reason := check(inner, depth + 1):
                return reason
        if heredoc_program(line) in SHELLS and (reason := check(body, depth + 1)):
            return reason
    for inner in substitutions(text):
        if reason := check(inner, depth + 1):
            return reason
    tokens = tokenize(text)
    if tokens is None:
        m = UNPARSED.search(text)
        return f"a command this guard cannot split into words that names `{m.group(0)}`" if m else None
    for seg in segments(tokens):
        if reason := check_segment(seg, depth):
            return reason
    return None


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
    except (ValueError, RecursionError):
        return 0
    if not isinstance(event, dict) or event.get("tool_name") != "Bash" or not review_agent(event):
        return 0
    command = (event.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str):
        return 0
    try:
        reason = check(command)
    except Exception as exc:  # noqa: BLE001 -- a guard bug must not wave a named form through
        m = UNPARSED.search(command)
        reason = f"a command naming `{m.group(0)}` that this guard failed on ({type(exc).__name__})" if m else None
    if reason:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": REFUSAL.format(what=reason),
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
