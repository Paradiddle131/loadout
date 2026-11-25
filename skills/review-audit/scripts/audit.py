#!/usr/bin/env python3
"""Reviews the reviews: gathers the `review` skill's records from PRs, samples findings, records audit judgments
back on the PRs, and sums both up. GitHub holds every record; the JSONL files are a snapshot, rebuilt at will.

  audit.py harvest --repo <owner/name> [--repo ...] --since <ISO time> [--until <ISO time>] --out <dir>
      reads, never writes: PRs updated since --since, their `🤖 Gates` and `🤖 Review` records posted from
      --since up to --until, and every `🤖 Audit` record they hold, whenever posted; only records the merge
      guard would trust count (author, unedited, exact title and marker, the two agreeing); writes
      <dir>/prs.jsonl, gates.jsonl, rounds.jsonl, findings.jsonl and audits.jsonl.
  audit.py sample --dir <dir> --n <count> [--seed <n>]
      picks findings to audit in turns: each turn takes one from every group of must-fix or other findings by
      first lens, must-fix groups first; it leaves out pre-existing ones and those an earlier audit judged;
      writes <dir>/sample.jsonl and prints one line per pick.
  audit.py record --repo <owner/name> --pr <n> --session <id> --file <judgments.json> [--backfill] [--dry-run]
      posts one `🤖 Audit` record on the PR: a table for people and the judgments as a JSON block.
  audit.py summary --dir <dir> [--session <id>] [--json]
      prints the batch's numbers: rounds, passes, convergence, lens yield and, from the audits, how often a
      checkable finding was wrong or mattered and a must-fix was ranked too high, each with its 95% interval,
      and how many findings were ranked too low, the findings by the effort their lens ran at and the rounds by depth
      (`unstamped` for a round line without them); "merged without a pass" reads the review record the merge
      guard saw at merge time, not the gates record or the tier. Then the rounds by the review path's version
      (`v` on each record's round line, `unstamped` without one) and the reviewers' tokens and seconds per PR,
      repo, day and month, with an estimated cost at list price (BLENDED_USD_PER_MTOK has the rate).

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(Path(__file__).resolve().parents[2] / "review" / "scripts"))
import blocking  # noqa: E402  (the review skill's reader of the verifier's `Blocking:` line)
import record as review_record  # noqa: E402  (the review skill's record builder: the round line, v and kit)
import findings as verifier_output  # noqa: E402  (a lenient reader of the verifier's prose, for counting only)

TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
MARKER = re.compile(r"<!-- loadout:(gates|review|audit)((?: [a-z_]+=[^\s=]+)+) -->")
# A record counts only in the shape the merge guard (cloud/hooks/merge-guard.py) trusts: an unedited comment by the
# owner, a member or a collaborator, its first line the record's title, its second line exactly one marker.
TITLE = {"gates": re.compile(r"🤖 Gates: (success|failure)"),
         "review": re.compile(r"🤖 Review: (pass|fail) \((routine|standard|sensitive) tier\)"),
         "audit": re.compile(r"🤖 Audit: \d+ findings? re-checked \(session [A-Za-z0-9._-]{1,64}\)")}
FIELDS = {"gates": {"sha", "state"}, "review": {"sha", "state", "tier", "reviewed", "depth"},
          "audit": {"session", "backfill"}}
DEPTHS = ("none", "light", "focused", "full")  # the review skill's plan.py ranks them
SHA = re.compile(r"[0-9a-f]{40}")
GUARD_REVIEW = re.compile(r"\s*<!-- loadout" r":review\b")  # how the merge guard spots a review record's marker
WHEN = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?")
SKIPPED = re.compile(r"(dropped|unverified|not checked)\b", re.I)  # verifier sections that hold no ranked finding
FINDING_ID = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+")
JUDGMENT_KEYS = {"round", "ids", "correct", "matters", "rank", "kind", "method", "note"}
KINDS = {"correct": {"yes", "no", "unverifiable"}, "matters": {"yes", "no"},
         "rank": {"right", "too-high", "too-low"},
         "kind": {"code", "test", "wording", "config", "data", "process"},
         "method": {"re-ran", "re-read", "record"}}
SESSION = re.compile(r"[A-Za-z0-9._-]{1,64}")
# A record's third line (review_record has the shape); the merge guard never reads it.
ROUND = re.compile("<!-- loadout" r":round((?: [a-z]+=[A-Za-z0-9._,:-]+)+) -->")
UNSTAMPED = "unstamped"  # the `v` of a record with no round line: one posted before the line existed
# The estimate's rate, in US dollars per million tokens. The reviewers run on Opus, whose list price is $4 per million
# input tokens and $20 per million output tokens (Claude Opus 5.5, Anthropic's API pricing as the claude-api skill
# lists it). The harness prints one total per agent, not input and output apart, so the rate blends them, assuming
# 90% input (a reviewer reads far more than it writes): 0.9 * 4 + 0.1 * 20. Cache reads, billed lower, make the true
# cost lower; another model makes it different: the column is an estimate at list price, never a bill.
BLENDED_USD_PER_MTOK = 5.6
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


def trusted_record(c: dict) -> tuple[str, dict] | None:
    """The record's kind and marker fields when `c` is a record the merge guard would trust, else None."""
    if c.get("author_association") not in TRUSTED or c.get("updated_at") != c.get("created_at"):
        return None
    lines = (c.get("body") or "").split("\n")
    m = MARKER.fullmatch(lines[1].strip()) if len(lines) > 1 else None
    title = TITLE[m.group(1)].fullmatch(lines[0].strip()) if m else None
    if not title:
        return None
    kind, f = m.group(1), fields(m.group(2))
    if len(f) != len(m.group(2).split()) or not set(f) <= FIELDS[kind]:
        return None  # a repeated or unknown key
    if kind != "audit" and not {"sha", "state"} <= set(f):
        return None
    if kind == "audit":
        return (kind, f) if re.search(rf"\(session {re.escape(f.get('session', ''))}\)$", lines[0].strip()) else None
    said = {"pass": "success", "fail": "failure"}.get(title.group(1), title.group(1))
    if f["state"] != said or (kind == "review" and title.group(2) != f.get("tier")):
        return None  # the title and the marker disagree
    if kind == "review" and f.get("depth", "none") not in DEPTHS:
        return None
    if kind != "audit" and (not SHA.fullmatch(f["sha"]) or ("reviewed" in f and not SHA.fullmatch(f["reviewed"]))):
        return None  # state and tier need no check of their own: they must equal the title's, which TITLE limits
    return kind, f


