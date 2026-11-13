"""The merge guard's command reading (cloud/hooks/merge-guard.py), proved on generated and recorded commands.

- the false-refusal corpus: ordinary commands an agent runs pass through the real hook, and a stub `gh` that
  fails the test if anything calls it shows none of them reads GitHub;
- the covered-forms matrix: every covered program and flag spelling, behind every covered wrapper, in every
  covered position, is refused when the PR has no records;
- random compositions of ordinary commands, with and without one covered merge, are refused exactly when
  they hold the merge, each within the parse budget;
- pathological inputs finish within the budget, decided by the records or by the hint rule.
Run: uvx --from pytest==8.4.2 pytest -q cloud/hooks/tests
"""

from __future__ import annotations

import importlib.util
import json
import os
import random
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

GUARD = Path(__file__).resolve().parent.parent / "merge-guard.py"
REPO = "example-owner/example-repo"
HEAD = "b" * 40
ENC = REPO.replace("/", "%2F")


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("merge_guard", GUARD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[ModuleType, Path]:
    """The guard in process, reading a PR with no records from a fake GitHub (no subprocess, no network)."""
    mod = load()

    def gh_json(endpoint: str) -> object:
        if "/comments?" in endpoint:
            return []
        if "/pulls?" in endpoint:
            return [{"number": 12}]
        return {"number": 12, "head": {"sha": HEAD}, "base": {"repo": {"default_branch": "main"}}}

    monkeypatch.setattr(mod, "gh_json", gh_json)
    monkeypatch.setenv("GH_REPO", REPO)
    return mod, tmp_path


def decide(mod: ModuleType, command: str, cwd: Path) -> str:
    return mod.decide({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)})


# The false-refusal corpus: commands an agent really runs, merge-looking phrases in their arguments included.

