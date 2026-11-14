"""bin/friction against a stub `gh`, from a throwaway clone whose origin is an invented repository.

Run: uvx --from pytest==8.4.2 pytest -q bin/tests
"""

from __future__ import annotations

import fcntl
import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FRICTION = Path(__file__).resolve().parent.parent / "friction"
REPO = "example-owner/example-repo"

# `gh api` against files in $STUB_DIR: issues.json, label.json, comments.json; calls.jsonl logs every call.
# STUB_FAIL=<text>: a call whose endpoint contains it fails as gh does; STUB_MANGLE=1: a posted comment reads back
# changed.
STUB_GH = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
d = Path(os.environ["STUB_DIR"])
args = sys.argv[1:]
assert args[0] == "api", args
method, endpoint, payload, i = "GET", "", None, 1
while i < len(args):
    if args[i] == "-X":
        method, i = args[i + 1], i + 2
    elif args[i] == "--input":
        payload, i = json.loads(sys.stdin.read()), i + 2
    else:
        endpoint, i = args[i], i + 1
with (d / "calls.jsonl").open("a") as log:
    log.write(json.dumps({"method": method, "endpoint": endpoint, "payload": payload}) + "\n")
if os.environ.get("STUB_FAIL") and os.environ["STUB_FAIL"] in endpoint:
    sys.exit("gh: Server Error (HTTP 502)")
def load(name, default):
    p = d / name
    return json.loads(p.read_text()) if p.exists() else default
if method == "GET" and "/issues?" in endpoint:
    out = load("issues.json", [])
elif method == "GET" and endpoint.endswith("/labels/friction"):
    if not (d / "label.json").exists():
        sys.exit("gh: Not Found (HTTP 404)")
    out = load("label.json", {})
elif method == "POST" and endpoint.endswith("/labels"):
    (d / "label.json").write_text(json.dumps(payload))
    out = payload
elif method == "POST" and endpoint.endswith("/issues"):
    issues = load("issues.json", [])
    out = {**payload, "number": 7}
    (d / "issues.json").write_text(json.dumps(issues + [out]))
elif method == "POST" and endpoint.endswith("/comments"):
    posted = load("comments.json", [])
    out = {"id": len(posted) + 1, "endpoint": endpoint, "body": payload["body"]}
    (d / "comments.json").write_text(json.dumps(posted + [out]))
    if os.environ.get("STUB_MANGLE"):
        out = {**out, "body": out["body"] + "x"}
else:
    sys.exit(f"stub gh: no route for {method} {endpoint}")
