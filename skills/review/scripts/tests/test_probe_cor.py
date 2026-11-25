from pathlib import Path
from test_plan import COR, GRD, VER, plan, lenses_of, verdict  # noqa: F401
from test_review_scripts import World, w, env  # noqa: F401
def test_probe(w: World, tmp_path: Path) -> None:
    first = w.commit({"src/app.py": "x = 2\n"})
    assert verdict(w, tmp_path, first, [COR, VER], "standard", "FAIL", depth="focused").returncode == 0
    head = w.commit({"src/app.py": "x = 3\n", "RULES.md": "a new rule\n"})
    code, p, err = plan(w)
    print("PLAN", p["tier"], p["floor"], p["depth"], p["round"], lenses_of(p))
    done = verdict(w, tmp_path, head, [COR, VER], "sensitive", depth="focused")
    print("VERDICT rc", done.returncode, done.stderr.strip()[:300])
    print("MARKER", [l for l in w.comments()[-1]["body"].splitlines() if "loadout:review" in l])
    assert GRD in lenses_of(p), "guardrail-reviewer never planned on a sensitive change"
