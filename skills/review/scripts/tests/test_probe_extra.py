from test_plan import *  # noqa: F401,F403
from test_plan import (COR, CLM, VER, SENSITIVE, World, crafted, first_round, plan, post, review_file, verdict,
                       lenses_of)
from pathlib import Path


def _review_md_on_main(w, text):
    (w.seed / "REVIEW.md").write_text(text)
    w.git(w.seed, "add", "REVIEW.md")
    w.git(w.seed, "commit", "-qm", "policy")
    w.git(w.seed, "push", "-q", str(w.remote), "main")
    w.git(w.repo, "fetch", "-q", "origin")


def test_probe_repost_below_a_raised_floor_refuses(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    assert verdict(w, tmp_path, reviewed, [COR, VER], "standard").returncode == 0  # depth light
    _review_md_on_main(w, "Depth: full\n")
    w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    done = w.verdict("12", "--tier", "standard", "--reviewers", f"{COR}, {VER}", "--reviewed", reviewed,
                     "--file", review_file(tmp_path, reviewed), "--repost", cost=False)
    print("RC", done.returncode, done.stderr[-300:])
    assert done.returncode == 2, done.stderr


def test_probe_repost_of_a_record_that_reviewed_another_commit_refuses(w: World, tmp_path: Path) -> None:
    reviewed = w.commit({"src/app.py": "x = 2\n"})
    assert verdict(w, tmp_path, reviewed, [COR, VER], "standard").returncode == 0
    other = w.commit({"src/app.py": "x = 3\n"})
    done = w.verdict("12", "--tier", "standard", "--reviewers", f"{COR}, {VER}", "--reviewed", other,
                     "--file", review_file(tmp_path, other), "--repost", cost=False)
    print("RC", done.returncode, done.stderr[-300:])
    assert done.returncode == 2, done.stderr


def test_probe_a_routine_record_with_a_reviewed_line_starts_no_fix_round(w: World, tmp_path: Path) -> None:
    a = w.commit({"cloud/hooks/x.sh": "x\n"})
    post(w, crafted(a, a, f"VERDICT: PASS {a}\nReviewed: {a}\nBlocking: none\n\nNo findings.\n", tier="routine",
                    state="success", tmp=tmp_path))
    w.commit({"src/app.py": "x = 2\n"})
    code, p, err = plan(w)
    assert code == 0, err
    print("PLAN", p["round"], lenses_of(p))
    assert p["round"] == "first" and set(SENSITIVE) <= set(lenses_of(p)), p


def test_probe_repost_naming_an_unreviewed_commit_refuses(w: World, tmp_path: Path) -> None:
    r1 = w.commit({"src/app.py": "x = 2\n"})
    assert verdict(w, tmp_path, r1, [COR, VER], "standard", depth="full").returncode == 0
    r2 = w.commit({"src/app.py": "x = 3\n"})
    w.main_moves({"README.md": "main moved\n"})
    w.git(w.repo, "merge", "-q", "--no-edit", "origin/main")
    w.push()
    done = w.verdict("12", "--tier", "standard", "--reviewers", f"{COR}, {VER}", "--reviewed", r2,
                     "--file", review_file(tmp_path, r2), "--repost", cost=False)
    print("RC2", done.returncode, done.stderr[-300:])
    assert done.returncode == 2, done.stderr
