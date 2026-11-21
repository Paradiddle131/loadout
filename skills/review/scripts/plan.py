#!/usr/bin/env python3
"""Plans a review round from a PR's paths and the repo's policy: its depth, its lenses in order and each lens's effort.

  plan.py [--pr <n>] [--depth none|light|focused|full] [--json]
      the lead's preview: what verdict.sh will require of the round it records for PR <n> (the current branch's
      open PR when --pr is left out); --depth raises the depth, never lowers it below the floor.
  plan.py record --pr <n> [--depth <d>] --reviewers <names> --lens "<name> ... effort=<e> ..."...
      what verdict.sh runs: the same plan, then refuses a reviewer set missing a planned lens or the verifier, or a
      planned lens run below its planned effort; prints the marker's depth and the round line's pairs.
  plan.py floor --base <ref> --head <ref>
      what the merge guard runs, like tier.sh: the tier and the depth floor of the paths, from a local clone.

The preview and the record read the same inputs the same way, and neither takes a base, a head, a reviewed commit
or a prior output from the lead: no option can change what verdict.sh records except to raise it.

Inputs, where each is read from, who controls it, and how a lead-controlled one can only raise the plan:

| Input | Read from | Controlled by | Enforcement |
|---|---|---|---|
| PR head | `gh api repos/<r>/pulls/<n>`, `.head.sha` | GitHub's PR API | fetched by that sha; the checkout, `HEAD` and local branches are never read |
| Default branch name | the same answer, `.base.repo.default_branch` | GitHub's PR API | `origin/HEAD` and local branch names are never read |
| Default branch tip | `gh api repos/<r>/branches/<name>`, `.commit.sha`; then `git fetch --force origin +refs/heads/<name>:refs/remotes/origin/<name>` | GitHub (the sha), the remote (the objects) | the forced fetch overwrites a locally moved ref; a fetched tip other than GitHub's sha refuses |
| Changed paths | `git diff --name-only --no-renames $(git merge-base <tip> <head>) <head>` | the two shas above | computed from content-addressed commits only |
| Policy | `REVIEW.md` at the tip, parsed by tiers.py (tier.sh's parser), and the tip's instruction imports | the default branch on the remote | the change's own `REVIEW.md` is never read; an unparsable one rates every path sensitive; no line lowers a path below the built-in floor or below `## Sensitive` |
| Previous round | `gh api repos/<r>/issues/<n>/comments`, paged by hand: the newest review-marker comment by the owner, a member or a collaborator | a trusted record on the PR | used only when unedited, in verdict.sh's exact shape, above routine, its raw output's first `Reviewed:` naming its `reviewed=`, its `Blocking:` line readable, and `reviewed=` an ancestor of the head and not of the merge-base; else a first review (the widest plan); an older record is never used in its place; untrusted authors are ignored |
| Answered lenses | that record's `Blocking:` ids, by prefix | a trusted record | an id whose prefix names no lens plans the whole set |
| `--depth` | the lead's argument | the lead | the depth is the higher of it and the floor; one below the floor refuses |
| `--reviewers`, `--lens` | the lead's arguments to verdict.sh | the lead | must cover every planned lens and the verifier, each planned lens at its planned effort or above; extra lenses are accepted |
| `--pr` | the lead's argument | the lead | names the PR the record is posted on, so it can only describe that PR |
| Repo (`REVIEW_REPO`, else `origin`'s URL) and the object store | the local clone | the lead | every object is read by a sha GitHub named; the code these scripts run from is stamped as `kit=` on the round line |

Depths, ranked none < light < focused < full; the floor is the highest depth among the changed paths:
  routine path    none; standard path    light (or the policy's `Depth:`); sensitive path    focused.
  none     no reviewer: gates only.
  light    one lens and the verifier: correctness-reviewer, or claims-auditor when every changed path is routine.
  focused  the tier's set, correctness-reviewer first and alone, then the rest with its findings in their briefs;
           a fix round reruns only the lenses it answers and those its paths call for.
  full     the tier's set at once; a fix round reruns the whole set.
"""

from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write("plan.py: not implemented yet\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
