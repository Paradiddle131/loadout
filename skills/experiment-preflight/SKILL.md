---
name: experiment-preflight
description: Use before starting or resuming any paid, quota-bound or long measured pass (a model eval, a benchmark, a load test), and before freezing a question set or changing a scorer.
---

# Experiment preflight

A broken setup spends a pass's budget on runs later set aside.
Each step ends on **evidence**: an output pasted into the pass's preflight record (its issue, PR or run-evidence folder), never a sentence saying it was done.
The pass starts only when all eight items are in the record; an item marked not applicable carries its reason.
On resume, repeat steps 2 and 7 and paste `status`: a restart or a lost variable breaks a setup that worked yesterday.
A cost budget never permits a paid model where the repo or environment requires free ones.

## Outcomes

Every run ends **ok** or **wrong** (the scorer passed or failed the answer), or **infra**: the measured path did not run (a tool error, the data source refused or timed out, a rate limit, a lost process, a result withheld for want of a credential).

Classify infra from the trace (tool results, exit codes, logs), never from the answer's text: an honest "the tool failed" reads like a real answer.
An infra run never enters a score's numerator or denominator.

## Steps

1. **Question.** Write the question the pass answers, the result that would change a decision, and the decision it changes.
   Evidence: those three lines; a pass whose answer changes no decision does not run.
2. **Canary.** Run one known-easy and one known-hard case through the whole path, unlogged.
   Evidence: from each trace, the lines showing the measured thing at work: the tool called with a result (not an error), the data source reached, the subject's tool list as intended.
   The easy case scores ok; a miss is a setup fault; after two misses, stop and report to the owner.
3. **Parity.** Dump each setup's full configuration (model, prompt, tool list, data reach, limits, runner flags) to a file and diff them.
   Evidence: the diff; every line in it is the variable under test, and any other line is fixed or named as a confound in the record.
4. **Scorer.** Before trusting a new or changed scorer, run it on adversarial runs: a wrong answer containing the right number, the right answer in words or another unit, an empty answer, a refusal, and a run whose trace holds a tool error.
   Evidence: the scorer's output on each, kept as its unit tests: it fails the wrong, empty and refusal runs, passes the reworded one, and returns infra from the tool-error run's trace (a scorer seeing only answer text scores it wrong, never ok).
5. **Question set.** Before freezing, a reviewer who did not write the cases checks each for ties, constant or fixture-fixed answers, several readings and an expected answer that is itself wrong.
   Evidence: the reviewer's name (a fresh session's id or a person), its findings and how each was resolved; the author's own review does not count.
   Once frozen, the set has a version and a content hash; a fix is a new version, named by the results that ran on it.
6. **Budget in code.** Run the pass through the guard (below), its limits the numbers in the owner's go.
   Evidence: a quote of or link to the owner's go naming the number, beside the `init` line with the same limits; an alarm someone must read is not a budget.
7. **First results.** After the first few logged runs, read each in full: answer, trace, score, outcome.
   Evidence: the run ids read and one line each; the change under test shows in the traces, or the pass stops and goes to the owner.
   Two infra outcomes stop the pass (the guard refuses a higher limit the go does not name); find the cause before any rerun.
8. **Record.** The pass writes, where the repo keeps run evidence: configuration and diff, model and tool versions, question-set version, the guard's final `status`, and every run set aside with its reason.
   Evidence: the path or link to that record.

## The guard

`scripts/budget_guard.py` keeps a pass's counts in a JSON state file, one per owner's go, and stops the loop by exit code: `0` go on, `3` a limit reached, `2` refused (missing or corrupt state, changed limits, a missing cost under a cost limit); any non-zero exit stops the loop.

```bash
G="python3 <skill>/scripts/budget_guard.py --state runs/pass.json"
$G --max-runs 40 --max-cost 5 --go "<owner's words or link>" init
while $G start; do
  read -r outcome cost < <(run_one_case)   # prints "ok|wrong|infra <cost>", infra read from the trace
  $G record --outcome "$outcome" --cost "$cost" || break
done
$G status
```

`start` reserves a slot under a lock, so parallel workers together start at most the go's number; limits are fixed at `init`, and a new go is a new state file.
The cost limit checks spend so far: set it to the go minus one run's largest cost per parallel worker.
