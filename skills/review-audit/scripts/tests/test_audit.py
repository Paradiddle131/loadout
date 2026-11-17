"""Tests for audit.py: harvest against a fake GitHub, sampling, the audit record and the summary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import audit  # noqa: E402

RECORD = HERE.parents[2] / "review" / "scripts" / "record.py"
H1, H2 = "1" * 40, "2" * 40
REPO = "example-owner/example-repo"


def review_comment(cid: int, sha: str, state: str, output: str, when: str, who: str = "OWNER") -> dict:
    raw = Path(f"/tmp/audit-test-{cid}.txt")
    raw.write_text(output)
    body = subprocess.run([sys.executable, str(RECORD), "build", "--kind", "review", "--sha", sha, "--state", state,
                           "--tier", "standard", "--reviewed", sha,
                           "--title", f"🤖 Review: {'pass' if state == 'success' else 'fail'} (standard tier)",
                           "--line", "- Reviewers: correctness-reviewer, claims-auditor", "--file", str(raw),
                           "--details", "Reviewer output (raw)"], capture_output=True, text=True, check=True).stdout
    raw.unlink()
    return {"id": cid, "body": body, "author_association": who, "created_at": when, "updated_at": when,
            "html_url": f"https://github.com/{REPO}/pull/7#issuecomment-{cid}"}


FAIL_OUT = (f"VERDICT: FAIL {H1}\nReviewed: {H1}\nSteering from the brief: none\nSettled in the brief: none\n"
            "## Must-fix\n### COR-1, CLM-2\n- rank: must-fix\n- lens: correctness, claims\n- location: a.py:3\n"
            "- claim: the total drops rows\n- harm: an operator trusts a short total\n"
            "- evidence: run ->\n```\n### NOT-1\n## Nits\n```\n"
            "## Nits\n### CLM-3\n- rank: nit\n- lens: claims\n- claim: a test name says more\n")
PASS_OUT = f"VERDICT: PASS {H2}\nReviewed: {H2}\nSteering from the brief: keep it short\n## Must-fix\nnone\n"


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> dict:
    data = {
        f"repos/{REPO}/pulls?state=all&sort=updated&direction=desc": [
            {"number": 7, "title": "Fix totals", "state": "closed", "created_at": "2030-01-01T00:00:00Z",
             "updated_at": "2030-01-03T00:00:00Z", "merged_at": "2030-01-03T00:00:00Z",
             "head": {"sha": H2, "ref": "claude/totals"}},
            {"number": 3, "title": "Old", "state": "closed", "created_at": "2029-01-01T00:00:00Z",
             "updated_at": "2029-01-02T00:00:00Z", "merged_at": None, "head": {"sha": H1, "ref": "x"}}],
        f"repos/{REPO}/issues/7/comments": [
            {"id": 1, "body": f"🤖 Gates: success\n<!-- loadout" f":gates sha={H1} state=success -->\n",
             "author_association": "OWNER", "created_at": "2030-01-01T01:00:00Z", "updated_at": "2030-01-01T01:00:00Z"},
            review_comment(2, H1, "failure", FAIL_OUT, "2030-01-01T02:00:00Z"),
            review_comment(3, H2, "success", PASS_OUT, "2030-01-02T02:00:00Z"),
            review_comment(4, H2, "success", PASS_OUT, "2030-01-02T03:00:00Z", who="NONE"),
            {"id": 5, "body": "a person's comment", "author_association": "OWNER",
             "created_at": "2030-01-02T04:00:00Z", "updated_at": "2030-01-02T04:00:00Z"}],
    }
    calls: list[str] = []

    def fake(endpoint: str) -> object:
        calls.append(endpoint)
        base, _, query = endpoint.partition("?per_page=") if "?per_page=" in endpoint else endpoint.partition("&per_page=")
        page = int(query.split("page=")[-1])
        rows = data.get(base, [])
        return rows if page == 1 else []

    monkeypatch.setattr(audit, "gh_json", fake)
    return {"calls": calls}


def harvest(tmp: Path, since: str = "2029-12-01T00:00:00Z") -> Path:
    out = tmp / "snap"
    ns = audit.argparse.Namespace(repo=[REPO], since=since, until=None, out=str(out))
    assert audit.harvest(ns) == 0
    return out


def rows(d: Path, name: str) -> list[dict]:
    return audit.load(d, name)


def test_harvest_reads_trusted_records_into_rows(github: dict, tmp_path: Path) -> None:
    d = harvest(tmp_path)
    assert [p["pr"] for p in rows(d, "prs")] == [7]  # the PR updated before the window stops the walk
    assert [g["sha"] for g in rows(d, "gates")] == [H1]
    rounds = rows(d, "rounds")
    assert [(r["comment"], r["state"], r["must_fix"], r["nits"], r["steered"]) for r in rounds] == [
        (2, "failure", 1, 1, False), (3, "success", 0, 0, True)]  # comment 4 is not a trusted author
    assert rounds[0]["reviewers"] == "correctness-reviewer, claims-auditor"
    f = rows(d, "findings")
    assert [(x["ids"], x["must_fix"], x["harm"], x["lens"]) for x in f] == [
        (["COR-1", "CLM-2"], True, "an operator trusts a short total", "correctness, claims"),
        (["CLM-3"], False, None, "claims")]  # the fenced NOT-1 is quoted text, not a finding


def test_harvest_never_uses_paginate(github: dict, tmp_path: Path) -> None:
    harvest(tmp_path)
    assert github["calls"] and all("per_page=100&page=" in c for c in github["calls"])


def test_raw_output_reads_a_clipped_record() -> None:
    body = ("🤖 Review: fail (standard tier)\n<!-- loadout:review sha=x state=failure -->\n\n"
            "<details><summary>Reviewer output (raw)</summary>\n\nClipped to fit GitHub's comment size: the first 9.\n\n"
            "````text\nVERDICT: FAIL\n```\ninner\n```\n````\n\n</details>\n")
    assert audit.raw_output(body) == "VERDICT: FAIL\n```\ninner\n```"


def judgment(**k: object) -> dict:
    j = {"round": 2, "ids": ["COR-1", "CLM-2"], "correct": "yes", "matters": "yes", "rank": "right",
         "kind": "code", "method": "re-ran", "note": "ran the total; 3 rows short"}
    j.update(k)
    return j


def test_record_dry_run_holds_a_table_and_the_judgments(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    f = tmp_path / "j.json"
    f.write_text(json.dumps([judgment(note="a | pipe")]))
    ns = audit.argparse.Namespace(repo=REPO, pr=7, session="2030-01-05-batch", file=str(f), backfill=True,
                                  dry_run=True)
    assert audit.record(ns) == 0
    body = capsys.readouterr().out
    lines = body.split("\n")
    assert lines[0] == "🤖 Audit: 1 finding re-checked (session 2030-01-05-batch)"
    assert lines[1] == "<!-- loadout" ":audit session=2030-01-05-batch backfill=1 -->"
    assert "| COR-1, CLM-2 | yes | yes | right | code | re-ran | a \\| pipe |" in body
    assert audit.audit_json(body) == [judgment(note="a | pipe")]


@pytest.mark.parametrize("bad", [
    [], [judgment(correct="maybe")], [judgment(rank="fine")], [judgment(round="2")], [judgment(ids=[])],
    [judgment(note="two\nlines")]])
def test_record_refuses_a_malformed_judgment(tmp_path: Path, bad: list) -> None:
    f = tmp_path / "j.json"
    f.write_text(json.dumps(bad))
    ns = audit.argparse.Namespace(repo=REPO, pr=7, session="s1", file=str(f), backfill=False, dry_run=True)
    with pytest.raises(SystemExit):
        audit.record(ns)


def test_record_refuses_a_session_id_that_would_break_the_marker(tmp_path: Path) -> None:
    f = tmp_path / "j.json"
    f.write_text(json.dumps([judgment()]))
    ns = audit.argparse.Namespace(repo=REPO, pr=7, session="a b -->", file=str(f), backfill=False, dry_run=True)
    with pytest.raises(SystemExit):
        audit.record(ns)


def test_sample_takes_must_fix_first_and_skips_judged(github: dict, tmp_path: Path) -> None:
    d = harvest(tmp_path)
    ns = audit.argparse.Namespace(dir=str(d), n=1, seed=0, session=None)
    audit.sample(ns)
    assert [s["ids"] for s in rows(d, "sample")] == [["COR-1", "CLM-2"]]
    (d / "audits.jsonl").write_text(json.dumps({"repo": REPO, "pr": 7, **judgment()}) + "\n")
    audit.sample(audit.argparse.Namespace(dir=str(d), n=5, seed=0, session=None))
    assert [s["ids"] for s in rows(d, "sample")] == [["CLM-3"]]


def test_summary_counts_rounds_lenses_and_audits(github: dict, tmp_path: Path) -> None:
    d = harvest(tmp_path)
    (d / "audits.jsonl").write_text("\n".join(json.dumps({"repo": REPO, "pr": 7, "session": "s1", **j}) for j in [
        judgment(rank="too-high", kind="wording", matters="no"),
        judgment(round=2, ids=["CLM-3"], correct="no", matters="no", rank="right", kind="test")]) + "\n")
    s = audit.summarize(d, None)
    assert (s["rounds"], s["changes"], s["passes"], s["must_fix"]) == (2, 1, 1, 1)
    assert s["first_round_pass"][0] == 0 and s["rounds_per_merge"] == 2
    assert s["must_fix_with_harm"][0] == 1
    assert s["lens"]["correctness"] == {"must_fix": 1} and s["lens"]["claims"] == {"must_fix": 1, "other": 1,
                                                                                    "alone_other": 1}
    assert s["audited"] == 2 and s["wrong"][0] == 0.5
    assert s["must_fix_too_high"][0] == 1 and s["must_fix_wording"][0] == 1  # only the must-fix judgment counts
    [c] = s["attention"]
    assert c["series"] == [1, 0] and c["steered_rounds"] == 1 and not c["grew"] and not c["merged_without_pass"]


def test_summary_flags_a_merge_without_a_pass_on_its_head(github: dict, tmp_path: Path) -> None:
    d = harvest(tmp_path)
    prs = rows(d, "prs")
    prs[0]["head"] = "3" * 40  # merged at a head no review passed
    (d / "prs.jsonl").write_text("".join(json.dumps(p) + "\n" for p in prs))
    [c] = audit.summarize(d, None)["attention"]
    assert c["merged_without_pass"]


def test_wilson_interval() -> None:
    assert audit.wilson(0, 0) == [None, None, None]
    p, lo, hi = audit.wilson(9, 29)
    assert p == 0.31 and 0.17 < lo < 0.2 and 0.48 < hi < 0.51


@pytest.mark.parametrize("text, want", [
    ("correctness, claims", ["correctness", "claims"]), ("claims-auditor", ["claims"]),
    ("control-prober", ["control"]), ("guardrail (also noted by the control", ["guardrail"]),
    ("claims (the leak-hunter's finding is the same)", ["claims"]), (None, ["other"]), ("unnumbered", ["other"])])
def test_lenses_reads_free_text(text: str | None, want: list) -> None:
    assert audit.lenses(text) == want
