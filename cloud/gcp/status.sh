#!/usr/bin/env bash
# Every-session GCP status for a session whose environment names a project ($GCP_PROJECT), run by
# cloud/hooks/session-start.sh. Its stdout becomes session context, so every session, unattended
# ones included, starts knowing the project's month-to-date cost and whether its fences hold.
#   1. ~/.bigqueryrc: a default byte cap on every `bq query` ($GCP_MAX_BYTES_BILLED, default 1 GiB).
#   2. The PreToolUse guard (cloud/gcp/guard.py) is registered (the cloud plugin's hooks.json does it).
#   3. The session's credential lacks every fence-moving permission (asked with testIamPermissions).
#   4. Month-to-date cost after credits from the billing export ($GCP_BILLING_DATASET, default
#      billing_export), unknown while it has no rows for the month; above zero, the session is told
#      to stop GCP work and tell the owner.
# Read-only on GCP apart from one small query; always exits 0. See cloud/gcp/README.md.
set -u
project=${GCP_PROJECT:-}
[ -n "$project" ] && command -v bq >/dev/null || exit 0
here=$(cd "$(dirname "$0")" && pwd)
cap=${GCP_MAX_BYTES_BILLED:-1073741824}
dataset=${GCP_BILLING_DATASET:-billing_export}

printf -- '--project_id=%s\n[query]\n--use_legacy_sql=false\n--maximum_bytes_billed=%s\n' "$project" "$cap" > ~/.bigqueryrc

notes=()
grep -qs '"cloud@' ~/.claude/plugins/installed_plugins.json ||
  notes+=("the \$0 guard hook is not registered (the cloud plugin is not installed): run bash $(dirname "$here")/setup.sh <repo>")

fences='["serviceusage.services.enable","resourcemanager.projects.setIamPolicy","cloudquotas.quotas.update","bigquery.reservations.create","bigquery.capacityCommitments.create","iam.serviceAccountKeys.create","compute.instances.create"]'
held=$(curl -sS --max-time 20 -X POST -H 'content-type: application/json' \
  "https://cloudresourcemanager.googleapis.com/v1/projects/$project:testIamPermissions" \
  -d "{\"permissions\":$fences}" 2>/dev/null |
  python3 -c 'import json,sys; print(",".join(json.load(sys.stdin).get("permissions", [])))' 2>/dev/null)
[ -n "$held" ] && notes+=("the credential holds fence permissions ($held): narrow it (cloud/gcp/README.md)")

table=$(timeout 30 bq ls --format=json --max_results=100 "$project:$dataset" 2>/dev/null |
  python3 -c 'import json,sys; print(next((t["tableReference"]["tableId"] for t in json.load(sys.stdin) if t["tableReference"]["tableId"].startswith("gcp_billing_export_v1_")), ""))' 2>/dev/null)
if [ -z "$table" ]; then
  cost="unknown (no billing export table yet in $dataset; the first rows take about a day)"
else
  cost=$(timeout 40 bq query --quiet --format=csv --maximum_bytes_billed=104857600 \
    "SELECT IF(COUNT(*) = 0, 'none', FORMAT('%.2f', SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)))) FROM \`$project.$dataset.$table\` WHERE invoice.month = FORMAT_DATE('%Y%m', CURRENT_DATE()) AND project.id = '$project'" 2>/dev/null | tail -1)
  # No rows is the export's lag, not $0.00: nothing is proven until its first rows for the month land.
  case "$cost" in
    none) cost="unknown (no billing export rows for $project this month yet; the first rows take about a day)" ;;
    -[0-9]*.[0-9][0-9] | [0-9]*.[0-9][0-9]) ;;
    *) cost="unknown (the cost query failed)" ;;
  esac
fi

case "$cost" in unknown*) shown=$cost ;; *) shown="\$$cost" ;; esac
echo "gcp: $project is a \$0.00 lab (cloud/CLAUDE.md, GCP): month to date $shown, the export lagging hours; bq queries capped at $cap bytes."
case "$cost" in
  0.00 | -* | unknown*) ;;
  *) echo "gcp: STOP: the project has billed \$$cost this month: do no GCP work this session and put the cost first in the handoff." ;;
esac
for n in "${notes[@]}"; do echo "gcp: $n"; done
exit 0
