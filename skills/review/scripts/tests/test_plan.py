"""The review planner (plan.py) and what verdict.sh records from it: the depth floor of a change's paths, the lenses
and efforts a round must run, and every way around the plan found on an earlier attempt, each refused.

The plan reads only what GitHub names (the PR's head and default branch, that branch's tip, the PR's newest trusted
review record) and the default branch's REVIEW.md; nothing the lead passes may narrow it.
Run: uvx --from pytest==8.4.2 pytest -q skills/review/scripts/tests
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from test_review_scripts import (REVIEW, ROUND, SCRIPTS, World, base_has, env, review_file,  # noqa: F401
                                 round_fields, template_review_md, w)

PLAN = SCRIPTS / "plan.py"
RECORD = SCRIPTS / "record.py"
COR, CLM, GRD, CTL, LEAK = ("correctness-reviewer", "claims-auditor", "guardrail-reviewer", "control-prober",
                            "leak-hunter")
VER = "finding-verifier"
SENSITIVE = [COR, GRD]
HARM = "an operator trusts a total that drops rows"


def plan(w: World, *args: str, **extra: str) -> tuple[int, dict, str]:
    """plan.py's preview for PR 12, as JSON."""
    done = subprocess.run([sys.executable, str(PLAN), "--pr", "12", "--json", *args], cwd=w.repo,
                          env={**w.env, **extra}, capture_output=True, text=True, timeout=60)
    out = json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else {}
    return done.returncode, out, done.stderr


def lenses_of(p: dict) -> list[str]:
    return p["first"] + p["then"]


def must_fix(*ids: str) -> tuple[str, str]:
    """A verifier's `Blocking:` line listing `ids` as one must-fix, and the finding block it points at."""
    line = 'Blocking: [{"ids": "%s", "harm": "%s"}]' % (", ".join(ids), HARM)
    return line, f"## Must-fix\n### {', '.join(ids)}\n- rank: must-fix\n- harm: {HARM}\n"


