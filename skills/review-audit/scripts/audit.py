#!/usr/bin/env python3
"""Reviews the reviews: gathers the `review` skill's records from PRs, samples findings, records audit judgments
back on the PRs, and sums both up. GitHub holds every record; the JSONL files are a snapshot, rebuilt at will.

  audit.py harvest --repo <owner/name> [--repo ...] --since <ISO time> [--until <ISO time>] --out <dir>
      reads, never writes: PRs updated in the window and their trusted `🤖 Gates`, `🤖 Review` and `🤖 Audit`
      comments, into <dir>/prs.jsonl, gates.jsonl, rounds.jsonl, findings.jsonl and audits.jsonl.
  audit.py sample --dir <dir> --n <count> [--seed <n>] [--session <id>]
      picks findings to audit, spread over rank and lens, leaving out those an earlier audit judged;
      writes <dir>/sample.jsonl and prints one line per pick.
  audit.py record --repo <owner/name> --pr <n> --session <id> --file <judgments.json> [--backfill] [--dry-run]
      posts one `🤖 Audit` record on the PR: a table for people and the judgments as a JSON block.
  audit.py summary --dir <dir> [--session <id>] [--json]
      prints the batch's numbers: rounds, passes, convergence, lens yield and, from the audits, how often
      a finding was wrong, mattered, or was ranked too high or too low, each rate with its 95% interval.

A judgment (judgments.json is a list of them):
  {"round": <the 🤖 Review comment id>, "ids": ["COR-1"], "correct": "yes|no|unverifiable",
   "matters": "yes|no", "rank": "right|too-high|too-low", "kind": "code|test|wording|config|data|process",
   "method": "re-ran|re-read|record", "note": "<one line>"}
REST through `gh api` only, paged by hand (some proxies refuse GraphQL and `--paginate`).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "review" / "scripts"))
import findings as verifier_output  # noqa: E402  (the review skill's parser of the verifier's output)

TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
MARKER = re.compile(r"<!-- loadout:(gates|review|audit)((?: [a-z_]+=[^\s=]+)+) -->")
KINDS = {"correct": {"yes", "no", "unverifiable"}, "matters": {"yes", "no"},
         "rank": {"right", "too-high", "too-low"},
         "kind": {"code", "test", "wording", "config", "data", "process"},
         "method": {"re-ran", "re-read", "record"}}
SESSION = re.compile(r"[A-Za-z0-9._-]{1,64}")
LENSES = ("correctness", "claims", "guardrail", "leak", "control")


def lenses(text: str | None) -> list[str]:
    """The lenses a finding's free-text `lens:` field names, asides in parentheses left out."""
    plain = re.sub(r"\([^)]*\)?", " ", text or "").lower()
    found = [x for x in LENSES if re.search(rf"\b{x}", plain)]
    return found or ["other"]


def gh_json(endpoint: str) -> object:
    """One `gh api` read; tests replace this function."""
    out = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"audit.py: gh api {endpoint} failed: {out.stderr.strip()}")
    return json.loads(out.stdout or "null")


def pages(endpoint: str, per_page: int = 100):
    sep = "&" if "?" in endpoint else "?"
    n = 1
    while True:
        batch = gh_json(f"{endpoint}{sep}per_page={per_page}&page={n}") or []
        yield from batch
        if len(batch) < per_page:
            return
        n += 1


def fields(marker: str) -> dict:
    return dict(kv.split("=", 1) for kv in marker.split())


def raw_output(body: str) -> str:
    """The verifier's output that verdict.sh put under <details>, in a fence of three or more backticks."""
    m = re.search(r"<details><summary>[^<]*</summary>\s*\n(?:Clipped[^\n]*\n\s*\n)?(`{3,})[a-z]*\n", body)
    if not m:
        return ""
    end = body.find("\n" + m.group(1) + "\n", m.end() - 1)
    return body[m.end():end if end >= 0 else len(body)]


