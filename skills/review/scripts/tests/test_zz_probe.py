from test_plan import first_round, plan, lenses_of, COR, CLM, GRD, VER, SENSITIVE
from test_review_scripts import base_has, w, env  # noqa


def test_two_paths_sensitive_not_first(w, tmp_path):
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("CLM-1",))
    w.commit({"cloud/hooks/x.sh": "y\n", "a/b.md": "x\n"})
    code, p, err = plan(w)
    print("TWO", code, p.get("round"), lenses_of(p), err[-300:])
    assert p["round"] == "fix" and sorted(lenses_of(p)) == sorted([COR, CLM, GRD])
