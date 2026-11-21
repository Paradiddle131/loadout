#!/usr/bin/env python3
"""Builds and compares the PR comments gate_stamp.sh and verdict.sh post as records (lib.sh has the format).

  record.py build --kind gates|review --sha <head> --state success|failure --title <first line>
                  [--tier <tier>] [--reviewed <sha>] [--round <key=value>]... [--line <markdown line>]...
                  [--file <raw output>] [--details <summary>]
    prints the body: the title, the marker line, the round line, the lines, and the raw output under <details> in
    a fence longer than any backtick run in it, clipped (with a note) so the whole body fits GitHub's comment limit.
  record.py review-round --reviewers <names> --cycle <n> --dupes <n> --nits <n> --mustfix <n>
                  --lens "<name> model=<m> effort=<e> tokens=<n> seconds=<n> findings=<n>"... [--dismissals <file>]
    checks a review round's cost and shape and prints, one per line, the --round pairs (first line, blank-separated)
    and then the human table of the same numbers; exits 2 with the reason on a malformed or missing value.
    With --repost (an earlier round's verdict posted again after clean merges of the default branch) it takes no
    --cycle, --dupes, --nits or --lens and prints only repost=1, lenses and mustfix: no agent ran, so no usage.
  record.py version | kit
    prints the review path's version (`metadata.version` in ../SKILL.md) or the collection commit (below).
  record.py same <comment json> <sent body file>
    exits 0 when the comment's body is the one sent (line endings and trailing newlines aside), else 1.

The round line is a record's third line, for audits and people; the merge guard reads only the first two:
  <!-- loadout + :round v=<version> kit=<commit> [<key>=<value>]... -->   (one word, `loadout` and `:round` joined)
`v` is this skill's version, bumped by the rule in ../SKILL.md § Version; `kit` is the full commit of the clone these
scripts run from, `-dirty` appended when that clone has uncommitted changes to tracked files under skills/review,
agents or cloud/hooks, and `none` when the scripts are not where a clone of the collection keeps them (a copied
skill); never the repo under review. Keys are lowercase letters; values are letters, digits and . _ , - : only;
only `lens` may repeat. A review round adds cycle, lenses, dupes, mustfix, nits, one lens=<name>:<model>:<effort>:
<tokens>:<seconds>:<findings> per agent, and dismissals and promoted when the verifier gave them (a re-post:
repost=1, lenses and mustfix only); a later key
(such as a planned depth) is one more pair.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

COMMENT_MAX = 65536  # GitHub's limit on a comment body, in characters
SHA = re.compile(r"[0-9a-f]{40}")
HERE = Path(__file__).resolve().parent
ROUND_KEY = re.compile(r"[a-z]+")
ROUND_VALUE = re.compile(r"[A-Za-z0-9._,:-]+")
REPEATABLE = {"lens"}
SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
NAME = re.compile(r"[a-z][a-z0-9-]*")
MODEL = re.compile(r"[a-z0-9][a-z0-9.-]*")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
COUNT = re.compile(r"0|[1-9][0-9]*")
LENS_KEYS = ("model", "effort", "tokens", "seconds", "findings")
DISMISSALS = re.compile(r"^[ \t\v\f\r]*Dismissals:")
DISMISSALS_LINE = re.compile(r"[ \t\v\f\r]*Dismissals: re-ran (0|[1-9][0-9]*), promoted (0|[1-9][0-9]*)[ \t\v\f\r]*")
WATCHED = ("skills/review", "agents", "cloud/hooks")  # what a `-dirty` kit means: these changed, uncommitted


class NoVersion(ValueError):
    """The frontmatter holds no metadata.version line at all."""


def skill_version(text: str) -> str:
    """`metadata.version` from a SKILL.md's frontmatter; ValueError when it is missing, repeated or not semver.

    Only the frontmatter counts (the lines between a first-line `---` and the next `---`), only a `version:` line that
    is a direct child of a top-level `metadata:` line (at its first indentation, not nested deeper), and only a plain
    MAJOR.MINOR.PATCH value.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md has no frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError("SKILL.md's frontmatter is not closed") from None
    found, inside, child = [], False, None
    for ln in lines[1:end]:
        if ln and not ln[0].isspace():
            inside, child = ln.rstrip() == "metadata:", None
            continue
        if not inside or not ln.strip():
            continue
        indent = len(ln) - len(ln.lstrip())
        child = indent if child is None else child  # metadata's own keys sit at its first indentation
        m = re.fullmatch(r"\s+version:\s*(.*?)\s*", ln)
        if m and indent == child:
            found.append(m.group(1))
    if not found:
        raise NoVersion("SKILL.md's frontmatter holds no metadata.version line")
    if len(found) != 1:
        raise ValueError(f"SKILL.md's frontmatter holds {len(found)} metadata.version lines, not one")
    if not SEMVER.fullmatch(found[0]):
        raise ValueError(f"metadata.version is {found[0]!r}, not MAJOR.MINOR.PATCH")
    return found[0]


