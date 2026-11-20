---
name: debrief
description: "Use when the owner comes back after agents worked while they were away (scheduled wakes, long sessions, one repo or several) and asks what happened, what needs them, or to be caught up: one short visual pitch of the big picture."
---

# Debrief

The owner was away while agents worked; a debrief is the one thing they read to catch up, in place of the issues, PRs and logs, which are written for agents.
It is a pitch: short, plain English, visual, and built around **attention**, meaning what went wrong, what needs the owner, and what could be better.

## What it holds

- **The big picture first:** where the work stands against its scope, roadmap or vision, drawn as a picture, so the owner sees direction and distance left rather than a list of items.
- **Attention gets the space.** What went wrong, what is blocked, what the owner must decide, what could improve: each in a few plain lines, with its cost and what clears it.
- **Every change gets its line.** When anything landed, closed or waits, the attention part carries the lines [`landings.md`](landings.md) defines, after what needs the owner and is not a PR: risky and waiting changes in full, the expected one short line each; none goes silent.
- **The expected stays quiet.** Everything else that went as it should (no cost, rules held, nothing dropped) gets one short line or nothing; it earns detail only once it goes wrong.
- **Sections are a menu.** Usual ones: what happened, how the agents did, how the reviews did, what went wrong, what needs you and how to unblock, the next best action. Leave out any with nothing to say (nothing merged, closed, pushed or waiting; nothing blocks) and add any the work calls for.
- **Plain English for a reader outside the work**, by the standing rule on reports: process metadata stays in the PRs and issues, and every term the page shows gets a gloss.

## The form

- A visual, concise artifact that forces brevity: a short deck by default, or a dashboard or one page when the content suits it better. A long prose document invites detail; choose a form that resists it.
- Chart whatever a picture carries better than words: progress along a path, counts by state, time or wakes spent.
- Choose the look fresh for each debrief, from its content; a repo's own design system applies where it has one.
- Build it in the scratchpad, never in the target repo, and publish it as an artifact (with no artifact tool, send the file); the chat reply is a line or two and the link, since the artifact is the answer.

## Steps

1. **Window:** from when the owner last looked (their word, the last debrief, or when the schedule went on) to now (`date -u +%FT%H:%MZ`).
2. **Gather, read only:** commits on the default branch; the PRs of the window with their labels and records, read by [`landings.md`](landings.md); claims and handoffs on the issues; open owner questions; the collection's `friction` issue; and the final messages of the scheduled runs' sessions. For a large window, hand the reading to a subagent and ask it for facts, not prose.
3. **Check, don't relay:** test each run's last word against the record (a run that says "nothing to pick" is checked against the queue itself); when reviews ran and the owner asks, or a record looks off, audit them with the `handoff-auditor` agent and give its findings the space, its passes a line.
4. **Write down what you find but do not fix:** an issue, by the `issue` skill, or the repo's own place for review leftovers where its instructions name one.
5. **Build and publish** the artifact.
6. **Offer the way forward:** ask whether to clear the blockers one by one, each with a plain explanation and a recommended step the owner answers yes, no or how; a prompt for a fresh session to carry the work on comes only once the path is clear.

Done when the owner can tell from the artifact alone where the work stands against its goal, what went wrong, and what they must do next.
