from test_review_scripts import *
from test_review_scripts import PLANNED
import pytest
CASES = {"nodismiss": "VERDICT: PASS {h}\nReviewed: {h}\nBlocking: none\n\nNo findings.\n",
         "overpromoted": "VERDICT: PASS {h}\nReviewed: {h}\nBlocking: none\nDismissals: re-ran 0, promoted 3\n\nNo findings.\n"}
@pytest.mark.parametrize("case", list(CASES))
@pytest.mark.parametrize("tier", ["routine", "standard"])
def test_probe(w, tmp_path, case, tier):
    h = w.commit({"docs/a.md": "x\n"}); p = tmp_path / "o.txt"; p.write_text(CASES[case].format(h=h))
    extra = [] if tier == "routine" else ["--reviewers", PLANNED, "--cycle", "1", "--dupes", "0", "--nits", "0"]
    d = w.verdict("12", "--tier", tier, "--reviewed", h, "--file", str(p), *extra)
    body = w.comments()[0]["body"][:120].replace("\n", " | ") if w.comments() else ""
    print(f"\nPROBE {tier} {case}: rc={d.returncode} err={d.stderr.strip()[:140]!r} body={body!r}")
