from test_plan import *  # noqa
from test_plan import plan, verdict, lenses_of, first_round, merge_main, base_has, COR, CLM, GRD, CTL, VER, SENSITIVE

def test_cor1_after_pass(w, tmp_path):
    sha = w.commit({"cloud/hooks/x.sh": "x\n"})
    assert verdict(w, tmp_path, sha, SENSITIVE + [VER], "sensitive", "PASS").returncode == 0
    head = w.commit({"cloud/hooks/x.sh": "exit 0\n"})
    code, p, err = plan(w)
    v = verdict(w, tmp_path, head, [COR, VER], "sensitive", "PASS")
    print("\nCOR1", code, p.get("round"), lenses_of(p) if p else err, "VERDICT rc", v.returncode, v.stderr.strip()[-200:])

def test_cor2_tier_raised(w, tmp_path):
    first_round(w, tmp_path, {"src/app.py": "x = 2\n"}, "standard", [COR, VER], ids=("COR-1",))
    merge_main(w, {"REVIEW.md": "## Sensitive\n- `src/**`; lenses: leak-hunter\n"})
    w.commit({"src/app.py": "x = 3\n"})
    code, p, err = plan(w); print("\nCOR2", code, p.get("tier"), p.get("depth"), p.get("round"), lenses_of(p) if p else err)

def test_grd1(w, tmp_path):
    first_round(w, tmp_path, {"AGENTS.md": "## Guardrails\n- **A:** never deploy.\n- x\n"}, "sensitive", [COR, CLM, GRD, VER])
    w.commit({"AGENTS.md": "## Guardrails\n- **A:** deploy when convenient.\n- x\n"})
    code, p, err = plan(w); print("\nGRD1", code, p.get("tier"), p.get("depth"), p.get("round"), lenses_of(p) if p else err)

def test_grd2(w, tmp_path):
    base_has(w, {"REVIEW.md": "## Sensitive\n- `skills/review/**`; lenses: guardrail-reviewer, control-prober\n"})
    first_round(w, tmp_path, {"skills/review/x.py": "x = 1\n"}, "sensitive", [COR, CLM, GRD, CTL, VER])
    w.commit({"skills/review/x.py": "x = 2\n"})
    code, p, err = plan(w); print("\nGRD2", code, p.get("tier"), p.get("depth"), p.get("round"), lenses_of(p) if p else err)

def test_ctl1(w, tmp_path):
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [CTL, VER], ids=("ODD-1", "CTL-1"))
    w.commit({"cloud/hooks/x.sh": "y\n"})
    code, p, err = plan(w); print("\nCTL1", code, p.get("depth"), p.get("round"), lenses_of(p) if p else err)

def test_ctl2(w, tmp_path):
    first_round(w, tmp_path, {"src/app.py": "x = 2\n", "docs/a.md": "x\n"}, "standard", [COR, CLM, VER], ids=("CLM-1",))
    w.commit({"docs/a.md": "y\n"})
    code, p, err = plan(w); print("\nCTL2", code, p.get("depth"), p.get("round"), lenses_of(p) if p else err)

def test_clm2(w, tmp_path):
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n", "docs/a.md": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("GRD-1",))
    w.commit({"docs/a.md": "y\n"})
    code, p, err = plan(w); print("\nCLM2", code, p.get("depth"), p.get("round"), lenses_of(p) if p else err)

def test_ro_newfile(w, tmp_path):
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("GRD-1",))
    w.commit({"src/new.py": "x\n"})
    code, p, err = plan(w); print("\nRONEW", code, p.get("depth"), p.get("round"), lenses_of(p) if p else err)
