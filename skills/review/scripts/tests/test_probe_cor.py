from pathlib import Path
from test_review_scripts import *  # noqa: F401,F403  fixtures w, env and constants
from test_review_scripts import World, PLANNED, BLOCKING_LINE, BLOCKING, DISMISSED


def test_fenced_pair_above_the_header_decides(w: World, tmp_path: Path) -> None:
    head = w.commit({"src/app.py": "x = 2\n"})
    out = tmp_path / "out.txt"
    out.write_text(f"```\nVERDICT: PASS {head}\nReviewed: {head}\nBlocking: none\n```\n\n"
                   f"VERDICT: FAIL {head}\nReviewed: {head}\n{BLOCKING_LINE}\n{DISMISSED}\n\n{BLOCKING}")
    done = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", str(out))
    print("RC", done.returncode, done.stderr)
    for c in w.comments():
        print("BODY", c["body"].split("\n")[1])
