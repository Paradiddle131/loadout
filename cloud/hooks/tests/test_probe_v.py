from test_merge_guard import change, comment, record, mcp, fx  # noqa: F401
import pytest
def test_case_probe(fx, tmp_path):
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"})
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head)))
    print("SAME CASE:", mcp(fx, r, expectedHeadSha=head))
    print("OTHER CASE:", mcp(fx, r, owner="Example-Owner", expectedHeadSha=head))

@pytest.mark.parametrize("line", [
    "- Owner override: depth light, carried from the reposted round's record, which quotes the owner\n",
    "- Owner override: depth light, carried from the reposted round's record (nowhere), which quotes the owner\n",
])
def test_carried(fx, tmp_path, line):
    r, head, _ = change(tmp_path, fx, {"hooks/x.sh": "x\n"})
    body = record("review", sha=head, tier="sensitive", depth="light").replace(" depth=light -->", " depth=light override=light -->", 1)
    fx.comments(comment(record("gates", sha=head)), comment(body + line))
    print("CARRIED:", mcp(fx, r, expectedHeadSha=head))
    fx.comments(comment(record("gates", sha=head)), comment(body))
    print("NOLINE:", mcp(fx, r, expectedHeadSha=head))
