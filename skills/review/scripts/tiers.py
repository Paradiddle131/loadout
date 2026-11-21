#!/usr/bin/env python3
"""The review tier of a change's paths, and the REVIEW.md parser tier.sh and plan.py share (tier.sh has the rules).

  tiers.py [--base <ref>] [--head <ref>]   what tier.sh runs: prints the tier, then the paths that decided it.

plan.py imports it: `changed` lists a change's paths, `load_rules` reads REVIEW.md at a ref (an unparsable one is
`broken`: every path sensitive, no clause read), and `rate` gives each path its tier, its lenses and the depth and
effort clauses of every REVIEW.md line that matches it.
"""

from __future__ import annotations

import argparse
import posixpath
import re
import subprocess
import sys

# File names matched at any depth and in any case; the instruction files among them are read for imports.
FLOOR_NAMES = ["CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "GEMINI.md", "REVIEW.md", "RULES.md", "SKILL.md",
               ".mcp.json", "CODEOWNERS"]
INSTRUCTION = {n.lower() for n in FLOOR_NAMES if n.endswith(".md")}
FLOOR = ["**/.claude/**", "**/.githooks/**", "**/.husky/**", "**/hooks/**", "**/githooks/**",
         ".github/workflows/**", ".github/actions/**", "docs/agents/**"]
IMPORT_DEPTH, IMPORT_FILES = 5, 500
DEFAULT_ROUTINE = ["*.md", "*.txt", "LICENSE*", "LICENCE*", "COPYING*"]
RANK = {"routine": 0, "standard": 1, "sensitive": 2}
DEPTHS = ("none", "light", "focused", "full")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
SECTIONS = ("sensitive", "routine", "paths")


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


def glob_re(g, icase=False):
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
    return re.compile(out + "$", re.IGNORECASE if icase else 0)


IMPORT = re.compile(r"(?:^|(?<=\s))@([^\s`'\"()<>\[\]{}]+)")


def imports(base):
    """{path: importer} for every file the base's instruction files import (`@path`), followed recursively."""
    tree = set(git("ls-tree", "-r", "--name-only", base).splitlines())
    todo = [(f, 0) for f in sorted(tree) if f.rsplit("/", 1)[-1].lower() in INSTRUCTION]
    seen, found = {f for f, _ in todo}, {}
    while todo and len(seen) < IMPORT_FILES:
        path, depth = todo.pop()
        if depth >= IMPORT_DEPTH:
            continue
        shown = subprocess.run(["git", "show", f"{base}:{path}"], capture_output=True, text=True)
        text = re.sub(r"(?ms)^(```|~~~).*?^\1", "", shown.stdout)  # fenced blocks import nothing
        text = re.sub(r"`[^`\n]*`", "", text)  # nor do code spans
        for m in IMPORT.finditer(text):
            ref = m.group(1).rstrip(".,;:!?")
            if ref.startswith(("/", "~")):
                continue  # outside the repo
            target = posixpath.normpath(posixpath.join(posixpath.dirname(path), ref))
            if target.startswith("../") or target not in tree or target in seen:
                continue
            seen.add(target)
            found[target] = path
            todo.append((target, depth + 1))
    return found


class Unparsable(Exception):
    pass


LENS_LIST = re.compile(r"[\w-]+(?:\s*,\s*[\w-]+)*")
EFFORT_LIST = re.compile(r"[a-z][a-z0-9-]*=[a-z]+(?:\s*,\s*[a-z][a-z0-9-]*=[a-z]+)*")
CLAUSES = ("lenses", "depth", "effort")  # in this order, each at most once
DEFAULT_DEPTH = re.compile(r"^Depth:\s*(\S*)\s*$")


def empty_rules():
    return {"sensitive": [], "routine": None, "paths": [], "depth": None}