def version(skill: Path = HERE.parent / "SKILL.md") -> str:
    return skill_version(skill.read_text(encoding="utf-8"))


def kit(scripts: Path = HERE) -> str:
    """The collection commit these scripts run from (module docstring); `none` outside such a clone."""
    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", str(scripts), *args], capture_output=True, text=True, check=False)

    try:
        top, head = git("rev-parse", "--show-toplevel"), git("rev-parse", "HEAD")
    except OSError:
        return "none"
    if top.returncode or head.returncode or not SHA.fullmatch(head.stdout.strip()):
        return "none"
    root = Path(top.stdout.strip())
    if False:
        return "none"  # a copy inside some other repo: its commit is not the collection's
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no", "--", *WATCHED],
                           capture_output=True, text=True, check=False)
    return head.stdout.strip() + ("-dirty" if dirty.returncode or dirty.stdout.strip() else "")


def round_line(pairs: list[str]) -> str:
    """The round line: v and kit first, then each `key=value` of `pairs`, checked (module docstring)."""
    split = [p.split("=", 1) for p in pairs]
    for kv in split:
        if len(kv) != 2 or not ROUND_KEY.fullmatch(kv[0]) or not ROUND_VALUE.fullmatch(kv[1]):
            raise ValueError(f"a --round pair is <key>=<value>: a lowercase key, a value of letters, digits and "
                             f". _ , - : (got {'='.join(kv)!r})")
    keys = [k for k, _ in split]
    if {"v", "kit"} & set(keys):
        raise ValueError("v and kit are the scripts' own: record.py adds them")
    if dup := sorted({k for k in keys if keys.count(k) > 1} - REPEATABLE):
        raise ValueError(f"a --round key appears twice: {', '.join(dup)}")
    return " ".join(["<!-- loadout" + ":round", f"v={version()}", f"kit={kit()}", *(f"{k}={v}" for k, v in split),
                     "-->"])


def names(text: str | None) -> list[str]:
    out = [n for n in re.split(r"[,\s]+", text or "") if n]
    if not out or not all(NAME.fullmatch(n) for n in out):
        raise ValueError(f"--reviewers is agent names, split by commas or blanks, each a lowercase letter then "
                         f"letters, digits or '-' (got {text!r})")
    if len(set(out)) != len(out):
        raise ValueError(f"--reviewers names an agent twice (got {text!r})")
    return out


def lens_spec(spec: str) -> dict:
    """One --lens value: `<name> model=<m> effort=<e> tokens=<n> seconds=<n> findings=<n>`, each key once."""
    parts = spec.split()
    if not parts or not NAME.fullmatch(parts[0]):
        raise ValueError(f"a --lens value starts with the agent's name (got {spec!r})")
    kv = [p.split("=", 1) for p in parts[1:]]
    if any(len(x) != 2 for x in kv) or sorted(k for k, _ in kv) != sorted(LENS_KEYS):
        raise ValueError(f"--lens {parts[0]} needs each of {', '.join(f'{k}=' for k in LENS_KEYS)} once and nothing "
                         f"else (got {spec!r})")
    f = dict(kv)
    if not MODEL.fullmatch(f["model"]):
        raise ValueError(f"--lens {parts[0]}: model= is the model the agent call named (got {f['model']!r})")
    if f["effort"] not in EFFORTS:
        raise ValueError(f"--lens {parts[0]}: effort= is one of {', '.join(EFFORTS)} (got {f['effort']!r})")
    for k in ("tokens", "seconds", "findings"):
        if not COUNT.fullmatch(f[k]):
            raise ValueError(f"--lens {parts[0]}: {k}= is a whole number (got {f[k]!r}); seconds are the harness's "
                             "milliseconds divided by 1000 and rounded")
    return {"name": parts[0], "model": f["model"], "effort": f["effort"],
            **{k: int(f[k]) for k in ("tokens", "seconds", "findings")}}


