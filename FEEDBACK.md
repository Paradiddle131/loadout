# Feeding back to this collection

The standing rules that write outside the repo being worked on: to the repo that holds this collection.
Import them beside [`RULES.md`](RULES.md) (`@<clone>/FEEDBACK.md`) only on a machine whose work may be described there; `cloud/memory.sh` imports both on Claude Code on the web.

- Improve this collection as you use it: when one of its skills, ways or rules gets something wrong or lacks what the work needed, or the owner corrects how you worked in a way likely to recur in other repos, open a PR on the repo that holds this file (branch `claude/<slug>`), written generic, saying what you hit, the evidence and the smallest change.
  It waits for the owner's review and is never merged by an agent; the current work carries on with a local workaround meanwhile.
- When anything of this collection refuses, slows or misleads the work, note it before working around it: write what got in the way and the workaround to a file with the Write tool, then run `<clone>/bin/friction note --file <file> --part <its name>`.
  The note is posted on this collection's tracker, which may be public: generic words only, no repo name, path, data or secret (the script refuses what it can tell).
  A silent workaround hides the defect from the owner.
