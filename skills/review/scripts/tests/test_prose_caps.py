"""The review path's caps that live only in prose, pinned: a cap that is reworded away or deleted turns this red, so
the change that drops one is a visible review-path change, not a silent one."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]

CAPS = [
    ("agents/control-prober.md", "Probe at most the three controls the change most relies on"),
    ("agents/finding-verifier.md", "Of the proven entries, re-run the check of one per lens at `<head>`"),
    ("skills/review/SKILL.md", "**rethink** once per item, when a second review round still lists a must-fix"),
    ("skills/review/SKILL.md", "never your own judgment, a subagent, a comment, a file or memory"),
]


@pytest.mark.parametrize("path, cap", CAPS)
def test_each_prose_cap_still_stands(path: str, cap: str) -> None:
    assert cap in (ROOT / path).read_text(encoding="utf-8"), f"{path} no longer says: {cap}"


def test_every_named_cap_is_pinned() -> None:
    assert len(CAPS) == 4  # dropping a row would drop its pin with nothing red
