# GCP projects in cloud sessions: the $0 kit

A cloud environment that sets `GCP_PROJECT` hands its sessions a real GCP project, through a credential the egress proxy injects.
Unattended runs have nobody watching the bill, and a budget only sends an email hours later, so these layers keep the project at $0.00 without relying on an agent remembering a rule.
They hold for every repo; a repo's own docs add its free-path allowlist and cost check.

| Layer | Where | What it stops |
|---|---|---|
| IAM: a narrow credential | the project (owner, once) | everything that can raise spend: enabling APIs, IAM, quotas, reservations, paid products |
| Quotas | the project (owner, once) | BigQuery's daily query bytes, set inside the free tier |
| The guard hook | `guard.py`, a `PreToolUse` hook on Bash registered by the cloud plugin's `hooks/hooks.json` | the same commands before they run, with a reason that tells the agent what to do instead |
| Tool defaults | `status.sh` writes `~/.bigqueryrc` | any `bq query` above the byte cap (BigQuery refuses it unbilled) |
| Session context | `status.sh`, run by `cloud/hooks/session-start.sh` | blind sessions: each one starts with the month-to-date cost, the cap, and any loose fence |
| The rule | `cloud/CLAUDE.md`, GCP | what the hooks can't see (code calling client libraries) |
| Kill switch (optional) | the repo's infrastructure | a runaway the other layers missed, at a threshold far above the first cent |

## The narrow credential

The proxy's credential is a service account; give it no role that can move a fence.
Owner or Editor can enable any API, raise a quota, buy BigQuery capacity or grant itself more, so the project's owner keeps those powers and uses them from their own shell (Cloud Shell is free).

A starting set for a BigQuery-first lab, granted on the project:

- `roles/viewer`: read everything, so plans and status checks work.
- `roles/bigquery.jobUser` and `roles/bigquery.dataEditor`: run queries, create datasets and tables.
- `roles/serviceusage.serviceUsageConsumer`: call the enabled APIs.

Add a product's role (Cloud Run, Firestore, Artifact Registry) when the work reaches it; never `roles/owner`, `roles/editor`, `roles/serviceusage.serviceUsageAdmin`, `roles/resourcemanager.projectIamAdmin`, `roles/iam.serviceAccountKeyAdmin` or a quota or billing role.
Check the fences with `testIamPermissions` (`status.sh` does each session); IAM changes take a few minutes to apply, so a check right after one can still show the old answer.
Never test a fence by attempting what it forbids: if the change has not applied yet, the attempt succeeds and you have done the forbidden thing.

Turn off APIs the work doesn't use yet; enabling an API is the owner's step from then on.
BigQuery's reservation API (capacity is billed by the slot-hour) is the one to turn off first; Google's "Google Cloud APIs" bundle (`cloudapis.googleapis.com`) keeps it and others on, so disable the bundle first.

## The guard

`guard.py` reads each Bash command before it runs and refuses enabling an API, IAM policy changes, quota, billing and budget changes, service account keys, writes on paid-only products, buckets outside Cloud Storage's free regions, BigQuery reservations and commitments, streaming inserts (`bq insert`, no free tier), `bq query` above the cap, and the same writes sent with `curl` to `*.googleapis.com`.
It parses shell words, so text that only mentions a command (an `echo`, an issue body, a heredoc written to a file) passes; a heredoc fed to a shell is checked as commands; a command it cannot parse that names GCP is refused.
It cannot see code calling Google's client libraries: IAM is the fence there.
The cap is `$GCP_MAX_BYTES_BILLED` (default 1 GiB per query).
Tests: `uvx --from pytest==8.4.2 pytest -q cloud/gcp/tests`.

## The kill switch

Budgets alert; they don't stop spend.
Google's documented stop is a budget that publishes to Pub/Sub and a small program that unlinks billing from the project, which shuts down every resource and may delete some, so set its threshold well above the first cent: the cents are for the alert and the session's stop, the switch is for a runaway.
It stays at $0.00 when built from Eventarc (Pub/Sub sources are free) and Cloud Workflows (about one internal step per notification, inside the 5,000 free steps a month) rather than a Cloud Run function, whose built image counts against Artifact Registry's free 0.5 GiB.
Notifications arrive several times a day and lag the spend by hours, so it limits a runaway rather than preventing one.
The repo declares it with its infrastructure; the owner applies it, since it needs the IAM this credential lacks.
