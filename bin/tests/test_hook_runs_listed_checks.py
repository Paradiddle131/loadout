"""The pre-commit hook runs every check AGENTS.md's `## Checks` lists: deleting one of its lines turns this red."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def listed_checks() -> list[str]:
    """The first word of each bullet's backticked command under `## Checks`, before `Tests:`."""
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    section = text.split("## Checks", 1)[1].split("\nTests:", 1)[0]
    return [m.group(1).split()[0] for m in re.finditer(r"^- `([^`]+)`", section, re.M)]


def test_agents_md_lists_the_checks() -> None:
    assert listed_checks() == ["bin/check-plugins.sh", "bin/check-refs", "bin/check-review-version", "gitleaks",
                               "bin/check-generic.sh", "cloud/githooks/check-process-ids.py"]


def test_the_pre_commit_hook_runs_every_listed_check() -> None:
    hook = [ln.strip() for ln in (ROOT / ".githooks/pre-commit").read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    missing = [c for c in listed_checks() if not any(re.search(rf"(^|[\s/\"]){re.escape(c)}\b", ln) for ln in hook)]
    assert missing == [], f"AGENTS.md lists checks the pre-commit hook does not run: {missing}"
