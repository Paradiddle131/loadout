"""bin/friction against a stub `gh` and a stub gitleaks, from a throwaway clone whose origin is invented.

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
import time
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent
FRICTION = BIN / "friction"
REPO = "example-owner/example-repo"

# `gh api` against files in $STUB_DIR: issues.json, label.json, comments.json; calls.jsonl logs every call.
# STUB_FAIL=<text>: a call whose endpoint contains it fails as gh does; STUB_MANGLE=1 (or `ws`): a posted comment
# reads back changed (or with trailing whitespace); STUB_LOGIN: the authenticated login; STUB_SLEEP: seconds per call.
STUB_GH = r'''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
d = Path(os.environ["STUB_DIR"])
time.sleep(float(os.environ.get("STUB_SLEEP") or 0))
args = sys.argv[1:]
assert args[0] == "api", args
method, endpoint, payload, jq, i = "GET", "", None, None, 1
while i < len(args):
    if args[i] == "-X":
        method, i = args[i + 1], i + 2
    elif args[i] == "--input":
        payload, i = json.loads(sys.stdin.read()), i + 2
    elif args[i] == "--jq":
        jq, i = args[i + 1], i + 2
    else:
        endpoint, i = args[i], i + 1
with (d / "calls.jsonl").open("a") as log:
    log.write(json.dumps({"method": method, "endpoint": endpoint, "payload": payload}) + "\n")
if os.environ.get("STUB_FAIL") and os.environ["STUB_FAIL"] in endpoint:
    sys.exit("gh: Server Error (HTTP 502)")
def load(name, default):
    p = d / name
    return json.loads(p.read_text()) if p.exists() else default
if method == "GET" and endpoint == "user":
    out = {"login": os.environ.get("STUB_LOGIN", "example-owner")}
    if jq == ".login":
        print(out["login"])
        sys.exit(0)
elif method == "GET" and "/issues?" in endpoint:
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
    mangle = os.environ.get("STUB_MANGLE")
    if mangle:
        out = {**out, "body": out["body"] + ("\n  " if mangle == "ws" else "x")}
else:
    sys.exit(f"stub gh: no route for {method} {endpoint}")
print(json.dumps(out))
'''
# gitleaks `stdin` as the real one answers it: exit 3 on a finding (here, a planted marker), 0 otherwise.
STUB_GITLEAKS = '#!/bin/sh\n[ "$1" = stdin ] || exit 9\nif grep -q PLANTED-SECRET; then exit 3; fi\nexit 0\n'


class Fx:
    def __init__(self, tmp: Path) -> None:
        self.clone = tmp / "collection"
        (self.clone / "bin").mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=self.clone, check=True)
        subprocess.run(["git", "remote", "add", "origin", f"https://github.com/{REPO}.git"], cwd=self.clone,
                       check=True)
        self.script = self.clone / "bin/friction"
        shutil.copy(FRICTION, self.script)
        shutil.copy(BIN / "check-generic.sh", self.clone / "bin/check-generic.sh")
        self.stub = tmp / "stub"
        self.stub.mkdir()
        self.bin = tmp / "path"
        self.bin.mkdir()
        for name, text in (("gh", STUB_GH), ("gitleaks", STUB_GITLEAKS)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        self.home = tmp / "home"
        self.log = self.home / ".claude/loadout-friction.jsonl"

    def env(self, **extra: str) -> dict[str, str]:
        return {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin", "STUB_DIR": str(self.stub),
                "GENERIC_DENY_FILE": str(self.home / "deny"), **extra}

    def run(self, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(self.script), *args], capture_output=True, text=True,
                              timeout=30, env=self.env(**extra), stdin=subprocess.DEVNULL)

    def refuse(self, rule: str, guard: str = "merge-guard") -> None:
        assert self.run("refusal", "--guard", guard, "--rule", rule).returncode == 0

    def lines(self) -> list[dict]:
        return [json.loads(x) for x in self.log.read_text().splitlines() if x]  # a racing repair may leave a blank

    def calls(self) -> list[tuple[str, str]]:
        p = self.stub / "calls.jsonl"
        return [(c["method"], c["endpoint"]) for c in map(json.loads, p.read_text().splitlines())] if p.exists() \
            else []

    def writes(self) -> list[tuple[str, str]]:
        return [c for c in self.calls() if c[0] != "GET"]

    def comments(self) -> list[str]:
        p = self.stub / "comments.json"
        return [c["body"] for c in json.loads(p.read_text())] if p.exists() else []

    def posted(self) -> int:
        p = Path(f"{self.log}.posted")
        return int(json.loads(p.read_text())["offset"]) if p.exists() else 0


@pytest.fixture
def fx(tmp_path: Path) -> Fx:
    return Fx(tmp_path)


def entries(body: str) -> list[str]:
    return [x for x in body.split("\n") if x.startswith("- ")]


def test_a_note_is_scanned_appended_then_posted_on_a_new_friction_issue(fx: Fx) -> None:
    done = fx.run("note", "the guard refused\na grep", "--part", "merge-guard", "--workaround", "used Grep " * 99)
    assert done.returncode == 0 and done.stderr.startswith("friction: posted 1 notes"), done.stderr
    [line] = fx.lines()
    assert line["kind"] == "note" and line["note"] == "the guard refused a grep" and line["part"] == "merge-guard"
    assert len(line["workaround"]) == 500 and len(line["at"]) == 10 and "local" not in line
    assert fx.calls() == [("GET", "user"), ("GET", f"repos/{REPO}/issues?state=open&labels=friction&per_page=100"),
                          ("GET", f"repos/{REPO}/labels/friction"), ("POST", f"repos/{REPO}/labels"),
                          ("POST", f"repos/{REPO}/issues"), ("POST", f"repos/{REPO}/issues/7/comments")]
    [body] = fx.comments()
    assert body.startswith("🤖 Friction: notes 1, refusals 0, from one home directory's log")
    [entry] = entries(body)
    assert entry.startswith(f"- {line['at']} note (merge-guard): the guard refused a grep; workaround: used Grep")
    assert fx.posted() == fx.log.stat().st_size
    issue = json.loads((fx.stub / "issues.json").read_text())[0]
    assert issue["labels"] == ["friction"] and issue["body"].startswith("🤖")


@pytest.mark.parametrize("rule, kept", [
    ("pr-merge", "pr-merge"), ("a" * 40, "a" * 40), ("a" * 41, "unnamed"), ("home/user/private-repo", "unnamed"),
    ("Pr-Merge", "unnamed"), ("gh pr merge 12; cat /srv/secret", "unnamed"), ("x_y", "unnamed"),
])
def test_a_refusal_holds_a_slug_guard_and_rule_only_and_never_posts(fx: Fx, rule: str, kept: str) -> None:
    fx.refuse(rule)
    [line] = fx.lines()
    assert set(line) == {"at", "kind", "guard", "rule"} and line["rule"] == kept
    assert fx.calls() == []


def test_record_refusal_never_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a-file").write_text("x")
    monkeypatch.setenv("LOADOUT_FRICTION_LOG", str(tmp_path / "a-file" / "log.jsonl"))
    runpy.run_path(str(FRICTION), run_name="friction")["record_refusal"]("merge-guard", "pr-merge")


def test_refusals_are_posted_as_counts_per_rule_with_no_times(fx: Fx) -> None:
    (fx.stub / "issues.json").write_text(json.dumps([{"number": 2, "pull_request": {}}, {"number": 5},
                                                     {"number": 3}]))
    for rule in ("pr-merge", "pr-merge", "pr-merge", "no-verify"):
        fx.refuse(rule)
    assert fx.calls() == []
    assert fx.run("flush").returncode == 0
    [body] = fx.comments()
    assert ("POST", f"repos/{REPO}/issues/3/comments") in fx.calls()
    assert body.startswith("🤖 Friction: notes 0, refusals 4, from one home directory's log")
    assert entries(body) == ["- refusals: merge-guard, rule no-verify: 1", "- refusals: merge-guard, rule pr-merge: 3"]
    assert "T" not in "".join(entries(body)) and ":00" not in body
    calls = len(fx.calls())
    assert fx.run("flush").returncode == 0 and len(fx.calls()) == calls  # nothing unposted: no call at all


def test_fields_are_checked_again_when_posted(fx: Fx) -> None:
    fx.log.parent.mkdir(parents=True)
    fx.log.write_text(json.dumps({"at": "x", "kind": "refusal", "guard": "/srv/private", "rule": "a b"}) + "\n"
                      + json.dumps({"at": "2000-01-02T03:04Z", "kind": "note", "note": "n"}) + "\n")
    fx.run("flush")
    [body] = fx.comments()
    assert entries(body) == ["- refusals: unnamed, rule unnamed: 1", "- 2000-01-02 note: n"] and "/srv" not in body


def test_note_text_cannot_leave_the_code_block(fx: Fx) -> None:
    fx.run("note", "@someone\n~~~\n# heading", "--workaround", "\n~~~\n@other")
    body = fx.comments()[0].split("\n")
    inside = body[body.index("~~~text") + 1:body.index("~~~")]
    assert len(inside) == 1 and inside[0].startswith("- ") and body.index("~~~") == len(body) - 2


@pytest.mark.parametrize("args, kind", [
    (["a key PLANTED-SECRET here"], "gitleaks"),
    (["fine", "--workaround", "a key PLANTED-SECRET here"], "gitleaks"),
    (["worked in acme-private today"], "check-generic"),  # a deny-list word
    (["the example-owner account"], "check-generic"),  # the origin's owner
    (["as filed in #12"], "check-generic"),  # an issue number
])
def test_a_note_that_names_a_secret_or_the_owners_world_is_refused_and_stored_nowhere(
        fx: Fx, args: list[str], kind: str) -> None:
    fx.home.mkdir()
    (fx.home / "deny").write_text("acme-private\n")
    done = fx.run("note", *args)
    assert done.returncode == 1 and "refused the note" in done.stderr and kind in done.stderr, done.stderr
    for word in ("PLANTED", "acme", "example-owner", "#12"):
        assert word not in done.stderr
    assert not fx.log.exists() and fx.calls() == []


@pytest.mark.parametrize("missing", ["gitleaks", "check-generic"])
def test_a_note_no_scanner_read_stays_local(fx: Fx, missing: str) -> None:
    if missing == "gitleaks":
        (fx.bin / "gitleaks").unlink()
    else:
        (fx.clone / "bin/check-generic.sh").unlink()
    done = fx.run("note", "a note")
    assert done.returncode == 0 and "no scanner ran" in done.stderr, done.stderr
    assert fx.lines()[0]["local"] is True and fx.calls() == [] and fx.comments() == []
    fx.refuse("pr-merge")
    fx.run("flush")
    [body] = fx.comments()
    assert entries(body) == ["- refusals: merge-guard, rule pr-merge: 1"]


def test_a_note_from_a_file_may_name_any_word(fx: Fx, tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text("refused while grepping for gh pr merge and --no-verify\n")
    done = fx.run("note", "--file", str(note), "--part", "merge-guard")
    assert done.returncode == 0, done.stderr
    assert "gh pr merge and --no-verify" in fx.comments()[0]
    assert fx.run("note").returncode == 2 and fx.run("note", "x", "--file", str(note)).returncode == 2


def test_a_note_that_is_not_utf8_is_kept_mended(fx: Fx) -> None:
    done = subprocess.run([sys.executable, str(fx.script), "note", b"caf\xe9 broke"], capture_output=True,
                          text=True, timeout=30, env=fx.env(), stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stderr
    assert fx.lines()[0]["note"].endswith(" broke") and "caf" in fx.comments()[0]


@pytest.mark.parametrize("case", ["comment fails", "issue list fails", "read back differs", "no gh", "no origin",
                                  "another account", "login unreadable"])
def test_a_failed_flush_loses_nothing_and_exits_0(fx: Fx, case: str) -> None:
    fx.refuse("spend", "gcp-guard")
    extra = {"comment fails": {"STUB_FAIL": "comments"}, "issue list fails": {"STUB_FAIL": "issues?"},
             "read back differs": {"STUB_MANGLE": "1"}, "another account": {"STUB_LOGIN": "someone-else"},
             "login unreadable": {"STUB_FAIL": "user"}}.get(case, {})
    if case == "no origin":
        subprocess.run(["git", "remote", "remove", "origin"], cwd=fx.clone, check=True)
    if case == "no gh":
        (fx.bin / "gh").rename(fx.bin / "gh.off")
    done = fx.run("note", "x", **extra)
    assert done.returncode == 0 and "not posted, kept for the next flush" in done.stderr, done.stderr
    assert fx.posted() == 0 and len(fx.lines()) == 2
    if case in ("another account", "login unreadable"):
        assert fx.writes() == []  # nothing written anywhere
    if case == "no gh":
        (fx.bin / "gh.off").rename(fx.bin / "gh")
    if case == "no origin":
        subprocess.run(["git", "remote", "add", "origin", f"https://github.com/{REPO}.git"], cwd=fx.clone,
                       check=True)
    assert fx.run("flush").returncode == 0
    assert "notes 1, refusals 1" in fx.comments()[-1] and fx.posted() == fx.log.stat().st_size


def test_a_read_back_with_trailing_whitespace_counts_as_posted(fx: Fx) -> None:
    fx.refuse("pr-merge")
    fx.run("flush", STUB_MANGLE="ws")
    assert len(fx.comments()) == 1 and fx.posted() == fx.log.stat().st_size


def test_posting_off_records_and_posts_nothing(fx: Fx) -> None:
    fx.refuse("pr-merge")
    done = fx.run("note", "x", LOADOUT_FRICTION_POST="0")
    assert "posting is off" in done.stderr and len(fx.lines()) == 2
    assert fx.calls() == [] and fx.posted() == 0


def test_a_torn_last_line_waits_and_the_next_append_starts_fresh(fx: Fx) -> None:
    fx.refuse("pr-merge")
    complete = fx.log.stat().st_size
    with fx.log.open("a") as f:
        f.write('{"at": "x", "kind": "re')
    fx.run("flush")
    assert entries(fx.comments()[0]) == ["- refusals: merge-guard, rule pr-merge: 1"] and fx.posted() == complete
    fx.refuse("no-verify")
    fx.run("flush")
    assert entries(fx.comments()[1]) == ["- refusals: merge-guard, rule no-verify: 1", "- unreadable lines: 1"]


def test_a_replaced_or_regrown_log_is_posted_from_its_start(fx: Fx) -> None:
    fx.refuse("pr-merge")
    fx.run("flush")
    Path(f"{fx.log}.posted").write_text(json.dumps({"offset": 999999, "ino": 0, "first": ""}))
    fx.run("flush")
    assert entries(fx.comments()[1]) == ["- refusals: merge-guard, rule pr-merge: 1"]
    fx.log.write_text("")  # truncated in place, then regrown past the old offset
    for rule in ("no-verify", "hooks-path", "merge-records"):
        fx.refuse(rule, guard="another-guard")
    fx.run("flush")
    assert entries(fx.comments()[2]) == [f"- refusals: another-guard, rule {r}: 1"
                                         for r in ("hooks-path", "merge-records", "no-verify")]


def test_a_long_log_is_posted_over_several_flushes(fx: Fx, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOADOUT_FRICTION_LOG", str(fx.log))
    append = runpy.run_path(str(FRICTION), run_name="friction")["append"]
    for i in range(150):
        append({"at": "x", "kind": "note", "note": f"{i} " + "y" * 600, "part": "a-skill"})
    fx.run("flush")
    assert len(fx.comments()[0]) <= 61_000 and 0 < fx.posted() < fx.log.stat().st_size
    fx.run("flush")
    assert sum(len(entries(b)) for b in fx.comments()) == 150 and fx.posted() == fx.log.stat().st_size


def test_a_hanging_gh_is_cut_by_the_call_timeout(fx: Fx) -> None:
    fx.refuse("pr-merge")
    start = time.monotonic()
    done = fx.run("flush", STUB_SLEEP="60", LOADOUT_FRICTION_BUDGET_S="3")
    assert time.monotonic() - start < 8 and "did not run" in done.stderr, done.stderr
    assert fx.posted() == 0


def test_the_flush_stops_when_its_budget_is_spent(fx: Fx) -> None:
    fx.refuse("pr-merge")
    start = time.monotonic()
    done = fx.run("flush", STUB_SLEEP="1.2", LOADOUT_FRICTION_BUDGET_S="3")
    assert time.monotonic() - start < 6 and "ran out" in done.stderr, done.stderr
    assert fx.writes() == [] and fx.posted() == 0


WRITER = """
import runpy, sys
record = runpy.run_path(sys.argv[1], run_name="friction")
for i in range(200):
    record["append"]({"at": "x", "kind": "note", "note": f"writer {sys.argv[2]} note {i} " + "z" * 480})
    record["record_refusal"]("merge-guard", "pr-merge")
"""


def test_writers_running_at_once_never_mix_their_lines(fx: Fx) -> None:
    env = {**fx.env(), "LOADOUT_FRICTION_LOG": str(fx.log)}
    procs = [subprocess.Popen([sys.executable, "-c", WRITER, str(FRICTION), str(n)], env=env) for n in range(8)]
    assert all(p.wait(timeout=120) == 0 for p in procs)
    lines = fx.lines()  # every line parses
    assert len(lines) == 8 * 400 and sum(e["kind"] == "note" for e in lines) == 1600


def test_one_flush_runs_at_a_time(fx: Fx) -> None:
    fx.refuse("pr-merge")
    with open(f"{fx.log}.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        done = fx.run("flush")
    assert "another flush is running" in done.stderr and fx.calls() == [] and fx.posted() == 0


def test_the_file_is_executable_and_self_contained() -> None:
    assert os.access(FRICTION, os.X_OK)
    imports = [x for x in FRICTION.read_text().splitlines() if x.startswith(("import ", "from "))]
    allowed = {"argparse", "fcntl", "json", "os", "re", "shutil", "subprocess", "sys", "tempfile", "time",
               "__future__", "pathlib"}
    assert {x.split()[1].split(".")[0] for x in imports} <= allowed
