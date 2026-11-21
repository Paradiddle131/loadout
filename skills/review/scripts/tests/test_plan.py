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
SENSITIVE = [COR, CLM, GRD]
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


def crafted(sha: str, reviewed: str, output: str, *, tmp: Path, tier: str = "standard",
            state: str = "failure") -> str:
    """A review record's body in verdict.sh's shape, built with record.py, holding `output` as its raw output."""
    raw = tmp / f"crafted-{reviewed[:8]}.txt"
    raw.write_text(output)
    title = f"🤖 Review: {'pass' if state == 'success' else 'fail'} ({tier} tier)"
    return subprocess.run([sys.executable, str(RECORD), "build", "--kind", "review", "--sha", sha, "--state", state,
                           "--tier", tier, "--reviewed", reviewed, "--title", title, "--line", "- x",
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
    assert (p["tier"], p["floor"], p["first"], sorted(p["then"])) == ("sensitive", "focused", [COR],
                                                                       sorted([CLM, GRD]))


def test_floor_review_md_sensitive_paths_need_focused_with_their_lenses(w: World) -> None:
    base_has(w, {"REVIEW.md": "## Sensitive\n- `src/**`; lenses: leak-hunter\n"})
    w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert p["floor"] == "focused" and p["first"] == [COR] and sorted(p["then"]) == sorted([CLM, GRD, LEAK])


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


@pytest.mark.parametrize("missing", [COR, CLM, GRD, VER])
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
    assert f["planned"] == ",".join([COR, CLM, GRD, VER])


# Efforts (each lens's own; the merge guard never reads them).


def test_effort_is_high_for_correctness_and_control_on_sensitive_code(w: World) -> None:
    base_has(w, {"REVIEW.md": "## Sensitive\n- `guard/**`; lenses: control-prober\n"})
    w.commit({"guard/check.py": "x\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert p["effort"] == {COR: "high", CLM: "medium", GRD: "medium", CTL: "high", VER: "medium"}


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
    done = verdict(w, tmp_path, head, SENSITIVE + [VER], "sensitive", effort={COR: "medium"})
    assert done.returncode == 2 and COR in done.stderr and "effort" in done.stderr and w.writes() == []
    done = verdict(w, tmp_path, head, SENSITIVE + [VER], "sensitive", effort={CLM: "xhigh"})
    assert done.returncode == 0, done.stderr


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
    assert p["round"] == "fix" and set(SENSITIVE) <= set(lenses_of(p))


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
    # An outsider's record that reviewed `later` would hide RULES.md from the fix range: it does not count.
    post(w, crafted(head, later, fail_output(later), tmp=tmp_path), assoc="NONE")
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
        body = crafted(head, later, "", tier="routine", state="success", tmp=tmp_path)
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


def test_the_previous_round_is_read_from_the_pr_never_passed_in(w: World, tmp_path: Path) -> None:
    # verdict.sh takes the previous round from the PR itself: an output file of another round only reaches it as
    # --file, which must name the reviewed commit.
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("GRD-1",))
    head = w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert p["round"] == "fix" and sorted(lenses_of(p)) == sorted([COR, GRD])


# Fix rounds rerun what they answer (focused) or the whole set (full).


def test_a_fix_round_reruns_the_lens_a_must_fix_came_from_and_correctness_on_code(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("CLM-1",))
    w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert p["first"] == [COR] and p["then"] == [CLM] and p["verifier"] == VER


def test_a_documentation_fix_runs_claims_auditor(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("COR-1",))
    w.commit({"docs/a.md": "x\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert sorted(lenses_of(p)) == sorted([COR, CLM])


def test_a_fix_round_runs_the_review_md_lenses_of_the_paths_it_changed(w: World, tmp_path: Path) -> None:
    base_has(w, {"REVIEW.md": "## Sensitive\n- `lib/**`; lenses: leak-hunter\n"})
    first_round(w, tmp_path, {"src/app.py": "x = 2\n"}, "standard", [COR, VER])
    w.commit({"lib/x.py": "x\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert set(SENSITIVE + [LEAK]) <= set(lenses_of(p))


def test_a_blocking_id_naming_no_lens_reruns_the_whole_set(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("ODD-1",))
    w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w)
    assert code == 0, err
    assert sorted(lenses_of(p)) == sorted(SENSITIVE)


def test_a_full_fix_round_reruns_the_whole_set(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("COR-1",))
    w.commit({"src/app.py": "x = 2\n"})
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