def audit_json(body: str) -> list:
    m = re.search(r"```json\n(.*?)\n```", body, re.S)
    try:
        data = json.loads(m.group(1)) if m else []
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def harvest(a: argparse.Namespace) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: dict[str, list] = defaultdict(list)
    for repo in a.repo:
        for pr in pages(f"repos/{repo}/pulls?state=all&sort=updated&direction=desc"):
            if pr["updated_at"] < a.since:
                break
            n = pr["number"]
            rows["prs"].append({"repo": repo, "pr": n, "title": pr["title"], "state": pr["state"],
                                "created_at": pr["created_at"], "merged_at": pr.get("merged_at"),
                                "head": pr["head"]["sha"], "branch": pr["head"]["ref"]})
            for c in pages(f"repos/{repo}/issues/{n}/comments"):
                if c.get("author_association") not in TRUSTED or a.until and c["created_at"] > a.until:
                    continue
                lines = (c.get("body") or "").split("\n")
                m = MARKER.search(lines[1]) if len(lines) > 1 and lines[0].startswith("🤖") else None
                if not m:
                    continue
                kind, f = m.group(1), fields(m.group(2))
                base = {"repo": repo, "pr": n, "comment": c["id"], "url": c.get("html_url"),
                        "created_at": c["created_at"], "edited": c.get("updated_at") != c["created_at"]}
                if kind == "gates":
                    rows["gates"].append({**base, "sha": f.get("sha"), "state": f.get("state")})
                elif kind == "audit":
                    for j in audit_json(c["body"]):
                        rows["audits"].append({**base, "session": f.get("session"),
                                               "backfill": f.get("backfill") == "1", **j})
                else:
                    parsed = verifier_output.parse(raw_output(c["body"]))
                    reviewers = next((ln.split(":", 1)[1].strip() for ln in lines
                                      if ln.startswith("- Reviewers:")), "")
                    fs = parsed["findings"]
                    rows["rounds"].append({
                        **base, "sha": f.get("sha"), "reviewed": f.get("reviewed"), "state": f.get("state"),
                        "tier": f.get("tier"), "reviewers": reviewers, "verdict": parsed["verdict"],
                        "steered": any(s.strip().lower() not in ("", "none") for s in parsed["steering"]),
                        "must_fix": sum(b["must_fix"] for b in fs),
                        "nits": sum((b["rank"] or "").startswith("nit") for b in fs),
                        "pre_existing": sum((b["rank"] or "").startswith("pre") for b in fs)})
                    for b in fs:
                        rows["findings"].append({
                            "repo": repo, "pr": n, "round": c["id"], "ids": b["ids"], "section": b["section"],
                            "rank": b["rank"], "must_fix": b["must_fix"], "harm": b["harm"],
                            **{k: b["fields"].get(k) for k in ("lens", "location", "claim")}})
    for name in ("prs", "gates", "rounds", "findings", "audits"):
        with open(out / f"{name}.jsonl", "w", encoding="utf-8") as fh:
            for r in rows[name]:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{name}: {len(rows[name])}")
    return 0


def load(d: Path, name: str) -> list[dict]:
    p = d / f"{name}.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def key(r: dict) -> tuple:
    return (r["repo"], r["pr"], r["round"], tuple(r["ids"]))


def sample(a: argparse.Namespace) -> int:
    d = Path(a.dir)
    judged = {key(j) for j in load(d, "audits") if "round" in j and "ids" in j}
    pool = [f for f in load(d, "findings") if key(f) not in judged and f["rank"] != "pre-existing"]
    rng = random.Random(a.seed)
    strata: dict[tuple, list] = defaultdict(list)
    for f in pool:
        strata[(f["must_fix"], lenses(f.get("lens"))[0])].append(f)
    for s in strata.values():
        rng.shuffle(s)
    picks: list[dict] = []
    order = sorted(strata, key=lambda s: (not s[0], s[1]))  # must-fix strata first, then by lens
    while len(picks) < a.n and any(strata[s] for s in order):
        for s in order:
            if strata[s] and len(picks) < a.n:
                picks.append(strata[s].pop())
    with open(d / "sample.jsonl", "w", encoding="utf-8") as fh:
        for f in picks:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
            print(f"{f['repo']}#{f['pr']} round {f['round']} {', '.join(f['ids'])} "
                  f"({'must-fix' if f['must_fix'] else f['rank']}, {f.get('lens')})")
    print(f"sampled {len(picks)} of {len(pool)} not yet judged")
    return 0