def dismissals(path: str | None) -> tuple[int, int] | None:
    """(re-ran, promoted) from the first `Dismissals:` line of the verifier's header; None when it has none.

    The header is the output's lines before its `Lens heads:` line or its first `##` heading, outside code fences: a
    `Dismissals:` line quoted in a finding below, or in a fence, is never read.
    """
    if not path:
        return None
    fence = ""
    for ln in open(path, encoding="utf-8", errors="replace").read().split("\n"):
        if m := re.match(r"\s*(`{3,}|~{3,})", ln):
            if not fence:
                fence = m.group(1)
            elif m.group(1).startswith(fence) and not ln.strip()[len(m.group(1)):].strip():
                fence = ""
            continue
        if fence:
            continue
        if re.match(r"\s*(Lens heads:|##)", ln):
            return None
        if DISMISSALS.match(ln):
            m = DISMISSALS_LINE.fullmatch(ln)
            if not m:
                raise ValueError(f"the verifier's Dismissals line is not `Dismissals: re-ran <n>, promoted <m>` "
                                 f"(got {ln.strip()!r})")
            return int(m.group(1)), int(m.group(2))
    return None


def review_round(a: argparse.Namespace) -> list[str]:
    """The round pairs (one line) and the human table lines for a review round (module docstring)."""
    who = names(a.reviewers)
    if a.repost:
        # A re-post records an earlier round's verdict again (the head moved only by clean merges): no agent ran.
        if a.cycle or a.dupes or a.nits or a.lens:
            raise ValueError("--repost records no new round, so it takes no --cycle, --dupes, --nits or --lens")
        if a.mustfix is None or not COUNT.fullmatch(a.mustfix):
            raise ValueError(f"--mustfix is a whole number (got {a.mustfix!r})")
        pairs = ["repost=1", f"lenses={','.join(who)}", f"mustfix={a.mustfix}"]
        round_line(pairs)
        return [" ".join(pairs)]
    for k in ("cycle", "dupes", "nits", "mustfix"):
        v = getattr(a, k)
        if v is None or not COUNT.fullmatch(v) or (k == "cycle" and v == "0"):
            raise ValueError(f"--{k} is a whole number{' from 1' if k == 'cycle' else ''} (got {v!r})")
    lenses = [lens_spec(s) for s in a.lens]
    given = [x["name"] for x in lenses]
    if len(set(given)) != len(given):
        raise ValueError(f"a --lens names an agent twice: {', '.join(sorted({g for g in given if given.count(g) > 1}))}")
    if set(given) != set(who):
        raise ValueError(f"the --lens agents ({', '.join(given) or 'none'}) are not the --reviewers "
                         f"({', '.join(who)}): give one --lens per agent that ran, the verifier included")
    lenses.sort(key=lambda x: who.index(x["name"]))
    pairs = [f"cycle={a.cycle}", f"lenses={','.join(who)}", f"dupes={a.dupes}", f"mustfix={a.mustfix}",
             f"nits={a.nits}"]
    if (d := dismissals(a.dismissals)) is not None:
        pairs += [f"dismissals={d[0]}", f"promoted={d[1]}"]
    pairs += [f"lens={x['name']}:{x['model']}:{x['effort']}:{x['tokens']}:{x['seconds']}:{x['findings']}"
              for x in lenses]
    round_line(pairs)  # the same check build makes, before anything is posted
    total = {k: sum(x[k] for x in lenses) for k in ("tokens", "seconds", "findings")}
    table = ["", "| Agent | Model | Effort | Tokens | Seconds | Findings |", "|---|---|---|---:|---:|---:|",
             *[f"| {x['name']} | {x['model']} | {x['effort']} | {x['tokens']} | {x['seconds']} | {x['findings']} |"
               for x in lenses],
             f"| Total (summed) | | | {total['tokens']} | {total['seconds']} | {total['findings']} |"]
    return [" ".join(pairs), *table]


