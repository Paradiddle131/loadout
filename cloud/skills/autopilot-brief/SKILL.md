---
name: autopilot-brief
description: Briefs the owner, on one visual page, on what a run of scheduled autopilot wakes did while they were away; the work grouped by epic, topic and work item, what is new in the code base, what went wrong, and what needs them. Use when the owner comes back after an unattended routine and asks for a brief, a recap or "what did the wakes do".
---

# Autopilot brief

One page that tells the owner, at a glance, what the wakes did since the routine went on.
It is the read side of the `autopilot` skill: the wakes write claims, handoffs and `Went wrong:` lines, and this page gathers them.
Fill [`template.html`](template.html): copy it, replace only the JSON block at its bottom, publish.
The template holds the structure and the look, so every brief reads the same, and you add or remove an item by editing one JSON entry.

The page, in order: the map of the work, what is new in the code base, a card per piece of work, what went wrong, wakes that did no work, and what needs the owner.
Each section opens with one plain line; details stay folded.

## 1. Find the window

- Start: the moment the routine went on: the profile's or Map's first commit, or the first `🤖 claimed` comment after it. The owner may name it.
- End: now (`date -u +%FT%H:%MZ`).
- Name both in the page's `window` line.

## 2. Collect (read only)

From the target's root, with `R=<owner>/<repo>` from `git remote get-url origin`:
- Commits: run `git fetch origin`, then `git log origin/<train or branches> --since=<start> --reverse --format='%h %cI %s'`, and the same on the default branch.
- Files: `git diff --name-status <last commit before start> origin/<train>` and `git diff --shortstat` over the same range, for the tree.
- Each issue of the profile's queue (its Map's sub-issues, or the `agent:*` issues): `gh api repos/$R/issues/<n>` and `.../comments`. Keep the `🤖 claimed <time> <wake id>` lines (one wake id is one wake) and the `🤖 Handoff` comments.
- The Digest's open owner questions and every `needs-owner` issue's last packet.
- The profile's `Known conditions` lines added in the window (`git log -p --since=<start> -- <profile>`).
- Non-`🤖` comments in the window: the owner's own interventions.
- Gaps between claims: an hour with no claim is a wake that did nothing, or never started.
A run with many issues fits in one subagent's read: hand it the window and the issue numbers, and ask for the JSON fields below, not prose.

## 3. Group (the map)

- One `epic` per Map or epic the wakes worked; issues outside any go under one epic named after the repo.
- Inside it, three to six `topics` by what the work is about (not by date or by wake), each with one plain `line`.
- Inside a topic, `subs`: one per piece of work the owner would name, usually one to three issues (a fix and its follow-up are one sub).
- Each issue of a sub is `[number, status, headline]`.
  The headline is the work item in one plain sentence with its result ("With only `silver` in reach: 35 of 36 right over three runs"), never the issue's title.
  The map shows a sub's name with one status pip per item; the headlines sit folded under it, so the map stays a map.
- Status of a sub and of each item: `landed` (on the train or merged), `running` (repeats or partial), `needs` (waits on the owner), `queued` (not started).

## 4. The code base tree

What is new, the way a pull request's file list shows it, but curated so the new parts stand out beside what was already there.
- `tree.line`: one sentence on the shape of the change; `tree.stats`: the diff's file count and lines.
- `nodes`: nested `{ name, state, note, count, children }`, with `state` one of `new` (highlighted), `changed`, `same` (grey context), `more` (a folded "14 more modules").
- Show a new file beside two or three of its existing siblings in grey, so the owner sees where it fits; collapse long runs into `more`; join neighbours with ` · `.
- Put a short `note` on each new or changed node: what it does, never its code.
- Scale it to the change: for a small change, every touched file; for a large one, the folders that matter, with counts (`+31 scripts`); generated logs and fragments go in one grey line.
- No per-issue diffs anywhere: the code is on the forge, and the tree shows where it went.

## 5. Write each card

- `changed`: one plain sentence on what is different now.
- `know`: one plain sentence on what the owner should take from it: a surprise, a limit, a number that moves the decision.
- Folded details: an optional `table` (results, or Before/After rows) when numbers carry the point, then `notes` (two to four bullets) and `links` (the finding, the commit).
- Aim for cards of the same size; mark `"wide": true` only for the one card that carries the run's main result.
- Write the way a colleague talks at handover: short sentences, real numbers, backticks for names; no wake ids, no hashes outside links.

## 6. What went wrong

One `wrong` row per distinct problem, from the handoffs' `Went wrong:` lines and anything the collection shows (a blocked wake, a claim yielded by mistake, a fix commit that undid an earlier wake's scoring).
- `kind`: `environment` (cloud, network, tools, quotas), `missing input` (a key, a grant, a decision the wakes had to wait for), `found in the work` (the system under study behaved differently from its docs or from the plan), or `setup` (the routine prompt, profile or queue the owner wrote before turning it on).
- `line`: what happened, in one sentence; `cost`: wakes or hours lost.
- `status`: `open`, `still unknown`, `known` (a known condition or upstream), `filed`, or `fixed`. The page sorts by it, open first, so the owner reads what still bites before what is history.
- Merge repeats into one row with the count.
- A `setup` row ends its notes with the change to the profile or prompt that would have avoided it, so the next routine starts better.

## 7. Wakes that did no work

No timeline: one `wakes.line` ("Every hourly wake picked up work"), then a row only for a wake that failed to start, found nothing pickable, ended on Mode `paused`, could do only part of its work (live steps blocked), or had to work around its own tooling.
Each row: `kind`, `line` (which wakes and why), `status`.

## 8. Needs you

One `needs` row per open owner question, most blocking first.
- `line`: the question in plain words.
- `unblocks`: what moves once it is answered.
- `notes`: the options and the recommendation.
The header's pill counts them and links here; an empty list says so.

## 9. Publish

- Write the filled copy to the scratchpad (never into the target repo) and check its JSON parses (`python3 -c` over the block).
- Render it once at desktop and phone widths with a few map lists open: no horizontal overflow, no console errors.
- Publish it with the Artifact tool when the session has it (icon `report`), else send the file. Give the owner the link and the headline in two lines.
- Fix gaps you notice in the wakes' records as a PR on the `autopilot` skill or the profile, not in the brief.