CORPUS = [
    # git
    "git status", "git status --short", "git diff", "git diff --stat origin/main...HEAD", "git log --oneline -20",
    "git log --grep='pr merge' --oneline", "git show HEAD --stat", "git branch -a", "git fetch origin",
    "git fetch origin main && git rebase origin/main", "git pull --ff-only", "git switch -c feature",
    "git checkout -B work origin/main", "git add -A", "git add cloud/hooks/merge-guard.py",
    "git commit -m 'fix: the guard reads gh pr merge'", "git commit -am 'docs: never use --no-verify'",
    "git commit -m \"refuse git push --no-verify and gh pr merge --auto\"",
    "git commit -m 'mergePullRequest is refused' -m 'pulls/12/merge is checked'", "git commit --amend --no-edit",
    "git commit -uno -m x", "git commit -Skey -m x", "git commit --no-verbose -m x",
    "git commit -F - <<'EOF'\nfix: skip nothing\n\nNever gh pr merge or git push --no-verify here.\nEOF",
    "git commit -m \"$(cat <<'EOF'\nfeat: guard\n\ngh pr merge 12 is checked\nEOF\n)\"",
    "git push origin HEAD", "git push -u origin feature", "git push -n origin main", "git push --force-with-lease",
    "git merge --no-ff feature", "git merge origin/main", "git rebase --continue", "git stash list",
    "git worktree list", "git rev-parse HEAD", "git remote get-url origin", "git ls-remote origin 'refs/heads/*'",
    "git -C /tmp/x log -1", "git -c user.name=t commit -m x", "git config core.hooksPath .githooks",
    "git config --get core.hooksPath", "git tag -l", "git blame -L 1,20 README.md", "git grep -n 'pr merge'",
    "git cherry-pick abc123", "git reset --soft HEAD~1", "git clean -n", "git reflog -5",
    # gh reads and ordinary writes
    "gh pr view 12", "gh pr view 12 --json state,mergeable", "gh pr list --state open", "gh pr checks 12",
    "gh pr diff 12", "gh pr create --title 'merge guard' --body 'checks gh pr merge'", "gh pr merge --help",
    "gh issue list --label bug", "gh issue view 3", "gh api /rate_limit", f"gh api repos/{REPO}",
    f"gh api repos/{REPO}/pulls/12", f"gh api repos/{REPO}/pulls/12/merge", f"gh api -X GET repos/{REPO}/pulls/12/merge",
    f"gh api repos/{REPO}/pulls?state=open --jq '.[].number'", f"gh api repos/{REPO}/issues/12/comments?per_page=100",
    f"gh api -X POST repos/{REPO}/issues/12/comments -F body=@note.md",
    f"gh api -X PATCH repos/{REPO}/pulls/12 -f title='merge guard'",
    f"gh api repos/{REPO}/commits/{HEAD}/status", "gh api graphql -f query='{ viewer { login } }'",
    "gh api graphql -f query='query { repository(owner:\"o\", name:\"r\") { pullRequest(number:1) { mergeable } } }'",
    "gh auth status", "gh release list", "gh run list --limit 5", "gh repo view --json name",
    "gh pr merge 12 --disable-auto",
    # curl and friends
    "curl -sSL https://example.com/install.sh -o install.sh", "curl -fsSL https://example.com/x.tar.gz | tar xz",
    "curl -s https://api.github.com/repos/example-owner/example-repo/pulls/12/merge",
    "curl -sI https://api.github.com/rate_limit", "curl -X POST -d '{}' https://example.com/hook",
    f"curl -H 'Accept: application/vnd.github+json' https://api.github.com/repos/{REPO}/pulls/12",
    "curl -sS \"$HTTPS_PROXY/__agentproxy/status\"", "curl -fsSL https://example.com/get.sh | bash",
    "wget -qO- https://example.com/file.txt", "wget https://example.com/archive.zip",
    "http GET https://api.github.com/repos/example-owner/example-repo/pulls/12/merge",
    "xh https://example.com/api", "xh post httpbin.org/post a=1",
    "curl -d '{\"query\":\"{viewer{login}}\"}' https://api.github.com/graphql",
    # searching and reading files
    "grep -rn 'gh pr merge' .", "grep -rn -- '--no-verify' cloud/", "grep -l mergePullRequest -r skills",
    "rg 'pulls/\\d+/merge' cloud", "rg -n --hidden 'core.hooksPath'", "rg -F 'gh pr merge --auto' docs",
    "find docs -name '*.md' -exec grep -l 'gh pr merge' {} +", "find . -name '*.py' -newer setup.cfg",
    "find . -type f -name '*.sh' | xargs grep -n 'git push --no-verify'",
    "strace -f -e trace=execve grep 'gh pr merge' README.md", "parallel echo ::: 'gh pr merge 5'",
    "sed -n '/gh pr merge/p' README.md", "sed -i 's/gh pr merge/gh pr view/' notes.md",
    "awk '/mergePullRequest/ {print FILENAME}' *.graphql", "awk -F: '{print $1}' /etc/passwd",
    "cat README.md", "head -50 cloud/CLAUDE.md", "tail -f /tmp/dockerd.log", "wc -l cloud/hooks/*.py",
    "ls -la", "ls cloud/hooks/tests", "tree -L 2", "jq '.hooks' cloud/hooks/hooks.json",
    "diff -u a.txt b.txt", "sort -u list.txt | uniq -c", "cut -d, -f1 data.csv", "file merge-guard.py",
    "stat README.md", "du -sh .", "df -h", "realpath .", "which gh", "command -v gh", "type gh",
    # echo, printf and other text with merge phrases
    "echo 'gh pr merge 12'", "echo \"gh pr merge 12 --auto\"", "echo gh pr merge 12", "printf '%s\\n' 'git push --no-verify'",
    "printf 'mergePullRequest\\n' > q.txt", "echo 'pulls/12/merge' >> notes.txt",
    "echo 'run: gh pr merge 12' # a note", "echo done # gh pr merge 12", "echo 'a#b'; ls",
    "cat > notes.md <<'EOF'\ngh pr merge 12\ngit commit --no-verify\nmergePullRequest\nEOF",
    "cat <<EOF > script.sh\n#!/bin/sh\ngh pr merge \"$1\"\nEOF",
    "tee -a log.md <<< 'gh pr merge 12 was refused'",
    "python3 - <<'EOF'\nimport subprocess\nprint('gh pr merge 12')\nEOF",
    "python3 -c 'print(\"gh pr merge 12\")'", "node -e 'console.log(\"git push --no-verify\")'",
    # package managers, builds and test runners
    "uv sync", "uv run pytest -q", "uv run ruff check .", "uvx ruff@0.14.0 check cloud/hooks",
    "uvx --from pytest==8.4.2 pytest -q cloud/hooks/tests -k merge", "pip install -r requirements.txt",
    "python3 -m pytest -q -k 'merge and not auto'", "pytest tests/test_merge.py::test_gh_pr_merge",
    "npm ci", "npm run build", "npm test -- --grep 'gh pr merge'", "npx prettier --check .", "pnpm install",
    "yarn test", "cargo test", "cargo build --release", "go test ./...", "make check", "make -j4 test",
    "make lint && make test", "tox -e py312", "node skills/report-kit/tests/scope.test.cjs",
    "bin/check-refs", "bash bin/check-generic.sh", "claude plugin validate --strict .",
    # docker
    "docker ps -a", "docker compose up -d --wait", "docker compose down", "docker build -t lab .",
    "docker run --rm -v \"$PWD:/w\" -w /w python:3.12 bash -c 'pip install -e . && pytest'",
    "docker exec -it web sh -c 'ls /app'", "docker logs --tail 50 web", "docker images",
    # shells, wrappers and compound commands
    "bash -lc 'uv run pytest -q'", "bash -c 'echo gh pr merge 12'", "bash -c \"grep -rn 'gh pr merge' docs\"",
    "sh -c 'cd /tmp && ls'", "bash -euo pipefail -c 'make test'", "bash scripts/run.sh 'gh pr merge 12'",
    "zsh -c 'echo $SHELL'", "bash <<'EOF'\nset -e\nuv sync\nuv run pytest -q\nEOF",
    "bash -s <<EOF\necho \"git push --no-verify is refused\"\nEOF", "eval \"$(ssh-agent -s)\"",
    "eval 'echo gh pr merge 12'", "env FOO=1 make test", "env -i PATH=/usr/bin ls", "sudo apt-get install -y jq",
    "sudo -u postgres psql -c 'select 1'", "timeout 60 uv run pytest -q", "timeout -s KILL 5 sleep 1",
    "nice -n 10 make", "time make test", "time -p pytest -q", "nohup python3 server.py &",
    "command ls -la", "exec bash", "cd /tmp && ls", "cd cloud/hooks; ls; cd -",
    "for f in *.md; do echo \"$f\"; done", "while read -r l; do echo \"$l\"; done < list.txt",
    "if [ -f x ]; then echo yes; else echo no; fi", "( cd /tmp && ls )", "{ echo a; echo b; } > out.txt",
    "test -d .git && echo repo || echo none", "ls 2>&1 | tee out.log", "make test &> build.log",
    "x=$(git rev-parse HEAD); echo $x", "echo `date -u +%FT%H:%MZ`", "export GH_REPO=example-owner/example-repo",
    "FOO=bar BAZ=qux env | sort", "ssh host 'gh pr merge 12'", "kill %1", "sleep 1 &", "jobs -l",
    "date -u +%FT%H:%MZ", "mkdir -p build/sbom", "rm -rf build", "cp a b", "mv a b", "chmod +x bin/x",
    "tar czf out.tgz dir", "unzip -o file.zip -d out", "openssl sha256 file", "sha256sum file",
    "gitleaks protect --staged", "shellcheck cloud/hooks/*.sh", "python3 cloud/githooks/check-process-ids.py --all",
]