def verdict(w: World, tmp: Path, sha: str, reviewers: list[str], tier: str, result: str = "PASS",
            ids: tuple[str, ...] = ("COR-1",), depth: str | None = None, effort: dict[str, str] | None = None,
            extra: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    """verdict.sh on PR 12 for `sha`, the round run by `reviewers`, each at `effort` (high by default)."""
    blocking, text = must_fix(*ids) if result == "FAIL" else ("Blocking: none", "No findings.\n")
    args = ["12", "--tier", tier, "--reviewers", ", ".join(reviewers), "--reviewed", sha,
            "--file", review_file(tmp, sha, result, text, blocking), "--cycle", "1", "--dupes", "0", "--nits", "0"]
    for r in reviewers:
        args += ["--lens", f"{r} model=opus effort={(effort or {}).get(r, 'high')} tokens=10 seconds=1 findings=0"]
    if depth:
        args += ["--depth", depth]
    return w.verdict(*args, *extra, cost=False)


def first_round(w: World, tmp: Path, files: dict[str, str], tier: str, reviewers: list[str],
                ids: tuple[str, ...] = ("COR-1",)) -> str:
    """A change of `files` and its first round, recorded as a FAIL listing `ids`; returns the reviewed commit."""
    sha = w.commit(files)
    done = verdict(w, tmp, sha, reviewers, tier, "FAIL", ids)
    assert done.returncode == 0, done.stderr
    return sha


FLOOR = {"routine": "none", "standard": "light", "sensitive": "focused"}


def crafted(sha: str, reviewed: str, output: str, *, tmp: Path, tier: str = "standard",
            state: str = "failure", depth: str | None = "floor") -> str:
    """A review record's body in verdict.sh's shape, built with record.py, holding `output` as its raw output.

    Its depth is its tier's floor unless given (None: a record from before depths), so a test of one of plan.py's
    record filters reaches that filter rather than the depth check before it.
    """
    raw = tmp / f"crafted-{reviewed[:8]}.txt"
    raw.write_text(output)
    title = f"🤖 Review: {'pass' if state == 'success' else 'fail'} ({tier} tier)"
    depth = FLOOR[tier] if depth == "floor" else depth
    return subprocess.run([sys.executable, str(RECORD), "build", "--kind", "review", "--sha", sha, "--state", state,
                           "--tier", tier, "--reviewed", reviewed, "--title", title, "--line", "- x",
                           *(["--depth", depth] if depth else []),
                           "--file", str(raw), "--details", "Reviewer output (raw)"],
                          capture_output=True, text=True, check=True).stdout


def post(w: World, body: str, assoc: str = "OWNER", edited: bool = False) -> None:
    cs = w.comments()
    at = f"2000-01-01T01:{len(cs):02d}:00Z"
    cs.append({"id": 2000 + len(cs), "body": body, "author_association": assoc, "created_at": at,
               "updated_at": "2000-02-01T00:00:00Z" if edited else at,
               "html_url": f"https://github.com/example-owner/example-repo/pull/12#issuecomment-{2000 + len(cs)}"})
    (w.fx / "comments.json").write_text(json.dumps(cs))


def fail_output(sha: str, ids: tuple[str, ...] = ("COR-1",), reviewed: str | None = None) -> str:
    blocking, text = must_fix(*ids)
    return f"VERDICT: FAIL {sha}\nReviewed: {reviewed or sha}\n{blocking}\n\n{text}"


# The depth floor: one rule each.


def test_floor_routine_paths_need_no_reviewer(w: World) -> None:
    w.commit({"docs/guide.md": "x\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert (p["tier"], p["floor"], p["depth"], lenses_of(p), p["verifier"]) == ("routine", "none", "none", [], "")


def test_floor_standard_paths_need_light_one_lens_and_the_verifier(w: World) -> None:
    w.commit({"src/app.py": "x = 2\n", "docs/guide.md": "x\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert (p["tier"], p["floor"], lenses_of(p), p["verifier"]) == ("standard", "light", [COR], VER)


@pytest.mark.parametrize("path", ["RULES.md", "cloud/hooks/x.sh", ".github/workflows/ci.yml", "docs/agents/a.md"])
def test_floor_built_in_sensitive_paths_need_focused_with_correctness_first(w: World, path: str) -> None:
    w.commit({path: "x\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert (p["tier"], p["floor"], p["first"], p["then"]) == ("sensitive", "focused", [COR], [GRD])


def test_floor_review_md_sensitive_paths_need_focused_with_their_lenses(w: World) -> None:
    base_has(w, {"REVIEW.md": "## Sensitive\n- `src/**`; lenses: leak-hunter\n"})
    w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert p["floor"] == "focused" and p["first"] == [COR] and sorted(p["then"]) == sorted([GRD, LEAK])


def test_floor_unparsable_review_md_rates_every_path_focused(w: World) -> None:
    base_has(w, {"REVIEW.md": "Depth: none\n\n## Routine\nanything goes\n"})
    w.commit({"docs/a.md": "x\n"})
    code, p, err = plan(w)
    assert code == 0 and "cannot be parsed" in err, err
    assert p["floor"] == "focused"


def test_light_on_routine_prose_runs_claims_auditor(w: World) -> None:
    w.commit({"docs/guide.md": "x\n"})
    code, p, err = plan(w, "--depth", "light")
    assert code == 0, err
    assert (p["floor"], p["depth"], lenses_of(p), p["verifier"]) == ("none", "light", [CLM], VER)


def test_full_runs_the_set_at_once(w: World) -> None:
    w.commit({"RULES.md": "x\n"})
    code, p, err = plan(w, "--depth", "full")
    assert code == 0, err
    assert p["depth"] == "full" and p["first"] == [] and sorted(p["then"]) == sorted(SENSITIVE)


# A raised depth is accepted, a lowered one refused.


def test_a_raised_depth_is_planned_and_recorded(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    assert plan(w, "--depth", "full")[1]["depth"] == "full"
    done = verdict(w, tmp_path, head, [COR, VER], "standard", depth="full")
    assert done.returncode == 0, done.stderr
    body = w.comments()[-1]["body"]
    assert body.split("\n")[1] == f"{REVIEW} sha={head} state=success tier=standard reviewed={head} depth=full -->"


@pytest.mark.parametrize("depth", ["none", "light"])
def test_a_depth_below_the_floor_is_refused(w: World, tmp_path: Path, depth: str) -> None:
    head = w.commit({"cloud/hooks/x.sh": "x\n"})
    code, _, err = plan(w, "--depth", depth)
    assert code == 2 and "below" in err, err
    done = verdict(w, tmp_path, head, SENSITIVE + [VER], "sensitive", depth=depth)
    assert done.returncode == 2 and "below" in done.stderr and w.writes() == []


def test_a_depth_that_is_no_depth_is_refused(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = verdict(w, tmp_path, head, [COR, VER], "standard", depth="deep")
    assert done.returncode == 2 and "--depth" in done.stderr and w.writes() == []


# The reviewer set must cover the plan.


@pytest.mark.parametrize("missing", [COR, GRD, VER])
def test_verdict_refuses_a_reviewer_set_missing_a_planned_lens_or_the_verifier(w: World, tmp_path: Path,
                                                                              missing: str) -> None:
    head = w.commit({"cloud/hooks/x.sh": "x\n"})
    ran = [x for x in SENSITIVE + [VER] if x != missing]
    done = verdict(w, tmp_path, head, ran, "sensitive")
    assert done.returncode == 2 and missing in done.stderr and "planned" in done.stderr, done.stderr
    assert w.writes() == []


def test_verdict_accepts_lenses_beyond_the_plan(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = verdict(w, tmp_path, head, [COR, LEAK, VER], "standard")
    assert done.returncode == 0, done.stderr


def test_verdict_records_depth_on_line_two_and_depth_and_planned_on_the_round_line(w: World, tmp_path: Path) -> None:
    head = w.commit({"cloud/hooks/x.sh": "x\n"})
    done = verdict(w, tmp_path, head, SENSITIVE + [VER], "sensitive")
    assert done.returncode == 0, done.stderr
    body = w.comments()[-1]["body"]
    assert body.split("\n")[1] == (f"{REVIEW} sha={head} state=success tier=sensitive reviewed={head} "
                                   "depth=focused -->")
    f = dict(x for x in round_fields(body) if x[0] != "lens")
    assert f["depth"] == "focused"
    assert f["planned"] == ",".join([COR, GRD, VER])


# Efforts (each lens's own; the merge guard never reads them).


def test_effort_is_medium_at_focused_and_high_for_correctness_and_control_at_full(w: World) -> None:
    base_has(w, {"REVIEW.md": "## Sensitive\n- `guard/**`; lenses: control-prober\n"})
    w.commit({"guard/check.py": "x\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert p["effort"] == {COR: "medium", GRD: "medium", CTL: "medium", VER: "medium"}
    code, p, err = plan(w, "--depth", "full")
    assert code == 0, err
    assert p["effort"] == {COR: "high", GRD: "medium", CTL: "high", VER: "medium"}


@pytest.mark.parametrize("files", [{"RULES.md": "x\n"}, {"src/app.py": "x = 2\n"}])
def test_effort_is_medium_on_sensitive_prose_and_on_standard_code(w: World, files: dict[str, str]) -> None:
    w.commit(files)
    code, p, err = plan(w)
    assert code == 0, err
    assert set(p["effort"].values()) == {"medium"}, p["effort"]


def test_review_md_sets_a_lens_effort_for_its_paths(w: World) -> None:
    base_has(w, {"REVIEW.md": "## Paths\n- `src/**`; effort: correctness-reviewer=high\n"
                              "- `lib/**`; effort: correctness-reviewer=low\n"})
    w.commit({"src/app.py": "x = 2\n"})
    assert plan(w)[1]["effort"][COR] == "high"
    w.git(w.repo, "reset", "-q", "--hard", "origin/main")
    w.commit({"lib/x.py": "x\n"})
    assert plan(w)[1]["effort"][COR] == "low"


def test_verdict_refuses_a_lens_run_below_its_planned_effort_and_accepts_one_above(w: World, tmp_path: Path) -> None:
    head = w.commit({"cloud/hooks/x.py": "x\n"})
    done = verdict(w, tmp_path, head, SENSITIVE + [VER], "sensitive", depth="full", effort={COR: "medium"})
    assert done.returncode == 2 and COR in done.stderr and "effort" in done.stderr and w.writes() == []
    done = verdict(w, tmp_path, head, SENSITIVE + [VER], "sensitive", depth="full", effort={GRD: "xhigh"})
    assert done.returncode == 0, done.stderr


# The owner's effort cap (LOADOUT_MAX_EFFORT): it lowers a planned effort, never raises one.

CAP = "LOADOUT_MAX_EFFORT"


def test_the_cap_lowers_each_planned_effort_above_it_and_is_printed(w: World) -> None:
    base_has(w, {"REVIEW.md": "## Sensitive\n- `guard/**`; lenses: control-prober; effort: finding-verifier=max\n"})
    w.commit({"guard/check.py": "x\n"})
    code, p, err = plan(w, "--depth", "full", **{CAP: "medium"})
    assert code == 0, err
    assert p["cap"] == "medium"
    assert p["effort"] == {COR: "medium", GRD: "medium", CTL: "medium", VER: "medium"}
    assert p["uncapped"] == {COR: "high", GRD: "medium", CTL: "high", VER: "max"}
    assert any(CAP in x and "high to medium" in x for x in p["why"]), p["why"]
    done = subprocess.run([sys.executable, str(PLAN), "--pr", "12", "--depth", "full"], cwd=w.repo,
                          env={**w.env, CAP: "medium"}, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert f"cap: medium ({CAP})" in done.stdout
    assert f"{COR} (medium, capped from high)" in done.stdout and f"{GRD} (medium)" in done.stdout
    assert f"verifier: {VER} (medium, capped from max)" in done.stdout


@pytest.mark.parametrize("cap", [None, ""])
def test_no_cap_plans_as_before_and_says_so(w: World, cap: str | None) -> None:
    w.commit({"cloud/hooks/x.py": "x\n"})
    code, p, err = plan(w, "--depth", "full", **({CAP: cap} if cap is not None else {}))
    assert code == 0, err
    assert p["cap"] is None and p["effort"][COR] == "high"
    done = subprocess.run([sys.executable, str(PLAN), "--pr", "12"], cwd=w.repo, env={**w.env, CAP: ""},
                          capture_output=True, text=True, timeout=60)
    assert f"cap: none ({CAP} unset)" in done.stdout, done.stderr


def test_the_cap_never_raises_a_planned_effort(w: World) -> None:
    base_has(w, {"REVIEW.md": "## Paths\n- `lib/**`; effort: correctness-reviewer=low\n"})
    w.commit({"lib/x.py": "x\n"})
    for cap in ("medium", "max"):
        code, p, err = plan(w, **{CAP: cap})
        assert code == 0, err
        assert p["effort"] == {COR: "low", VER: "medium"}, (cap, p["effort"])


@pytest.mark.parametrize("cap", ["huge", "Medium", "HIGH", "none", "0"])
def test_a_cap_outside_the_five_levels_refuses_the_plan_and_the_record(w: World, tmp_path: Path, cap: str) -> None:
    head = w.commit({"cloud/hooks/x.py": "x\n"})
    code, _, err = plan(w, **{CAP: cap})
    assert code == 2 and CAP in err and repr(cap) in err
    done = w.verdict("12", "--tier", "sensitive", "--reviewers", ", ".join(SENSITIVE + [VER]), "--reviewed", head,
                     "--file", review_file(tmp_path, head, "PASS", "No findings.\n", "Blocking: none"), **{CAP: cap})
    assert done.returncode != 0 and CAP in done.stderr and w.writes() == []


def test_floor_reads_no_cap(w: World) -> None:
    head = w.commit({"cloud/hooks/x.py": "x\n"})
    done = subprocess.run([sys.executable, str(PLAN), "floor", "--base", "origin/main", "--head", head], cwd=w.repo,
                          env={**w.env, CAP: "huge"}, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and done.stdout.strip() == "sensitive focused", done.stderr


def test_verdict_accepts_a_lens_at_the_cap_when_its_plan_was_higher_and_records_the_cap(w: World,
                                                                                       tmp_path: Path) -> None:
    head = w.commit({"cloud/hooks/x.py": "x\n"})
    at_cap = {COR: "medium", GRD: "medium", VER: "medium"}
    # planned high for correctness-reviewer: refused with no cap
    done = verdict(w, tmp_path, head, SENSITIVE + [VER], "sensitive", depth="full", effort=at_cap)
    assert done.returncode == 2 and "effort" in done.stderr and w.writes() == []
    blocking, text = ("Blocking: none", "No findings.\n")
    args = ["12", "--tier", "sensitive", "--reviewers", ", ".join(SENSITIVE + [VER]), "--reviewed", head,
            "--file", review_file(tmp_path, head, "PASS", text, blocking), "--cycle", "1", "--dupes", "0",
            "--nits", "0", "--depth", "full"]
    for r in SENSITIVE + [VER]:
        args += ["--lens", f"{r} model=opus effort={at_cap[r]} tokens=10 seconds=1 findings=0"]
    done = w.verdict(*args, cost=False, **{CAP: "medium"})
    assert done.returncode == 0, done.stderr
    f = dict(x for x in round_fields(w.comments()[-1]["body"]) if x[0] != "lens")
    assert f["cap"] == "medium" and f["depth"] == "full"


def test_verdict_under_a_cap_refuses_a_lens_below_the_cap_or_below_a_lower_plan(w: World, tmp_path: Path) -> None:
    head = w.commit({"cloud/hooks/x.py": "x\n"})
    blocking, text = ("Blocking: none", "No findings.\n")

    def under(cap: str, efforts: dict[str, str]) -> subprocess.CompletedProcess[str]:
        args = ["12", "--tier", "sensitive", "--reviewers", ", ".join(SENSITIVE + [VER]), "--reviewed", head,
                "--file", review_file(tmp_path, head, "PASS", text, blocking), "--cycle", "1", "--dupes", "0",
                "--nits", "0", "--depth", "full"]
        for r in SENSITIVE + [VER]:
            args += ["--lens", f"{r} model=opus effort={efforts.get(r, 'medium')} tokens=10 seconds=1 findings=0"]
        return w.verdict(*args, cost=False, **{CAP: cap})

    done = under("medium", {COR: "low"})  # below the cap, the plan having been high
    assert done.returncode == 2 and COR in done.stderr and f"{CAP}=medium" in done.stderr and w.writes() == []
    done = under("xhigh", {GRD: "low"})  # below a plan (medium) that the cap does not touch
    assert done.returncode == 2 and GRD in done.stderr and w.writes() == []
    done = under("xhigh", {COR: "medium"})  # the plan (high) is below the cap, so the cap lowers nothing
    assert done.returncode == 2 and COR in done.stderr and w.writes() == []
    done = under("low", {COR: "max", GRD: "max"})  # above the cap: the hook's to refuse, never the record's
    assert done.returncode == 0, done.stderr
    assert dict(x for x in round_fields(w.comments()[-1]["body"]) if x[0] != "lens")["cap"] == "low"


def test_no_cap_writes_no_cap_pair(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = verdict(w, tmp_path, head, [COR, VER], "standard")
    assert done.returncode == 0, done.stderr
    assert "cap" not in dict(round_fields(w.comments()[-1]["body"]))


# Lab policy, and the floor no REVIEW.md line lowers.


@pytest.mark.parametrize("policy, floor", [("Depth: light", "light"), ("Depth: none", "none"),
                                           ("Depth: full", "full")])
def test_a_repo_default_depth_sets_standard_paths(w: World, policy: str, floor: str) -> None:
    base_has(w, {"REVIEW.md": f"# Review\n\n{policy}\n"})
    w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w)
    assert code == 0 and "cannot be parsed" not in err, err
    assert p["floor"] == floor
    assert lenses_of(p) == ([] if floor == "none" else [COR])


def test_a_per_path_none_needs_only_what_it_says(w: World) -> None:
    base_has(w, {"REVIEW.md": "## Paths\n- `notebooks/**` — scratch analysis; depth: none\n"})
    w.commit({"notebooks/a.py": "x\n"})
    assert plan(w)[1]["floor"] == "none"
    w.commit({"src/app.py": "x = 2\n"})
    assert plan(w)[1]["floor"] == "light"


def test_a_per_path_depth_raises_anywhere(w: World) -> None:
    base_has(w, {"REVIEW.md": "## Routine\n- `docs/**`; depth: light\n\n## Paths\n- `src/**`; depth: full\n"})
    w.commit({"docs/a.md": "x\n"})
    assert plan(w)[1]["floor"] == "light"
    w.commit({"src/app.py": "x = 2\n"})
    assert plan(w)[1]["floor"] == "full"


@pytest.mark.parametrize("path", ["RULES.md", ".githooks/pre-commit", "cloud/hooks/x.sh", ".claude/settings.json",
                                  ".github/workflows/ci.yml", "docs/agents/autopilot.md", "skills/x/SKILL.md"])
def test_no_review_md_line_lowers_the_built_in_floor(w: World, path: str) -> None:
    base_has(w, {"REVIEW.md": "# Review\n\nDepth: none\n\n## Routine\n- `**`; depth: none\n\n"
                              "## Paths\n- `**`; depth: none\n"})
    w.commit({path: "x\n"})
    code, p, err = plan(w)
    assert code == 0 and "cannot be parsed" not in err, err
    assert (p["tier"], p["floor"]) == ("sensitive", "focused")


def test_no_review_md_line_lowers_its_own_sensitive_list(w: World) -> None:
    base_has(w, {"REVIEW.md": "Depth: none\n\n## Sensitive\n- `src/**`\n\n## Paths\n- `src/**`; depth: none\n"})
    w.commit({"src/app.py": "x = 2\n"})
    assert plan(w)[1]["floor"] == "focused"


@pytest.mark.parametrize("line", ["- `src/**`; depth: light", "- `src/**`; depth: none", "- `src/**`; depth: deep",
                                  "- `src/**`; effort: correctness-reviewer=huge",
                                  "- `src/**`; depth: full; lenses: leak-hunter"])
def test_a_sensitive_line_below_focused_or_out_of_shape_fails_safe(w: World, line: str) -> None:
    base_has(w, {"REVIEW.md": f"## Sensitive\n{line}\n"})
    w.commit({"docs/a.md": "x\n"})
    code, p, err = plan(w)
    assert code == 0 and "cannot be parsed" in err, err
    assert p["floor"] == "focused"


def test_the_template_s_depth_and_effort_lines_parse(w: World) -> None:
    block = template_review_md()
    assert "Depth: " in block and "; depth: " in block and "; effort: " in block
    base_has(w, {"REVIEW.md": block})
    w.commit({"d/x.py": "x\n"})  # a `## Paths` line: depth none, correctness-reviewer at low effort
    code, p, err = plan(w, "--depth", "light")
    assert code == 0 and "cannot be parsed" not in err, err
    assert (p["floor"], p["effort"][COR]) == ("none", "low")
    w.commit({"b/y.py": "y\n"})  # a sensitive line raised to full
    assert plan(w)[1]["floor"] == "full"


# Ways around found on the earlier attempt: each is closed.


def test_a_fix_round_reads_every_commit_since_the_reviewed_one(w: World, tmp_path: Path) -> None:
    # A fix-round diff that hides a sensitive path: the sensitive commit is not the newest one.
    first_round(w, tmp_path, {"src/app.py": "x = 2\n"}, "standard", [COR, VER])
    w.commit({"RULES.md": "a new rule\n"})
    w.commit({"src/app.py": "x = 3\n"})
    code, p, err = plan(w)
    assert code == 0, err
    # The light round reviewed less than the focused floor the head now has: the whole change is reviewed again.
    assert p["round"] == "first" and set(SENSITIVE) <= set(lenses_of(p))


def test_a_fix_round_to_a_sensitive_path_is_refused_without_the_sensitive_set(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"src/app.py": "x = 2\n"}, "standard", [COR, VER])
    head = w.commit({"cloud/hooks/merge-guard.py": "x\n"})
    done = verdict(w, tmp_path, head, [COR, VER], "sensitive")
    assert done.returncode == 2 and GRD in done.stderr and len(w.comments()) == 1


@pytest.mark.parametrize("option", [["--base", "origin/main"], ["--head", "HEAD"], ["--since", "HEAD"],
                                    ["--prior", "x.txt"]])
def test_the_preview_takes_no_base_head_since_or_prior(w: World, option: list[str]) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    code, _, err = plan(w, *option)
    assert code == 2 and "unrecognized arguments" in err, err


@pytest.mark.parametrize("option", ["--base", "--head", "--since", "--prior"])
def test_verdict_takes_no_plan_input(w: World, tmp_path: Path, option: str) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    done = verdict(w, tmp_path, head, [COR, VER], "standard", extra=(option, "origin/main"))
    assert done.returncode == 2 and w.writes() == []


def test_a_locally_set_origin_head_does_not_narrow_the_plan(w: World, tmp_path: Path) -> None:
    # The default branch comes from GitHub's PR answer, not origin/HEAD: an origin/HEAD at a commit that holds the
    # sensitive part of the change hides it from a diff against origin/HEAD.
    w.commit({"cloud/hooks/x.sh": "x\n"})
    w.git(w.repo, "push", "-q", "origin", "HEAD:side")
    w.git(w.repo, "fetch", "-q", "origin")
    w.git(w.repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/side")
    head = w.commit({"src/app.py": "x = 2\n"})
    assert plan(w)[1]["floor"] == "focused"
    done = verdict(w, tmp_path, head, [COR, VER], "standard")
    assert done.returncode == 2 and w.writes() == []


def test_a_locally_moved_default_branch_ref_does_not_narrow_the_plan(w: World, tmp_path: Path) -> None:
    sensitive = w.commit({"cloud/hooks/x.sh": "x\n"})
    head = w.commit({"src/app.py": "x = 2\n"})
    w.git(w.repo, "update-ref", "refs/remotes/origin/main", sensitive)
    w.git(w.repo, "config", "remote.origin.fetch", "+refs/heads/feature:refs/remotes/origin/feature")
    assert plan(w)[1]["floor"] == "focused"
    w.git(w.repo, "update-ref", "refs/remotes/origin/main", sensitive)
    done = verdict(w, tmp_path, head, [COR, VER], "standard")
    assert done.returncode == 2 and w.writes() == []


def test_a_fetched_default_branch_other_than_github_s_refuses(w: World, tmp_path: Path) -> None:
    sensitive = w.commit({"cloud/hooks/x.sh": "x\n"})
    head = w.commit({"src/app.py": "x = 2\n"})
    (w.fx / "branches.json").write_text(json.dumps({"main": sensitive}))  # GitHub and the remote disagree
    code, _, err = plan(w)
    assert code == 2 and "main" in err, err
    done = verdict(w, tmp_path, head, [COR, VER], "standard")
    assert done.returncode == 2 and w.writes() == []


def test_the_plan_rates_the_prs_head_not_a_stale_checkout(w: World, tmp_path: Path) -> None:
    earlier = w.commit({"src/app.py": "x = 2\n"})
    w.commit({"cloud/hooks/x.sh": "x\n"})
    w.git(w.repo, "reset", "-q", "--hard", earlier)  # the local checkout lags the PR's head
    code, p, err = plan(w)
    assert code == 0, err
    assert p["floor"] == "focused" and set(SENSITIVE) <= set(lenses_of(p))


def test_the_fix_round_comes_from_the_newest_trusted_record_not_an_untrusted_one(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"src/app.py": "x = 2\n"}, "standard", [COR, VER])
    later = w.commit({"RULES.md": "a rule\n"})
    head = w.commit({"src/app.py": "x = 3\n"})
    # An outsider's record that reviewed `later`, at the head's tier and floor, would hide RULES.md from the fix range:
    # it does not count.
    post(w, crafted(head, later, fail_output(later), tier="sensitive", tmp=tmp_path), assoc="NONE")
    code, p, err = plan(w)
    assert code == 0, err
    assert set(SENSITIVE) <= set(lenses_of(p))


@pytest.mark.parametrize("spoil", ["edited", "reviewed-mismatch", "no-blocking", "routine", "malformed"])
def test_an_unusable_newest_trusted_record_plans_a_first_review_not_an_older_record(w: World, tmp_path: Path,
                                                                                    spoil: str) -> None:
    reviewed = first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER])
    later = w.commit({"src/app.py": "x = 2\n"})
    head = w.commit({"src/app.py": "x = 3\n"})
    out = fail_output(later)
    body = crafted(head, later, out, tier="sensitive", tmp=tmp_path)
    if spoil == "reviewed-mismatch":
        body = crafted(head, later, fail_output(later, reviewed=reviewed), tier="sensitive", tmp=tmp_path)
    elif spoil == "no-blocking":
        body = crafted(head, later, f"VERDICT: FAIL {later}\nReviewed: {later}\n\nprose\n", tier="sensitive",
                       tmp=tmp_path)
    elif spoil == "routine":
        # A routine record at focused depth that does carry verifier-shaped output: only its tier, below the change's,
        # keeps it from starting a fix round.
        body = crafted(head, later, out, tier="routine", depth="focused", tmp=tmp_path)
    elif spoil == "malformed":
        body = body.replace("state=failure", "state=failure state=failure")
    post(w, body, edited=spoil == "edited")
    code, p, err = plan(w)
    assert code == 0, err
    assert p["round"] == "first" and p["since"] is None, p


def test_a_record_of_a_commit_off_the_branch_plans_a_first_review(w: World, tmp_path: Path) -> None:
    gone = first_round(w, tmp_path, {"src/app.py": "x = 2\n"}, "standard", [COR, VER])
    w.git(w.repo, "reset", "-q", "--hard", "origin/main")
    w.commit({"src/app.py": "x = 9\n"})  # a force-push: the reviewed commit is no longer on the branch
    code, p, err = plan(w)
    assert code == 0, err
    assert p["round"] == "first" and p["since"] is None and gone not in json.dumps(p)


def test_a_record_at_or_before_the_merge_base_plans_a_first_review(w: World, tmp_path: Path) -> None:
    mb = w.git(w.repo, "rev-parse", "origin/main")
    head = w.commit({"cloud/hooks/x.sh": "x\n"})
    post(w, crafted(head, mb, fail_output(mb), tier="sensitive", tmp=tmp_path))
    code, p, err = plan(w)
    assert code == 0, err
    assert p["round"] == "first" and set(SENSITIVE) <= set(lenses_of(p))


def header_reviewed(tmp: Path, output: str) -> tuple[int, str]:
    """blocking.py --header on `output`, the read verdict.sh makes: its exit code and the `Reviewed:` line it prints."""
    f = tmp / "header.txt"
    f.write_text(output)
    done = subprocess.run([sys.executable, str(SCRIPTS / "blocking.py"), "--header", str(f)], capture_output=True,
                          text=True)
    return done.returncode, (done.stdout.split("\n") + ["", ""])[1]


def test_the_previous_round_reads_the_reviewed_line_verdict_sh_reads(w: World, tmp_path: Path) -> None:
    reviewed = first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER])
    later = w.commit({"src/app.py": "x = 2\n"})
    head = w.commit({"src/app.py": "x = 3\n"})
    # The header at the top names `later`; a line quoted after `> ` below names another commit: both readers take
    # the top line.
    out = fail_output(later) + f"\n> Reviewed: {reviewed}\n"
    assert header_reviewed(tmp_path, out) == (0, f"Reviewed: {later}")
    post(w, crafted(head, later, out, tier="sensitive", tmp=tmp_path))
    code, p, err = plan(w)
    assert code == 0 and (p["round"], p["since"]) == ("fix", later), (p, err)


@pytest.mark.parametrize("decoy", ["```\nReviewed: {later}\n```\n", "```text\nReviewed: {later}\n```\n",
                                   "````\n```\nReviewed: {later}\n````\n", "Reviewed: {later}\n"])
def test_a_previous_round_whose_output_holds_a_second_reviewed_line_plans_a_first_review(w: World, tmp_path: Path,
                                                                                       decoy: str) -> None:
    reviewed = first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER])
    later = w.commit({"src/app.py": "x = 2\n"})
    head = w.commit({"src/app.py": "x = 3\n"})
    # A decoy above the header names the record's `reviewed=`, while the header names an older commit: verdict.sh
    # refuses the output, so plan.py never starts a fix round from it.
    out = decoy.replace("{later}", later) + fail_output(reviewed)
    code, _ = header_reviewed(tmp_path, out)
    assert code == 2
    post(w, crafted(head, later, out, tier="sensitive", tmp=tmp_path))
    code, p, err = plan(w)
    assert code == 0 and p["round"] == "first" and p["since"] is None, (p, err)


def test_the_previous_round_is_read_from_the_pr_never_passed_in(w: World, tmp_path: Path) -> None:
    # verdict.sh takes the previous round from the PR itself: an output file of another round only reaches it as
    # --file, which must name the reviewed commit.
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("GRD-1",))
    head = w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert p["round"] == "fix" and sorted(lenses_of(p)) == sorted([COR, GRD])  # GRD's must-fix, a code fix


# Fix rounds rerun what they answer, the lenses REVIEW.md names for their paths, correctness on code and, on a
# sensitive fix path, the sensitive set (focused), or the whole set (full).


@pytest.mark.parametrize("ids, lenses", [(("CLM-1",), [CLM]), (("COR-1",), [COR]), (("GRD-2", "CTL-1"), [GRD, CTL]),
                                         (("COR-RO-1",), [COR]), (("GRD-RO-3",), [GRD])])
def test_a_fix_round_reruns_only_the_lens_each_must_fix_came_from(w: World, tmp_path: Path, ids: tuple[str, ...],
                                                                  lenses: list[str]) -> None:
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=ids)
    w.commit({"docs/a.md": "x\n"})  # a prose-only fix: only what it answers
    code, p, err = plan(w)
    assert code == 0, err
    assert p["round"] == "fix" and sorted(lenses_of(p)) == sorted(lenses) and p["verifier"] == VER


def test_a_code_fix_answering_another_lens_is_read_for_correctness_too(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("CLM-1",))
    head = w.commit({"src/app.py": "import os\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert p["round"] == "fix" and sorted(lenses_of(p)) == sorted([COR, CLM])
    done = verdict(w, tmp_path, head, [CLM, VER], "sensitive", "PASS", ids=())
    assert done.returncode == 2 and COR in done.stderr


def test_a_sensitive_fix_path_after_another_path_still_runs_the_sensitive_set(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("CLM-1",))
    w.commit({"a/b.md": "x\n", "cloud/hooks/x.sh": "y\n"})  # the sensitive path sorts last
    code, p, err = plan(w)
    assert code == 0, err
    assert p["round"] == "fix" and sorted(lenses_of(p)) == sorted([COR, CLM, GRD])


def test_a_fix_round_runs_the_review_md_lenses_of_the_paths_it_changed(w: World, tmp_path: Path) -> None:
    base_has(w, {"REVIEW.md": "## Sensitive\n- `lib/**`; lenses: leak-hunter\n"})
    first_round(w, tmp_path, {"src/app.py": "x = 2\n"}, "standard", [COR, VER])
    w.commit({"lib/x.py": "x\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert set(SENSITIVE + [LEAK]) <= set(lenses_of(p))


def test_a_fix_round_after_a_sensitive_round_runs_the_review_md_lenses_of_its_paths(w: World,
                                                                                    tmp_path: Path) -> None:
    base_has(w, {"REVIEW.md": "## Sensitive\n- `lib/**`; lenses: leak-hunter\n"})
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("COR-1",))
    w.commit({"lib/x.py": "x\n"})  # a sensitive fix path: the sensitive set runs too
    code, p, err = plan(w)
    assert code == 0, err
    assert p["round"] == "fix" and sorted(lenses_of(p)) == sorted([COR, GRD, LEAK])


def test_a_blocking_id_naming_no_lens_reruns_correctness(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("ODD-1",))
    w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert p["round"] == "fix" and lenses_of(p) == [COR]


def test_a_round_deeper_than_the_last_reviews_the_whole_change_and_a_full_fix_round_the_whole_set(
        w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("COR-1",))
    w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w, "--depth", "full")
    assert code == 0, err
    assert p["round"] == "first" and p["since"] is None and sorted(p["then"]) == sorted(SENSITIVE)
    head = w.commit({"src/app.py": "x = 3\n"})
    done = verdict(w, tmp_path, head, SENSITIVE + [VER], "sensitive", "FAIL", depth="full")
    assert done.returncode == 0, done.stderr
    w.commit({"src/app.py": "x = 4\n"})
    code, p, err = plan(w, "--depth", "full")
    assert code == 0, err
    assert p["round"] == "fix" and p["first"] == [] and sorted(p["then"]) == sorted(SENSITIVE)


# The record shapes: a routine record on a floor-none change, and a re-post.


def test_a_routine_record_is_accepted_on_a_floor_none_change(w: World) -> None:
    base_has(w, {"REVIEW.md": "Depth: none\n"})
    head = w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "routine")
    assert done.returncode == 0, done.stderr
    assert w.comments()[-1]["body"].split("\n")[1] == (f"{REVIEW} sha={head} state=success tier=routine "
                                                       f"reviewed={head} depth=none -->")


def test_a_routine_record_is_still_refused_above_floor_none(w: World) -> None:
    w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "routine")
    assert done.returncode == 2 and w.writes() == []


def test_a_repost_keeps_the_reposted_rounds_depth_and_plan(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    assert verdict(w, tmp_path, reviewed, [COR, VER], "standard", depth="full").returncode == 0
    w.main_moves({"README.md": "main moved\n"})
    w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    done = w.verdict("12", "--tier", "standard", "--reviewers", f"{COR}, {VER}", "--reviewed", reviewed,
                     "--file", review_file(tmp_path, reviewed), "--repost", cost=False)
    assert done.returncode == 0, done.stderr
    body = w.comments()[-1]["body"]
    assert body.split("\n")[1].endswith(f"reviewed={reviewed} depth=full -->")
    f = dict(x for x in round_fields(body) if x[0] != "lens")
    assert f["repost"] == "1" and f["depth"] == "full" and f["planned"] == f"{COR},{VER}"


# The fix round's checks, one test each.


def test_a_default_depth_above_focused_raises_sensitive_paths_too(w: World) -> None:
    base_has(w, {"REVIEW.md": "Depth: full\n"})
    w.commit({"RULES.md": "a rule\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert (p["tier"], p["floor"]) == ("sensitive", "full")


def test_a_depth_line_with_no_value_fails_safe(w: World) -> None:
    base_has(w, {"REVIEW.md": "Depth:\n"})
    w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w)
    assert code == 0 and "cannot be parsed" in err, err
    assert (p["tier"], p["floor"]) == ("sensitive", "focused")


def test_a_fence_inside_a_list_stays_unparsable(w: World) -> None:
    base_has(w, {"REVIEW.md": "## Sensitive\n```\n- `src/**`\n```\n"})
    w.commit({"docs/a.md": "x\n"})
    code, p, err = plan(w)
    assert code == 0 and "cannot be parsed" in err, err
    assert p["floor"] == "focused"


def test_the_floor_of_a_change_with_no_paths_is_refused_with_its_reason(w: World) -> None:
    done = subprocess.run([sys.executable, str(PLAN), "floor", "--base", "HEAD", "--head", "HEAD"], cwd=w.repo,
                          env=w.env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 2 and "changes nothing" in done.stderr and "Traceback" not in done.stderr, done.stderr


def test_verdict_refuses_when_the_plans_head_is_not_the_head_it_read(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    later = w.commit({"src/app.py": "x = 3\n"})  # pushed: the remote holds it, and plan.py reads it as the head
    pr = json.loads((w.fx / "pr.json").read_text())
    (w.fx / "pr-later.json").write_text(json.dumps(pr))
    (w.fx / "pr.json").write_text(json.dumps({**pr, "head": {"sha": reviewed}}))
    done = verdict(w, tmp_path, reviewed, [COR, VER], "standard", extra=())
    assert done.returncode == 2 and "moved while the plan was read" in done.stderr, done.stderr
    assert w.writes() == [] and later


def repost(w: World, tmp: Path, reviewed: str) -> subprocess.CompletedProcess[str]:
    return w.verdict("12", "--tier", "standard", "--reviewers", f"{COR}, {VER}", "--reviewed", reviewed,
                     "--file", review_file(tmp, reviewed), "--repost", cost=False)


def merge_main(w: World, files: dict[str, str] | None = None) -> str:
    for name, text in (files or {"README.md": "main moved\n"}).items():
        (w.seed / name).write_text(text)
    w.git(w.seed, "add", ".")
    w.git(w.seed, "commit", "-qm", "main moves")
    w.git(w.seed, "push", "-q", str(w.remote), "main")
    w.git(w.repo, "fetch", "-q", "origin")
    w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    return w.git(w.repo, "rev-parse", "HEAD")


def test_a_repost_of_a_round_recorded_before_depths_is_refused(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    out = f"VERDICT: PASS {reviewed}\nReviewed: {reviewed}\nBlocking: none\n\nNo findings.\n"
    post(w, crafted(reviewed, reviewed, out, tier="standard", state="success", depth=None, tmp=tmp_path))
    merge_main(w, {"REVIEW.md": "## Paths\n- `src/**`; depth: full\n"})
    before = len(w.writes())
    done = repost(w, tmp_path, reviewed)
    assert done.returncode == 2 and "record the round anew" in done.stderr, done.stderr
    assert len(w.writes()) == before


@pytest.mark.parametrize("spoil", ["another commit", "depth without a plan", "plan without a depth"])
def test_a_repost_needs_the_newest_record_of_the_reviewed_commit_whole(w: World, tmp_path: Path, spoil: str) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    assert verdict(w, tmp_path, reviewed, [COR, VER], "standard").returncode == 0
    cs = w.comments()
    if spoil == "another commit":
        other = w.commit({"src/app.py": "x = 3\n"})
        cs[-1]["body"] = cs[-1]["body"].replace(f"reviewed={reviewed}", f"reviewed={other}")
    elif spoil == "depth without a plan":
        lines = cs[-1]["body"].split("\n")
        lines[2] = " ".join(x for x in lines[2].split() if not x.startswith("planned="))
        cs[-1]["body"] = "\n".join(lines)
    else:
        cs[-1]["body"] = cs[-1]["body"].replace(" depth=light -->", " -->", 1)
    (w.fx / "comments.json").write_text(json.dumps(cs))
    merge_main(w)
    done = repost(w, tmp_path, reviewed)
    assert done.returncode == 2 and "record the round anew" in done.stderr, done.stderr


def test_a_repost_below_the_floor_at_the_head_is_refused(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    assert verdict(w, tmp_path, reviewed, [COR, VER], "standard").returncode == 0  # depth light
    merge_main(w, {"REVIEW.md": "## Paths\n- `src/**`; depth: full\n"})  # main raises the floor afterwards
    done = repost(w, tmp_path, reviewed)
    assert done.returncode == 2 and "below the floor full" in done.stderr, done.stderr


# A fence outside the lists is ordinary text, as it was before depths: it neither opens nor closes anything, so no
# fence shape can hide a later list.
@pytest.mark.parametrize("review_md", [
    "# R\n\n```\nan example\n\n## Sensitive\n- `src/**`\n",  # a fence never closed
    "# R\n\n    ```\n    indented code\n\n## Sensitive\n- `src/**`\n",  # a fence 4 spaces in
    "# R\n\n```make check``` runs the gates.\n\n```\nan example\n```\n\n## Sensitive\n- `src/**`\n",  # inline code
    "# R\n\n```\nan example\n```\n\n## Sensitive\n- `src/**`\n",  # a closed example
])
def test_a_fence_before_the_lists_hides_none_of_them(w: World, review_md: str) -> None:
    base_has(w, {"REVIEW.md": review_md})
    w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w)
    assert code == 0 and "cannot be parsed" not in err, err
    assert (p["tier"], p["floor"]) == ("sensitive", "focused"), (p, err)
    done = w.run("tier.sh")
    assert done.stdout.split("\n")[:2] == ["sensitive", "src/app.py"], done.stdout + done.stderr


def test_a_repost_without_a_record_is_refused(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    merge_main(w)
    done = repost(w, tmp_path, reviewed)
    assert done.returncode == 2 and "record the round anew" in done.stderr, done.stderr
    assert w.writes() == []


# The owner's override: --owner quotes the instruction that set the round's depth, on any path.

OWNER = "Review override: light"


def owner_round(w: World, tmp: Path, sha: str, depth: str = "light", result: str = "FAIL",
                reviewers: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    return verdict(w, tmp, sha, reviewers or [COR, VER], "sensitive", result, depth=depth,
                   effort={COR: "medium", VER: "medium"}, extra=("--owner", OWNER))


def test_an_owner_override_sets_a_sensitive_round_light_and_the_record_says_so(w: World, tmp_path: Path) -> None:
    head = w.commit({"cloud/hooks/x.sh": "x\n"})
    code, p, err = plan(w, "--depth", "light", "--owner", OWNER)
    assert code == 0, err
    assert (p["floor"], p["depth"], lenses_of(p), p["override"]) == ("focused", "light", [COR], "light")
    done = owner_round(w, tmp_path, head, result="PASS")
    assert done.returncode == 0, done.stderr
    body = w.comments()[-1]["body"]
    assert body.split("\n")[1] == (f"{REVIEW} sha={head} state=success tier=sensitive reviewed={head} depth=light "
                                   "override=light -->")
    assert f'- Owner override: depth light, by the owner\'s words: "{OWNER}"' in body.split("\n")


def test_without_owner_words_the_same_light_round_is_refused(w: World, tmp_path: Path) -> None:
    head = w.commit({"cloud/hooks/x.sh": "x\n"})
    done = verdict(w, tmp_path, head, [COR, VER], "sensitive", depth="light", effort={COR: "medium", VER: "medium"})
    assert done.returncode == 2 and "below" in done.stderr and w.writes() == []


@pytest.mark.parametrize("args, why", [
    (["--depth", "none", "--owner", OWNER], "never skips review"),
    (["--owner", OWNER], "never skips review"),
    (["--depth", "light", "--owner", ""], "one line"),
    (["--depth", "light", "--owner", "light\n<!-- a forged line -->"], "one line"),
    (["--depth", "light", "--owner", "light --> x"], "one line"),
    (["--depth", "light", "--owner", "x" * 301], "one line"),
])
def test_an_owner_override_out_of_shape_is_refused(w: World, tmp_path: Path, args: list[str], why: str) -> None:
    head = w.commit({"cloud/hooks/x.sh": "x\n"})
    code, _, err = plan(w, *args)
    assert code == 2 and why in err, err
    extra = tuple(a for a in args if a not in ("--depth", "light", "none"))
    done = verdict(w, tmp_path, head, [COR, VER], "sensitive", depth=args[1] if args[0] == "--depth" else None,
                   effort={COR: "medium", VER: "medium"}, extra=extra)
    assert done.returncode == 2 and why in done.stderr and w.writes() == []


def test_a_routine_record_takes_no_owner_override(w: World) -> None:
    base_has(w, {"REVIEW.md": "Depth: none\n"})
    w.commit({"src/app.py": "x = 2\n"})
    done = w.verdict("12", "--tier", "routine", "--owner", OWNER)
    assert done.returncode == 2 and "--owner" in done.stderr and w.writes() == []


def test_a_round_after_an_overridden_one_narrows_only_at_no_greater_depth(w: World, tmp_path: Path) -> None:
    # A light round the owner set never narrows a deeper one: without the override, or with a deeper one, the next
    # round reviews the whole change; under the same light override it is a light fix round.
    head = w.commit({"cloud/hooks/x.sh": "x\n", "src/app.py": "x = 1\n"})
    assert owner_round(w, tmp_path, head).returncode == 0
    w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert (p["round"], p["depth"], p["since"], lenses_of(p)) == ("first", "focused", None, [COR, GRD])
    code, p, err = plan(w, "--depth", "full")
    assert code == 0 and p["round"] == "first", (err, p)
    code, p, err = plan(w, "--depth", "focused", "--owner", OWNER)
    assert code == 0 and p["round"] == "first", (err, p)
    code, p, err = plan(w, "--depth", "light", "--owner", OWNER)
    assert code == 0, err
    assert (p["round"], lenses_of(p)) == ("fix", [COR])
    fix = w.git(w.repo, "rev-parse", "HEAD")
    done = verdict(w, tmp_path, fix, [COR, VER], "sensitive", effort={COR: "medium", VER: "medium"})
    assert done.returncode == 2 and GRD in done.stderr and len(w.comments()) == 1


def test_a_repost_carries_the_override_and_takes_no_owner_words(w: World, tmp_path: Path) -> None:
    head = w.commit({"cloud/hooks/x.sh": "x\n"})
    assert owner_round(w, tmp_path, head, result="PASS").returncode == 0
    merge_main(w)
    args = ("12", "--tier", "sensitive", "--reviewers", f"{COR}, {VER}", "--reviewed", head,
            "--file", review_file(tmp_path, head), "--repost")
    done = w.verdict(*args, "--owner", OWNER, cost=False)
    assert done.returncode == 2 and "--owner" in done.stderr
    done = w.verdict(*args, cost=False)
    assert done.returncode == 0, done.stderr
    body = w.comments()[-1]["body"]
    assert body.split("\n")[1].endswith(f"reviewed={head} depth=light override=light -->")
    first = w.comments()[-2]["html_url"]
    assert f"- Owner override: depth light, carried from the reposted round's record ({first}), which quotes the owner" in body


def test_a_repost_of_a_light_round_with_no_override_stays_refused_below_the_floor(w: World, tmp_path: Path) -> None:
    head = w.commit({"cloud/hooks/x.sh": "x\n"})
    assert owner_round(w, tmp_path, head, result="PASS").returncode == 0
    cs = w.comments()
    cs[-1]["body"] = cs[-1]["body"].replace(" override=light -->", " -->", 1)
    (w.fx / "comments.json").write_text(json.dumps(cs))
    merge_main(w)
    done = w.verdict("12", "--tier", "sensitive", "--reviewers", f"{COR}, {VER}", "--reviewed", head,
                     "--file", review_file(tmp_path, head), "--repost", cost=False)
    assert done.returncode == 2 and "below the floor" in done.stderr, done.stderr


def test_a_repost_of_a_record_whose_override_is_not_its_depth_is_refused(w: World, tmp_path: Path) -> None:
    head = w.commit({"cloud/hooks/x.sh": "x\n"})
    assert owner_round(w, tmp_path, head, result="PASS").returncode == 0
    cs = w.comments()
    cs[-1]["body"] = cs[-1]["body"].replace(" override=light -->", " override=focused -->", 1)
    (w.fx / "comments.json").write_text(json.dumps(cs))
    merge_main(w)
    done = w.verdict("12", "--tier", "sensitive", "--reviewers", f"{COR}, {VER}", "--reviewed", head,
                     "--file", review_file(tmp_path, head), "--repost", cost=False)
    assert done.returncode == 2 and "names another depth" in done.stderr, done.stderr


@pytest.mark.parametrize("override, depth", [("focused", "light"), ("none", "none"), ("light", None)])
def test_record_py_refuses_an_override_that_is_not_the_record_s_depth(override: str, depth: str | None) -> None:
    done = subprocess.run([sys.executable, str(RECORD), "build", "--kind", "review", "--sha", "a" * 40, "--state",
                           "success", "--tier", "sensitive", "--reviewed", "a" * 40, "--title",
                           "🤖 Review: pass (sensitive tier)", *(["--depth", depth] if depth else []),
                           "--override", override], capture_output=True, text=True)
    assert done.returncode == 1 and "--override" in done.stderr, done.stderr


# A fix round never narrows from a record that reviewed less than the change now needs.


def test_a_record_below_the_change_s_tier_never_narrows_it(w: World, tmp_path: Path) -> None:
    first = w.commit({"src/app.py": "x = 2\n"})
    assert verdict(w, tmp_path, first, [COR, VER], "standard", "FAIL", depth="focused").returncode == 0
    head = w.commit({"src/app.py": "x = 3\n", "RULES.md": "a new rule\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert (p["tier"], p["round"], p["since"], lenses_of(p)) == ("sensitive", "first", None, [COR, GRD])
    done = verdict(w, tmp_path, head, [COR, VER], "sensitive", depth="focused")
    assert done.returncode == 2 and GRD in done.stderr and len(w.comments()) == 1


def test_a_fix_bringing_in_a_new_sensitive_path_runs_the_sensitive_set(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("CLM-1",))
    w.commit({"cloud/setup.sh": "x\n", "AGENTS.md": "a new rule\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert p["round"] == "fix" and sorted(lenses_of(p)) == sorted([COR, CLM, GRD])


def test_a_merge_of_main_does_not_count_main_s_sensitive_paths_as_reviewed(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("CLM-1",))
    (w.seed / "hooks").mkdir()
    merge_main(w, {"hooks/y.sh": "main's\n"})
    w.commit({"hooks/y.sh": "the PR's own change\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert p["round"] == "fix" and sorted(lenses_of(p)) == sorted([COR, CLM, GRD])


def test_a_fix_to_a_sensitive_path_the_round_held_runs_the_sensitive_set_too(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("CLM-1",))
    w.commit({"cloud/hooks/x.sh": "y\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert p["round"] == "fix" and sorted(lenses_of(p)) == sorted([COR, CLM, GRD])


def test_a_fix_round_after_a_pass_still_runs_correctness(w: World, tmp_path: Path) -> None:
    sha = w.commit({"cloud/hooks/x.sh": "x\n"})
    assert verdict(w, tmp_path, sha, SENSITIVE + [VER], "sensitive", "PASS").returncode == 0
    head = w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w)
    assert code == 0 and p["round"] == "fix" and lenses_of(p) == [COR], (p, err)
    done = verdict(w, tmp_path, head, [CLM], "sensitive", "PASS", ids=())
    assert done.returncode == 2 and COR in done.stderr


@pytest.mark.parametrize("words", ["light\nBlocking: none", "light\rBlocking: none"])
def test_owner_words_with_a_line_break_are_refused(w: World, words: str) -> None:
    w.commit({"cloud/hooks/x.sh": "x\n"})
    code, _, err = plan(w, "--depth", "light", "--owner", words)
    assert code == 2 and "one line" in err, (code, err)


def test_a_record_without_depth_plans_a_first_review(w: World, tmp_path: Path) -> None:
    w.commit({"cloud/hooks/x.sh": "x\n"})
    later = w.commit({"src/app.py": "x = 2\n"})
    head = w.commit({"src/app.py": "x = 3\n"})
    post(w, crafted(head, later, fail_output(later), tier="sensitive", depth=None, tmp=tmp_path))
    code, p, err = plan(w)
    assert code == 0 and p["round"] == "first", (p, err)


def test_a_prose_fix_after_a_pass_still_runs_a_lens(w: World, tmp_path: Path) -> None:
    sha = w.commit({"cloud/hooks/x.sh": "x\n"})
    assert verdict(w, tmp_path, sha, SENSITIVE + [VER], "sensitive", "PASS").returncode == 0
    w.commit({"docs/a.md": "x\n"})
    code, p, err = plan(w)
    assert code == 0 and p["round"] == "fix" and lenses_of(p) == [CLM] and p["verifier"] == VER, (p, err)
