"""The GCP $0 guard (cloud/gcp/guard.py): what it refuses and what it lets through.

Run: uvx --from pytest==8.4.2 pytest -q cloud/gcp/tests
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parent.parent / "guard.py"


def run(command: str, home: Path, tool: str = "Bash", **env: str) -> dict | None:
    event = {"tool_name": tool, "tool_input": {"command": command}}
    out = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin", **env},
        check=True,
    )
    return json.loads(out.stdout) if out.stdout.strip() else None


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / ".bigqueryrc").write_text(
        "--project_id=p\n[query]\n--maximum_bytes_billed=1073741824\n"
    )
    return tmp_path


DENIED = [
    "gcloud services enable compute.googleapis.com --project p",
    "gcloud --project=p services enable run.googleapis.com",
    "gcloud beta services enable workflows.googleapis.com",
    "cd /tmp && gcloud services enable compute.googleapis.com | tail -1",
    "timeout 30 gcloud services enable x.googleapis.com",
    "CLOUDSDK_CORE_PROJECT=p gcloud services enable x.googleapis.com",
    "bash -c 'gcloud services enable compute.googleapis.com'",
    "gcloud projects add-iam-policy-binding p --member=user:a --role=roles/owner",
    "gcloud projects remove-iam-policy-binding p --member=user:a --role=roles/owner",
    "gcloud run services set-iam-policy svc policy.json",
    "gcloud billing projects unlink p",
    "gcloud billing budgets create --billing-account=x --budget-amount=1USD",
    "gcloud alpha quotas preferences update QueryUsagePerDay --preferred-value=99999999",
    "gcloud iam service-accounts keys create key.json --iam-account=a@p.iam.gserviceaccount.com",
    "gcloud compute instances create vm-1 --zone us-central1-a",
    "gcloud container clusters create-auto c --region us-central1",
    "gcloud sql instances create db --tier db-f1-micro",
    "gcloud composer environments create env --location us-central1",
    "gcloud storage buckets create gs://b --location=EU",
    "gcloud storage buckets create gs://b",
    "gsutil mb -l europe-west1 gs://b",
    "bq mk --reservation --slots=100 r1",
    "bq mk --capacity_commitment --plan=MONTHLY --slots=100",
    "bq insert ds.t rows.json",
    "bq query --maximum_bytes_billed=999999999999999 'select 1'",
    "curl -X POST https://serviceusage.googleapis.com/v1/projects/p/services/compute.googleapis.com:enable",
    "curl -s -d '{}' https://cloudresourcemanager.googleapis.com/v1/projects/p:setIamPolicy",
    "curl -X PATCH 'https://cloudquotas.googleapis.com/v1/projects/p/locations/global/quotaPreferences/q'",
    "curl -X PUT https://cloudbilling.googleapis.com/v1/projects/p/billingInfo -d '{}'",
    "curl -d @rows.json https://bigquery.googleapis.com/bigquery/v2/projects/p/datasets/d/tables/t/insertAll",
]

ALLOWED = [
    "gcloud services list --enabled --project p",
    "gcloud services disable bigqueryreservation.googleapis.com --project p",
    "gcloud projects get-iam-policy p --format=json",
    "gcloud compute instances list --project p",
    "gcloud storage buckets create gs://b --location=us-central1",
    "gsutil mb -l US-CENTRAL1 gs://b",
    "bq ls --project_id p",
    "bq query 'select 1'",
    "bq query --dry_run 'select * from big'",
    "bq query --maximum_bytes_billed=104857600 'select 1'",
    "bq mk --dataset p:silver",
    "curl -s https://serviceusage.googleapis.com/v1/projects/p/services?filter=state:ENABLED",
    "curl -s -X POST https://cloudresourcemanager.googleapis.com/v1/projects/p:testIamPermissions -d '{}'",
    "echo 'gcloud services enable compute.googleapis.com'",
    "gh api repos/o/r/issues -f body='run gcloud services enable x in Cloud Shell'",
    "git commit -m 'docs: gcloud services enable is the owner step'",
    "ls -la",
]


@pytest.mark.parametrize("command", DENIED)
def test_denies(command: str, home: Path) -> None:
    out = run(command, home)
    assert out, f"not refused: {command}"
    decision = out["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "testIamPermissions" in decision["permissionDecisionReason"]


@pytest.mark.parametrize("command", ALLOWED)
def test_allows(command: str, home: Path) -> None:
    assert run(command, home) is None, f"refused: {command}"


def test_query_without_any_cap_is_refused(tmp_path: Path) -> None:
    assert run("bq query 'select 1'", tmp_path)


def test_cap_follows_the_environment(home: Path) -> None:
    assert run(
        "bq query --maximum_bytes_billed=2000 'select 1'",
        home,
        GCP_MAX_BYTES_BILLED="1000",
    )
    assert (
        run(
            "bq query --maximum_bytes_billed=500 'select 1'",
            home,
            GCP_MAX_BYTES_BILLED="1000",
        )
        is None
    )


def test_other_tools_pass(home: Path) -> None:
    assert run("gcloud services enable x", home, tool="Write") is None


def test_heredoc_text_passes(home: Path) -> None:
    # A file written with a heredoc may quote GCP commands and hold apostrophes.
    doc = "cat > pr.md <<'MD'\nThe owner's step: gcloud services enable x\nMD\necho ok"
    assert run(doc, home) is None
    assert run("python3 - <<'PY'\nprint(\"bq insert t\")\nPY", home) is None


def test_heredoc_fed_to_a_shell_is_checked(home: Path) -> None:
    assert run("bash <<'EOF'\ngcloud services enable compute.googleapis.com\nEOF", home)
    assert run("sudo bash <<-EOF\n\tgcloud billing projects unlink p\n\tEOF", home)


def test_commands_after_a_heredoc_are_checked(home: Path) -> None:
    assert run("cat > f <<'EOF'\nit's text\nEOF\ngcloud services enable x", home)


def test_unparseable_gcp_command_is_refused(home: Path) -> None:
    assert run("gcloud services list --filter='oops", home)


BEHIND_KEYWORDS = [
    "if true; then gcloud services enable compute.googleapis.com; fi",
    "if false; then :; elif true; then gcloud services enable x.googleapis.com; fi",
    "if false; then :; else gcloud services enable x.googleapis.com; fi",
    "for i in 1; do gcloud services enable x.googleapis.com; done",
    "while true; do bq insert ds.t rows.json; break; done",
    "until false; do gsutil mb -l europe-west1 gs://b; done",
    "! gcloud services enable x.googleapis.com",
    "true && { gcloud services enable x.googleapis.com; }",
    "( gcloud services enable x.googleapis.com )",
]


@pytest.mark.parametrize("command", BEHIND_KEYWORDS)
def test_a_command_behind_a_shell_keyword_is_checked(command: str, home: Path) -> None:
    decision = run(command, home)
    assert decision and decision["hookSpecificOutput"]["permissionDecision"] == "deny", command


def test_keyword_words_as_arguments_still_pass(home: Path) -> None:
    assert run("echo if then do gcloud services enable", home) is None
    assert run("if true; then gcloud services list; fi", home) is None


def test_a_refusal_is_noted_in_the_friction_log_without_the_command(home: Path) -> None:
    log = home / ".claude/loadout-friction.jsonl"
    assert run("gcloud services enable private-api.googleapis.com --project p", home)
    assert run("gcloud services list --enabled --project p", home) is None
    lines = [json.loads(x) for x in log.read_text().splitlines()]
    assert lines == [{"at": lines[0]["at"], "kind": "refusal", "guard": "gcp-guard", "rule": "spend"}]
    assert "private" not in log.read_text()


def test_an_unwritable_friction_log_leaves_the_refusal_alone(home: Path) -> None:
    (home / "a-file").write_text("x")
    decision = run("gcloud services enable x.googleapis.com", home,
                   LOADOUT_FRICTION_LOG=str(home / "a-file" / "log.jsonl"))
    assert decision and decision["hookSpecificOutput"]["permissionDecision"] == "deny"
