from test_audit import *  # noqa: F401,F403  (fixtures and helpers)
from test_audit import github  # noqa: F401


def test_newer_trusted_gates_record_keeps_the_pass(github, tmp_path):
    github["data"][f"repos/{REPO}/issues/7/comments"].append(
        {"id": 30, "body": f"🤖 Gates: success\n<!-- loadout" f":gates sha={H2} state=success -->\n",
         "author_association": "OWNER", "created_at": "2030-01-02T09:00:00Z", "updated_at": "2030-01-02T09:00:00Z"})
    [c] = audit.summarize(harvest(tmp_path), None)["series"]
    assert not c["merged_without_pass"]


def test_reviewer_prefix_marker_is_not_the_guards_review(github, tmp_path):
    github["data"][f"repos/{REPO}/issues/7/comments"].append(
        {"id": 31, "body": "🤖 note\n<!-- loadout" ":reviewer-notes x -->\n",
         "author_association": "OWNER", "created_at": "2030-01-02T09:00:00Z", "updated_at": "2030-01-02T09:00:00Z"})
    [c] = audit.summarize(harvest(tmp_path), None)["series"]
    assert not c["merged_without_pass"]


def test_malformed_audit_block_rows_do_not_break_sample(github, tmp_path):
    github["data"][f"repos/{REPO}/issues/7/comments"].append(
        {"id": 32, "body": "🤖 Audit: 1 finding re-checked (session s9)\n<!-- loadout" ":audit session=s9 -->\n"
         '```json\n[{"round": "2", "ids": "COR-1"}, {"round": 2}]\n```\n',
         "author_association": "OWNER", "created_at": "2030-01-02T09:00:00Z", "updated_at": "2030-01-02T09:00:00Z"})
    d = harvest(tmp_path)
    assert rows(d, "audits") == []
    audit.sample(audit.argparse.Namespace(dir=str(d), n=5, seed=0))


def test_marker_without_sha_or_state_is_refused():
    for body in ["🤖 Review: pass (standard tier)\n<!-- loadout" ":review state=success tier=standard -->\n",
                 "🤖 Gates: success\n<!-- loadout" f":gates sha={H2} -->\n"]:
        assert audit.trusted_record({"body": body, "author_association": "OWNER", "created_at": "t", "updated_at": "t"}) is None
