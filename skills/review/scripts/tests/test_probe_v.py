import pytest
from test_review_scripts import *  # noqa
from test_review_scripts import routine_output, DISMISSED, BLOCKING_LINE

@pytest.mark.parametrize("text", [
    "VERDICT: PASS {h}\nReviewed: {h}\nBlocking: none\nDismissals: re-ran 1, promoted 0\nDismissals: re-ran 1, promoted 0\n\nNo findings.\n",
    "VERDICT: PASS {h}\nReviewed: {h}\nBlocking: none\nDismissals: re-ran x\n\nNo findings.\n",
    "VERDICT: PASS {h}\nReviewed: {h}\nBlocking: none\n\n## Nits\nDismissals: re-ran 0, promoted 0\n",
    "VERDICT: PASS {h}\nReviewed: {h}\nBlocking: none\nDismissals: re-ran 2, promoted 1\n\nNo findings.\n",
])
def test_probe(w, tmp_path, text):
    head = w.commit({"docs/a.md": "x\n"})
    out = routine_output(tmp_path, text.format(h=head))
    d = w.verdict("12", "--tier", "routine", "--reviewed", head, "--file", out)
    print("PROBE", d.returncode, d.stderr.strip()[:160].replace("\n"," "), (w.comments()[0]["body"][:60] if w.comments() else "-"))

def test_probe_nofile(w):
    w.commit({"docs/a.md": "x\n"})
    d = w.verdict("12", "--tier", "routine")
    print("PROBE nofile", d.returncode, d.stderr.strip()[:100], w.comments()[0]["body"][:40] if w.comments() else "-")