def round_fields(body: str) -> dict:
    """The round line's fields (review_record has the shape): `v`, `kit`, the counts as integers, `lenses` as a
    list, and `lens` as one dict per agent; `v` is `unstamped` when the third line is no round line."""
    lines = (body or "").replace("\r\n", "\n").split("\n")
    m = ROUND.fullmatch(lines[2].strip()) if len(lines) > 2 else None
    if not m:
        return {"v": UNSTAMPED, "kit": None}
    out: dict = {"lens": []}
    for kv in m.group(1).split():
        k, v = kv.split("=", 1)
        if k == "lens":
            parts = v.split(":")
            if len(parts) == 6 and all(p.isdigit() for p in parts[3:]):
                out["lens"].append({"name": parts[0], "model": parts[1], "effort": parts[2], "tokens": int(parts[3]),
                                    "seconds": int(parts[4]), "findings": int(parts[5])})
        elif k == "lenses":
            out[k] = v.split(",")
        else:
            out.setdefault(k, int(v) if v.isdigit() else v)
    out.setdefault("v", UNSTAMPED)
    out.setdefault("kit", None)
    return out


def stamp(rf: dict) -> dict:
    """The fields every harvested row carries from its round line."""
    return {"v": rf["v"], "kit": rf["kit"]}


def raw_output(body: str) -> str:
    """The verifier's output that verdict.sh put under <details>, in a fence of three or more backticks."""
    m = re.search(r"<details><summary>[^<]*</summary>\s*\n(?:Clipped[^\n]*\n\s*\n)?(?:Escaped for GitHub[^\n]*\n\s*\n)?"
                  r"(`{3,})[a-z]*\n", body)
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