def build(a: argparse.Namespace) -> str:
    if not SHA.fullmatch(a.sha) or (a.reviewed and not SHA.fullmatch(a.reviewed)):
        sys.exit("record.py: a sha must be 40 hex characters")
    if "\n" in a.title or "-->" in a.title:
        sys.exit("record.py: the title is one line")
    marker = f"<!-- loadout:{a.kind} sha={a.sha} state={a.state}"
    if a.tier:
        marker += f" tier={a.tier}"
    if a.reviewed:
        marker += f" reviewed={a.reviewed}"
    marker += " -->"
    try:
        third = round_line(a.round)
    except (OSError, ValueError) as exc:
        sys.exit(f"record.py: {exc}")
    head = "\n".join([a.title, marker, third, "", *a.line]) + "\n"
    raw = open(a.file, encoding="utf-8", errors="replace").read() if a.file else ""
    if not raw.strip():
        return head
    fence = "```"
    while fence in raw:
        fence += "`"

    def body(text: str, note: str = "") -> str:
        return (head + f"\n<details><summary>{a.details}</summary>\n\n" + note + fence + "text\n" + text
                + ("" if text.endswith("\n") else "\n") + fence + "\n\n</details>\n")

    out, keep = body(raw), len(raw)
    while len(out) > COMMENT_MAX:
        keep = max(0, keep - (len(out) - COMMENT_MAX))
        note = f"Clipped to fit GitHub's comment size: the {'last' if a.tail else 'first'} {keep} of {len(raw)} characters.\n\n"
        out = body(raw[len(raw) - keep:] if a.tail else raw[:keep], note)
    return out


FOOTER = re.compile(r"(\s*\n---\s*\n_Generated by \[Claude Code\]\(https://claude\.ai/code\)_)?\s*")


def same(comment: str, sent: str) -> int:
    back = json.load(open(comment)).get("body") or ""
    norm = lambda s: s.replace("\r\n", "\n").rstrip("\n")  # noqa: E731
    back, body = norm(back), norm(open(sent, encoding="utf-8").read())
    if not back.startswith(body):
        return 1
    # A cloud session's proxy appends its own attribution footer to every comment it relays;
    # nothing else may follow the body that was sent.
    return 0 if FOOTER.fullmatch(back[len(body):]) else 1


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--kind", choices=["gates", "review"], required=True)
    b.add_argument("--sha", required=True)
    b.add_argument("--state", choices=["success", "failure"], required=True)
    b.add_argument("--title", required=True)
    b.add_argument("--tier", choices=["routine", "standard", "sensitive"])
    b.add_argument("--reviewed")
    b.add_argument("--round", action="append", default=[])
    b.add_argument("--line", action="append", default=[])
    b.add_argument("--file")
    b.add_argument("--details", default="Output (raw)")
    b.add_argument("--tail", action="store_true", help="clip from the start, keeping the end")
    r = sub.add_parser("review-round")
    for k in ("reviewers", "cycle", "dupes", "nits", "mustfix"):
        r.add_argument(f"--{k}")
    r.add_argument("--lens", action="append", default=[])
    r.add_argument("--dismissals")
    r.add_argument("--repost", action="store_true")
    sub.add_parser("version")
    sub.add_parser("kit")
    s = sub.add_parser("same")
    s.add_argument("comment")
    s.add_argument("sent")
    a = p.parse_args()
    if a.cmd == "build":
        sys.stdout.write(build(a))
        return 0
    if a.cmd == "review-round":
        try:
            print("\n".join(review_round(a)))
        except (OSError, ValueError) as exc:
            print(f"record.py: {exc}", file=sys.stderr)
            return 2
        return 0
    if a.cmd == "version":
        try:
            print(version())
        except (OSError, ValueError) as exc:
            print(f"record.py: {exc}", file=sys.stderr)
            return 2
        return 0
    if a.cmd == "kit":
        print(kit())
        return 0
    return same(a.comment, a.sent)


if __name__ == "__main__":
    sys.exit(main())