def check_judgments(items: object) -> list[dict]:
    if not isinstance(items, list) or not items:
        sys.exit("audit.py: the judgments file is a non-empty JSON list")
    for i, j in enumerate(items):
        if not isinstance(j, dict) or not isinstance(j.get("round"), int) or not j.get("ids"):
            sys.exit(f"audit.py: judgment {i} needs an integer `round` and its `ids`")
        for k, allowed in KINDS.items():
            if j.get(k) not in allowed:
                sys.exit(f"audit.py: judgment {i}: `{k}` is one of {sorted(allowed)}, got {j.get(k)!r}")
        if "\n" in str(j.get("note", "")):
            sys.exit(f"audit.py: judgment {i}: the note is one line")
    return items


def record(a: argparse.Namespace) -> int:
    if not SESSION.fullmatch(a.session):
        sys.exit("audit.py: --session is letters, digits, '.', '_' or '-', at most 64")
    items = check_judgments(json.loads(Path(a.file).read_text(encoding="utf-8")))
    cell = lambda s: str(s).replace("|", "\\|")  # noqa: E731
    marker = "<!-- loadout" + f":audit session={a.session}" + (" backfill=1" if a.backfill else "") + " -->"
    body = "\n".join([
        f"🤖 Audit: {len(items)} finding{'s' if len(items) != 1 else ''} re-checked (session {a.session})", marker, "",
        "| Finding | Correct | Matters | Rank | Kind | How | Note |", "|---|---|---|---|---|---|---|",
        *[f"| {cell(', '.join(j['ids']))} | {j['correct']} | {j['matters']} | {j['rank']} | {j['kind']} | "
          f"{j['method']} | {cell(j.get('note', ''))} |" for j in items],
        "", "<details><summary>Data</summary>", "", "```json", json.dumps(items, ensure_ascii=False), "```", "",
        "</details>", ""])
    if a.dry_run:
        sys.stdout.write(body)
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(body)
    out = subprocess.run(["gh", "api", "-X", "POST", f"repos/{a.repo}/issues/{a.pr}/comments",
                          "-F", f"body=@{fh.name}"], capture_output=True, text=True)
    Path(fh.name).unlink()
    if out.returncode:
        sys.exit(f"audit.py: posting the audit record failed: {out.stderr.strip()}")
    sent = json.loads(out.stdout)
    back = gh_json(f"repos/{a.repo}/issues/comments/{sent['id']}")
    if audit_json(back.get("body") or "") != items:
        sys.exit(f"audit.py: comment {sent['id']} does not hold the judgments sent; delete it and run again")
    print(sent.get("html_url", sent["id"]))
    return 0


def wilson(k: int, n: int) -> list:
    if not n:
        return [None, None, None]
    p, z = k / n, 1.96
    mid = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(p, 3), round(max(0, mid - half), 3), round(min(1, mid + half), 3)]


def summarize(d: Path, session: str | None) -> dict:
    prs = {(p["repo"], p["pr"]): p for p in load(d, "prs")}
    rounds = sorted(load(d, "rounds"), key=lambda r: r["created_at"])
    finds = load(d, "findings")
    audits = [j for j in load(d, "audits") if session in (None, j.get("session"))]
    by_pr: dict[tuple, list] = defaultdict(list)
    for r in rounds:
        by_pr[(r["repo"], r["pr"])].append(r)
    changes = []
    for k, rs in by_pr.items():
        p = prs.get(k, {})
        series = [r["must_fix"] for r in rs]
        last = rs[-1]
        passed_head = last["state"] == "success" and p.get("head") in (last.get("sha"), None)
        changes.append({"repo": k[0], "pr": k[1], "rounds": len(rs), "series": series,
                        "first_pass": rs[0]["state"] == "success", "merged": bool(p.get("merged_at")),
                        "grew": any(b > a for a, b in zip(series, series[1:])),
                        "merged_without_pass": bool(p.get("merged_at")) and not passed_head,
                        "steered_rounds": sum(r["steered"] for r in rs)})
    lens: dict[str, Counter] = defaultdict(Counter)
    for f in finds:
        names = lenses(f.get("lens"))
        for x in names:
            lens[x]["must_fix" if f["must_fix"] else "other"] += 1
            if len(names) == 1:
                lens[x]["alone_must_fix" if f["must_fix"] else "alone_other"] += 1
    judged_mf = [j for j in audits if j.get("rank") in KINDS["rank"]
                 and any(key({**f, "round": f["round"]}) == (j["repo"], j["pr"], j["round"], tuple(j["ids"]))
                         and f["must_fix"] for f in finds)]
    checkable = [j for j in audits if j.get("correct") in ("yes", "no")]
    merged = [c for c in changes if c["merged"]]
    return {
        "rounds": len(rounds), "changes": len(changes),
        "passes": sum(r["state"] == "success" for r in rounds),
        "first_round_pass": wilson(sum(c["first_pass"] for c in changes), len(changes)),
        "rounds_per_merge": round(sum(c["rounds"] for c in merged) / len(merged), 2) if merged else None,
        "must_fix": sum(f["must_fix"] for f in finds),
        "must_fix_with_harm": wilson(sum(bool(f["harm"]) for f in finds if f["must_fix"]),
                                     sum(f["must_fix"] for f in finds)),
        "lens": {k: dict(v) for k, v in sorted(lens.items())},
        "audited": len(audits),
        "wrong": wilson(sum(j["correct"] == "no" for j in checkable), len(checkable)),
        "matters": wilson(sum(j.get("matters") == "yes" for j in checkable), len(checkable)),
        "must_fix_too_high": wilson(sum(j["rank"] == "too-high" for j in judged_mf), len(judged_mf)),
        "must_fix_wording": wilson(sum(j.get("kind") == "wording" for j in judged_mf), len(judged_mf)),
        "too_low": sum(j.get("rank") == "too-low" for j in audits),
        "attention": [c for c in changes if c["grew"] or c["merged_without_pass"] or c["steered_rounds"]],
        "series": changes,
    }


