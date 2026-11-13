---
name: concern-to-rule
description: "Use when someone's concern about one piece of work should become a reusable rule in this collection, proven by a blind agent that applies it."
---

A concern a reviewer raises once ("these parts don't read apart", "this says the same thing three times") usually names a gap in the collection's rules, not only a flaw in one page.
This skill closes the gap in two moves:

- **Teach:** turn the concern into generic rules (and the smallest support they need) in the collection: the repo that holds this skill.
- **Trial:** hand the concern, in the reviewer's words, and the taught collection to a **blind** agent that has never seen your diagnosis, and let it fix the work.

What the blind agent gets right, the collection now teaches; each **miss** is either its lapse or a gap the collection still has.
The work is done when the reviewer has the fixed work, the collection has the rules, and every miss is fixed or filed.

It needs a subagent tool (two fresh agents) and a way to show the work (screenshots, a preview link).
Isolate, set up and check each subagent by the `delegating` skill (its two briefs stay as [BRIEFS.md](BRIEFS.md) writes them); run it in the foreground, or wait for its report before acting.

## Steps

1. **See it as the reader does.**
   Capture the work as its reviewer meets it: screenshots at the widths and themes that matter, kept as the **before** set.
   Write the concern down twice: the reviewer's words, verbatim, and your own diagnosis (each part of the work, what it shows, what repeats, which existing rule it breaks).
   Sort the reviewer's sentences: what they call a problem, and what they only describe ("it sits in its own scroll box"); a description is not a complaint, and the shape they chose stays unless they name it; ask when you cannot tell.
   Done when every sentence of the concern points at something visible in the before set, and each is marked a problem or a description.

2. **Research.**
   Delegate to one subagent with the research brief in [BRIEFS.md](BRIEFS.md): the concern in both forms, the before set, the collection's relevant skill, and a worktree of the collection on a new branch.
   It finds what in the concern is generic (a rule the collection lacks, or one it states too weakly to steer an agent), grounds each rule in primary sources, and drafts the rules and their smallest support as uncommitted edits.
   It tries each drafted rule on the work itself, at its real size, not only on the skill's own fixture: a rule that reads well on nine sample items can make an eighty-item page many screens long.
   Each source must be about the same kind of thing the rule rules on (advice about a small inline list does not rule a page-long reference).
   Done when its note diagnoses every part of the work, each drafted rule says what it rules, why, its grounds, and when not, and the note shows the work with each rule applied.

3. **Teach.**
   Review the draft as if you were the owner: verify every number it claims (contrast, sizes, check results) by running it yourself, cut what is page-specific or restates the environment, and fix drift it found on the way.
   Cut any rule that would overrule a design the reviewer chose and did not complain about, and any rule that contradicts a choice the collection already makes for the same job (a second control for something the page already does one way).
   Commit it, open the PR (the `pr` skill), and keep it open: the trial runs against its branch.
   Done when the collection's own checks pass on the branch and its PR states each new rule in one line.

4. **Trial.**
   Give a fresh subagent the trial brief in [BRIEFS.md](BRIEFS.md), which carries exactly three things: the reviewer's words, the collection at the teach branch, and the work in its own worktree.
   It fixes the work, runs the work's checks, commits locally, and reports which rules it used and where the collection left it guessing.
   Done when its report names, for each part of the concern, what it changed and which rule led it there.

5. **Inspect.**
   Re-run the work's checks yourself on a frozen copy of the trial's build, and put before and trial side by side at the same widths and themes.
   Sort every miss (in the trial's report or found by you) in one table:

   | Miss | Its kind | Where it is fixed |
   |---|---|---|
   | what a reader would see | lapse (the rule was there and clear) / missing rule / unclear rule / missing support (a component, a check) | the work, or the teach PR |

   Then judge the trial as the reviewer would, by eye against the before set, with the skill's own design review (a critique, not only its checks): zero problems from a checker is not "reads well".
   Done when every row has a kind and a home, every lapse names the rule the trial had and passed over, and you can say whether the trial reads better than the before.

6. **Fold in and fix.**
   Bring the trial into the work's branch, fix every miss in the work, and fix every gap on the teach branch (a rule, its wording, a component, a check); the work may carry a stopgap until the collection's fix lands.
   Merge the teach PR only when the owner has said so for this loop, after this step: the rules that land are the ones a blind agent proved.
   Done when the work's checks pass on the final build and the teach PR holds every gap's fix.

7. **Report.**
   Give the owner, in one message: the work's preview and the trial's (or one page comparing before, trial and final), the rules the collection gained, the scorecard (rules the trial used, its misses by kind), and what still needs them.
   Done when the owner can open each preview and every miss is fixed in the work or carried by the teach PR.

## Ground rules

- **Going back is an outcome.** When the trial reads worse than the before, or the reviewer keeps none of what was tried, the work returns to its before state, and the loop's yield is what the misses teach the collection, not a rule built on the failed shape.
- **The skill's steps, not only its rules:** both briefs send the agent through the skill's steps as written (its design direction and review included), since rules alone let a page pass every check and still read badly.

- **Blind means blind:** the trial brief carries only the reviewer's words, the collection and the work, so whatever the trial gets right, the rules taught it.
- **Generic in the collection, specific in the work,** as the collection's `AGENTS.md` defines generic.
- **Long checks run once per stage,** in the background, against a frozen copy of the build, so a rebuild cannot change the page under them.
- **Show every visible change** to the reviewer where they look (the preview), after each stage that changes what they would see.