def bound(value: str | None, end: bool) -> str | None:
    """A window bound as GitHub writes times; a plain date covers its whole day."""
    if value is None:
        return None
    if not WHEN.fullmatch(value):
        sys.exit(f"audit.py: a window bound is YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ, got {value!r}")
    return value if "T" in value else value + ("T23:59:59Z" if end else "T00:00:00Z")


def harvest(a: argparse.Namespace) -> int:
    a.since, a.until = bound(a.since, False), bound(a.until, True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: dict[str, list] = defaultdict(list)
    for repo in a.repo:
        for pr in pages(f"repos/{repo}/pulls?state=all&sort=updated&direction=desc"):
            if pr["updated_at"] < a.since:
                break
            n = pr["number"]
            row = {"repo": repo, "pr": n, "title": pr["title"], "state": pr["state"],
                   "created_at": pr["created_at"], "merged_at": pr.get("merged_at"),
                   "head": pr["head"]["sha"], "branch": pr["head"]["ref"]}
            rows["prs"].append(row)
            newest = None  # the newest trusted comment with a review marker line, picked as the merge guard picks it
            for c in pages(f"repos/{repo}/issues/{n}/comments"):
                lines2 = (c.get("body") or "").split("\n")
                if (c.get("author_association") in TRUSTED and len(lines2) > 1
                        and GUARD_REVIEW.match(lines2[1])
                        and not (row["merged_at"] and c["created_at"] > row["merged_at"])  # what the guard saw at merge
                        and (newest is None or (c["created_at"], c["id"]) > (newest["created_at"], newest["id"]))):
                    newest = c
                if not (rec := trusted_record(c)):
                    continue
                kind, f = rec
                if kind != "audit" and not (a.since <= c["created_at"] <= (a.until or c["created_at"])):
                    continue  # rounds and gates of the window only; audit records are read whenever posted
                lines = c["body"].split("\n")
                base = {"repo": repo, "pr": n, "comment": c["id"], "url": c.get("html_url"),
                        "created_at": c["created_at"]}
                rf = round_fields(c["body"])
                if kind == "gates":
                    rows["gates"].append({**base, "sha": f.get("sha"), "state": f.get("state"), **stamp(rf),
                                          "seconds": rf.get("seconds") if isinstance(rf.get("seconds"), int) else None})
                elif kind == "audit":
                    for j in audit_json(c["body"]):
                        if isinstance(j, dict) and type(j.get("round")) is int and isinstance(j.get("ids"), list):
                            # the record's own repo, PR and session win over the block's keys
                            rows["audits"].append({**{k: j.get(k) for k in JUDGMENT_KEYS}, **base,
                                                   "session": f.get("session"), "backfill": f.get("backfill") == "1",
                                                   **stamp(rf)})
                else:
                    raw = raw_output(c["body"])
                    parsed = verifier_output.parse(raw)
                    reviewers = next((ln.split(":", 1)[1].strip() for ln in lines
                                      if ln.startswith("- Reviewers:")), "")
                    fs = [b for b in parsed["findings"] if not SKIPPED.match(b["section"])]
                    try:  # the verifier's own list of must-fix findings, when the record has one
                        listed = {i.strip() for e in blocking.read(raw) for i in e["ids"].split(",")}
                    except ValueError:
                        listed = None  # a record made before the `Blocking:` line, or a malformed one
                    for b in fs:
                        if listed is not None:
                            b["must_fix"] = bool(set(b["ids"]) & listed)
                        rank = (b["rank"] or b["section"]).lower()
                        b["kind_rank"] = ("must-fix" if b["must_fix"] else "nit" if rank.startswith("nit")
                                          else "pre-existing" if rank.startswith("pre") else "other")
                    harms = None if listed is None else len(blocking.read(raw))
                    rows["rounds"].append({
                        **base, "sha": f.get("sha"), "reviewed": f.get("reviewed"), "state": f.get("state"),
                        "tier": f.get("tier"), "reviewers": reviewers, "verdict": parsed["verdict"],
                        "blocking_line": harms,
                        "steered": any(s.strip().lower() not in ("", "none") for s in parsed["steering"]),
                        "must_fix": harms if harms is not None else sum(b["must_fix"] for b in fs),
                        "nits": sum(b["kind_rank"] == "nit" for b in fs),
                        "pre_existing": sum(b["kind_rank"] == "pre-existing" for b in fs),
                        **stamp(rf), **{k: rf[k] if isinstance(rf.get(k), int) else None
                                        for k in ("cycle", "dupes", "dismissals", "promoted")},
                        "lead_nits": rf["nits"] if isinstance(rf.get("nits"), int) else None,
                        "repost": rf.get("repost") == 1,
                        "lenses": rf.get("lens", []),
                        "depth": f.get("depth") or (rf["depth"] if isinstance(rf.get("depth"), str) else None),
                        "floor": rf["floor"] if isinstance(rf.get("floor"), str) else None,
                        "planned": (None if not isinstance(rf.get("planned"), str)
                                    else [] if rf["planned"] == "none" else rf["planned"].split(",")),
                        "tokens": sum(x["tokens"] for x in rf.get("lens", [])),
                        "seconds": sum(x["seconds"] for x in rf.get("lens", []))})
                    for b in fs:
                        rows["findings"].append({
                            "repo": repo, "pr": n, "round": c["id"], "ids": b["ids"], "section": b["section"],
                            "rank": b["kind_rank"], "must_fix": b["must_fix"], "harm": b["harm"],
                            **{k: b["fields"].get(k) for k in ("lens", "location", "claim")}})
            # what the merge guard reads: the newest trusted comment whose marker line opens `<!-- loadout:review`
            # (as the guard matches it), or "refused" when that record would not count
            nrec = trusted_record(newest) if newest else None
            row["guard_review"] = (None if newest is None else
                                   {"state": nrec[1]["state"], "sha": nrec[1]["sha"]} if nrec and nrec[0] == "review"
                                   else "refused")
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
    if not (d / "findings.jsonl").exists():
        sys.exit(f"audit.py: {a.dir} holds no harvest; run `audit.py harvest --out {a.dir}` first")
    if a.n < 1:
        sys.exit("audit.py: --n is at least 1")
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
        if not isinstance(j, dict) or type(j.get("round")) is not int:
            sys.exit(f"audit.py: judgment {i} needs an integer `round`")
        if extra := set(j) - JUDGMENT_KEYS:
            sys.exit(f"audit.py: judgment {i} has keys a judgment does not carry: {sorted(extra)}")
        ids = j.get("ids")
        if not isinstance(ids, list) or not ids or not all(isinstance(x, str) and FINDING_ID.fullmatch(x)
                                                           for x in ids):
            sys.exit(f"audit.py: judgment {i}: `ids` is a list of finding ids such as COR-1")
        for k, allowed in KINDS.items():
            if j.get(k) not in allowed:
                sys.exit(f"audit.py: judgment {i}: `{k}` is one of {sorted(allowed)}, got {j.get(k)!r}")
        if not isinstance(j.get("note"), str) or not j["note"].strip() or "\n" in j["note"]:
            sys.exit(f"audit.py: judgment {i}: `note` is one line of text")
    return items


def record(a: argparse.Namespace) -> int:
    if not SESSION.fullmatch(a.session):
        sys.exit("audit.py: --session is letters, digits, '.', '_' or '-', at most 64")
    items = check_judgments(json.loads(Path(a.file).read_text(encoding="utf-8")))
    for rnd in sorted({j["round"] for j in items}):  # each judged round is a trusted review record on this PR
        c = gh_json(f"repos/{a.repo}/issues/comments/{rnd}") or {}
        rec = trusted_record(c) if isinstance(c, dict) else None
        if not rec or rec[0] != "review" or not str(c.get("issue_url", "")).endswith(f"/issues/{a.pr}"):
            sys.exit(f"audit.py: comment {rnd} is no trusted review record on {a.repo}#{a.pr}")
        blocks = {tuple(b["ids"]) for b in verifier_output.parse(raw_output(c["body"]))["findings"]
                  if not SKIPPED.match(b["section"])}  # the findings harvest counts: no dropped or unverified block
        for j in items:
            if j["round"] == rnd and tuple(j["ids"]) not in blocks:
                sys.exit(f"audit.py: {', '.join(j['ids'])} is no finding of review record {rnd}; use a block's ids")
    cell = lambda s: str(s).replace("|", "\\|")  # noqa: E731
    marker = "<!-- loadout" + f":audit session={a.session}" + (" backfill=1" if a.backfill else "") + " -->"
    try:
        stamped = review_record.round_line([])
    except (OSError, ValueError) as exc:
        sys.exit(f"audit.py: cannot read the review path's version: {exc}")
    body = "\n".join([
        f"🤖 Audit: {len(items)} finding{'s' if len(items) != 1 else ''} re-checked (session {a.session})", marker,
        stamped, "",
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
    latest: dict[tuple, dict] = {}
    for j in sorted(load(d, "audits"), key=lambda j: (j.get("created_at") or "", j.get("comment") or 0)):
        latest[(j.get("session"), j["repo"], j["pr"], j["round"], tuple(j["ids"]))] = j  # a re-posted record counts once
    audits = [j for j in latest.values() if session in (None, j.get("session"))]
    by_pr: dict[tuple, list] = defaultdict(list)
    for r in rounds:
        by_pr[(r["repo"], r["pr"])].append(r)
    changes = []
    for k, rs in by_pr.items():
        p = prs.get(k, {})
        series = [r["must_fix"] for r in rs]
        g = p.get("guard_review", rs[-1])  # the merge guard's own reading when the harvest recorded it
        passed_head = (isinstance(g, dict) and g.get("state") == "success"
                       and p.get("head") in (g.get("sha"), None))
        changes.append({"repo": k[0], "pr": k[1], "rounds": len(rs), "series": series,
                        "first_pass": rs[0]["state"] == "success", "merged": bool(p.get("merged_at")),
                        "grew": any(b > a for a, b in zip(series, series[1:])),
                        "merged_without_pass": bool(p.get("merged_at")) and not passed_head,
                        "steered_rounds": sum(r["steered"] for r in rs)})
    lens: dict[str, Counter] = defaultdict(Counter)
    # Findings by the effort their lens ran at (the round line's lens= entries); a finding several lenses raised counts
    # once under each distinct effort among them, and `unstamped` holds those whose round line gave no effort.
    effort: dict[str, Counter] = defaultdict(Counter)
    ran = {(r["repo"], r["pr"], r["comment"]): r.get("lenses") or [] for r in rounds}
    for f in finds:
        agents = ran.get((f["repo"], f["pr"], f["round"]), [])
        levels = {a["effort"] for x in lenses(f.get("lens")) for a in agents if a["name"].startswith(x)}
        for level in levels or {UNSTAMPED}:
            effort[level]["must_fix" if f["must_fix"] else "other"] += 1
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
    return {**_costs(rounds, by_pr),
        "rounds": len(rounds), "changes": len(changes),
        "passes": sum(r["state"] == "success" for r in rounds),
        "first_round_pass": wilson(sum(c["first_pass"] for c in changes), len(changes)),
        "rounds_per_merge": round(sum(c["rounds"] for c in merged) / len(merged), 2) if merged else None,
        "must_fix": sum(f["must_fix"] for f in finds),
        "must_fix_with_harm": wilson(sum(bool(f["harm"]) for f in finds if f["must_fix"]),
                                     sum(f["must_fix"] for f in finds)),
        "lens": {k: dict(v) for k, v in sorted(lens.items())},
        "effort": {k: dict(v) for k, v in sorted(effort.items())},
        "depth": dict(sorted(Counter(r.get("depth") or UNSTAMPED for r in rounds).items())),
        "audited": len(audits),
        "wrong": wilson(sum(j["correct"] == "no" for j in checkable), len(checkable)),
        "matters": wilson(sum(j.get("matters") == "yes" for j in checkable), len(checkable)),
        "must_fix_too_high": wilson(sum(j["rank"] == "too-high" for j in judged_mf), len(judged_mf)),
        "must_fix_wording": wilson(sum(j.get("kind") == "wording" for j in judged_mf), len(judged_mf)),
        "too_low": sum(j.get("rank") == "too-low" for j in audits),
        "attention": [c for c in changes if c["grew"] or c["merged_without_pass"] or c["steered_rounds"]],
        "series": changes,
    }


def est_usd(tokens: int) -> float:
    """The estimate at list price (BLENDED_USD_PER_MTOK has the rate and its assumption)."""
    return round(tokens * BLENDED_USD_PER_MTOK / 1_000_000, 2)


def _costs(rounds: list[dict], by_pr: dict[tuple, list]) -> dict:
    """Rounds grouped by the review path's version, and the reviewers' tokens and seconds per PR, repo, day, month.

    Must-fix and nits are the harvest's own counts (the same ones the headline numbers use), so stamped and unstamped
    rounds compare; duplicates, tokens and seconds come from the round line, so an unstamped round adds none of them.
    Cycles to pass: per PR, the cycle its first passing round's line names (its place among the PR's rounds when the
    line has none), averaged within the version of that passing round. Seconds are summed over agents, not wall time.
    A round's usage counts once: a re-post (`repost=1`, no agent ran) adds none, and neither does a later record of the
    same PR, reviewed commit and per-agent usage as an earlier one.
    """
    seen: set[tuple] = set()
    usage: dict[int, tuple[int, int]] = {}
    for r in rounds:
        k = (r["repo"], r["pr"], r.get("reviewed"), json.dumps(r.get("lenses") or []))
        fresh = not r.get("repost") and k not in seen
        seen.add(k)
        usage[id(r)] = (r.get("tokens") or 0, r.get("seconds") or 0) if fresh else (0, 0)
    by_v: dict[str, dict] = {}
    for r in rounds:
        g = by_v.setdefault(r.get("v") or UNSTAMPED, {"rounds": 0, "passes": 0, "to_pass": [], "must_fix": 0,
                                                       "nits": 0, "dupes": 0, "tokens": 0, "seconds": 0})
        g["rounds"] += 1
        g["passes"] += r["state"] == "success"
        g["must_fix"] += r["must_fix"]
        g["nits"] += r["nits"]
        g["dupes"] += r.get("dupes") or 0
        g["tokens"] += usage[id(r)][0]
        g["seconds"] += usage[id(r)][1]
    for rs in by_pr.values():
        for i, r in enumerate(rs):
            if r["state"] == "success":
                cyc = r.get("cycle")
                by_v[r.get("v") or UNSTAMPED]["to_pass"].append(cyc if isinstance(cyc, int) else i + 1)
                break
    for g in by_v.values():
        t = g.pop("to_pass")
        g["cycles_to_pass"] = round(sum(t) / len(t), 2) if t else None
        g["est_usd"] = est_usd(g["tokens"])
    totals: dict[str, dict] = {"pr": {}, "repo": {}, "day": {}, "month": {}}
    for r in rounds:
        when = r.get("created_at") or ""
        for by, k in (("pr", f"{r['repo']}#{r['pr']}"), ("repo", r["repo"]), ("day", when[:10]), ("month", when[:7])):
            t = totals[by].setdefault(k, {"rounds": 0, "tokens": 0, "seconds": 0})
            t["rounds"] += 1
            t["tokens"] += usage[id(r)][0]
            t["seconds"] += usage[id(r)][1]
    for t in (t for by in totals.values() for t in by.values()):
        t["est_usd"] = est_usd(t["tokens"])
    return {"by_version": dict(sorted(by_v.items())), "cost": {by: dict(sorted(v.items())) for by, v in totals.items()},
            "usd_per_mtok": BLENDED_USD_PER_MTOK}


def summary(a: argparse.Namespace) -> int:
    if not (Path(a.dir) / "rounds.jsonl").exists():
        sys.exit(f"audit.py: {a.dir} holds no harvest; run `audit.py harvest --out {a.dir}` first")
    if a.session and not any(j.get("session") == a.session for j in load(Path(a.dir), "audits")):
        sys.exit(f"audit.py: no audit record in {a.dir} carries session {a.session}")
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
            ("Mattered, of those checkable", pct(s["matters"])), ("Must-fix ranked too high", pct(s["must_fix_too_high"])),
            ("Must-fix about wording only", pct(s["must_fix_wording"])), ("Ranked too low", s["too_low"])]
    print("| Measure | Value |\n|---|---|")
    for k, v in rows:
        print(f"| {k} | {v} |")
    print("\n| Lens | Must-fix | Alone | Other | Alone |\n|---|---|---|---|---|")
    for k, v in s["lens"].items():
        print(f"| {k} | {v.get('must_fix', 0)} | {v.get('alone_must_fix', 0)} | {v.get('other', 0)} | "
              f"{v.get('alone_other', 0)} |")
    print("\n| Lens effort | Must-fix | Other |\n|---|---|---|")
    for k, v in s["effort"].items():
        print(f"| {k} | {v.get('must_fix', 0)} | {v.get('other', 0)} |")
    print("\n| Depth | Rounds |\n|---|---|")
    for k, v in s["depth"].items():
        print(f"| {k} | {v} |")
    print("\n| Needs a look | Rounds | Must-fix per round | Why |\n|---|---|---|---|")
    for c in s["attention"]:
        why = [w for w, on in (("grew", c["grew"]), ("merged without a pass", c["merged_without_pass"]),
                               ("steered", c["steered_rounds"])) if on]
        print(f"| {c['repo']}#{c['pr']} | {c['rounds']} | {', '.join(map(str, c['series']))} | {', '.join(why)} |")
    est = f"Est. USD at list price (${s['usd_per_mtok']}/M tokens)"
    print(f"\n| Review path version | Rounds | Passed | Cycles to pass | Must-fix | Nits | Duplicates merged | Tokens | "
          f"{est} | Agent seconds |\n|---|---|---|---|---|---|---|---|---|---|")
    for v, g in s["by_version"].items():
        print(f"| {v} | {g['rounds']} | {g['passes']} | {g['cycles_to_pass'] if g['cycles_to_pass'] is not None else 'n/a'} "
              f"| {g['must_fix']} | {g['nits']} | {g['dupes']} | {g['tokens']} | {g['est_usd']:.2f} | {g['seconds']} |")
    print(f"\n| Per | Which | Rounds | Tokens | {est} | Agent seconds |\n|---|---|---|---|---|---|")
    for by, label in (("pr", "PR"), ("repo", "repo"), ("day", "day"), ("month", "month")):
        for k, t in s["cost"][by].items():
            print(f"| {label} | {k} | {t['rounds']} | {t['tokens']} | {t['est_usd']:.2f} | {t['seconds']} |")
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