def summary(a: argparse.Namespace) -> int:
    s = summarize(Path(a.dir), a.session)
    if a.json:
        json.dump(s, sys.stdout, indent=1)
        sys.stdout.write("\n")
        return 0
    pct = lambda w: "n/a" if w[0] is None else f"{w[0]:.0%} ({w[1]:.0%}-{w[2]:.0%})"  # noqa: E731
    rows = [("Review rounds", s["rounds"]), ("Changes reviewed", s["changes"]), ("Rounds passed", s["passes"]),
            ("First round passed", pct(s["first_round_pass"])), ("Rounds per merged change", s["rounds_per_merge"]),
            ("Must-fix findings", s["must_fix"]), ("Must-fix naming a harm", pct(s["must_fix_with_harm"])),
            ("Findings audited", s["audited"]), ("Wrong, of those checkable", pct(s["wrong"])),
            ("Mattered", pct(s["matters"])), ("Must-fix ranked too high", pct(s["must_fix_too_high"])),
            ("Must-fix about wording only", pct(s["must_fix_wording"])), ("Ranked too low", s["too_low"])]
    print("| Measure | Value |\n|---|---|")
    for k, v in rows:
        print(f"| {k} | {v} |")
    print("\n| Lens | Must-fix | Alone | Other | Alone |\n|---|---|---|---|---|")
    for k, v in s["lens"].items():
        print(f"| {k} | {v.get('must_fix', 0)} | {v.get('alone_must_fix', 0)} | {v.get('other', 0)} | "
              f"{v.get('alone_other', 0)} |")
    print("\n| Needs a look | Rounds | Must-fix per round | Why |\n|---|---|---|---|")
    for c in s["attention"]:
        why = [w for w, on in (("grew", c["grew"]), ("merged without a pass", c["merged_without_pass"]),
                               ("steered", c["steered_rounds"])) if on]
        print(f"| {c['repo']}#{c['pr']} | {c['rounds']} | {', '.join(map(str, c['series']))} | {', '.join(why)} |")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("harvest")
    h.add_argument("--repo", action="append", required=True)
    h.add_argument("--since", required=True)
    h.add_argument("--until")
    h.add_argument("--out", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--dir", required=True)
    s.add_argument("--n", type=int, required=True)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--session")
    r = sub.add_parser("record")
    r.add_argument("--repo", required=True)
    r.add_argument("--pr", type=int, required=True)
    r.add_argument("--session", required=True)
    r.add_argument("--file", required=True)
    r.add_argument("--backfill", action="store_true")
    r.add_argument("--dry-run", action="store_true")
    m = sub.add_parser("summary")
    m.add_argument("--dir", required=True)
    m.add_argument("--session")
    m.add_argument("--json", action="store_true")
    a = p.parse_args()
    return {"harvest": harvest, "sample": sample, "record": record, "summary": summary}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
