from test_review_scripts import *  # noqa: F403
def test_gate_stamp_last_line_holding_zwsp_reads_back(w, tmp_path):
    w.commit({"src/app.py": "x = 2\n"})
    log = tmp_path / "log.txt"
    log.write_text("ok\n12 passed a​b\n", encoding="utf-8")
    done = w.run("gate_stamp.sh", "--", "cat", str(log), LC_ALL="C.UTF-8")
    assert done.returncode == 0, done.stderr
    [c] = w.comments()
    assert "- Last line: 12 passed a\\u{200B}b" in c["body"], c["body"]
