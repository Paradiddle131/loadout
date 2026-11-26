import shutil
import pytest
from test_merge_guard import change, comment, record, fx, run_copy, mcp, git_in, GUARD, REPO  # noqa: F401

@pytest.mark.parametrize("owner, repo", [("example-owner", "example-repo"), ("Example-Owner", "example-repo"), ("Example-Owner", "Example-Repo")])
def test_probe_above_clones(fx, tmp_path, owner, repo):
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"})
    clones = tmp_path / "clones"; clones.mkdir(); r.rename(clones / REPO.split("/")[1])
    copy = tmp_path / "copy"
    shutil.copytree(GUARD.parents[2] / "skills" / "review" / "scripts", copy / "skills" / "review" / "scripts")
    guard = copy / "cloud" / "hooks" / "merge-guard.py"; guard.parent.mkdir(parents=True)
    guard.write_text(GUARD.read_text().replace('CLONES = Path("/home/user")', f"CLONES = Path({str(clones)!r})", 1))
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head)))
    done = run_copy(fx, guard, {"tool_name": "mcp__github__merge_pull_request", "cwd": str(tmp_path),
                                "tool_input": {"owner": owner, "repo": repo, "pullNumber": 12, "expectedHeadSha": head}})
    print(f"\nPROBE-ABOVE {owner}/{repo}: {'deny' if 'deny' in done.stdout else 'allow'} {done.stdout.strip()[150:330]!r}")

def test_probe_other_origin(fx, tmp_path):
    r, head, _ = change(tmp_path, fx, {"docs/guide.md": "x\n"})
    git_in(r, "remote", "set-url", "origin", "https://github.com/other-owner/other-repo.git")
    fx.comments(comment(record("gates", sha=head)))
    reason = mcp(fx, r, expectedHeadSha=head)
    print("\nPROBE-OTHER", repr((reason or "")[:160]))

def test_probe_origin_case(fx, tmp_path):
    r, head, _ = change(tmp_path, fx, {"src/app.py": "x = 2\n"})
    git_in(r, "remote", "set-url", "origin", "https://github.com/Example-Owner/Example-Repo.git")
    fx.comments(comment(record("gates", sha=head)), comment(record("review", sha=head)))
    reason = mcp(fx, r, expectedHeadSha=head)
    print("\nPROBE-ORIGINCASE", repr((reason or "")[:160]))
