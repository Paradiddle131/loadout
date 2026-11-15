"""The settings step of `cloud/setup.sh`, run on its own against a scratch home."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

SETUP = Path(__file__).resolve().parents[2] / "setup.sh"
BLANK = {"commit": "", "pr": "", "sessionUrl": False}


def settings_step() -> str:
    """The Python heredoc that rewrites `~/.claude/settings.json`."""
    found = re.search(r"^python3 - <<'EOF'\n(.*?)^EOF$", SETUP.read_text(), re.S | re.M)
    assert found and "settings.json" in found.group(1)
    return found.group(1)


def run(home: Path, settings: dict | None) -> dict:
    path = home / ".claude/settings.json"
    if settings is not None:
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(settings))
    env = {**os.environ, "HOME": str(home)}
    subprocess.run([sys.executable, "-c", settings_step()], env=env, check=True)
    return json.loads(path.read_text())


def test_drops_the_blank_attribution_block_an_older_setup_wrote(tmp_path: Path) -> None:
    assert run(tmp_path, {"attribution": BLANK, "model": "x"}) == {"model": "x"}


def test_keeps_an_attribution_value_set_another_way(tmp_path: Path) -> None:
    mine = {"commit": "Made by hand"}
    assert run(tmp_path, {"attribution": mine}) == {"attribution": mine}


def test_writes_no_attribution_on_a_fresh_home(tmp_path: Path) -> None:
    assert "attribution" not in run(tmp_path, None)
