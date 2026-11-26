from test_review_scripts import *

def _run(w, tmp_path, text):
    head = w.commit({"src/app.py": "x = 2\n"})
    p = tmp_path / "o.txt"; p.write_text(text(head))
    d = w.verdict("12", "--tier", "standard", "--reviewers", PLANNED, "--reviewed", head, "--file", str(p))
    print("\nRC", d.returncode, "ERR", d.stderr.strip()[-200:])
    for c in w.comments(): print("BODY2", c["body"].split("\n")[1][:90])

def test_zw(w, tmp_path):
    _run(w, tmp_path, lambda h: f"VERDICT: PASS {h}\nRe​viewed: {h}\nBlocking: none\nReviewed: {h}\n{BLOCKING_LINE}\n{DISMISSED}\n\n{BLOCKING}")

def test_plain(w, tmp_path):
    _run(w, tmp_path, lambda h: f"VERDICT: PASS {h}\nReviewed: {h}\nBlocking: none\nReviewed: {h}\n{BLOCKING_LINE}\n{DISMISSED}\n\n{BLOCKING}")
