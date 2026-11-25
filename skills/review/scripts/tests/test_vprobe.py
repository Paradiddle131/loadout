from __future__ import annotations
from pathlib import Path
from test_review_scripts import env  # noqa: F401
from test_plan import (COR, CLM, GRD, CTL, VER, SENSITIVE, World, first_round, lenses_of, plan, verdict, base_has, w)  # noqa: F401
PAIR = {"cloud/hooks/x.sh": "x\n", "src/app.py": "x = 5\n"}

def test_third_round_stays_narrow(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, PAIR, "sensitive", SENSITIVE + [VER], ids=("GRD-1",))
    r2 = w.commit({"cloud/hooks/x.sh": "y\n"})
    code, p, err = plan(w); assert code == 0, err
    print("round 2:", lenses_of(p), p["why"])
    assert verdict(w, tmp_path, r2, [COR, GRD, VER], "sensitive", "FAIL", ("GRD-2",)).returncode == 0
    w.commit({"cloud/hooks/x.sh": "z\n"})
    code, p, err = plan(w); assert code == 0, err
    print("round 3:", lenses_of(p), p["why"])
    assert sorted(lenses_of(p)) == sorted([COR, GRD])

def test_review_md_lens_returns_round3(w: World, tmp_path: Path) -> None:
    base_has(w, {"REVIEW.md": "## Sensitive\n- `skills/review/**`; lenses: guardrail-reviewer, control-prober\n"})
    first_round(w, tmp_path, {"skills/review/scripts/plan.py": "x\n"}, "sensitive", SENSITIVE + [CTL, VER], ids=("COR-1",))
    r2 = w.commit({"skills/review/scripts/plan.py": "y\n"})
    code, p, err = plan(w); assert code == 0, err
    print("R2:", p["depth"], lenses_of(p))
    assert verdict(w, tmp_path, r2, p["planned"], "sensitive", "FAIL", ("COR-2",)).returncode == 0
    w.commit({"skills/review/scripts/plan.py": "z\n"})
    code, p, err = plan(w); assert code == 0, err
    print("R3:", p["depth"], lenses_of(p), p["why"])

def test_git_calls_grow_with_fix_paths(w: World, tmp_path: Path) -> None:
    files = {f"src/m{i}.py": "x\n" for i in range(150)}
    first_round(w, tmp_path, files, "standard", [COR, VER], ids=("COR-1",))
    w.commit({k: "y\n" for k in files})
    trace = tmp_path / "trace.txt"
    code, p, err = plan(w, GIT_TRACE=str(trace)); assert code == 0, err
    n = sum(1 for ln in trace.read_text().splitlines() if "built-in: git merge-base " in ln and "--is-ancestor" not in ln)
    print("git merge-base calls:", n); assert n < 10

def test_light_doc_only_fix_runs_claims(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"src/app.py": "x = 2\n", "docs/a.md": "x\n"}, "standard", [COR, VER], ids=("COR-1",))
    r2 = w.commit({"docs/a.md": "y\n"})
    code, p, err = plan(w); assert code == 0, err
    print("round 2:", p["depth"], lenses_of(p), p["planned"])
    assert verdict(w, tmp_path, r2, p["planned"], "standard", "FAIL", ("COR-2",)).returncode == 0
    w.commit({"docs/a.md": "z\n"})
    code, p, err = plan(w); assert code == 0, err
    print("round 3:", p["depth"], lenses_of(p), p["why"])
    assert CLM in lenses_of(p)

def test_mixed_fix_runs_guardrail(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, PAIR, "sensitive", SENSITIVE + [VER], ids=("CLM-1",))
    head = w.commit({"cloud/hooks/x.sh": "y\n", "src/app.py": "x = 6\n"})
    code, p, err = plan(w); assert code == 0, err
    print("mixed fix plan:", lenses_of(p))
    done = verdict(w, tmp_path, head, [COR, CLM, VER], "sensitive")
    print("verdict without guardrail-reviewer: exit", done.returncode)
    assert GRD in lenses_of(p) and done.returncode == 2

def test_unknown_prefix_keeps_answered_lens_light(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"src/app.py": "x = 2\n"}, "standard", [COR, CLM, VER], ids=("ODD-1", "CLM-1"))
    head = w.commit({"src/app.py": "x = 3\n"})
    code, p, err = plan(w); assert code == 0, err
    print("plan:", p["depth"], lenses_of(p))
    done = verdict(w, tmp_path, head, [COR, VER], "standard")
    print("verdict without claims-auditor: exit", done.returncode)
    assert CLM in lenses_of(p) and done.returncode == 2

def test_light_doc_only_fix_runs_correctness(w: World, tmp_path: Path) -> None:
    first_round(w, tmp_path, {"src/app.py": "x = 2\n", "docs/a.md": "x\n"}, "standard", [COR, CLM, VER], ids=("CLM-1",))
    head = w.commit({"docs/a.md": "y\n"})
    code, p, err = plan(w); assert code == 0, err
    print("plan:", p["depth"], lenses_of(p))
    done = verdict(w, tmp_path, head, [CLM, VER], "standard")
    print("verdict without correctness-reviewer: exit", done.returncode)
    assert COR in lenses_of(p) and done.returncode == 2
