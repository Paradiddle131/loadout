"""The session-start GCP status line (cloud/gcp/status.sh) against a fake `bq` and `curl` on PATH.

Run: uvx --from pytest==8.4.2 pytest -q cloud/gcp/tests
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

STATUS = Path(__file__).resolve().parent.parent / "status.sh"
LISTING = (
    '[{"tableReference": {"tableId": "gcp_billing_export_v1_000000_000000_000000"}}]'
)


def run(tmp_path: Path, query: str) -> str:
    """status.sh's stdout, with `bq ls` finding the export table and `bq query` printing `query`."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "bq").write_text(
        "#!/usr/bin/env bash\n"
        'case "$1" in\n'
        f"  ls) echo '{LISTING}' ;;\n"
        f"  query) printf '{query}' ;;\n"
        "esac\n"
    )
    (bindir / "curl").write_text("#!/usr/bin/env bash\necho '{}'\n")
    for tool in ("bq", "curl"):
        (bindir / tool).chmod(0o755)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = {
        **os.environ,
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(home),
        "GCP_PROJECT": "lab-test",
    }
    out = subprocess.run(
        ["bash", str(STATUS)], env=env, capture_output=True, text=True, check=True
    )
    return out.stdout


def test_an_export_without_rows_this_month_is_unknown(tmp_path: Path) -> None:
    out = run(tmp_path, "f0_\\nnone\\n")
    assert (
        "month to date unknown (no billing export rows for lab-test this month yet"
        in out
    )
    assert "$0.00" not in out.replace("is a $0.00 lab", "")
    assert "STOP" not in out


@pytest.mark.parametrize("query", ["", "f0_\\n", "Error in query string\\n"])
def test_a_failed_query_is_unknown(tmp_path: Path, query: str) -> None:
    out = run(tmp_path, query)
    assert "month to date unknown (the cost query failed)" in out
    assert "STOP" not in out


def test_zero_cost_is_shown(tmp_path: Path) -> None:
    out = run(tmp_path, "f0_\\n0.00\\n")
    assert "month to date $0.00," in out
    assert "STOP" not in out


def test_a_cost_stops_the_session(tmp_path: Path) -> None:
    out = run(tmp_path, "f0_\\n0.42\\n")
    assert "month to date $0.42," in out
    assert "gcp: STOP: the project has billed $0.42 this month" in out
