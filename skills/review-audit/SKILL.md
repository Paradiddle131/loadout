---
name: review-audit
description: "Use when the owner asks how the reviews have been going, to review the reviews, or to audit a batch of review rounds across repos: gather the `review` skill's records, re-check a sample of findings, record the judgments on each PR, and report the numbers."
---

# Review audit

The `review` skill leaves a `🤖 Review` record on every PR it reviews; this skill reads a batch of them back, has a fresh auditor re-check a sample of the findings, and posts the judgments as `🤖 Audit` records beside them.
GitHub holds every record, so any past audit session can be read again; the JSONL files are a snapshot, rebuilt by harvesting.
`$A` is this skill's folder; `$A/scripts/audit.py` is the tool, its header gives every argument.

## 1. Name the batch

- The repos (each `<owner>/<repo>` the owner names, or every repo of theirs that uses the `review` skill), the window (`--since`, `--until`), and a session id: `<UTC date>-<short slug>`, from `date -u +%F`.
- Done when the three are written in the session's notes.

## 2. Harvest

- `python3 $A/scripts/audit.py harvest --repo <o/r> [--repo ...] --since <ISO> --out <dir>`: reads only, writes `prs`, `gates`, `rounds`, `findings` and `audits` JSONL files in `<dir>` (the session's scratchpad).
- Only records the merge guard would trust count: by the repo's owner, a member or a collaborator, unedited, with the exact title and marker and the two agreeing; a review round's must-fix findings are the ones its `Blocking:` line lists, where the record has one.
- Done when the counts it prints are in the notes.

## 3. Sample

- `python3 $A/scripts/audit.py sample --dir <dir> --n <count>`: takes one finding in turn from each group of must-fix or other findings by first lens, must-fix groups first in each turn, and leaves out pre-existing findings and those an earlier audit judged.
- Thirty is a working default; `summary` gives the wrong, mattered and ranked-too-high rates a 95% interval each, so a smaller batch shows a wider one.
- Done when `sample.jsonl` exists.

## 4. Audit

- Give each sampled finding to [`finding-auditor`](../../agents/finding-auditor.md), a fresh subagent per repo or per PR, on Opus at medium effort set in the call: the finding's record link, its round's reviewed commit, the repo's clone and the change base.
  Give no view of yours on the finding: the auditor judges it cold.
- Each judgment carries `round`, `ids`, `correct`, `matters`, `rank`, `kind`, `method` and a one-line `note`, and nothing else (the shape is in `audit.py`'s header).
- `record` refuses a judgment whose `round` is not a trusted review record on that PR, or with keys or ids out of shape.
- Check each judgment the way the `delegating` skill checks a report: rerun at least one `re-ran` judgment per auditor yourself.
- Done when every sampled finding has a judgment, or is listed as not reached with the reason.

## 5. Record

- Per PR, `python3 $A/scripts/audit.py record --repo <o/r> --pr <n> --session <id> --file <judgments.json>` posts one `🤖 Audit` record and reads it back; `--backfill` marks judgments taken from an audit made before this skill.
- An audit record changes no merge: the merge guard reads only gates and review records.
- Done when each PR with a judgment has its record.

## 6. Report

- Harvest again (it picks up the new audit records), then `python3 $A/scripts/audit.py summary --dir <dir> --session <id>`.
- Give the owner its tables as they are: the headline numbers with their intervals, the lens table, and the changes that need a look; add a sentence only where a number needs one.
- Every problem the audit finds in the review path itself is an issue (the `issue` skill) on the audited repo; where this collection's `FEEDBACK.md` is imported, also a `bin/friction note` in generic words, as `FEEDBACK.md` says, so nothing of a private repo reaches the collection's public tracker.
- Done when the owner has the tables and the issues are filed.
