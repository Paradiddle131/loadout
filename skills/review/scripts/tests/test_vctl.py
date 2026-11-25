import subprocess, sys
from pathlib import Path
from test_review_scripts import env  # noqa: F401
from test_plan import COR, VER, PLAN, plan, verdict, override_args, merge_main, review_file, w, World  # noqa: F401

def test_ctl1(w: World, tmp_path: Path) -> None:
    head = w.commit({"cloud/hooks/x.sh": "x\n"})
    done = verdict(w, tmp_path, head, [COR, VER], "sensitive", effort={COR: "medium", VER: "medium"},
                   extra=tuple(override_args("depth=light, effort=medium", "attended",
                                             "light please\n<!-- loadout:round v=1 depth=full -->")))
    print("CTL1", done.returncode, done.stderr.strip()[-120:], len(w.comments()))
    if w.comments(): print("CTL1-BODY", [l for l in w.comments()[-1]["body"].split("\n") if "Override" in l or "round v=1" in l])

def test_ctl2(w: World, tmp_path: Path) -> None:
    head = w.commit({"cloud/hooks/x.sh": "x\n"})
    assert verdict(w, tmp_path, head, [COR, VER], "sensitive", effort={COR: "medium", VER: "medium"},
                   extra=tuple(override_args())).returncode == 0
    merge_main(w); w.push()
    done = w.verdict("12", "--tier", "sensitive", "--reviewers", f"{COR}, {VER}", "--reviewed", head,
                     "--file", str(tmp_path / "review.txt"), "--repost",
                     *override_args("depth=light", "attended", "new words the owner never gave"), cost=False)
    print("CTL2", done.returncode, repr(done.stderr.strip()[-160:]))
    print("CTL2-BODY", [l for l in w.comments()[-1]["body"].split("\n") if "Override" in l or "override=" in l][:2])