print(json.dumps(out))
'''


class Fx:
    def __init__(self, tmp: Path) -> None:
        self.clone = tmp / "collection"
        (self.clone / "bin").mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=self.clone, check=True)
        subprocess.run(["git", "remote", "add", "origin", f"https://github.com/{REPO}.git"], cwd=self.clone,
                       check=True)
        self.script = self.clone / "bin/friction"
        shutil.copy(FRICTION, self.script)
        self.stub = tmp / "stub"
        self.stub.mkdir()
        self.bin = tmp / "path"
        self.bin.mkdir()
        (self.bin / "gh").write_text(STUB_GH)
        (self.bin / "gh").chmod(0o755)
        self.log = tmp / "home/.claude/loadout-friction.jsonl"
        self.home = tmp / "home"

    def env(self, gh: bool = True, **extra: str) -> dict[str, str]:
        path = f"{self.bin}:/usr/bin:/bin" if gh else "/usr/bin:/bin"
        return {"HOME": str(self.home), "PATH": path, "STUB_DIR": str(self.stub), **extra}

    def run(self, *args: str, gh: bool = True, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(self.script), *args], capture_output=True, text=True,
                              timeout=60, env=self.env(gh, **extra), stdin=subprocess.DEVNULL)

    def lines(self) -> list[dict]:
        return [json.loads(x) for x in self.log.read_text().splitlines()]

    def calls(self) -> list[tuple[str, str]]:
        p = self.stub / "calls.jsonl"
        return [(c["method"], c["endpoint"]) for c in map(json.loads, p.read_text().splitlines())] if p.exists() \
            else []

    def comments(self) -> list[dict]:
        p = self.stub / "comments.json"
        return json.loads(p.read_text()) if p.exists() else []

    def posted(self) -> int:
        p = Path(f"{self.log}.posted")
        return int(p.read_text()) if p.exists() else 0


@pytest.fixture
def fx(tmp_path: Path) -> Fx:
    return Fx(tmp_path)


def test_a_note_is_appended_then_posted_on_a_new_friction_issue(fx: Fx) -> None:
    done = fx.run("note", "the guard refused\na grep", "--part", "merge-guard", "--workaround", "used Grep " * 99)
    assert done.returncode == 0, done.stderr
    [line] = fx.lines()
    assert line["kind"] == "note" and line["note"] == "the guard refused a grep" and line["part"] == "merge-guard"
    assert len(line["workaround"]) == 500
    assert fx.calls() == [("GET", f"repos/{REPO}/issues?state=open&labels=friction&per_page=100"),
                          ("GET", f"repos/{REPO}/labels/friction"), ("POST", f"repos/{REPO}/labels"),
                          ("POST", f"repos/{REPO}/issues"), ("POST", f"repos/{REPO}/issues/7/comments")]
    [comment] = fx.comments()
    assert comment["body"].startswith("🤖 Friction: 1 new entry")
    assert "note (merge-guard): the guard refused a grep; workaround: used Grep" in comment["body"]
    assert fx.posted() == fx.log.stat().st_size
    issue = json.loads((fx.stub / "issues.json").read_text())[0]
    assert issue["labels"] == ["friction"] and issue["body"].startswith("🤖")


def test_a_refusal_holds_the_guard_and_rule_only_and_never_posts(fx: Fx) -> None:
    assert fx.run("refusal", "--guard", "merge-guard", "--rule", "pr-merge").returncode == 0
    assert fx.run("refusal", "--guard", "merge-guard", "--rule", "gh pr merge 12; cat /srv/secret").returncode == 0
    assert [set(e) for e in fx.lines()] == [{"at", "kind", "guard", "rule"}] * 2
    assert [e["rule"] for e in fx.lines()] == ["pr-merge", "unnamed"]
    assert "secret" not in fx.log.read_text() and fx.calls() == []


def test_record_refusal_never_raises(fx: Fx, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a-file").write_text("x")
    monkeypatch.setenv("LOADOUT_FRICTION_LOG", str(tmp_path / "a-file" / "log.jsonl"))
    runpy.run_path(str(FRICTION), run_name="friction")["record_refusal"]("merge-guard", "pr-merge")


def test_a_flush_posts_every_unposted_line_as_one_comment_on_the_open_issue(fx: Fx) -> None:
    (fx.stub / "issues.json").write_text(json.dumps([{"number": 2, "pull_request": {}}, {"number": 5},
                                                     {"number": 3}]))
    for rule in ("pr-merge", "no-verify", "merge-records"):
        fx.run("refusal", "--guard", "merge-guard", "--rule", rule)
    assert fx.calls() == []
    assert fx.run("flush").returncode == 0
    [comment] = fx.comments()
    assert comment["endpoint"] == f"repos/{REPO}/issues/3/comments"
    body = comment["body"].split("\n")
    assert body[0] == "🤖 Friction: 3 new entries from one session's log"
    assert [b for b in body if b.startswith("- ")] == [b for b in body[3:-2]]
    assert len([b for b in body if b.startswith("- ")]) == 3
    calls = len(fx.calls())
    assert fx.run("flush").returncode == 0 and len(fx.calls()) == calls  # nothing unposted: no call at all
    fx.run("note", "one more")
    assert len(fx.comments()) == 2 and "1 new entry" in fx.comments()[1]["body"]


def test_note_text_cannot_leave_the_code_block(fx: Fx) -> None:
    fx.run("note", "@someone\n~~~\n# heading", "--workaround", "\n~~~\n@other")
    body = fx.comments()[0]["body"].split("\n")
    inside = body[body.index("~~~text") + 1:body.index("~~~")]
    assert len(inside) == 1 and inside[0].startswith("- ") and body.index("~~~") == len(body) - 2


@pytest.mark.parametrize("case", ["comment fails", "issue list fails", "read back differs", "no gh", "no origin"])
def test_a_failed_flush_loses_nothing_and_exits_0(fx: Fx, case: str) -> None:
    fx.run("refusal", "--guard", "gcp-guard", "--rule", "spend")
    extra = {"comment fails": {"STUB_FAIL": "comments"}, "issue list fails": {"STUB_FAIL": "issues?"},
             "read back differs": {"STUB_MANGLE": "1"}}.get(case, {})
    if case == "no origin":
        subprocess.run(["git", "remote", "remove", "origin"], cwd=fx.clone, check=True)
    done = fx.run("note", "x", gh=case != "no gh", **extra)
    assert done.returncode == 0 and "not posted, kept for the next flush" in done.stderr, done.stderr
    assert fx.posted() == 0 and len(fx.lines()) == 2
    if case == "no origin":
        subprocess.run(["git", "remote", "add", "origin", f"https://github.com/{REPO}.git"], cwd=fx.clone,
                       check=True)
    assert fx.run("flush").returncode == 0
    assert "2 new entries" in fx.comments()[-1]["body"] and fx.posted() == fx.log.stat().st_size


def test_an_unfinished_last_line_waits(fx: Fx) -> None:
    fx.run("refusal", "--guard", "merge-guard", "--rule", "pr-merge")
    complete = fx.log.stat().st_size
    with fx.log.open("a") as f:
        f.write('{"at": "x", "kind": "re')
    fx.run("flush")
    assert "1 new entry" in fx.comments()[0]["body"] and fx.posted() == complete


def test_a_long_log_is_posted_over_several_flushes(fx: Fx, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOADOUT_FRICTION_LOG", str(fx.log))
    note = runpy.run_path(str(FRICTION), run_name="friction")["record_note"]
    for i in range(150):
        note(f"{i} " + "y" * 600, "a-skill", None)
    fx.run("flush")
    first = fx.comments()[0]["body"]
    assert len(first) <= 61_000 and 0 < fx.posted() < fx.log.stat().st_size
    fx.run("flush")
    posted = sum(int(c["body"].split(" ")[2]) for c in fx.comments())
    assert posted == 150 and fx.posted() == fx.log.stat().st_size


WRITER = """
import runpy, sys
record = runpy.run_path(sys.argv[1], run_name="friction")
for i in range(200):
    record["record_note"](f"writer {sys.argv[2]} note {i} " + "z" * 480, "part", "w" * 400)
    record["record_refusal"]("merge-guard", "pr-merge")
"""


def test_writers_running_at_once_never_mix_their_lines(fx: Fx) -> None:
    env = {**fx.env(), "LOADOUT_FRICTION_LOG": str(fx.log)}
    procs = [subprocess.Popen([sys.executable, "-c", WRITER, str(FRICTION), str(n)], env=env) for n in range(8)]
    assert all(p.wait(timeout=120) == 0 for p in procs)
    lines = fx.lines()  # every line parses
    assert len(lines) == 8 * 400
    assert sum(e["kind"] == "note" for e in lines) == 1600


def test_the_file_is_executable_and_self_contained() -> None:
    assert os.access(FRICTION, os.X_OK)
    imports = [x for x in FRICTION.read_text().splitlines() if x.startswith(("import ", "from "))]
    allowed = {"argparse", "fcntl", "json", "os", "re", "subprocess", "sys", "time", "__future__", "pathlib"}
    assert {x.split()[1].split(".")[0] for x in imports} <= allowed


def test_a_replaced_log_is_posted_from_its_start(fx: Fx) -> None:
    fx.run("refusal", "--guard", "merge-guard", "--rule", "pr-merge")
    Path(f"{fx.log}.posted").write_text("999999")
    fx.run("flush")
    assert "1 new entry" in fx.comments()[0]["body"] and fx.posted() == fx.log.stat().st_size


def test_one_flush_runs_at_a_time(fx: Fx) -> None:
    fx.run("refusal", "--guard", "merge-guard", "--rule", "pr-merge")
    with open(f"{fx.log}.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        done = fx.run("flush")
    assert "another flush is running" in done.stderr and fx.calls() == [] and fx.posted() == 0
