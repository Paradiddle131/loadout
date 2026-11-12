# Guardrails and defaults

How an owner's standing constraints are written, so agents respect them and still challenge them when evidence says so.
Two tiers; no third.

## The tiers

- **Guardrail:** a constraint the owner decides. Only the owner changes it; the agent may, and should, challenge it when evidence conflicts.
- **Default:** a current pick (a tool, a version, a pattern). The agent changes it in the PR that needs the change, with its reason in the architecture document ([`finished.md`](finished.md#decisions)).
- Guardrails live in `CLAUDE.md § Guardrails`, one line each, under a short bold name. Defaults are the architecture document's choices; `CLAUDE.md` holds no list of them.
- A guardrail states something checkable and its reason in one clause; a wish ("keep it simple") is a default or nothing.
- A merged PR is the owner's acceptance; no `[owner]` or `[proposed]` tags, no status field.

## Changing a guardrail

- Only after the owner answers a conflict packet (below) or asks for the change.
- The PR that changes it cites the answer (issue comment link) and amends the line in place; git is the history.
- A guardrail nothing can violate any more is deleted.

## The conflict protocol

A **conflict** is evidence that a guardrail blocks the better option, rests on a fact that changed, or clashes with another guardrail.

1. Stop before acting on the part the conflict touches.
2. Post a conflict packet as a comment on the issue being worked (a new issue if none fits), and label it `needs-owner`.
3. Keep working on everything the conflict doesn't touch; it lands as usual. The PR body's `Open` names the packet.
4. When the owner answers, follow the answer, and amend the guardrail if the answer says so.

Both failure modes are wrong: complying silently when the evidence says the guardrail hurts, and working around it (meeting its letter, defeating its purpose).
A guardrail is followed **and** questioned; a conflict is reported, never resolved by the agent alone.

Packet template:

```markdown
**Guardrail conflict: <name>**
<name> says: <quote>.
Evidence: <the fact, with its source: a doc link, a command and its output, a file:line>.
Conflict: <what the guardrail blocks or breaks, concretely>.
- **A.** Keep <name>: <what we do instead, and its cost>.
- **B.** Amend <name> to <new wording>: <cost, what it opens>.
- **C.** <a third option, if one is real>.
**Recommendation:** <letter>, because <one line>.
Untouched by this: <what the agent keeps doing meanwhile>.
```

## Section template

```markdown
## Guardrails
The owner decides these; when evidence conflicts with one, post a conflict packet and keep working on the rest ([ways/guardrails.md](https://github.com/<owner>/<collection>/blob/main/ways/guardrails.md)). Everything else is a default: a choice in the architecture document.
- **<name>:** <the constraint>; <why>.
- **<name>:** …
```

## Worked example

A region guardrail said: default `europe-west4`, and `europe-west1` as the exception for a product not offered there; another requires the org's Terraform module wherever one exists.
A probe found the org's Cloud Run, Cloud SQL and url-map modules accept only `europe-west4` and `europe-west9`.

```markdown
**Guardrail conflict: EU data residency**
EU data residency says: "default `europe-west4`; `europe-west1` only where a product isn't offered there".
Evidence: the platform probe: the org's Cloud Run, Cloud SQL and url-map modules accept `europe-west4` and `europe-west9` only.
Conflict: an exception in `europe-west1` forces raw resources where the org-modules guardrail requires a module.
- **A.** Keep the region line: raw resources for any exception service; breaks the org-modules guardrail and loses the org module's defaults.
- **B.** Amend the region line to name `europe-west9` (or an EU multi-region) as the exception: same EU guarantee, works with the modules.
**Recommendation:** B, because it keeps both guardrails' purposes with one word changed.
Untouched by this: every resource in `europe-west4`, which is all of them today.
```

The owner chose B; the change amended the region line and cited the answer.
