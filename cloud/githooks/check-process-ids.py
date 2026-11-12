#!/usr/bin/env python3
"""Fails when a commit adds a process id to a checked-in file (RULES.md, ways/finished.md).

A process id is a reference into the work's history: an issue or PR reference (a bare hash and number,
"issue" or "PR" and a number, a link to this repo's own tracker), a phase, stage, milestone, sprint or
epic number used as a work label, or a decision-record id (an ADR number anywhere; a register-style id
such as a letter and a number where it is cited: inside parentheses, after "see" or "per", after a
plan file's name, or opening a comment). The reference belongs in the commit message or the PR.
In a repo whose CLAUDE.md or AGENTS.md opts in to the ways of working, a new documentation file named
as a plan, roadmap, ledger, lessons or decision record fails too: that content lives on the tracker.

By default it checks only the lines the staged commit adds, so ids already in the tree never block
unrelated work; --range A..B checks the lines a range adds, --all audits every tracked file.
Never checked: binary files, lockfiles, vendored and minified files, files marked generated in their
first lines, and history files (a ledger, a changelog). The hash pattern skips stylesheets and SVG,
and a hex colour in a colour context. Standards (UTF, SHA, ISO, RFC, HTTP and the like) never count.
A repo lists the tokens it defines (product codes, fixture keys) in `.process-ids` at its root, one
case-sensitive glob per line, with `path: <glob>` lines for paths to skip (`*` crosses folders) and
`names: on|off` to force the file-name rule; a line carrying `ref-ok` is exempt (a test fixture).
The pre-commit hook of the repos a cloud session works on (cloud/githooks/pre-commit) runs it, and so
does this repo's own.
Usage: check-process-ids.py [--all | --range A..B] [repo-dir]
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

LOCKFILES = {
    "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "uv.lock",
    "poetry.lock", "pdm.lock", "Pipfile.lock", "Cargo.lock", "Gemfile.lock", "composer.lock", "go.sum",
    "flake.lock", "mix.lock", "pubspec.lock", "Podfile.lock", "packages.lock.json",
}
VENDORED = {"node_modules", "vendor", "vendored", "third_party", "third-party", ".yarn", "generated",
            "__generated__", "__snapshots__"}
GENERATED_SUFFIXES = (".min.js", ".min.css", ".map", "_pb2.py", "_pb2.pyi", ".pb.go", ".snap")
GENERATED_MARK = re.compile(r"@generated|DO NOT EDIT|[Cc]ode generated|[Aa]uto-?generated")
HISTORY = re.compile(r"(^|/)(LEDGER(\.md)?|ledger\.d/.*|(CHANGELOG|CHANGES|HISTORY|NEWS)[^/]*)$")
STYLE_SUFFIXES = {".css", ".scss", ".sass", ".less", ".styl", ".svg"}
DOC_SUFFIXES = {".md", ".markdown", ".mdx", ".rst", ".txt", ".adoc", ".org", ".html"}

# Standards and well-known tokens a register-style id would otherwise match.
STANDARD_PREFIXES = {
    "UTF", "UCS", "SHA", "MD", "ISO", "IEC", "IEEE", "RFC", "HTTP", "TLS", "SSL", "CVE", "CWE", "GHSA",
    "AES", "DES", "RSA", "EC", "ES", "PEP", "ECMA", "UTC", "GMT", "CP", "WIN", "KOI", "DDR", "USB",
    "IPV", "GPT", "PCI", "ANSI", "ASCII", "NIST", "OWASP", "CIS", "SOC", "PCIDSS", "HL", "IP", "TCP",
    "UDP", "BASE", "X", "H", "MPEG", "OAUTH", "OIDC", "JWT", "SAML", "IETF", "W", "LTS", "FIPS", "ITU",
    "KEP", "JEP", "JSR", "EIP", "BIP", "ERC", "WCAG",
}
STANDARD_TOKENS = {"S3", "EC2", "K8s", "K3s", "D3", "P2P", "Q1", "Q2", "Q3", "Q4", "P50", "P75", "P90",
                   "P95", "P99", "P999", "H1", "H2", "H3", "H4", "H5", "H6", "A3", "A4", "A5", "G1", "I2C",
                   "L1", "L2", "L3", "L4", "L7", "P256", "P384", "P521", "P-192", "P-224", "P-256", "P-384", "P-521",
                   "C4", "CC0", "WSL2", "E2E",
                   *(f"F{n}" for n in range(1, 13))}

ISSUE_HASH = re.compile(r"(?<![\w&{$#/.\\'-])#(\d{1,6})(?![\w-])")
ISSUE_WORD = re.compile(r"(?i:\b(?:issues?|tickets?|pull requests?|merge requests?)\s*(?:#|no\.\s*)?\d+\b)"
                        r"|\b(?:PRs?|MRs?)\s*#?\d+\b")
WORK_LABEL = re.compile(r"(?i)(?<![a-z])(?:phase|stage|milestone|sprint|epic)[ _-]?\d+[a-z]?(?![a-z0-9])")
DECISION = re.compile(r"(?i)\b(?:ADRs?|MADR|RFD)[ _-]?\d+\b|\bdecision(?: record)? #?\d+\b")
REGISTER = re.compile(r"(?<![\w./-])[A-Z]{1,4}(?:-\d{1,4}|\d{1,4})[a-z]?(?![\w-]|\.\d)")
CITE_BEFORE = re.compile(r"(?:\(\s*|[,;]\s*|\b(?:see|per|cf\.?)\s+|\.md\s+|§\s*|^\s*(?:#|//|--|/?\*)\s*)$",
                         re.IGNORECASE)
CITE_AFTER = re.compile(r"^\s*(?:[),;:]|and\b|or\b|$)")
COLOUR_CONTEXT = re.compile(r"(?i)\b(?:colou?r|fill|stroke|background|border|gradient|shadow|outline|"
                            r"stop-color|theme|palette|hex)\b|#[0-9a-f]*[a-f][0-9a-f]*\b")
RECORD_WORDS = {"plan", "plans", "roadmap", "ledger", "lessons", "decisions", "decision", "adr", "adrs",
                "progress", "backlog", "milestones", "todo"}
RECORD_DIRS = {"adr", "adrs", "decisions", "decision-records", "decision-log", "ledger.d", "lessons",
               "plans", "roadmap"}
OPT_IN = re.compile(r"(?im)^\W*ways of working\b.*\]\([^)]*\bways\b")

HINT_IDS = ("check-process-ids: name the work for what it does (its behaviour, its reason) and put the issue, "
            "PR, phase or decision reference in the commit message or the PR body. A token this repo defines "
            "goes in .process-ids; a test fixture's line takes ref-ok.")
HINT_NAMES = ("check-process-ids: keep the roadmap, plan, progress, lessons and decisions on the tracker "
              "(epics and sub-issues, a decision weighed on its issue); the architecture document holds the "
              "current design and each choice's reason (ways/finished.md).")


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=cwd, capture_output=True,
                          text=True, check=True, errors="replace").stdout


class Config:
    def __init__(self, root: Path) -> None:
        self.tokens: list[str] = []
        self.paths: list[str] = []
        self.names: bool | None = None
        f = root / ".process-ids"
        lines = f.read_text(errors="replace").splitlines() if f.is_file() else []
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("path:"):
                self.paths.append(line[5:].strip())
            elif line.startswith("names:"):
                self.names = line[6:].strip().lower() == "on"
            else:
                self.tokens.append(line)
        if self.names is None:
            text = "".join((root / n).read_text(errors="replace") for n in ("CLAUDE.md", "AGENTS.md")
                           if (root / n).is_file())
            self.names = bool(OPT_IN.search(text))

    def allowed(self, token: str) -> bool:
        return any(fnmatch.fnmatchcase(token, p) for p in self.tokens)

    def skipped(self, path: str) -> bool:
        return any(fnmatch.fnmatchcase(path, p) for p in self.paths)


def skipped_path(path: str, history: bool = True) -> bool:
    p = PurePosixPath(path)
    return (p.name in LOCKFILES or p.suffix == ".lock" or bool(VENDORED & set(p.parts[:-1]))
            or p.name.endswith(GENERATED_SUFFIXES) or p.parts[0] == ".pr-images"
            or (history and bool(HISTORY.search(path))))


def own_tracker(root: Path) -> re.Pattern[str]:
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root, capture_output=True,
                         text=True).stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    own = rf"github\.com/{re.escape(m.group(1))}/{re.escape(m.group(2))}" if m else r"(?!x)x"
    return re.compile(rf"(?i)(?:{own}|\.\./\.\.)/(?:issues|pull|pulls|discussions)/\d+")


def register_hits(line: str) -> list[str]:
    hits = []
    for m in REGISTER.finditer(line):
        tok = m.group(0)
        prefix = re.match(r"[A-Z]+", tok).group(0)  # type: ignore[union-attr]
        if prefix in STANDARD_PREFIXES or tok in STANDARD_TOKENS:
            continue
        before, after = line[: m.start()], line[m.end():]
        opened = before.rfind("(")
        in_parens = opened > before.rfind(")")
        # A citation's parenthesis follows a space, as in prose; a call's or a shell expansion's does not.
        if in_parens and (opened > 0 and not before[opened - 1].isspace() or before.endswith("((")):
            continue
        if not CITE_AFTER.match(after) and not re.search(r"(?i)\b(?:see|per|cf\.?)\s+$", before):
            continue
        if re.search(r"[,;]\s*$", before) and not in_parens:
            continue
        if CITE_BEFORE.search(before):
            hits.append(tok)
    return hits


def scan_line(line: str, path: str, tracker: re.Pattern[str]) -> list[str]:
    if "ref-ok" in line:
        return []
    hits: list[str] = []
    if PurePosixPath(path).suffix.lower() not in STYLE_SUFFIXES:
        for m in ISSUE_HASH.finditer(line):
            digits = m.group(1)
            colour = len(digits) in (3, 4, 6, 8) and (
                COLOUR_CONTEXT.search(line) or re.search(r"[:=\"']\s*$", line[: m.start()]))
            if not colour:
                hits.append(m.group(0))
    hits += [m.group(0) for m in ISSUE_WORD.finditer(line)]
    hits += [m.group(0) for m in tracker.finditer(line)]
    docker = re.match(r"(?i)(.*\.)?(docker|container)file(\..*)?$", PurePosixPath(path).name)
    hits += [m.group(0) for m in WORK_LABEL.finditer(line)
             if not (docker and m.group(0).lower().startswith("stage"))]  # a multi-stage build's stages
    hits += [m.group(0) for m in DECISION.finditer(line)]
    hits += register_hits(line)
    return hits


def scan_name(path: str, tracker: re.Pattern[str], names: bool) -> list[str]:
    hits = []
    for part in PurePosixPath(path).parts:
        spaced = re.sub(r"[_]", " ", part)
        hits += [m.group(0) for m in WORK_LABEL.finditer(spaced)]
        hits += [m.group(0) for m in DECISION.finditer(spaced)]
        hits += [m.group(0) for m in re.finditer(r"(?i)\b(?:issue|pr|pull)[ -]?\d+\b|#\d+", spaced)]
    p = PurePosixPath(path)
    if names and (p.suffix.lower() in DOC_SUFFIXES or p.suffix == ""):
        words = set(re.split(r"[-_. ]+", p.stem.lower()))
        dirs = {d.lower() for d in p.parts[:-1]}
        if words & RECORD_WORDS or dirs & RECORD_DIRS:
            hits.append(f"record file {p.name}")
    return hits


def blob_head(root: Path, rev: str, path: str) -> str:
    try:
        if rev == "worktree":
            with open(root / path, encoding="utf-8", errors="replace") as fh:
                return "".join(fh.readline() for _ in range(5))
        out = subprocess.run(["git", "show", f"{rev}{path}"], cwd=root, capture_output=True).stdout
        return b"\n".join(out.split(b"\n")[:5]).decode("utf-8", "replace")
    except OSError:
        return ""


def added_lines(root: Path, diff_args: list[str]) -> dict[str, list[tuple[int, str]]]:
    out = git("diff", "-U0", "--no-color", "--no-ext-diff", "--diff-filter=ACMR", "--src-prefix=a/",
              "--dst-prefix=b/", *diff_args, cwd=root)
    files: dict[str, list[tuple[int, str]]] = {}
    cur, n = None, 0
    for line in out.splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
            if cur is not None:
                files.setdefault(cur, [])
        elif line.startswith("@@ "):
            m = re.match(r"@@ -\S+ \+(\d+)", line)
            n = int(m.group(1)) if m else 0
        elif line.startswith("+") and cur is not None:
            files[cur].append((n, line[1:]))
            n += 1
    return files


def tracked_lines(root: Path) -> dict[str, list[tuple[int, str]]]:
    files = {}
    for path in git("ls-files", cwd=root).splitlines():
        f = root / path
        if not f.is_file():
            continue
        data = f.read_bytes()
        if b"\0" in data[:8000]:
            continue
        files[path] = list(enumerate(data.decode("utf-8", "replace").splitlines(), 1))
    return files


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--all", action="store_true", help="audit every tracked file")
    mode.add_argument("--range", metavar="A..B", help="check the lines a commit range adds")
    ap.add_argument("repo", nargs="?", default=".")
    args = ap.parse_args(argv)
    root = Path(git("rev-parse", "--show-toplevel", cwd=Path(args.repo)).strip())
    cfg, tracker = Config(root), own_tracker(root)

    if args.all:
        files, new = tracked_lines(root), git("ls-files", cwd=root).splitlines()
        rev, scope = "worktree", "tracked files"
    elif args.range:
        a, _, b = args.range.partition("..")
        b = b or "HEAD"
        files = added_lines(root, [a, b])
        new = git("diff", "--name-only", "--diff-filter=AR", a, b, cwd=root).splitlines()
        rev, scope = f"{b}:", f"the lines {args.range} adds"
    else:
        files = added_lines(root, ["--cached"])
        new = git("diff", "--cached", "--name-only", "--diff-filter=AR", cwd=root).splitlines()
        rev, scope = ":", "the staged changes"

    found_ids = found_names = 0
    for path in sorted(files):
        if skipped_path(path) or cfg.skipped(path) or not files[path]:
            continue
        if GENERATED_MARK.search(blob_head(root, rev, path)):
            continue
        for n, text in files[path]:
            hits = [h for h in scan_line(text, path, tracker) if not cfg.allowed(h)]
            if hits:
                found_ids += 1
                print(f"{path}:{n}: [{', '.join(dict.fromkeys(hits))}] {text.strip()[:160]}")
    for path in sorted(new):
        if cfg.skipped(path) or skipped_path(path, history=False):
            continue
        hits = [h for h in scan_name(path, tracker, bool(cfg.names)) if not cfg.allowed(h)]
        if HISTORY.search(path):  # a ledger or changelog may carry ids; only the record-file rule applies
            hits = [h for h in hits if h.startswith("record file")]
        for h in dict.fromkeys(hits):
            if h.startswith("record file"):
                found_names += 1
            else:
                found_ids += 1
            print(f"{path}: [{h}] file name")
    if found_ids:
        print(HINT_IDS, file=sys.stderr)
    if found_names:
        print(HINT_NAMES, file=sys.stderr)
    if found_ids or found_names:
        return 1
    print(f"check-process-ids: {scope}, no process id" + (", no record file" if cfg.names else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
