# Portable documents

How a reusable document (a skill, a way, a template, a script's header) stays usable by whoever adopts it next.
A reusable document is read in repos its author never saw, so it carries the general claim and nothing of the day it was written.

## Roles, not instances

- Name the role: `<owner>` for the account, `<repo>` for the repository, "the target repo" for the one being worked on.
- Derive the instance value at run time where a command needs it: `git remote get-url origin` (not `gh repo view`, whose GraphQL call some proxies refuse).
- Examples are invented (`example-owner/example-repo`); a real neighbour's name reads as a dependency on it.
- A path names its anchor (`~/.claude/`, the repo root), never one machine's home directory.

## History belongs to git

- The history behind a line is the date it was learned, the issue that proved it, the repo it was measured on.
- It goes in the commit and the PR body; `git log -S '<phrase>'` and `git blame` reach it from the line.
- In the document it is sediment from the day it lands: true once, stale soon, and noise to every reader who wasn't there.
- Keep the claim and its reason; move the instance to the PR.

Illustrative rewrites:

| Instance (goes in the PR) | Portable (stays in the document) |
|---|---|
| Learned on `<date>` when `<repo>` broke the cache. | An anonymous registry request is rate-limited; log in first. |
| Issue `#<n>` proved the retry is needed. | The first push after a token refresh can fail; retry once. |
| Measured on `<repo>`: 40 s to 6 s. | A cached image makes session start a download, not a build. |
| Run `gh pr list -R <real-owner>/<real-repo>`. | Run `gh pr list -R <owner>/<repo>`, with both from `git remote get-url origin`. |

## The guard

- A pre-commit hook fails a staged reusable file that names the owner's login, a sibling clone, a date, or an issue or PR number.
- Fixtures and a private mirror are exempt by path; nothing is exempt by line.
- [`../bin/check-generic.sh`](../bin/check-generic.sh) is a working guard: owner from the remote, siblings from the parent directory (as a path or `owner/name`), extra words from a deny file.
- A repo that acts on itself (builds, syncs, links its tracker) takes `<owner>/<repo>` from its origin remote, so a fork works against itself; history (ledgers, changelogs, dated decisions) keeps its facts.
  [`../cloud/githooks/check-portable.sh`](../cloud/githooks/check-portable.sh) guards it from outside the repo: run as the repo's pre-commit hook ([`../cloud/githooks/`](../cloud/githooks/pre-commit)), it fails a commit that adds the owner's login.
- Code follows the same rule for issue numbers ([`decisions.md § References`](decisions.md#references)).
