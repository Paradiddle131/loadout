"""budget_guard.py stops a pass by exit code and fails closed on every state it cannot trust."""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parent.parent / "budget_guard.py"
GO, REFUSED, STOP = 0, 2, 3


def guard(state: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", str(GUARD), "--state", str(state), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def init(state: Path, *limits: str) -> None:
    r = guard(state, *limits, "init")
    assert r.returncode == GO, r.stderr


def counts(state: Path) -> dict:
    return json.loads(state.read_text())["counts"]


@pytest.fixture
def state(tmp_path: Path) -> Path:
    return tmp_path / "pass.json"


def test_run_limit_stops_exactly_at_n(state: Path) -> None:
    init(state, "--max-runs", "3")
    assert [guard(state, "record", "--outcome", "ok").returncode for _ in range(3)] == [GO, GO, STOP]
    r = guard(state, "start")
    assert r.returncode == STOP
    assert "STOP: runs 3/3 reached" in r.stderr
    assert counts(state)["recorded"] == 3


def test_start_reserves_and_refuses_the_run_past_n(state: Path) -> None:
    init(state, "--max-runs", "2")
    assert guard(state, "start").returncode == GO
    assert guard(state, "start").returncode == GO
    assert guard(state, "start").returncode == STOP
    assert counts(state)["started"] == 2


def test_infra_failures_stop_at_the_threshold(state: Path) -> None:
    init(state, "--max-runs", "50")
    assert guard(state, "record", "--outcome", "wrong").returncode == GO
    assert guard(state, "record", "--outcome", "infra").returncode == GO
    r = guard(state, "record", "--outcome", "infra")
    assert r.returncode == STOP
    assert "infrastructure failures 2/2 reached" in r.stderr
    assert guard(state, "start").returncode == STOP


def test_infra_threshold_is_configurable(state: Path) -> None:
    init(state, "--max-runs", "50", "--max-infra-failures", "1")
    assert guard(state, "record", "--outcome", "infra").returncode == STOP


def test_cost_limit_stops_when_reached(state: Path) -> None:
    init(state, "--max-runs", "50", "--max-cost", "1.0")
    assert guard(state, "record", "--outcome", "ok", "--cost", "0.5").returncode == GO
    r = guard(state, "record", "--outcome", "ok", "--cost", "0.5")
    assert r.returncode == STOP
    assert "cost 1/1 reached" in r.stderr


def test_cost_limit_needs_a_cost_on_every_record(state: Path) -> None:
    init(state, "--max-runs", "5", "--max-cost", "1.0")
    r = guard(state, "record", "--outcome", "ok")
    assert r.returncode == REFUSED
    assert counts(state)["recorded"] == 0


def test_limits_cannot_be_raised_mid_pass(state: Path) -> None:
    init(state, "--max-runs", "2")
    r = guard(state, "--max-runs", "200", "record", "--outcome", "ok")
    assert r.returncode == REFUSED
    assert "differs" in r.stderr
    assert guard(state, "--max-runs", "2", "record", "--outcome", "ok").returncode == GO


def test_init_refuses_to_reset_an_existing_state(state: Path) -> None:
    init(state, "--max-runs", "2")
    guard(state, "record", "--outcome", "ok")
    assert guard(state, "--max-runs", "2", "init").returncode == REFUSED
    assert counts(state)["recorded"] == 1


def test_missing_state_fails_closed(state: Path) -> None:
    for cmd in (["start"], ["record", "--outcome", "ok"], ["status"]):
        assert guard(state, *cmd).returncode == REFUSED
    assert not state.exists()


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{not json",
        "[]",
        '{"schema": 1}',
        '{"schema": 1, "limits": {"max_runs": 5, "max_cost": null, "max_infra_failures": 2},'
        ' "counts": {"started": 0, "recorded": 1, "ok": 0, "wrong": 0, "infra": 0}, "cost": 0}',
        '{"schema": 1, "limits": {"max_runs": 5, "max_cost": null, "max_infra_failures": 2},'
        ' "counts": {"started": -4, "recorded": 0, "ok": 0, "wrong": 0, "infra": 0}, "cost": 0}',
        '{"schema": 1, "limits": {"max_runs": 5, "max_cost": null, "max_infra_failures": 2},'
        ' "counts": {"started": 0, "recorded": 0, "ok": 0, "wrong": 0, "infra": 0}, "cost": "0"}',
    ],
    ids=["empty", "truncated", "list", "no-fields", "counts-disagree", "negative", "cost-string"],
)
def test_corrupt_state_fails_closed(state: Path, text: str) -> None:
    state.write_text(text)
    for cmd in (["start"], ["record", "--outcome", "ok"], ["status"]):
        r = guard(state, *cmd)
        assert r.returncode == REFUSED, (cmd, r.stdout, r.stderr)
        assert "refusing to continue" in r.stderr
    assert state.read_text() == text


def test_concurrent_writers_lose_no_counts(state: Path) -> None:
    n = 40
    init(state, "--max-runs", str(n))
    outcomes = ["ok", "wrong"] * (n // 2)
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda o: guard(state, "record", "--outcome", o).returncode, outcomes))
    c = counts(state)
    assert (c["recorded"], c["ok"], c["wrong"]) == (n, n // 2, n // 2)
    assert codes.count(STOP) == 1
    assert codes.count(GO) == n - 1


def test_concurrent_starts_never_exceed_the_limit(state: Path) -> None:
    init(state, "--max-runs", "5")
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda _: guard(state, "start").returncode, range(20)))
    assert codes.count(GO) == 5
    assert codes.count(STOP) == 15
    assert counts(state)["started"] == 5


def test_status_prints_counts_and_stops(state: Path) -> None:
    init(state, "--max-runs", "1")
    guard(state, "record", "--outcome", "ok")
    r = guard(state, "status")
    assert r.returncode == GO
    assert "recorded=1/1 ok=1 wrong=0 infra=0/2" in r.stdout
    assert "STOP: runs 1/1 reached" in r.stdout


def test_shell_loop_stops_at_the_limit(state: Path, tmp_path: Path) -> None:
    init(state, "--max-runs", "4")
    log = tmp_path / "runs.log"
    script = (
        f'g() {{ "{sys.executable}" -I "{GUARD}" --state "{state}" "$@"; }}\n'
        "for i in $(seq 1 100); do\n"
        "  g start || break\n"
        f'  echo "$i" >> "{log}"\n'
        "  g record --outcome ok || break\n"
        "done\n"
    )
    subprocess.run(["bash", "-c", script], check=True, capture_output=True)
    assert log.read_text().split() == ["1", "2", "3", "4"]