def clauses(text, n, section):
    """The `; key: value` clauses after an item's globs and reason, checked: {lenses, depth, effort}."""
    out, last = {"lenses": [], "depth": None, "effort": {}}, -1
    for part in text.split(";"):
        m = re.fullmatch(r"\s*([a-z]+):\s*(.*?)\s*", part)
        if not m or m.group(1) not in CLAUSES or CLAUSES.index(m.group(1)) <= last:
            raise Unparsable(f"line {n}: after the globs and reason come only `; lenses: a, b`, `; depth: <d>` and "
                             "`; effort: <lens>=<level>, ...`, each once and in that order")
        key, value = m.group(1), m.group(2)
        last = CLAUSES.index(key)
        if key == "lenses":
            if section != "sensitive":
                raise Unparsable(f"line {n}: lenses belong to sensitive globs")
            if not LENS_LIST.fullmatch(value):
                raise Unparsable(f"line {n}: `lenses:` takes lens names only")
            out["lenses"] = [x.strip() for x in value.split(",")]
        elif key == "depth":
            if value not in DEPTHS:
                raise Unparsable(f"line {n}: `depth:` is one of {', '.join(DEPTHS)}")
            if section == "sensitive" and DEPTHS.index(value) < DEPTHS.index("focused"):
                raise Unparsable(f"line {n}: a sensitive glob's depth is focused or full")
            out["depth"] = value
        else:
            if not EFFORT_LIST.fullmatch(value):
                raise Unparsable(f"line {n}: `effort:` is `<lens>=<level>, ...`")
            for pair in value.split(","):
                lens, level = (x.strip() for x in pair.split("="))
                if level not in EFFORTS or lens in out["effort"]:
                    raise Unparsable(f"line {n}: an effort is one of {', '.join(EFFORTS)}, once per lens")
                out["effort"][lens] = level
    return out


def split_clauses(rest):
    """(globs and reason, clause text or None): the first `;` outside a backticked glob starts the clauses."""
    inside = False
    for i, ch in enumerate(rest):
        if ch == "`":
            inside = not inside
        elif ch == ";" and not inside:
            return rest[:i], rest[i + 1:]
    return rest, None


def parse(text):
    """{'sensitive': [item], 'routine': [item] or None, 'paths': [item], 'depth': <d> or None}; an item is
    {'glob', 'lenses', 'depth', 'effort'}."""
    lists, section, seen, fence = empty_rules(), None, set(), None
    for n, line in enumerate(text.splitlines(), 1):
        mark = re.match(r" {0,3}(`{3,}|~{3,})", line)  # a fence line: at most 3 spaces in (CommonMark)
        if section is None and (fence or mark):
            # A fenced block outside the lists holds an example, never a rule (as imports() reads instruction files);
            # inside a list a fence is not an item, so it stays unparsable, and so does a fence never closed.
            if mark and not fence:
                fence = mark.group(1)
            elif mark and mark.group(1).startswith(fence[0] * len(fence)) and not line.strip().strip(fence[0]):
                fence = None
            continue
        h = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if h:
            name = h.group(2).strip().lower()
            if len(h.group(1)) == 2 and name in SECTIONS:
                if name in seen:
                    raise Unparsable(f"line {n}: a second `## {h.group(2)}`")
                seen.add(name)
                section = name
                if name == "routine":
                    lists["routine"] = []
            else:
                section = None
            continue
        if section is None:
            d = DEFAULT_DEPTH.match(line)
            if d:
                if lists["depth"] is not None:
                    raise Unparsable(f"line {n}: a second `Depth:` line")
                if d.group(1) not in DEPTHS:
                    raise Unparsable(f"line {n}: `Depth:` is one of {', '.join(DEPTHS)}")
                lists["depth"] = d.group(1)
            continue
        if not line.strip():
            continue
        item = re.match(r"^\s*[-*]\s+(.*)$", line)
        if not item:
            raise Unparsable(f"line {n}: under `## {section.title()}` every line is a `- ` item")
        rest, tail = split_clauses(item.group(1))
        parsed = clauses(tail, n, section) if tail is not None else {"lenses": [], "depth": None, "effort": {}}
        # The reason is plain text after ` — `: no backtick (a glob written there by mistake would vanish) and no
        # `;` (the clauses start at the first one).
        rest, dash, reason = rest.partition(" — ")
        if dash and "`" in reason:
            raise Unparsable(f"line {n}: a reason after ` — ` holds no backtick and no `;` (globs go before it, "
                             "`; lenses: a, b` after it)")
        globs = re.findall(r"`([^`]+)`", rest)
        if not globs or re.sub(r"`[^`]+`", "", rest).strip(" ,"):
            raise Unparsable(f"line {n}: an item is backticked globs, optionally ` — <reason>`, then optionally "
                             "`; lenses: a, b`, `; depth: <d>`, `; effort: <lens>=<level>`")
        for g in globs:
            if g.strip() != g or g.startswith("/") or "\\" in g or ";" in g:
                raise Unparsable(f"line {n}: `{g}` is not a glob this script reads")
            entry = {"glob": g, **parsed}
            if section == "routine":
                lists["routine"].append(entry)
            else:
                lists[section].append(entry)
    if fence:
        raise Unparsable(f"a fenced block opened with {fence} is never closed")
    return lists