def test_the_corpus_is_large() -> None:
    assert len(CORPUS) >= 150 and len(set(CORPUS)) == len(CORPUS), len(CORPUS)


@pytest.fixture
def no_github(tmp_path: Path) -> dict[str, str]:
    """An environment whose `gh` records any call and fails: no command of the corpus may reach it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(f"#!/bin/sh\necho \"$*\" >> {tmp_path / 'gh-called'}\nexit 1\n")
    gh.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "GH_REPO"}
    return {**env, "PATH": f"{bin_dir}:/usr/bin:/bin", "CALLED": str(tmp_path / "gh-called")}


@pytest.mark.parametrize("command", CORPUS)
def test_ordinary_commands_pass_and_read_nothing(command: str, no_github: dict[str, str], tmp_path: Path) -> None:
    clone = tmp_path / "clone"
    clone.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=clone, check=True)
    subprocess.run(["git", "remote", "add", "origin", f"https://github.com/{REPO}.git"], cwd=clone, check=True)
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command},
             "cwd": str(clone)}
    done = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event), capture_output=True, text=True,
                          timeout=30, env=no_github)
    assert done.returncode == 0 and done.stdout == "", (command, done.stdout, done.stderr)
    assert not Path(no_github["CALLED"]).exists(), (command, Path(no_github["CALLED"]).read_text())


# The covered forms, as tables: programs with every flag spelling, wrappers, and positions in a command line.

PLACEHOLDER = "repos/{owner}/{repo}/pulls/12/merge"
PROGRAMS = {
    "no gates record": [
        "gh pr merge 12", "gh pr merge '#12'", f"gh pr merge https://github.com/{REPO}/pull/12",
        f"gh pr merge 12 -R {REPO}", f"gh pr merge 12 -R{REPO}", f"gh pr merge 12 -R={REPO}",
        f"gh pr merge 12 --repo {REPO}", f"gh pr merge 12 --repo={REPO}", f"gh -R {REPO} pr merge 12",
        "gh pr merge 12 --squash --delete-branch", "gh pr merge feature",
        f"gh api -X PUT repos/{REPO}/pulls/12/merge", f"gh api -XPUT repos/{REPO}/pulls/12/merge",
        f"gh api -X=PUT repos/{REPO}/pulls/12/merge", f"gh api --method PUT repos/{REPO}/pulls/12/merge",
        f"gh api --method=PUT repos/{REPO}/pulls/12/merge", f"gh api -X put /repos/{REPO}/pulls/12/merge/",
        f"gh api -f merge_method=squash repos/{REPO}/pulls/12/merge",
        f"gh api -fmerge_method=squash repos/{REPO}/pulls/12/merge",
        f"gh api --input body.json repos/{REPO}/pulls/12/merge",
        f"gh api -X PUT https://api.github.com/repos/{REPO}/pulls/12/merge",
        f"gh api -X PUT repos%2F{ENC}%2Fpulls%2F12%2Fmerge", f"gh api -X PUT repos/{REPO}/pulls/12/../12/merge",
        f"gh api -X PUT REPOS/{REPO}/PULLS/12/MERGE", f"gh api -X PUT {PLACEHOLDER}",
    ],
    "auto-merge": ["gh pr merge 12 --auto", "gh pr merge --auto 12", f"gh pr merge 12 --auto -R {REPO}"],
    "GraphQL": [
        "gh api graphql -f query='mutation{mergePullRequest(input:{}){clientMutationId}}'",
        "gh api graphql -fquery='mutation{mergePullRequest(input:{}){clientMutationId}}'",
        "gh api graphql -f=query='mutation{mergePullRequest(input:{}){clientMutationId}}'",
        "gh api graphql --raw-field query='mutation{mergePullRequest(input:{}){clientMutationId}}'",
        "gh api graphql --raw-field=query='mutation{mergePullRequest(input:{}){clientMutationId}}'",
        "gh api graphql -F query='mutation{enablePullRequestAutoMerge(input:{}){clientMutationId}}'",
        "gh api graphql -F query=@q.graphql", "gh api graphql -Fquery=@q.graphql",
        "gh api graphql --field=query=@q.graphql", "gh api graphql --input q.json", "gh api graphql --input=q.json",
        "curl -d @q.json https://api.github.com/graphql", "curl --data-binary=@q.json https://api.github.com/graphql",
        "curl -d '{\"query\":\"mutation{mergePullRequest(input:{}){clientMutationId}}\"}' https://api.github.com/graphql",
        "wget --post-file=q.json https://api.github.com/graphql", "http POST https://api.github.com/graphql @q.json",
    ],
    "HTTP client": [
        f"curl -X PUT https://api.github.com/repos/{REPO}/pulls/12/merge",
        f"curl -XPUT https://api.github.com/repos/{REPO}/pulls/12/merge",
        f"curl --request PUT https://api.github.com/repos/{REPO}/pulls/12/merge",
        f"curl --request=PUT https://api.github.com/repos/{REPO}/pulls/12/merge",
        f"curl -sS -d '{{}}' https://api.github.com/repos/{REPO}/pulls/12/merge",
        f"curl -X PUT https://api.github.com/repos%2F{ENC}%2Fpulls%2F12%2Fmerge",
        f"curl -X PUT api.github.com/repos/{REPO}/pulls/12/merge",
        f"wget --method=PUT https://api.github.com/repos/{REPO}/pulls/12/merge",
        f"wget --method PUT https://api.github.com/repos/{REPO}/pulls/12/merge",
        f"http PUT https://api.github.com/repos/{REPO}/pulls/12/merge",
        f"https put api.github.com/repos/{REPO}/pulls/12/merge",
        f"xh put https://api.github.com/repos/{REPO}/pulls/12/merge",
        f"xh https://api.github.com/repos/{REPO}/pulls/12/merge merge_method=squash",
    ],
    "fix what it names": [
        "git commit --no-verify -m x", "git commit -n -m x", "git commit -nm x", "git commit -anm x",
        "git commit --no-veri -m x", "git push --no-verify", "git push --no-verif origin feature",
        "git -c core.hooksPath=/dev/null commit -m x", "git -ccore.hooksPath=/dev/null push",
        "git --config-env=core.hooksPath=E commit -m x", "git --config-env core.hooksPath=E push",
        "git -C /tmp/x commit --no-verify",
    ],
}
WRAPPERS = [
    "", "env ", "env -i ", "env - ", "env -u X ", "env -uX ", "env --unset=X ", "env --unset X ", "env FOO=1 ",
    "command ", "command -p ", "sudo ", "sudo -E ", "sudo -u root ", "sudo -uroot ", "sudo --user=root ",
    "sudo --user root ", "sudo -u root -- ", "timeout 30 ", "timeout 1.5m ", "timeout -s KILL 30 ",
    "timeout -sKILL 30 ", "timeout --signal=KILL 30 ", "timeout --signal KILL 30 ", "timeout --sig KILL 30 ",
    "timeout -k 1 30 ", "timeout --preserve-status 30 ", "nice ", "nice -n 5 ", "nice -n5 ", "nice -5 ",
    "nice --adjustment=5 ", "nice --adjustment 5 ", "time ", "time -p ", "time -f %e ", "time -o t.txt ",
    "time --format=%e ", "exec ", "exec -a name ", "nohup ", "FOO=1 ", "/usr/bin/env ", "sudo -u root timeout 5 env -i ",
]
CONTEXTS = [
    "@C@", "true && @C@", "false || @C@", "echo a; @C@", "echo a | @C@", "@C@ | tail -1", "@C@ 2>&1 | tee log", "@C@ > out.txt",
    "@C@ &", "echo a\n@C@", "( @C@ )", "{ @C@; }", "x=$(@C@)", "echo `@C@`", "if true; then @C@; fi",
    "if @C@; then :; fi", "while true; do @C@; break; done", "until false; do @C@; done", "! @C@", "cd /tmp && @C@",
    "bash -c @Q@", "bash -lc @Q@", "sh -c -- @Q@", "zsh -fc @Q@", "dash -ec @Q@", "bash -o pipefail -c @Q@",
    "bash +x -c @Q@", "bash -c -e @Q@", "bash --norc -c @Q@", "/bin/bash -c @Q@", "eval @Q@", "eval @C@", "env -S @Q@",
    "bash <<< @Q@", "bash <<'EOF'\n@C@\nEOF", "sudo bash -s <<EOF\n@C@\nEOF", "sh <<-EOF\n\t@C@\n\tEOF",
    "bash -c @Q2@",
]


def compose(context: str, command: str) -> str:
    """`context` with @C@ as the command, @Q@ as it quoted and @Q2@ as `bash -c @Q@` quoted."""
    sub = {"C": command, "Q": shlex.quote(command), "Q2": shlex.quote("bash -c " + shlex.quote(command))}
    return re.sub(r"@(C|Q2|Q)@", lambda m: sub[m.group(1)], context)


def test_every_covered_form_is_refused_without_records(guard: tuple[ModuleType, Path]) -> None:
    mod, cwd = guard
    missed, count = [], 0
    for want, programs in PROGRAMS.items():
        for program in programs:
            for wrapper in WRAPPERS:
                for context in CONTEXTS:
                    line = compose(context, wrapper + program)
                    count += 1
                    reason = decide(mod, line, cwd)
                    # `eval C` re-reads `#12` as a comment, as bash does: a merge that names no PR.
                    if want not in reason and not (want == "no gates record" and "names no PR" in reason):
                        missed.append((line, reason))
    assert not missed, f"{len(missed)} of {count} covered forms were not refused as expected: {missed[:20]}"
    assert count > 20000


# Random compositions: refused exactly when they hold a covered merge.

HARMLESS = [c for c in CORPUS if "#" not in c and not c.startswith(("cd ", "export "))]
MERGE_PIECES = [(w + p, want) for want, ps in PROGRAMS.items() for p in ps for w in WRAPPERS[:12]]
SEPARATORS = [" && ", " || ", "; ", " | ", "\n", " & ", " |& "]
NESTINGS = ["@C@", "( @C@ )", "{ @C@; }", "bash -c @Q@", "eval @Q@", "if true; then @C@; fi", "x=$(@C@)"]


def test_random_compositions_are_refused_exactly_when_they_merge(guard: tuple[ModuleType, Path]) -> None:
    mod, cwd = guard
    rng = random.Random(20240601)
    wrong, slowest = [], 0.0
    for _ in range(3000):
        pieces = [rng.choice(HARMLESS) for _ in range(rng.randint(1, 5))]
        merge = rng.random() < 0.5
        want = ""
        if merge:
            piece, want = rng.choice(MERGE_PIECES)
            pieces.insert(rng.randint(0, len(pieces)), piece)
        line = ""
        for k, piece in enumerate(pieces):
            nesting = rng.choice(NESTINGS) if "\n" not in piece else "@C@"
            if k:
                line += "\n" if "\n" in line.rsplit("\n", 1)[-1] or "\n" in pieces[k - 1] else rng.choice(SEPARATORS)
            line += compose(nesting, piece)
        start = time.monotonic()
        reason = decide(mod, line, cwd)
        slowest = max(slowest, time.monotonic() - start)
        if (want not in reason) if merge else reason:
            wrong.append((line, want, reason))
    assert not wrong, f"{len(wrong)} wrong decisions: {wrong[:10]}"
    assert slowest < mod.PARSE_BUDGET, slowest


# Pathological inputs: bounded, and decided by the records or by the hint rule.

PATHOLOGICAL = [
    ("setsid " * 60 + "gh pr merge 5", ""),  # setsid is not a covered wrapper
    ("strace " * 60 + "find -exec " * 60 + "gh pr merge 5", ""),
    ("timeout 1 " * 60 + "gh pr merge 5", "no gates record"),
    ("sudo -u root " * 200 + "gh pr merge 5", "no gates record"),
    ("echo " + "w " * 20000 + "; gh pr merge 5", "no gates record"),
    ("echo " + "w " * 20000, ""),
    ("true; " * 20000 + "echo gh pr merge 5", "could not check"),  # too many commands, with a hint
    ("true; " * 20000, ""),  # too many commands, no hint
    ("echo 'gh pr merge 5", "could not check"),  # unbalanced quotes, with a hint
    ("echo 'it is", ""),
    ("x" * 1_200_000 + " gh pr merge 5", "could not check"),  # too long
    ("cat <<A\n" * 3000 + "gh pr merge 5", "could not check"),  # heredocs that never end, too many commands
    ("cat <<A\n" * 1000 + "gh pr merge 5", "no gates record"),  # heredocs that never end are not heredocs
]


def nested(command: str, levels: int) -> str:
    for _ in range(levels):
        command = "bash -c " + shlex.quote(command)
    return command


@pytest.mark.parametrize("command, want", PATHOLOGICAL + [
    (nested("gh pr merge 5", 4), "no gates record"),
    (nested("gh pr merge 5", 12), "could not check"),
    (nested("echo hi", 12), ""),
    (nested("eval " + shlex.quote("gh pr merge 5"), 3), "no gates record"),
], ids=lambda x: x[:40] if isinstance(x, str) else None)
def test_pathological_input_is_bounded(guard: tuple[ModuleType, Path], command: str, want: str) -> None:
    mod, cwd = guard
    start = time.monotonic()
    reason = decide(mod, command, cwd)
    assert time.monotonic() - start < mod.PARSE_BUDGET + 0.5
    assert (want in reason) if want else reason == "", reason


def test_a_parse_past_its_time_is_decided_by_the_hint(guard: tuple[ModuleType, Path],
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    mod, cwd = guard
    monkeypatch.setattr(mod, "PARSE_BUDGET", 0.0)
    reason = decide(mod, "ls; gh pr merge 5", cwd)
    assert "could not check" in reason and "more than 0 s" in reason and "command of its own" in reason
    assert decide(mod, "ls; echo hi", cwd) == ""
