from test_merge_guard import *  # noqa: F403
from test_merge_guard import local, fx  # noqa: F401


@pytest.mark.parametrize("sleep,budget", [("0", "30"), ("0.9", "3")])
def test_floor_under_budget(fx, local, sleep, budget):
    r, head = local
    # A slow `git show` stands in for tier.sh reading many instruction files in a large repo.
    b = fx.d.parent / "bin"
    b.mkdir(exist_ok=True)
    (b / "git").write_text('#!/bin/sh\n[ "$1" = show ] && sleep 1.5\nexec /usr/bin/git "$@"\n')
    (b / "git").chmod(0o755)
    (r / "CLAUDE.md").write_text("x\n")
    env = {**os.environ, **ID}
    subprocess.run(["/usr/bin/git", "add", "."], cwd=r, check=True, env=env)
    subprocess.run(["/usr/bin/git", "commit", "-qm", "c"], cwd=r, check=True, env=env)
    subprocess.run(["/usr/bin/git", "update-ref", "refs/remotes/origin/main", "HEAD~1"], cwd=r, check=True, env=env)
    head = subprocess.run(["/usr/bin/git", "rev-parse", "HEAD"], cwd=r, capture_output=True, text=True).stdout.strip()
    (fx.d / "pr.json").write_text(json.dumps({"number": 12, "head": {"sha": head}}))
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head, tier="routine")))
    reason = run(fx, {"tool_name": "mcp__github__merge_pull_request",
                      "tool_input": {"owner": "example-owner", "repo": "example-repo", "pullNumber": 12,
                                     "expectedHeadSha": head}}, r, STUB_SLEEP=sleep, MERGE_GUARD_BUDGET_S=budget)
    print(f"\nsleep={sleep} budget={budget} -> {reason!r}")
