from test_plan import *  # noqa
def test_probe_fix_round_adding_new_sensitive_path(w, tmp_path):
    first_round(w, tmp_path, {"cloud/hooks/x.sh": "x\n"}, "sensitive", SENSITIVE + [VER], ids=("COR-1",))
    w.commit({"cloud/setup.sh": "chmod 777 /etc\n", "AGENTS.md": "new rule\n"})
    code, p, err = plan(w)
    print("PLAN>>", code, p["round"], p["tier"], p["depth"], lenses_of(p), p["planned"])