def changed(base, head):
    """(merge-base, the paths `git diff --name-only --no-renames <merge-base> <head>` lists)."""
    mb = git("merge-base", base, head).strip()
    return mb, [x for x in git("diff", "--name-only", "--no-renames", mb, head).splitlines() if x]


def load_rules(base, prog="tier.sh"):
    """(rules, broken): REVIEW.md at `base`; an unparsable one warns on stderr and is `broken` (every path
    sensitive, no clause read)."""
    shown = subprocess.run(["git", "show", f"{base}:REVIEW.md"], capture_output=True, text=True)
    if shown.returncode:
        return empty_rules(), None
    try:
        return parse(shown.stdout), None
    except Unparsable as exc:
        print(f"{prog}: warning: REVIEW.md on {base} cannot be parsed ({exc}): every path counts as sensitive",
              file=sys.stderr)
        return empty_rules(), str(exc)


def rate(paths, rules, broken, imported):
    """{path: {'tier', 'lenses', 'imported_by', 'depths', 'efforts'}}: `depths` and `efforts` are the clauses of every
    REVIEW.md line whose glob matches the path, whatever its section."""
    floor = ([glob_re(g, icase=True) for g in FLOOR_NAMES] + [glob_re(g) for g in FLOOR]
             + [re.compile(re.escape(f) + "$") for f in imported])
    sensitive = [(glob_re(e["glob"]), e) for e in rules["sensitive"]]
    routine_items = rules["routine"] if rules["routine"] is not None else [
        {"glob": g, "lenses": [], "depth": None, "effort": {}} for g in DEFAULT_ROUTINE]
    routine = [(glob_re(e["glob"]), e) for e in routine_items]
    others = [(glob_re(e["glob"]), e) for e in rules["paths"]]
    out = {}
    for path in paths:
        hits = [e for r, e in sensitive if r.match(path)]
        lines = hits + [e for r, e in routine + others if r.match(path)]
        if broken or hits or any(r.match(path) for r in floor):
            t = "sensitive"
        elif any(r.match(path) for r, _ in routine):
            t = "routine"
        else:
            t = "standard"
        out[path] = {"tier": t, "lenses": sorted({x for e in hits for x in e["lenses"]}),
                     "imported_by": imported.get(path),
                     "depths": [e["depth"] for e in lines if e["depth"]],
                     "efforts": [e["effort"] for e in lines if e["effort"]]}
    return out


def top_tier(rated):
    return max((r["tier"] for r in rated.values()), key=RANK.get)


def main():
    p = argparse.ArgumentParser(prog="tier.sh")
    p.add_argument("--base")
    p.add_argument("--head", default="HEAD")
    a = p.parse_args()
    base = a.base or default_base()
    try:
        _, paths = changed(base, a.head)
    except RuntimeError as exc:
        sys.exit(f"tier.sh: {exc}")
    if not paths:
        print(f"tier.sh: {a.head} changes nothing against {base}", file=sys.stderr)
        sys.exit(2)
    rules, broken = load_rules(base)
    try:
        imported = imports(base)
    except RuntimeError as exc:
        sys.exit(f"tier.sh: {exc}")
    rated = rate(paths, rules, broken, imported)
    top = top_tier(rated)
    print(top)
    for path, r in rated.items():
        if r["tier"] == top:
            notes = [f"imported by {r['imported_by']}"] if r["imported_by"] else []
            notes += [f"lenses: {', '.join(r['lenses'])}"] if r["lenses"] else []
            print(f"{path} ({'; '.join(notes)})" if notes else path)


if __name__ == "__main__":
    main()
