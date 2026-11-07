---
name: issue
description: "Use when filing or editing a GitHub issue, or saving a session's plan, analysis or visual onto one, in any repo."
---

An issue is read by whoever picks the work up later, often an agent with none of your context.
Put what they must know on one screen, in this order: what is wrong or wanted, the proof, when it is done.
Everything else goes under `<details>`, and the session's durable work (a plan, a root-cause analysis, a visual) goes on the issue as **artifacts**, so it outlives the session.

````markdown
<One or two sentences: what is wrong or wanted, in the reader's words.>

## Evidence

- <the symptom as a run: the command and its output, `path:line`, or what the screen shows>
- **Suspected cause:** <one line, or "unknown">

## Done when

- <a check that passes: a command, a test, an observable result>

## Needs you

<Optional: one plain-English sentence per decision only the owner can make. No such item, no section.>

<details>
<summary>Context, reasoning, notes</summary>

<repro steps, what was tried, options weighed, related issues and PRs, what is not known>

</details>
````

## Rules

- **One screen.** At most about 15 lines outside `<details>`; one line per bullet, no paragraphs there.
- **Title is the ask,** imperative and specific: `Fail agent-eval on a refused key`, not `agent-eval bug`.
- **Evidence is runs, not adjectives,** as in the `pr` skill; a feature request's evidence is where its absence hurts.
- **Done when is checkable:** someone can tell done from not-done without asking you.
- **Needs you** holds only a real decision; never a no-op line.
- **Details hold the rest:** repro steps, logs beyond the key line, options and why, links.
  Several `<details>` blocks are fine when the topics differ; leave a blank line after `<summary>…</summary>` or GitHub shows raw Markdown.
- Search open issues first; add to a match (a comment in this same shape) instead of filing a twin.
- A repo's own issue template or labels win; they only rename these sections.
- Editing an existing issue follows the same shape; rewrite a wall of text into it rather than appending.

## Artifacts

The session's files vanish with it.
Before you leave an issue, keep the few that the next person would otherwise redo, as artifacts on it.

**Keep** (at most about three, each standing alone):

| What | `type` |
|---|---|
| An implementation plan | `plan` |
| A root-cause analysis, research notes, a decision write-up | `generic` (Markdown) |
| A self-contained HTML visual: diagram, report, prototype | `embedded_html` |
| A published page, a prototype, a thread elsewhere | `link` |

**Leave behind:** scratch files, full logs (quote the key line under Evidence), anything the repo or a rerun regenerates, and anything secret or private (a public repo's artifacts are public).

- **Name each for what it holds:** `Plan - fail fast on a refused key`, `RCA - retries ignored in eval` (names allow only letters, digits, spaces, `.`, `-`, `_`; a `:` or `/` is refused with 422).
- **Concise:** an artifact earns its place by saving the reader work; cut a session's narrative down to findings and decisions.
- **HTML stands alone:** inline CSS, images as `data:` URIs, no scripts or external requests (GitHub previews it in a sandbox and warns the reader about network calls).
- **Update, don't duplicate:** a newer version of the same plan is a `PATCH` to its artifact (GitHub keeps the history).
- The body points to an artifact only when it relies on it: `Plan: see the artifact "Plan - …"`.

```bash
# gh ≥ 2.103 has `gh issue artifact`; the REST calls work with any gh.
A=repos/<owner>/<repo>/issues/<n>/artifacts
gh api -X POST $A -f type=plan -f name="Plan - <what>" -F body=@plan.md   # -F reads the file; -f would post the path
gh api -X PATCH $A/<artifact_number> -F body=@plan.md
gh api $A --jq '.[] | "\(.number) \(.type) \(.name)"'                    # read back what landed
gh api $A/<artifact_number> --jq .artifact.body                          # one artifact reads as {artifact, versions}
```

Artifacts are in public preview: when the endpoint refuses, put the artifact's Markdown in a comment under `<details>` and say so.
