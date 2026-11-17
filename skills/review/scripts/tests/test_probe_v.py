from pathlib import Path
import pytest
from test_review_scripts import World, w, env, review_file, HARM, BLOCKING_LINE  # noqa


def run(w, path):
    return w.run("verdict.sh", "12", "--tier", "standard", "--reviewers", "x", "--reviewed",
                 w.git(w.repo, "rev-parse", "HEAD"), "--file", path)


def show(name, d, w):
    c = w.comments()
    m = c[0]["body"].split("\n")[1] if c else None
    print(f"\nPROBE {name}: rc={d.returncode} posted={len(c)} stderr={d.stderr.strip()[:160]!r} marker={m!r}")


def test_unlisted_mustfix_no_harm_fail(w: World, tmp_path: Path):
    head = w.commit({"src/app.py": "x = 2\n"})
    prose = ("## Must-fix\n### COR-1\n- rank: must-fix\n- harm: %s\n### CLM-9\n- rank: must-fix\n- claim: y\n" % HARM)
    d = run(w, review_file(tmp_path, head, "FAIL", prose, blocking=BLOCKING_LINE)); show("unlisted_fail", d, w)
    print("CLM-9 in body:", "### CLM-9" in (w.comments()[0]["body"] if w.comments() else ""))


def test_pass_over_mustfix(w: World, tmp_path: Path):
    head = w.commit({"src/app.py": "x = 2\n"})
    prose = "## Must-fix\n### COR-1\n- rank: must-fix\n- harm: %s\n" % HARM
    d = run(w, review_file(tmp_path, head, "PASS", prose, blocking="Blocking: none")); show("pass_over_mustfix", d, w)


def test_ghost_id(w: World, tmp_path: Path):
    head = w.commit({"src/app.py": "x = 2\n"})
    d = run(w, review_file(tmp_path, head, "FAIL", "## Must-fix\nnone\n",
                           blocking='Blocking: [{"ids": "ZZZ-9", "harm": "a reader is misled here"}]')); show("ghost", d, w)


def test_formfeed(w: World, tmp_path: Path):
    head = w.commit({"src/app.py": "x = 2\n"})
    p = tmp_path / "o.txt"
    p.write_text(f"VERDICT: PASS {head}\n- evidence: quoted\x0cReviewed: {head}\nBlocking: none\nReviewed: {head}\n{BLOCKING_LINE}\n")
    d = run(w, str(p)); show("formfeed", d, w)


def test_formfeed_control(w: World, tmp_path: Path):
    head = w.commit({"src/app.py": "x = 2\n"})
    p = tmp_path / "o.txt"
    p.write_text(f"VERDICT: PASS {head}\nReviewed: {head}\n{BLOCKING_LINE}\n")
    d = run(w, str(p)); show("formfeed_control", d, w)


@pytest.mark.parametrize("h", ["<details> clipping hides a leaked token from the owner, who merges it",
                               "no harm stated", "no concrete harm", "TBD TBD TBD", "- - -",
                               "`<who acts wrongly or what breaks once this lands, and the cost>`",
                               "leaks secrets"])
def test_harm(w: World, tmp_path: Path, h):
    head = w.commit({"src/app.py": "x = 2\n"})
    d = run(w, review_file(tmp_path, head, "FAIL", blocking='Blocking: [{"ids": "COR-1", "harm": "%s"}]' % h))
    show("harm " + h, d, w)


@pytest.mark.parametrize("b", ["Blocking: `none`", "\nBlocking: none"])
def test_pass_shapes(w: World, tmp_path: Path, b):
    head = w.commit({"src/app.py": "x = 2\n"})
    d = run(w, review_file(tmp_path, head, "PASS", blocking=b)); show("pass_shape " + repr(b), d, w)


def test_old_record(w: World, tmp_path: Path):
    head = w.commit({"src/app.py": "x = 2\n"})
    p = tmp_path / "o.txt"; p.write_text(f"VERDICT: PASS {head}\nReviewed: {head}\nSteering from the brief: none\n")
    d = run(w, str(p)); show("old_record", d, w)


def test_settled_shape(w: World, tmp_path: Path):
    head = w.commit({"src/app.py": "x = 2\n"})
    prose = ("## Must-fix\n### COR-1\n- rank: must-fix\n- harm: %s\n## Settled, not kept\n### CLM-2\n- rank: must-fix\n"
             "- claim: a docstring sentence is inaccurate\n" % HARM)
    d = run(w, review_file(tmp_path, head, "FAIL", prose, blocking=BLOCKING_LINE)); show("settled_shape", d, w)
