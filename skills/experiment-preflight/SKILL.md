---
name: experiment-preflight
description: Use before starting or resuming any paid, quota-bound or long measured pass (a model eval, a benchmark, a load test), and before freezing a question set or changing a scorer.
---

# Experiment preflight

A measured pass spends budget once; a broken setup spends it on runs that are later set aside.
Each step below ends on **evidence**: an output pasted into the pass's preflight record (its issue, PR or the repo's run-evidence folder), never a sentence saying the step was done.
The pass starts only when all eight items are in the record; an item marked not applicable carries its reason.
On resume, repeat steps 2 and 7 and paste `status`: a restarted container, a lost variable or a moved dependency breaks a setup that worked yesterday.

## Outcomes

Every run ends in exactly one of three outcomes:

- **ok**: the subject answered and the scorer passed it;
- **wrong**: the subject answered and the scorer failed it;
- **infra**: the measured path did not run: a tool returned an error, the data source refused or timed out, a rate limit, a lost process, an empty answer after any of these, a result withheld for want of a credential.

Classify infra from the trace (tool results, exit codes, logs), never from the answer's text: a subject that honestly reports a broken tool reads like a real answer.
An infra run is neither right nor wrong; it never enters a score's numerator or denominator.

## Steps

1. **Question.** Write the question the pass answers, the result that would change a decision, and the decision it changes.
   Evidence: those three lines; a pass whose answer changes no decision does not run.
2. **Canary.** Run one known-easy and one known-hard case through the whole path, unlogged.
   Evidence: from each trace, the lines showing the thing measured at work: the tool called with its result (not an error), the data source reached, the subject's tool list exactly as intended.
   The easy case scores ok; a miss on it is a setup fault: fix it before step 3.
3. **Parity.** Dump each setup's full configuration (model, prompt, tool list, data reach, limits, runner flags) to a file and diff them.
   Evidence: the diff; every line in it is the variable under test, and any other line is fixed or named as a confound in the record.
4. **Scorer.** Before trusting a new or changed scorer, run it on adversarial answers: a wrong answer that contains the right number, the right answer in words or another unit, an empty answer, an infrastructure error message, a refusal.
   Evidence: the scorer's output on each; it fails the wrong, empty and refusal cases, passes the reworded right one, and returns infra for the error.
   Keep these as the scorer's unit tests, so a later change reruns them.
5. **Question set.** Before freezing, a reviewer that did not write the cases (a fresh agent or a person) checks each for ties, constant or fixture-fixed answers, several readings and an expected answer that is itself wrong.
   Evidence: the review's findings and how each was resolved.
   Once frozen, the set has a version and a content hash; a fix is a new version, and results name the version they ran on.
6. **Budget in code.** Create the guard with the number in the owner's go, and run the pass through it (below).
   Evidence: the `init` line, its limits matching the go; an alarm or a progress note someone must read is not a budget.
7. **First results.** After the first few logged runs, read each in full: answer, trace, score, outcome.
   Evidence: the run ids read and one line each; the change under test shows in the traces, or the pass stops and goes to the owner.
   Two infra outcomes stop the pass (the guard enforces it); find the cause before any rerun.
8. **Record.** The pass writes, where the repo keeps run evidence: configuration and its diff, model and tool versions, question-set version, the guard's final `status`, outcome counts, and every run set aside with its reason.
   Evidence: the path or link to that record.

## The guard

`scripts/budget_guard.py` keeps a pass's counts in a JSON state file, one file per owner's go, and stops the loop by exit code: `0` go on, `3` a limit is reached, `2` refused (missing or corrupt state, changed limits, a missing cost under a cost limit).
Every non-zero exit stops the loop, so a fault in the guard stops the pass too.

```bash
G="python3 <skill>/scripts/budget_guard.py --state runs/pass.json"
$G --max-runs 40 --max-cost 5 --max-infra-failures 2 init
while $G start; do
  read -r outcome cost < <(run_one_case)   # prints "ok|wrong|infra <cost>", infra read from the trace
  $G record --outcome "$outcome" --cost "$cost" || break
done
$G status
```

`start` reserves a slot under a lock, so parallel workers together start at most the go's number.
Limits are fixed at `init`: a call naming different ones is refused, and a new go is a new state file.
