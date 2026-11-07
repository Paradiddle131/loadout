# Decisions

How a repo records what it decided, and how long a document may live.

## The register

- The plan holds one `## Decisions` table: one row per **live** decision, nothing else.
- Each row has a stable id (`D7`, `SL-3`): a short prefix per plan, numbers never reused.
- A row is amended in place when the decision moves; git is its history.
- A superseded row is deleted in the PR that supersedes it; its id stays retired.
- A row states the decision in bold, then the why: the evidence, and the rejected options in one clause each.
- One row per fork with real alternatives; a step that had none is a plan step or a PR, not a row.
- The plan's first lines say: "Decisions are a register: one row per live decision, amended in place, a superseded row deleted in the PR that supersedes it; git is the history."

Row template:

```markdown
| # | Decision | Why |
|---|---|---|
| D12 | **<the decision, one sentence; pins and names exact>** <scope or limits> | <evidence with a source>; rejected: <option> (<one clause>), <option> (<one clause>). |
```

## The long form

Only when the alternatives were real **and** the choice is costly to undo (a data model, a vendor, a security boundary).
It lives at `docs/decisions/<id>-<slug>.md`; the row links it and stays the summary an agent reads first.
It is amended in place like its row, and deleted with it.

```markdown
# <id>: <decision>

Context: <the forces, with sources>
Options: A <…> / B <…> / C <…>, each with its cost
Choice: <letter>, because <…>
Undo cost: <what reversing it would take>
Revisit when: <the observable trigger>
```

## Proposing a decision

- An agent writes the row in its final form in the PR that needs it; the merge accepts it.
- The PR body lists each new or changed row under `Decisions`, so the owner reviews them in one place.
- A row the owner must weigh before the work can start (a guardrail conflict, a costly fork) goes as a decision packet on the issue instead ([`guardrails.md`](guardrails.md)); the row follows the answer.
- No status column and no `Proposed` state: a row on `main` is live, a row in an open PR is the proposal.

## Pruning

- A PR that changes behaviour a row describes amends or deletes that row in the same diff.
- A row nothing in the code or plan depends on any more is deleted.
- A row past one screen is split, or its detail moves to a long form.

## Research documents expire

- A research doc stays only while the code does not yet hold what it says.
- The PR that absorbs it into code, tests or a register row deletes it.
- A one-off finding is an issue comment, never a doc.

## References

- Code, tests and docstrings cite a decision id only where the behaviour would surprise a reader (`# D12: retries live in Airflow, not here`).
- Code never cites an issue or PR number: a reader of the code has the code, not the tracker; say the behaviour in words.
- Issues and PRs cite code (`path:line`, a commit sha) and decision ids; the plan's steps table may link its issues, since the plan is the map's index.
- Commit messages and PR bodies may cite anything.

Guard, run as a test or in `make lint` (a line marked `ref-ok` is exempt, for fixtures that need a `#n`):

```bash
# Fails on an issue or PR number in code dirs; list the repo's code dirs.
! git grep -nIE '(\b[Ii]ssues? #?[0-9]+|\bPRs? #?[0-9]+|(^|[^&[:alnum:]_/#])#[0-9]{1,5}\b)' \
    -- src tests scripts ':!*.css' ':!*.svg' ':!*.json' | grep -v 'ref-ok'
```

```python
def test_code_cites_no_issue_numbers() -> None:
    pattern = r"(\b[Ii]ssues? #?[0-9]+|\bPRs? #?[0-9]+|(^|[^&[:alnum:]_/#])#[0-9]{1,5}\b)"
    found = subprocess.run(
        ["git", "grep", "-nIE", pattern, "--", *CODE_DIRS, ":!*.css", ":!*.svg", ":!*.json"],
        capture_output=True, text=True,
    ).stdout.splitlines()
    assert [ln for ln in found if "ref-ok" not in ln] == []
```
