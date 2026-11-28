"""The reviewer guard (cloud/gcp/reviewer_guard.py): what it refuses a review agent, and what it lets through.

Each refused form belongs to one rule; deleting that rule from the guard turns its cases red. Each ordinary review
read is pinned as passing.
Run: uvx --from pytest==8.4.2 pytest -q cloud/gcp/tests
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
GUARD = HERE.parent / "reviewer_guard.py"
ROOT = HERE.parents[2]
sys.path.insert(0, str(GUARD.parent))
import reviewer_guard  # noqa: E402

REVIEWER = "some-plugin:correctness-reviewer"


def run(command: str, agent: str | None = REVIEWER, tool: str = "Bash", home: Path | None = None) -> dict | None:
    event: dict = {"tool_name": tool, "tool_input": {"command": command}, "hook_event_name": "PreToolUse"}
    if agent is not None:
        event["agent_type"], event["agent_id"] = agent, "a1"
    env = {"PATH": "/usr/bin:/bin"} | ({"HOME": str(home)} if home else {})
    out = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event), capture_output=True, text=True,
                         env=env, check=True, timeout=30)
    assert out.stderr == "", out.stderr[-300:]
    return json.loads(out.stdout) if out.stdout.strip() else None


# One list per rule: a cloud CLI as the command word.
CLOUD_CLI = [
    "gcloud projects describe p",
    "bq query --dry_run 'SELECT 1'",
    "gsutil ls gs://b",
    "/usr/bin/gcloud auth list",
    "cd wt && bq query 'select 1'",
    "true || gcloud config list",
    "git status; gsutil ls",
    "ls | xargs -n1 gcloud",
    "(cd wt; gcloud config list)",
    "x=$(gcloud config get project)",
    'x="$(gcloud config get project)"',
    "echo `bq ls`",
    "timeout 30 gcloud auth list",
    "timeout -s KILL 30 bq ls",
    "sudo -u root gcloud info",
    "command gcloud info",
    "exec gcloud info",
    "nice -n 5 bq ls",
    "env FOO=1 gcloud info",
    "env -S 'gcloud info'",
    "time -p bq ls",
    "bash -c 'gcloud config list'",
    "sh -ec 'bq ls'",
    "eval gcloud config list",
    "if true; then gsutil ls; fi",
    "bash <<'EOF'\ngcloud config list\nEOF",
    "cat > f <<EOF\n$(gcloud config list)\nEOF",
]

# A Google API host in a word given to a program that is not a text tool.
API_HOST = [
    "curl -s https://cloudresourcemanager.googleapis.com/v3/projects/p",
    "wget -qO- https://storage.googleapis.com/b/o",
    "python3 -c \"import urllib.request as u; u.urlopen('https://bigquery.googleapis.com/x')\"",
    "uv run python -c \"import requests; requests.get('https://iam.googleapis.com/v1/x')\"",
    "node -e \"fetch('https://storage.googleapis.com/b')\"",
    "python3 - <<'PY'\nimport urllib.request\nurllib.request.urlopen('https://storage.googleapis.com/b')\nPY",
]

# A pytest run that widens the repo's selection, and the make targets that run the whole suite.
WIDENING = [
    'uv run pytest -o addopts="" -q tests/x.py',
    "uv run pytest -oaddopts= -q tests/x.py",
    "uv run pytest --override-ini=addopts= tests",
    "uv run pytest --override-ini addopts= tests",
    "pytest -m live tests",
    "pytest -m 'not slow or live'",
    "pytest -qm live",
    "python -m pytest -m live",
    "python3 -m pytest -vo addopts=",
    "uvx --from pytest==8.4.2 pytest -m live tests",
    "pytest -p no:cacheprovider tests",
    "pytest -pno:randomly tests",
    "pytest -c other.ini tests",
    "pytest --config-file=other.ini tests",
    "pytest --noconftest tests",
    "coverage run -m pytest -m live",
    'PYTEST_ADDOPTS="-o addopts=" pytest tests',
    "export PYTEST_ADDOPTS=-mlive",
    "make check",
    "make test",
    "make -C sub -j4 test",
    "cd wt && make check",
]

# Setting, emptying, unsetting or un-exporting a project or proxy variable.
VARIABLES = [
    "GCP_PROJECT= uv run pytest tests",
    "LEDGER_LAB_GCP_PROJECT=other uv run pytest tests",
    "GCP_PROJECT=other",
    "CLOUDSDK_CORE_PROJECT=other true",
    "HTTPS_PROXY= curl https://example.com",
    "https_proxy= curl https://example.com",
    "HTTP_PROXY=x true",
    "NO_PROXY=example.com curl https://example.com",
    "unset LEDGER_LAB_GCP_PROJECT; uv run pytest -q tests",
    "unset -v GCP_PROJECT",
    "env -u GCP_PROJECT uv run pytest tests",
    "env -uGCP_PROJECT true",
    "env --unset=HTTPS_PROXY true",
    "env --unset CLOUDSDK_CORE_PROJECT true",
    "env -i bash",
    "env - true",
    "exec -c bash",
    "sudo env GCP_PROJECT= true",
    "timeout 5 env -u GCP_PROJECT true",
    "export GCP_PROJECT=other",
    "export -n GCP_PROJECT",
    "declare +x CLOUDSDK_CORE_PROJECT",
    "declare -x GCP_PROJECT=",
    "local HTTPS_PROXY=",
    "readonly GCP_PROJECT=x",
    "read GCP_PROJECT < /dev/null",
    "printf -v GCP_PROJECT %s x",
    "bash -lc 'unset GCP_PROJECT && true'",
]

DENIED = CLOUD_CLI + API_HOST + WIDENING + VARIABLES

# The ordinary reads a review needs.
ALLOWED = [
    "git log --oneline -5",
    "git log -S bq --oneline",
    "git log -S googleapis.com -p",
    "git -C /tmp/wt/head show HEAD:cloud/gcp/guard.py",
    "git commit -m 'mention gcloud and storage.googleapis.com'",
    "grep -n gcloud cloud/gcp/guard.py",
    "grep -rn 'GCP_PROJECT=' .",
    "grep -rn storage.googleapis.com cloud",
    "grep -n 'unset GCP_PROJECT' f",
    "rg googleapis",
    "rg -n 'storage.googleapis.com' cloud",
    "rg -- '-o addopts' .",
    "cat cloud/gcp/guard.py",
    "sed -n 1,40p cloud/gcp/guard.py",
    "head -20 f | grep -c bq",
    "echo 'run gcloud projects list'",
    "echo \"$GCP_PROJECT\"",
    "printenv GCP_PROJECT",
    "env | grep -c PROXY",
    "command -v gcloud",
    "uv run pytest tests/x.py",
    "uv run pytest -q tests/x.py",
    "uv run pytest -q -x tests/a.py tests/b.py::test_one",
    "uv run pytest -k 'gcloud and not live' tests/x.py",
    "uv run pytest -p xdist -n 2 tests",
    "uvx --from pytest==8.4.2 pytest -q cloud/gcp/tests",
    "python -m pytest -q tests/x.py 2>&1 | tail -5",
    "python -c 'print(1)'",
    "python3 -c 'import json; print(json.dumps({}))'",
    "make lint",
    "make typecheck",
    "cat > /tmp/notes.md <<'EOF'\ngcloud projects list\ncurl https://storage.googleapis.com/b\nunset GCP_PROJECT\nEOF",
    "gh api repos/o/r/issues -f body='see storage.googleapis.com and gcloud'",
    "jq -r '.url | test(\"googleapis.com\")' f.json",
    "uv run pytest -q tests/x.py # not -m live",
    "mktemp -d",
]


def refusal(out: dict | None) -> str:
    assert out, "not refused"
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse" and spec["permissionDecision"] == "deny"
    return spec["permissionDecisionReason"]


@pytest.mark.parametrize("command", DENIED)
def test_a_reviewer_is_refused_each_named_form(command: str) -> None:
    assert reviewer_guard.check(command), command


@pytest.mark.parametrize("command", ALLOWED)
def test_a_reviewer_keeps_the_ordinary_reads(command: str) -> None:
    assert reviewer_guard.check(command) is None, command


@pytest.mark.parametrize(
    ("command", "what"),
    [
        ('uv run pytest -o addopts="" -q tests/x.py', "pytest's `-o`"),
        ("cd x && bq query 'select 1'", "a `bq` command"),
        ("env -u GCP_PROJECT true", "unsetting `GCP_PROJECT`"),
        ("curl https://storage.googleapis.com/b", "a Google API host in a `curl` command"),
        ("make check", "`make check`"),
    ],
)
def test_the_refusal_says_what_and_that_the_brief_forbids_it(command: str, what: str) -> None:
    reason = refusal(run(command))
    assert f"refused {what}" in reason
    assert "Your brief forbids it" in reason and "unverified" in reason


def test_the_refusal_copies_no_host_name() -> None:
    reason = refusal(run("curl https://cloudresourcemanager.googleapis.com/v3/projects/p"))
    assert "cloudresourcemanager" not in reason and "projects/p" not in reason


@pytest.mark.parametrize("agent", ["correctness-reviewer", "some-plugin:claims-auditor", "some-plugin:finding-verifier"])
def test_a_review_agent_is_known_bare_or_plugin_scoped(agent: str) -> None:
    assert run("gcloud info", agent=agent)


@pytest.mark.parametrize("agent", [None, "", "Explore", "general-purpose", "Plan", "some-plugin:not-a-reviewer",
                                   "correctness-reviewer-2"])
@pytest.mark.parametrize("command", ['uv run pytest -o addopts="" -q tests/x.py', "gcloud info",
                                     "unset GCP_PROJECT", "make check"])
def test_the_lead_and_other_agents_pass_through(agent: str | None, command: str) -> None:
    assert run(command, agent=agent) is None


def test_other_tools_pass_through() -> None:
    assert run("gcloud info", tool="Read") is None


def test_the_reviewer_set_is_the_agents_folder() -> None:
    names = {re.search(r"^name:\s*(\S+)", p.read_text(), re.M).group(1) for p in (ROOT / "agents").glob("*.md")}
    assert reviewer_guard.REVIEW_AGENTS == names


def test_the_hook_is_registered_for_bash() -> None:
    hooks = json.loads((ROOT / "cloud/hooks/hooks.json").read_text())["hooks"]["PreToolUse"]
    commands = [h["command"] for entry in hooks if entry["matcher"] == "Bash" for h in entry["hooks"]]
    assert any("gcp/reviewer_guard.py" in c for c in commands)


def test_it_writes_nothing(tmp_path: Path) -> None:
    assert run("gcloud info", home=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_unparseable_text_that_names_a_cloud_tool_is_refused() -> None:
    assert reviewer_guard.check("gcloud info 'unbalanced")
    assert reviewer_guard.check("echo 'unbalanced") is None


def test_malformed_input_passes() -> None:
    done = subprocess.run([sys.executable, str(GUARD)], input="not json", capture_output=True, text=True, check=True)
    assert done.stdout == ""
