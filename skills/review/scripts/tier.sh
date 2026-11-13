#!/usr/bin/env bash
# Prints the review tier a change's paths call for: one line `routine`, `standard` or `sensitive`, then the
# changed paths that decided it (a sensitive path with the lenses REVIEW.md names for it).
#
# Usage: tier.sh [--base <ref>] [--head <ref>]
#   --base defaults to the remote's default branch (origin/HEAD, else origin/main or origin/master);
#   --head defaults to HEAD. The changed paths are `git diff --name-only --no-renames
#   $(git merge-base <base> <head>) <head>`: a rename lists both its old and its new path.
#
# Rules, highest tier among the changed paths wins; an empty diff is an error (exit 2):
# - sensitive: a built-in floor that always applies (CLAUDE.md, AGENTS.md, REVIEW.md and RULES.md at any depth,
#   .claude/**, .githooks/**, **/hooks/**, **/githooks/**, .github/workflows/**), plus the globs under
#   `## Sensitive` in REVIEW.md; a line there may end with `; lenses: a, b`.
# - routine: the globs under `## Routine` in REVIEW.md; with no such list, **/*.md, **/*.txt and licence files.
# - standard: everything else.
# REVIEW.md (repo root) is read from the base, never from the change, so a change cannot lower its own tier.
# REVIEW.md lists globs in backticks, one or more per `- ` line. A glob without a slash matches the file name
# at any depth; `**` spans folders, `*` and `?` stay within one. A REVIEW.md this script cannot parse makes
# every path sensitive, with a warning on stderr.
set -euo pipefail
exec python3 - "$@" <<'EOF'
import argparse, re, subprocess, sys

FLOOR = ["CLAUDE.md", "AGENTS.md", "REVIEW.md", "RULES.md", ".claude/**", ".githooks/**", "**/hooks/**",
         "**/githooks/**", ".github/workflows/**"]
DEFAULT_ROUTINE = ["*.md", "*.txt", "LICENSE*", "LICENCE*", "COPYING*"]
RANK = {"routine": 0, "standard": 1, "sensitive": 2}


def git(*args):
    done = subprocess.run(["git", *args], capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


def default_base():
    try:
        return git("symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD").strip()
    except RuntimeError:
        for c in ("origin/main", "origin/master"):
            if subprocess.run(["git", "rev-parse", "-q", "--verify", c], capture_output=True).returncode == 0:
                return c
    sys.exit("tier.sh: cannot tell the remote's default branch: pass --base, or run `git remote set-head origin --auto`")


def glob_re(g):
    if "/" not in g.rstrip("/"):
        g = "**/" + g
    out, i = "", 0
    while i < len(g):
        if g.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif g.startswith("**", i):
            out, i = out + ".*", i + 2
        elif g[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif g[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(g[i]), i + 1
    return re.compile(out + "$")


class Unparsable(Exception):
    pass


def parse(text):
    """{'sensitive': [(glob, lenses)], 'routine': [glob] or None}."""
    lists, section, seen = {"sensitive": [], "routine": None}, None, set()
    for n, line in enumerate(text.splitlines(), 1):
        h = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if h:
            name = h.group(2).strip().lower()
            if len(h.group(1)) == 2 and name in ("sensitive", "routine"):
                if name in seen:
                    raise Unparsable(f"line {n}: a second `## {h.group(2)}`")
                seen.add(name)
                section = name
                if name == "routine":
                    lists["routine"] = []
            else:
                section = None
            continue
        if section is None or not line.strip():
            continue
        item = re.match(r"^\s*[-*]\s+(.*)$", line)
        if not item:
            raise Unparsable(f"line {n}: under `## {section.title()}` every line is a `- ` item")
        rest, lenses = item.group(1), ""
        m = re.search(r";\s*lenses:\s*(.+?)\s*$", rest)
        if m:
            if section != "sensitive":
                raise Unparsable(f"line {n}: lenses belong to sensitive globs")
            rest, lenses = rest[: m.start()], m.group(1)
        globs = re.findall(r"`([^`]+)`", rest)
        if not globs or re.sub(r"`[^`]+`", "", rest).strip(" ,"):
            raise Unparsable(f"line {n}: an item is backticked globs (and optionally `; lenses: a, b`)")
        for g in globs:
            if g.strip() != g or g.startswith("/") or "\\" in g:
                raise Unparsable(f"line {n}: `{g}` is not a glob this script reads")
            if section == "sensitive":
                lists["sensitive"].append((g, lenses))
            else:
                lists["routine"].append(g)
    return lists


def main():
    p = argparse.ArgumentParser(prog="tier.sh")
    p.add_argument("--base")
    p.add_argument("--head", default="HEAD")
    a = p.parse_args()
    base = a.base or default_base()
    try:
        mb = git("merge-base", base, a.head).strip()
        paths = [x for x in git("diff", "--name-only", "--no-renames", mb, a.head).splitlines() if x]
    except RuntimeError as exc:
        sys.exit(f"tier.sh: {exc}")
    if not paths:
        print(f"tier.sh: {a.head} changes nothing against {base}", file=sys.stderr)
        sys.exit(2)
    rules, broken = {"sensitive": [], "routine": None}, None
    shown = subprocess.run(["git", "show", f"{base}:REVIEW.md"], capture_output=True, text=True)
    if shown.returncode == 0:
        try:
            rules = parse(shown.stdout)
        except Unparsable as exc:
            broken = str(exc)
            print(f"tier.sh: warning: REVIEW.md on {base} cannot be parsed ({broken}): every path counts as sensitive",
                  file=sys.stderr)
    sensitive = [(glob_re(g), "") for g in FLOOR] + [(glob_re(g), l) for g, l in rules["sensitive"]]
    routine = [glob_re(g) for g in (rules["routine"] if rules["routine"] is not None else DEFAULT_ROUTINE)]
    tiers = {}
    for path in paths:
        hits = [l for r, l in sensitive if r.match(path)]
        if broken or hits:
            lenses = sorted({x.strip() for l in hits for x in l.split(",") if x.strip()})
            tiers[path] = ("sensitive", lenses)
        elif any(r.match(path) for r in routine):
            tiers[path] = ("routine", [])
        else:
            tiers[path] = ("standard", [])
    top = max((t for t, _ in tiers.values()), key=RANK.get)
    print(top)
    for path, (t, lenses) in tiers.items():
        if t == top:
            print(f"{path} (lenses: {', '.join(lenses)})" if lenses else path)


main()
EOF
