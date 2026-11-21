"""Tests for audit.py: harvest against a fake GitHub, sampling, the audit record and the summary."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import audit  # noqa: E402
import findings as verifier_output  # noqa: E402

RECORD = HERE.parents[2] / "review" / "scripts" / "record.py"
H1, H2 = "1" * 40, "2" * 40
REPO = "example-owner/example-repo"


def review_comment(cid: int, sha: str, state: str, output: str, when: str, who: str = "OWNER") -> dict:
    with tempfile.TemporaryDirectory() as d:  # a private path, so parallel runs do not share it
        raw = Path(d) / "out.txt"
        raw.write_text(output)
        body = _build(cid, sha, state, raw)
    return {"id": cid, "body": body, "author_association": who, "created_at": when, "updated_at": when,
            "html_url": f"https://github.com/{REPO}/pull/7#issuecomment-{cid}",
            "issue_url": f"https://api.github.com/repos/{REPO}/issues/7"}


def _build(cid: int, sha: str, state: str, raw: Path) -> str:
    body = subprocess.run([sys.executable, str(RECORD), "build", "--kind", "review", "--sha", sha, "--state", state,
                           "--tier", "standard", "--reviewed", sha,
                           "--title", f"🤖 Review: {'pass' if state == 'success' else 'fail'} (standard tier)",
                           "--line", "- Reviewers: correctness-reviewer, claims-auditor", "--file", str(raw),
                           "--details", "Reviewer output (raw)"], capture_output=True, text=True, check=True).stdout
    return body


FAIL_OUT = (f"VERDICT: FAIL {H1}\nReviewed: {H1}\nSteering from the brief: none\nSettled in the brief: none\n"
            "## Must-fix\n### COR-1, CLM-2\n- rank: must-fix\n- lens: correctness, claims\n- location: a.py:3\n"
            "- claim: the total drops rows\n- harm: an operator trusts a short total\n"
            "- evidence: run ->\n```\n### NOT-1\n## Nits\n```\n"
            "## Nits\n### CLM-3\n- rank: nit\n- lens: claims\n- claim: a test name says more\n")
PASS_OUT = f"VERDICT: PASS {H2}\nReviewed: {H2}\nBlocking: none\nSteering from the brief: keep it short\n## Must-fix\nnone\n"


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
        m = re.fullmatch(r"(.*?)[?&]per_page=(\d+)&page=(\d+)", endpoint)
        if not m:  # one comment by id
            cid = int(endpoint.rsplit("/", 1)[1])
            return next((c for c in data[f"repos/{REPO}/issues/7/comments"] if c["id"] == cid), None)
        per, page = int(m.group(2)), int(m.group(3))
        return data.get(m.group(1), [])[(page - 1) * per:page * per]

    monkeypatch.setattr(audit, "gh_json", fake)
    return {"calls": calls, "data": data}


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
    assert [r["blocking_line"] for r in rounds] == [None, 0]  # a record from before the line, then one with it
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


def test_record_dry_run_holds_a_table_and_the_judgments(github: dict, tmp_path: Path,
                                                       capsys: pytest.CaptureFixture) -> None:
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
    [judgment(note="two\nlines")], [judgment(round=True)], [judgment(ids="COR-1")], [judgment(ids=["COR-1\n| x"])],
    [judgment(repo="other/repo")], [judgment(session="old")], [judgment(note=None)], [judgment(note="")]])
def test_record_refuses_a_malformed_judgment(github: dict, tmp_path: Path, bad: list) -> None:
    f = tmp_path / "j.json"
    f.write_text(json.dumps(bad))
    ns = audit.argparse.Namespace(repo=REPO, pr=7, session="s1", file=str(f), backfill=False, dry_run=True)
    with pytest.raises(SystemExit, match="judgment"):
        audit.record(ns)


def test_record_refuses_a_session_id_that_would_break_the_marker(github: dict, tmp_path: Path) -> None:
    f = tmp_path / "j.json"
    f.write_text(json.dumps([judgment()]))
    ns = audit.argparse.Namespace(repo=REPO, pr=7, session="a b -->", file=str(f), backfill=False, dry_run=True)
    with pytest.raises(SystemExit, match="--session"):
        audit.record(ns)


def test_sample_opens_with_a_must_fix_and_skips_judged(github: dict, tmp_path: Path) -> None:
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


def judge_file(tmp: Path, items: list) -> str:
    f = tmp / "j.json"
    f.write_text(json.dumps(items))
    return str(f)


def test_harvest_skips_records_the_merge_guard_would_not_trust(github: dict, tmp_path: Path) -> None:
    comments = github["data"][f"repos/{REPO}/issues/7/comments"]
    edited = dict(review_comment(6, H2, "success", PASS_OUT, "2030-01-02T05:00:00Z"), updated_at="2030-01-09T00:00:00Z")
    loose = {"id": 8, "author_association": "OWNER", "created_at": "2030-01-02T06:00:00Z",
             "updated_at": "2030-01-02T06:00:00Z",
             "body": "🤖 just a note\nsee <!-- loadout" ":review sha=zz state=success --> here\n"}
    bad_sha = dict(review_comment(9, H2, "success", PASS_OUT, "2030-01-02T07:00:00Z"))
    bad_sha["body"] = bad_sha["body"].replace(f"sha={H2}", "sha=zz", 1)
    disagree = dict(review_comment(11, H2, "success", PASS_OUT, "2030-01-02T08:00:00Z"))
    disagree["body"] = disagree["body"].replace("Review: pass", "Review: fail", 1)  # title fail, marker success
    twice = dict(review_comment(12, H2, "success", PASS_OUT, "2030-01-02T09:00:00Z"))
    twice["body"] = twice["body"].replace("state=success", "state=failure state=success", 1)
    gates = {"id": 13, "author_association": "OWNER", "created_at": "2030-01-02T10:00:00Z",
             "updated_at": "2030-01-02T10:00:00Z",
             "body": f"🤖 Gates: failure\n<!-- loadout" f":gates sha={H2} state=success -->\n"}
    comments += [edited, loose, bad_sha, disagree, twice, gates]
    d = harvest(tmp_path)
    assert [r["comment"] for r in rows(d, "rounds")] == [2, 3]
    assert [g["comment"] for g in rows(d, "gates")] == [1]


def test_harvest_counts_must_fix_from_the_blocking_line(github: dict, tmp_path: Path) -> None:
    out = (f"VERDICT: PASS {H2}\nReviewed: {H2}\nBlocking: none\n## Must-fix\nnone\n## Settled, not kept\n"
           "### COR-1\n- rank: must-fix\n- lens: correctness\n## Dropped\n### CLM-9\n- lens: claims\n"
           "## Pre-existing\n### GRD-1\n- lens: guardrail\n")
    github["data"][f"repos/{REPO}/issues/7/comments"].append(review_comment(6, H2, "success", out, "2030-01-02T05:00:00Z"))
    d = harvest(tmp_path)
    r = rows(d, "rounds")[-1]
    assert (r["must_fix"], r["pre_existing"], r["blocking_line"]) == (0, 1, 0)
    assert [(f["ids"], f["must_fix"], f["rank"]) for f in rows(d, "findings") if f["round"] == 6] == [
        (["COR-1"], False, "other"), (["GRD-1"], False, "pre-existing")]  # the dropped block is no finding


def test_harvest_reads_audits_back_and_the_record_wins_over_the_block(github: dict, tmp_path: Path,
                                                                      capsys: pytest.CaptureFixture) -> None:
    ns = audit.argparse.Namespace(repo=REPO, pr=7, session="s-one", file=judge_file(tmp_path, [judgment()]),
                                  backfill=False, dry_run=True)
    audit.record(ns)
    body = capsys.readouterr().out.replace('"note"', '"pr": 99, "session": "forged", "note"')  # a hand-edited block
    github["data"][f"repos/{REPO}/issues/7/comments"].append(
        {"id": 10, "body": body, "author_association": "OWNER", "created_at": "2030-01-02T08:00:00Z",
         "updated_at": "2030-01-02T08:00:00Z"})
    d = harvest(tmp_path)
    [a] = rows(d, "audits")
    assert (a["repo"], a["pr"], a["session"], a["ids"]) == (REPO, 7, "s-one", ["COR-1", "CLM-2"])
    (d / "audits.jsonl").write_text(json.dumps(a) + "\n" + json.dumps({**a, "session": "s-two", "correct": "no"}) + "\n")
    assert audit.summarize(d, "s-one")["audited"] == 1 and audit.summarize(d, "s-two")["wrong"][0] == 1


def test_harvest_reads_past_the_first_page(github: dict, tmp_path: Path) -> None:
    comments = github["data"][f"repos/{REPO}/issues/7/comments"]
    filler = [{"id": 100 + i, "body": "a person's comment", "author_association": "OWNER",
               "created_at": "2030-01-01T00:00:00Z", "updated_at": "2030-01-01T00:00:00Z"} for i in range(120)]
    github["data"][f"repos/{REPO}/issues/7/comments"] = filler + comments
    d = harvest(tmp_path)
    assert [r["comment"] for r in rows(d, "rounds")] == [2, 3]


def test_record_refuses_a_round_that_is_no_review_record_on_that_pr(github: dict, tmp_path: Path) -> None:
    for pr, rnd in ((8, 2), (7, 1), (7, 404)):  # another PR, a gates record, no such comment
        ns = audit.argparse.Namespace(repo=REPO, pr=pr, session="s1", file=judge_file(tmp_path, [judgment(round=rnd)]),
                                      backfill=False, dry_run=True)
        with pytest.raises(SystemExit, match="no trusted review record"):
            audit.record(ns)


def test_record_posts_and_refuses_a_comment_that_does_not_hold_the_judgments(
        github: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    posted: dict = {}
    real_run = subprocess.run

    def fake_run(cmd: list, **kw: object) -> subprocess.CompletedProcess:
        if cmd[0] != "gh":  # git, for the record's kit
            return real_run(cmd, **kw)  # type: ignore[call-overload]
        posted["body"] = Path(cmd[-1].split("@", 1)[1]).read_text()
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"id": 77, "html_url": "u77"}), "")

    monkeypatch.setattr(audit.subprocess, "run", fake_run)
    comments = github["data"][f"repos/{REPO}/issues/7/comments"]
    ns = audit.argparse.Namespace(repo=REPO, pr=7, session="s1", file=judge_file(tmp_path, [judgment()]),
                                  backfill=False, dry_run=False)
    comments.append({"id": 77, "body": "placeholder"})
    for c in comments:  # the read-back returns what was posted
        if c["id"] == 77:
            c["body"] = "x"
    real = audit.gh_json
    monkeypatch.setattr(audit, "gh_json", lambda e: {"body": posted["body"]} if e.endswith("/77") else real(e))
    assert audit.record(ns) == 0 and "u77" in capsys.readouterr().out
    monkeypatch.setattr(audit, "gh_json", lambda e: {"body": "changed"} if e.endswith("/77") else real(e))
    with pytest.raises(SystemExit, match="does not hold the judgments"):
        audit.record(ns)


def test_summary_refuses_a_folder_with_no_harvest(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="holds no harvest"):
        audit.summary(audit.argparse.Namespace(dir=str(tmp_path / "missing"), session=None, json=False))


def test_harvest_keeps_records_up_to_until(github: dict, tmp_path: Path) -> None:
    out = tmp_path / "snap"
    audit.harvest(audit.argparse.Namespace(repo=[REPO], since="2029-12-01T00:00:00Z", until="2030-01-01T12:00:00Z",
                                           out=str(out)))
    assert [r["comment"] for r in rows(out, "rounds")] == [2]


def test_harvest_keeps_rounds_from_since_on(github: dict, tmp_path: Path) -> None:
    d = harvest(tmp_path, since="2030-01-02T00:00:00Z")
    assert [r["comment"] for r in rows(d, "rounds")] == [3] and rows(d, "gates") == []


def test_summary_flags_a_change_whose_must_fix_count_grew(github: dict, tmp_path: Path) -> None:
    d = harvest(tmp_path)
    rounds = rows(d, "rounds")
    rounds[1]["must_fix"], rounds[1]["state"] = 3, "failure"
    (d / "rounds.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rounds))
    [c] = audit.summarize(d, None)["attention"]
    assert c["grew"] and c["series"] == [1, 3]


def test_sample_leaves_out_pre_existing_findings(github: dict, tmp_path: Path) -> None:
    d = harvest(tmp_path)
    found = rows(d, "findings")
    for f in found:
        f["rank"], f["must_fix"] = "pre-existing", False
    (d / "findings.jsonl").write_text("".join(json.dumps(f) + "\n" for f in found))
    audit.sample(audit.argparse.Namespace(dir=str(d), n=5, seed=0))
    assert rows(d, "sample") == []


GOOD = (f"🤖 Review: pass (standard tier)\n<!-- loadout" f":review sha={H2} state=success tier=standard reviewed={H2} -->\n")


@pytest.mark.parametrize("body", [
    GOOD.replace("Review: pass", "Review: fail"),  # the title disagrees with the state
    GOOD.replace("(standard tier)", "(routine tier)"),  # ... or with the tier
    GOOD.replace("state=success", "state=failure state=success"),  # a repeated key
    GOOD.replace(" -->", " extra=1 -->"),  # an unknown key
    GOOD.replace("state=success", "state=maybe"),
    GOOD.replace(f"reviewed={H2}", "reviewed=zz"),
    GOOD.replace("tier=standard", "tier=huge").replace("(standard tier)", "(huge tier)"),
    GOOD.replace("<!-- loadout", "see <!-- loadout"),  # the marker inside other text
    GOOD.replace("🤖 Review: pass (standard tier)", "🤖 Review: pass (standard tier) and more"),
    f"🤖 Gates: failure\n<!-- loadout" f":gates sha={H2} state=success -->\n",
    f"🤖 Audit: 1 finding re-checked (session s-one)\n<!-- loadout" ":audit session=s-two -->\n",
])
def test_trusted_record_refuses_malformed_or_disagreeing_records(body: str) -> None:
    c = {"id": 1, "body": body, "author_association": "OWNER", "created_at": "t", "updated_at": "t"}
    assert audit.trusted_record(c) is None
    assert audit.trusted_record(dict(c, body=GOOD)) == ("review", {"sha": H2, "state": "success", "tier": "standard",
                                                                    "reviewed": H2})


def test_record_refuses_a_round_by_an_untrusted_or_edited_author_or_of_another_kind(github: dict, tmp_path: Path) -> None:
    comments = github["data"][f"repos/{REPO}/issues/7/comments"]
    url = f"https://api.github.com/repos/{REPO}/issues/7"
    comments[0]["issue_url"] = url  # a gates record on the right PR
    comments.append(dict(review_comment(14, H2, "success", PASS_OUT, "2030-01-02T05:00:00Z"),
                         updated_at="2030-01-09T00:00:00Z"))  # edited
    comments.append(dict(review_comment(15, H2, "success", PASS_OUT, "2030-01-02T06:00:00Z"),
                         issue_url=url + "7"))  # PR 77
    for rnd in (1, 4, 14, 15):  # gates, a NONE author, edited, another PR
        ns = audit.argparse.Namespace(repo=REPO, pr=7, session="s1", file=judge_file(tmp_path, [judgment(round=rnd)]),
                                      backfill=False, dry_run=True)
        with pytest.raises(SystemExit, match="no trusted review record"):
            audit.record(ns)


def test_harvest_reads_audit_records_outside_the_window_with_their_backfill_flag(github: dict, tmp_path: Path,
                                                                                capsys: pytest.CaptureFixture) -> None:
    audit.record(audit.argparse.Namespace(repo=REPO, pr=7, session="early", file=judge_file(tmp_path, [judgment()]),
                                          backfill=True, dry_run=True))
    body = capsys.readouterr().out
    github["data"][f"repos/{REPO}/issues/7/comments"] += [
        {"id": 20, "body": body, "author_association": "OWNER", "created_at": "2029-01-01T00:00:00Z",
         "updated_at": "2029-01-01T00:00:00Z"},
        {"id": 21, "body": body, "author_association": "OWNER", "created_at": "2031-01-01T00:00:00Z",
         "updated_at": "2031-01-01T00:00:00Z"}]
    out = tmp_path / "snap"
    audit.harvest(audit.argparse.Namespace(repo=[REPO], since="2030-01-01T00:00:00Z", until="2030-12-31T00:00:00Z",
                                           out=str(out)))
    assert [(a["comment"], a["backfill"]) for a in rows(out, "audits")] == [(20, True), (21, True)]


def test_harvest_counts_a_round_s_must_fix_by_blocking_entries(github: dict, tmp_path: Path) -> None:
    out = (f"VERDICT: FAIL {H2}\nReviewed: {H2}\n"
           'Blocking: [{"ids": "COR-1, CLM-2", "harm": "an operator trusts a total that drops rows"}]\n'
           "## Must-fix\n### COR-1\n- rank: must-fix\n### CLM-2\n- rank: must-fix\n### GRD-3\n- rank: must-fix\n")
    github["data"][f"repos/{REPO}/issues/7/comments"].append(review_comment(6, H2, "failure", out, "2030-01-02T05:00:00Z"))
    d = harvest(tmp_path)
    assert rows(d, "rounds")[-1]["must_fix"] == 1  # one listed entry, though two blocks say must-fix
    assert [f["must_fix"] for f in rows(d, "findings") if f["round"] == 6] == [True, True, False]


def test_summary_leaves_unverifiable_judgments_out_of_the_rates(github: dict, tmp_path: Path) -> None:
    d = harvest(tmp_path)
    (d / "audits.jsonl").write_text("\n".join(json.dumps({"repo": REPO, "pr": 7, "session": "s1", **j}) for j in [
        judgment(correct="no"), judgment(ids=["CLM-3"], correct="unverifiable")]) + "\n")
    assert audit.summarize(d, None)["wrong"][0] == 1


def test_summary_flags_a_merge_whose_newest_review_record_was_edited(github: dict, tmp_path: Path) -> None:
    comments = github["data"][f"repos/{REPO}/issues/7/comments"]
    comments.append(dict(review_comment(16, H2, "failure", FAIL_OUT.replace(H1, H2), "2030-01-02T09:00:00Z"),
                         updated_at="2030-01-02T10:00:00Z"))  # the newest record, edited: the guard refuses it
    [c] = audit.summarize(harvest(tmp_path), None)["series"]
    assert c["merged_without_pass"]


def test_summary_flags_a_merge_whose_newest_review_failed(github: dict, tmp_path: Path) -> None:
    github["data"][f"repos/{REPO}/issues/7/comments"].append(
        review_comment(17, H2, "failure", FAIL_OUT.replace(H1, H2), "2030-01-02T09:00:00Z"))
    [c] = audit.summarize(harvest(tmp_path), None)["series"]
    assert c["merged_without_pass"]


def test_sample_and_summary_refuse_a_folder_or_session_with_nothing_in_it(github: dict, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="holds no harvest"):
        audit.sample(audit.argparse.Namespace(dir=str(tmp_path / "missing"), n=5, seed=0))
    d = harvest(tmp_path)
    with pytest.raises(SystemExit, match="carries session nope"):
        audit.summary(audit.argparse.Namespace(dir=str(d), session="nope", json=False))


def test_record_refuses_a_failed_post(github: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit.subprocess, "run", lambda cmd, **_: subprocess.CompletedProcess(cmd, 1, "", "HTTP 422"))
    ns = audit.argparse.Namespace(repo=REPO, pr=7, session="s1", file=judge_file(tmp_path, [judgment()]),
                                  backfill=False, dry_run=False)
    with pytest.raises(SystemExit, match="posting the audit record failed"):
        audit.record(ns)


def test_audit_json_reads_only_a_list() -> None:
    assert audit.audit_json('```json\n{"round": 2}\n```') == []
    assert audit.audit_json('```json\n[{"round": 2}]\n```') == [{"round": 2}]


def test_summary_takes_the_newest_review_record_as_the_merge_guard_does(github: dict, tmp_path: Path) -> None:
    comments = github["data"][f"repos/{REPO}/issues/7/comments"]
    comments += [  # newer trusted comments the guard does not read as review records
        {"id": 40, "author_association": "OWNER", "created_at": "2030-01-02T09:00:00Z", "updated_at": "2030-01-02T09:00:00Z",
         "body": "🤖 note\n<!-- loadout" ":reviewer-notes x -->\n"},
        {"id": 41, "author_association": "OWNER", "created_at": "2030-01-02T10:00:00Z", "updated_at": "2030-01-02T10:00:00Z",
         "body": f"🤖 Gates: success\n<!-- loadout" f":gates sha={H2} state=success -->\n"}]
    d = harvest(tmp_path)
    [c] = audit.summarize(d, None)["series"]
    assert not c["merged_without_pass"] and rows(d, "prs")[0]["guard_review"] == {"state": "success", "sha": H2}


def test_harvest_labels_a_refused_newest_review_record(github: dict, tmp_path: Path) -> None:
    github["data"][f"repos/{REPO}/issues/7/comments"].append(
        dict(review_comment(42, H2, "success", PASS_OUT, "2030-01-02T09:00:00Z"), updated_at="2030-01-03T00:00:00Z"))
    assert rows(harvest(tmp_path), "prs")[0]["guard_review"] == "refused"


@pytest.mark.parametrize("marker", ["<!-- loadout" ":review state=success tier=standard -->",
                                    "<!-- loadout" f":gates sha={H2} -->"])
def test_trusted_record_needs_sha_and_state(marker: str) -> None:
    title = "🤖 Gates: success" if "gates" in marker else "🤖 Review: pass (standard tier)"
    c = {"id": 1, "body": f"{title}\n{marker}\n", "author_association": "OWNER", "created_at": "t", "updated_at": "t"}
    assert audit.trusted_record(c) is None


def test_harvest_skips_audit_rows_out_of_shape(github: dict, tmp_path: Path) -> None:
    body = ("🤖 Audit: 1 finding re-checked (session s1)\n<!-- loadout" ":audit session=s1 -->\n\n```json\n"
            + json.dumps([{"round": "2", "ids": ["COR-1"]}, {"round": 2, "ids": "COR-1"}, {"round": 2},
                          {"round": 2, "ids": ["COR-1", "CLM-2"]}]) + "\n```\n")
    github["data"][f"repos/{REPO}/issues/7/comments"].append(
        {"id": 43, "body": body, "author_association": "OWNER", "created_at": "2030-01-05T00:00:00Z",
         "updated_at": "2030-01-05T00:00:00Z"})
    assert [a["ids"] for a in rows(harvest(tmp_path), "audits")] == [["COR-1", "CLM-2"]]


def test_summary_counts_a_re_posted_audit_record_once(github: dict, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    audit.record(audit.argparse.Namespace(repo=REPO, pr=7, session="s1", file=judge_file(tmp_path, [judgment()]),
                                          backfill=False, dry_run=True))
    body = capsys.readouterr().out
    for cid in (44, 45):
        github["data"][f"repos/{REPO}/issues/7/comments"].append(
            {"id": cid, "body": body, "author_association": "OWNER", "created_at": "2030-01-05T00:00:00Z",
             "updated_at": "2030-01-05T00:00:00Z"})
    assert audit.summarize(harvest(tmp_path), "s1")["audited"] == 1


def test_record_refuses_ids_that_are_no_finding_of_the_round(github: dict, tmp_path: Path) -> None:
    for ids in (["COR-99"], ["COR-1"]):  # unknown, and only part of the block `COR-1, CLM-2`
        ns = audit.argparse.Namespace(repo=REPO, pr=7, session="s1", file=judge_file(tmp_path, [judgment(ids=ids)]),
                                      backfill=False, dry_run=True)
        with pytest.raises(SystemExit, match="no finding of review record 2"):
            audit.record(ns)


def test_harvest_reads_a_plain_date_as_its_whole_day(github: dict, tmp_path: Path) -> None:
    out = tmp_path / "snap"
    audit.harvest(audit.argparse.Namespace(repo=[REPO], since="2030-01-01", until="2030-01-02", out=str(out)))
    assert [r["comment"] for r in rows(out, "rounds")] == [2, 3]
    with pytest.raises(SystemExit, match="window bound"):
        audit.harvest(audit.argparse.Namespace(repo=[REPO], since="last week", until=None, out=str(out)))


def test_sample_takes_one_finding_per_group_in_turn(tmp_path: Path) -> None:
    rows_ = [{"repo": REPO, "pr": 1, "round": 1, "ids": [f"{lens[:3].upper()}-{i}"], "must_fix": False, "rank": "nit",
              "lens": lens} for lens in ("correctness", "claims") for i in range(2)]
    (tmp_path / "findings.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows_))
    audit.sample(audit.argparse.Namespace(dir=str(tmp_path), n=2, seed=0))
    assert sorted(r["lens"] for r in rows(tmp_path, "sample")) == ["claims", "correctness"]
    with pytest.raises(SystemExit, match="at least 1"):
        audit.sample(audit.argparse.Namespace(dir=str(tmp_path), n=0, seed=0))


def test_harvest_reads_a_record_without_the_backfill_flag_as_live(github: dict, tmp_path: Path,
                                                                  capsys: pytest.CaptureFixture) -> None:
    audit.record(audit.argparse.Namespace(repo=REPO, pr=7, session="live", file=judge_file(tmp_path, [judgment()]),
                                          backfill=False, dry_run=True))
    github["data"][f"repos/{REPO}/issues/7/comments"].append(
        {"id": 46, "body": capsys.readouterr().out, "author_association": "OWNER",
         "created_at": "2030-01-05T00:00:00Z", "updated_at": "2030-01-05T00:00:00Z"})
    assert [a["backfill"] for a in rows(harvest(tmp_path), "audits")] == [False]


# What the merge guard saw at merge time, and the checks each mutant of the last review left green.


def test_merged_without_pass_leaves_out_records_posted_after_the_merge(github: dict, tmp_path: Path) -> None:
    cs = github["data"][f"repos/{REPO}/issues/7/comments"]
    cs.append(review_comment(50, H2, "failure", FAIL_OUT.replace(H1, H2), "2030-01-05T00:00:00Z"))
    [c] = audit.summarize(harvest(tmp_path / "a"), None)["series"]
    assert not c["merged_without_pass"]  # a failing re-review after a guarded merge is no bypass
    cs[:] = [c for c in cs if c["id"] not in (3, 50)]
    cs.append(review_comment(51, H2, "success", PASS_OUT, "2030-01-05T00:00:00Z"))
    [c] = audit.summarize(harvest(tmp_path / "b"), None)["series"]
    assert c["merged_without_pass"]  # a pass posted after an unguarded merge does not hide it
    cs.append(review_comment(52, H2, "success", PASS_OUT, "2030-01-03T00:00:00Z"))  # the merge's own second
    [c] = audit.summarize(harvest(tmp_path / "c"), None)["series"]
    assert not c["merged_without_pass"]


@pytest.mark.parametrize("section", ["Dropped", "Unverified", "Not checked"])
def test_harvest_and_record_leave_out_a_block_the_verifier_did_not_rank(github: dict, tmp_path: Path,
                                                                        section: str) -> None:
    out = (f"VERDICT: PASS {H2}\nReviewed: {H2}\nBlocking: none\n## Must-fix\nnone\n"
           f"## {section}\n### CLM-9\n- lens: claims\n- claim: not a defect\n")
    github["data"][f"repos/{REPO}/issues/7/comments"].append(review_comment(6, H2, "success", out,
                                                                            "2030-01-02T05:00:00Z"))
    assert [f for f in rows(harvest(tmp_path / "h"), "findings") if f["round"] == 6] == []
    ns = audit.argparse.Namespace(repo=REPO, pr=7, session="s1", backfill=False, dry_run=True,
                                  file=judge_file(tmp_path, [judgment(round=6, ids=["CLM-9"], correct="no")]))
    with pytest.raises(SystemExit, match="no finding of review record 6"):
        audit.record(ns)


def test_summary_does_not_flag_an_open_pr_without_a_pass(github: dict, tmp_path: Path) -> None:
    d = harvest(tmp_path)
    prs = rows(d, "prs")
    prs[0]["merged_at"], prs[0]["head"] = None, "3" * 40
    (d / "prs.jsonl").write_text("".join(json.dumps(p) + "\n" for p in prs))
    [c] = audit.summarize(d, None)["series"]
    assert not c["merged_without_pass"]


def test_summary_counts_a_must_fix_without_a_harm_against_the_harm_rate(github: dict, tmp_path: Path) -> None:
    d = harvest(tmp_path)
    found = rows(d, "findings") + [{"repo": REPO, "pr": 7, "round": 2, "ids": ["GRD-8"], "rank": "must-fix",
                                    "must_fix": True, "harm": None, "lens": "guardrail"}]
    (d / "findings.jsonl").write_text("".join(json.dumps(f) + "\n" for f in found))
    assert audit.summarize(d, None)["must_fix_with_harm"][0] == 0.5


def test_summary_does_not_flag_a_steady_must_fix_count(github: dict, tmp_path: Path) -> None:
    d = harvest(tmp_path)
    rounds = rows(d, "rounds")
    rounds[1]["must_fix"], rounds[1]["state"] = 1, "failure"
    (d / "rounds.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rounds))
    [c] = audit.summarize(d, None)["series"]
    assert c["series"] == [1, 1] and not c["grew"]


def test_sample_draws_every_lens_before_a_second_of_any(tmp_path: Path) -> None:
    rows_ = [{"repo": REPO, "pr": 1, "round": 1, "ids": [f"{lens[:3].upper()}-{i}"], "must_fix": False,
              "rank": "nit", "lens": lens} for lens in ("correctness", "claims", "guardrail") for i in range(4)]
    (tmp_path / "findings.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows_))
    for seed in range(5):
        audit.sample(audit.argparse.Namespace(dir=str(tmp_path), n=3, seed=seed))
        assert sorted(r["lens"] for r in rows(tmp_path, "sample")) == ["claims", "correctness", "guardrail"]


@pytest.mark.parametrize(("field", "bad"), [("matters", "maybe"), ("kind", "other"), ("method", "guess")])
def test_record_refuses_a_value_out_of_its_set(github: dict, tmp_path: Path, field: str, bad: str) -> None:
    ns = audit.argparse.Namespace(repo=REPO, pr=7, session="s1", backfill=False, dry_run=True,
                                  file=judge_file(tmp_path, [judgment(**{field: bad})]))
    with pytest.raises(SystemExit):
        audit.record(ns)


def test_summary_keeps_the_newest_of_two_differing_re_posts(github: dict, tmp_path: Path,
                                                            capsys: pytest.CaptureFixture) -> None:
    for cid, correct in ((44, "yes"), (45, "no")):
        audit.record(audit.argparse.Namespace(repo=REPO, pr=7, session="s1", backfill=False, dry_run=True,
                                              file=judge_file(tmp_path, [judgment(correct=correct)])))
        github["data"][f"repos/{REPO}/issues/7/comments"].append(
            {"id": cid, "body": capsys.readouterr().out, "author_association": "OWNER",
             "created_at": f"2030-01-0{cid - 39}T00:00:00Z", "updated_at": f"2030-01-0{cid - 39}T00:00:00Z"})
    s = audit.summarize(harvest(tmp_path), "s1")
    assert s["audited"] == 1 and s["wrong"][0] == 1  # the later record, which says wrong, wins


def test_harvest_skips_a_non_dict_row_in_an_audit_block(github: dict, tmp_path: Path) -> None:
    body = ("🤖 Audit: 1 finding re-checked (session s1)\n<!-- loadout" ":audit session=s1 -->\n\n"
            "```json\n[1, \"x\"]\n```\n")
    github["data"][f"repos/{REPO}/issues/7/comments"].append(
        {"id": 47, "body": body, "author_association": "OWNER", "created_at": "2030-01-05T00:00:00Z",
         "updated_at": "2030-01-05T00:00:00Z"})
    assert rows(harvest(tmp_path), "audits") == []


# findings.py: each parse rule on its own


def test_findings_a_shorter_or_other_fence_does_not_close_a_fence() -> None:
    text = "## Must-fix\n````\n```\n### COR-1\n````\n### COR-2\n- rank: must-fix\n- harm: rows drop\n"
    assert [b["ids"] for b in verifier_output.parse(text)["findings"]] == [["COR-2"]]
    text = "## Must-fix\n```\n~~~\n### COR-1\n```\n"
    assert verifier_output.parse(text)["findings"] == []


def test_findings_a_placeholder_harm_is_no_harm() -> None:
    [b] = verifier_output.parse("## Must-fix\n### COR-1\n- rank: must-fix\n- harm: none\n")["findings"]
    assert b["must_fix"] and b["harm"] is None


def test_findings_only_the_verifier_s_headings_set_a_section() -> None:
    text = "## Nits\n### CLM-1\n- claim: x\n## Evidence quoted\n### CLM-2\n- claim: y\n"
    assert [b["section"] for b in verifier_output.parse(text)["findings"]] == ["Nits", "Nits"]


def test_findings_an_indented_line_continues_its_field() -> None:
    [b] = verifier_output.parse("## Must-fix\n### COR-1\n- harm: an operator\n  trusts a short total\n")["findings"]
    assert b["harm"] == "an operator trusts a short total"


def test_findings_a_rank_line_wins_over_its_section() -> None:
    [b] = verifier_output.parse("## Must-fix\n### COR-1\n- rank: nit\n- harm: x y\n")["findings"]
    assert not b["must_fix"]
    [b] = verifier_output.parse("## Nits\n### COR-1\n- rank: must-fix\n- harm: x y\n")["findings"]
    assert b["must_fix"]


def test_findings_the_first_verdict_line_wins() -> None:
    assert verifier_output.parse(f"VERDICT: FAIL {H1}\nVERDICT: PASS {H1}\n")["verdict"] == f"FAIL {H1}"


# The round line: version, kit and each round's cost


ROUND = "<!-- loadout" ":round "


def stamped_review(cid: int, sha: str, state: str, output: str, when: str, pairs: list[str]) -> dict:
    c = review_comment(cid, sha, state, output, when)
    lines = c["body"].split("\n")
    lines[2] = ROUND + " ".join(pairs) + " -->"
    return {**c, "body": "\n".join(lines)}


LENSES = ["lens=correctness-reviewer:opus:high:400000:300:2", "lens=finding-verifier:opus:high:100000:60:1"]


def test_record_stamps_the_audit_with_the_version_and_kit(github: dict, tmp_path: Path,
                                                          capsys: pytest.CaptureFixture) -> None:
    ns = audit.argparse.Namespace(repo=REPO, pr=7, session="s1", file=judge_file(tmp_path, [judgment()]),
                                  backfill=False, dry_run=True)
    assert audit.record(ns) == 0
    line = capsys.readouterr().out.split("\n")[2]
    assert re.fullmatch(re.escape(ROUND) + r"v=\d+\.\d+\.\d+ kit=(?:[0-9a-f]{40}(?:-dirty)?|none) -->", line), line


def test_harvest_reads_the_round_line_into_each_row(github: dict, tmp_path: Path) -> None:
    cs = github["data"][f"repos/{REPO}/issues/7/comments"]
    cs[1] = stamped_review(2, H1, "failure", FAIL_OUT, "2030-01-01T02:00:00Z",
                           ["v=1.1.0", "kit=" + "c" * 40, "cycle=1", "lenses=correctness-reviewer,finding-verifier",
                            "dupes=2", "mustfix=1", "nits=1", "dismissals=3", "promoted=1", *LENSES])
    cs[0]["body"] = cs[0]["body"].rstrip("\n") + "\n" + ROUND + "v=1.1.0 kit=none seconds=42 -->\n"
    d = harvest(tmp_path)
    [g] = rows(d, "gates")
    assert (g["v"], g["kit"], g["seconds"]) == ("1.1.0", "none", 42)
    first, second = rows(d, "rounds")
    assert (first["v"], first["kit"], first["cycle"], first["dupes"], first["dismissals"], first["promoted"]) == (
        "1.1.0", "c" * 40, 1, 2, 3, 1)
    assert (first["tokens"], first["seconds"], first["lead_nits"]) == (500000, 360, 1)
    assert first["lenses"][0] == {"name": "correctness-reviewer", "model": "opus", "effort": "high",
                                  "tokens": 400000, "seconds": 300, "findings": 2}
    assert second["v"] == audit.review_record.version() and second["tokens"] == 0 and second["cycle"] is None


@pytest.mark.parametrize("third", ["", "<!-- loadout" ":round v=1.1.0 -- garbage", "plain text"])
def test_harvest_reads_a_record_without_a_round_line_as_unstamped(github: dict, tmp_path: Path, third: str) -> None:
    cs = github["data"][f"repos/{REPO}/issues/7/comments"]
    lines = cs[1]["body"].split("\n")
    cs[1]["body"] = "\n".join(lines[:2] + [third] + lines[3:])
    d = harvest(tmp_path)
    assert rows(d, "rounds")[0]["v"] == "unstamped" and rows(d, "gates")[0]["v"] == "unstamped"
    assert rows(d, "rounds")[0]["must_fix"] == 1  # the line two record still counts


def test_summary_groups_rounds_by_version_and_totals_their_cost(github: dict, tmp_path: Path,
                                                                capsys: pytest.CaptureFixture) -> None:
    cs = github["data"][f"repos/{REPO}/issues/7/comments"]
    lines = cs[1]["body"].split("\n")
    cs[1]["body"] = "\n".join(lines[:2] + [""] + lines[3:])  # an unstamped first round
    cs[2] = stamped_review(3, H2, "success", PASS_OUT, "2030-02-02T02:00:00Z",
                           ["v=1.1.0", "kit=none", "cycle=2", "lenses=correctness-reviewer,finding-verifier",
                            "dupes=4", "mustfix=0", "nits=0", *LENSES])
    d = harvest(tmp_path)
    before = {k: v for k, v in audit.summarize(d, None).items() if k not in ("by_version", "cost", "usd_per_mtok")}
    s = audit.summarize(d, None)
    assert s["by_version"]["unstamped"] == {"rounds": 1, "passes": 0, "must_fix": 1, "nits": 1, "dupes": 0,
                                            "tokens": 0, "seconds": 0, "cycles_to_pass": None, "est_usd": 0.0}
    assert s["by_version"]["1.1.0"] == {"rounds": 1, "passes": 1, "must_fix": 0, "nits": 0, "dupes": 4,
                                        "tokens": 500000, "seconds": 360, "cycles_to_pass": 2,
                                        "est_usd": round(500000 * audit.BLENDED_USD_PER_MTOK / 1e6, 2)}
    assert s["cost"]["pr"] == {f"{REPO}#7": {"rounds": 2, "tokens": 500000, "seconds": 360, "est_usd": 2.8}}
    assert s["cost"]["repo"][REPO]["tokens"] == 500000
    assert s["cost"]["month"] == {"2030-01": {"rounds": 1, "tokens": 0, "seconds": 0, "est_usd": 0.0},
                                  "2030-02": {"rounds": 1, "tokens": 500000, "seconds": 360, "est_usd": 2.8}}
    assert set(s["cost"]["day"]) == {"2030-01-01", "2030-02-02"}
    assert (s["rounds"], s["passes"], s["must_fix"]) == (2, 1, 1) and before == {
        k: v for k, v in s.items() if k not in ("by_version", "cost", "usd_per_mtok")}
    audit.summary(audit.argparse.Namespace(dir=str(d), session=None, json=False))
    out = capsys.readouterr().out
    assert "| Review path version |" in out and "| 1.1.0 | 1 | 1 | 2.0 | 0 | 0 | 4 | 500000 | 2.80 | 360 |" in out
    assert f"| PR | {REPO}#7 | 2 | 500000 | 2.80 | 360 |" in out and "Est. USD at list price" in out


def test_the_cost_rate_is_the_stated_blend_of_the_opus_list_price() -> None:
    assert audit.BLENDED_USD_PER_MTOK == pytest.approx(0.9 * 4 + 0.1 * 20)


def round_row(n: int, state: str, v: str = "1.1.0", cycle: int | None = None, tokens: int = 0, **k: object) -> dict:
    lens = [{"name": "x", "model": "opus", "effort": "high", "tokens": tokens, "seconds": 10, "findings": 0}]
    return {"repo": REPO, "pr": 7, "comment": n, "created_at": f"2030-01-0{n}T00:00:00Z", "state": state,
            "must_fix": 0, "nits": 0, "v": v, "cycle": cycle, "dupes": 0, "reviewed": H1,
            "lenses": lens if tokens else [], "tokens": tokens, "seconds": 10 if tokens else 0, **k}


def costs(rows_: list[dict]) -> dict:
    return audit._costs(rows_, {(REPO, 7): rows_})


def test_a_repost_and_a_repeated_record_add_no_usage() -> None:
    first = round_row(1, "success", cycle=1, tokens=400000)
    repost = round_row(2, "success", repost=True)
    again = round_row(3, "success", cycle=1, tokens=400000)  # the same usage posted twice for one reviewed commit
    other = round_row(4, "success", cycle=2, tokens=400000, reviewed=H2)
    c = costs([first, repost, again, other])
    assert c["cost"]["pr"][f"{REPO}#7"] == {"rounds": 4, "tokens": 800000, "seconds": 20, "est_usd": 4.48}
    assert c["by_version"]["1.1.0"]["tokens"] == 800000


def test_harvest_marks_a_repost(github: dict, tmp_path: Path) -> None:
    cs = github["data"][f"repos/{REPO}/issues/7/comments"]
    cs[2] = stamped_review(3, H2, "success", PASS_OUT, "2030-01-02T02:00:00Z",
                           ["v=1.1.0", "kit=none", "repost=1", "lenses=x", "mustfix=0"])
    assert [r["repost"] for r in rows(harvest(tmp_path), "rounds")] == [False, True]


def test_cycles_to_pass_takes_only_each_prs_first_passing_round() -> None:
    c = costs([round_row(1, "failure", cycle=1), round_row(2, "success", cycle=2), round_row(3, "success", cycle=5)])
    assert c["by_version"]["1.1.0"]["cycles_to_pass"] == 2


def test_cycles_to_pass_counts_an_unstamped_rounds_place_among_its_prs_rounds() -> None:
    c = costs([round_row(1, "failure", v="unstamped"), round_row(2, "failure", v="unstamped"),
               round_row(3, "success", v="unstamped")])
    assert c["by_version"]["unstamped"]["cycles_to_pass"] == 3


def test_harvest_reads_only_line_three_as_the_round_line(github: dict, tmp_path: Path) -> None:
    quoted = FAIL_OUT + "\n" + ROUND + "v=9.9.9 kit=none lens=x:opus:high:999999:9:9 -->\n"
    cs = github["data"][f"repos/{REPO}/issues/7/comments"]
    c = review_comment(2, H1, "failure", quoted, "2030-01-01T02:00:00Z")
    lines = c["body"].split("\n")
    cs[1] = {**c, "body": "\n".join(lines[:2] + [""] + lines[3:])}  # unstamped, its raw output quoting a round line
    r = rows(harvest(tmp_path), "rounds")[0]
    assert r["v"] == "unstamped" and r["tokens"] == 0


def test_harvest_stamps_audit_rows_with_their_records_version_and_kit(github: dict, tmp_path: Path,
                                                                      capsys: pytest.CaptureFixture) -> None:
    ns = audit.argparse.Namespace(repo=REPO, pr=7, session="s1", file=judge_file(tmp_path, [judgment()]),
                                  backfill=False, dry_run=True)
    audit.record(ns)
    body = capsys.readouterr().out.replace(f"kit={audit.review_record.kit()}", "kit=" + "d" * 40)
    github["data"][f"repos/{REPO}/issues/7/comments"].append(
        {"id": 9, "body": body, "author_association": "OWNER", "created_at": "2030-01-03T00:00:00Z",
         "updated_at": "2030-01-03T00:00:00Z"})
    [a] = rows(harvest(tmp_path), "audits")
    assert (a["v"], a["kit"]) == (audit.review_record.version(), "d" * 40)


def test_record_refuses_when_the_review_paths_version_cannot_be_read(github: dict, tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> str:
        raise ValueError("SKILL.md's frontmatter holds no metadata.version line")

    monkeypatch.setattr(audit.review_record, "version", broken)
    ns = audit.argparse.Namespace(repo=REPO, pr=7, session="s1", file=judge_file(tmp_path, [judgment()]),
                                  backfill=False, dry_run=True)
    with pytest.raises(SystemExit, match="cannot read the review path's version"):
        audit.record(ns)
