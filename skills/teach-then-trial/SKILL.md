---
name: teach-then-trial
description: "Use when a reviewer's concern about one piece of work should become a reusable rule in this collection, proven by a blind agent that applies it."
---

A concern a reviewer raises once ("these parts don't read apart", "this says the same thing three times") usually names a gap in the collection's rules, not only a flaw in one page.
This skill closes the gap in two moves:

- **Teach:** turn the concern into generic rules (and the smallest support they need) in the collection: the repo that holds this skill.
- **Trial:** hand the concern, in the reviewer's words, and the taught collection to a **blind** agent that has never seen your diagnosis, and let it fix the work.

What the blind agent gets right, the collection now teaches; each **miss** is either its lapse or a gap the collection still has.
The work is done when the reviewer has the fixed work, the collection has the rules, and every miss is fixed or filed.

It needs a subagent tool (two fresh agents) and a way to show the work (screenshots, a preview link).
Run every subagent in the foreground, or wait for its report before acting: nothing it reports counts until you have checked it.

## Steps

1. **See it as the reader does.**
   Capture the work as its reviewer meets it: screenshots at the widths and themes that matter, kept as the **before** set.
   Write the concern down twice: the reviewer's words, verbatim, and your own diagnosis (each part of the work, what it shows, what repeats, which existing rule it breaks).
   Done when every sentence of the concern points at something visible in the before set.

2. **Research.**
   Delegate to one subagent with the research brief in [BRIEFS.md](BRIEFS.md): the concern in both forms, the before set, the collection's relevant skill, and a worktree of the collection on a new branch.
   It finds what in the concern is generic (a rule the collection lacks, or one it states too weakly to steer an agent), grounds each rule in primary sources, and drafts the rules and their smallest support as uncommitted edits.
   Done when its note diagnoses every part of the work and each drafted rule says what it rules, why, its grounds, and when not.

3. **Teach.**
   Review the draft as if you were the owner: verify every number it claims (contrast, sizes, check results) by running it yourself, cut what is page-specific or restates the environment, and fix drift it found on the way.
   Commit it, open the PR (the `pr` skill), and keep it open: the trial runs against its branch.
   Done when the collection's own checks pass on the branch and its PR states each new rule in one line.

4. **Trial.**
   Give a fresh subagent the trial brief in [BRIEFS.md](BRIEFS.md): the reviewer's words, the collection at the teach branch, and the work in its own worktree; nothing of your diagnosis or the research note.
   It fixes the work, runs the work's checks, commits locally, and reports which rules it used and where the collection left it guessing.
   Done when its report names, for each part of the concern, what it changed and which rule led it there.

5. **Inspect.**
   Re-run the work's checks yourself on a frozen copy of the trial's build, and put before and trial side by side at the same widths and themes.
   Sort every miss (in the trial's report or found by you) in one table:

   | Miss | Its kind | Where it is fixed |
   |---|---|---|
   | what a reader would see | lapse (the rule was there and clear) / missing rule / unclear rule / missing support (a component, a check) | the work, or the teach PR |

   Done when every row has a kind and a home, and no rule the trial ignored was missed for want of reading.

6. **Fold in and fix.**
   Bring the trial into the work's branch, fix every miss in the work, and fix every gap on the teach branch (a rule, its wording, a component, a check); the work may carry a stopgap until the collection's fix lands.
   Merge the teach PR only when the owner has said so for this loop, after this step: the rules that land are the ones a blind agent proved.
   Done when the work's checks pass on the final build and the teach PR holds every gap's fix.

7. **Report.**
   Give the owner, in one message: the work's preview and the trial's (or one page comparing before, trial and final), the rules the collection gained, the scorecard (rules the trial used, its misses by kind), and what still needs them.

## Ground rules

- **Blind means blind:** the trial brief carries the reviewer's words and the collection, never your diagnosis, the research note or a hint at the fix; a trial that was told the answer proves nothing about the rules.
- **Generic in the collection, specific in the work:** a rule that names the work, its project or its data stays in the work; the collection's own writing rules (its `AGENTS.md`) decide.
- **Long checks run once per stage,** in the background, against a frozen copy of the build, so a rebuild cannot change the page under them.
- **Show every visible change** to the reviewer where they look (the preview), after each stage that changes what they would see.
