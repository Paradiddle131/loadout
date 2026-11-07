#!/usr/bin/env bash
# claim.sh <issue> [--wake <id>] [--session <url>] [--dry-run]: the skill's claim step.
# Adds `agent:claimed`, comments `🤖 claimed <timestamp> <wake id> [<session url>]`, re-reads the comments and yields
# to an earlier live claim of another wake id (same minute: the lower comment id wins), deleting
# only our comment; the label stays for the earlier wake.
# A claim is live while its latest `claimed`/`still on it` comment is under 3 hours old and no
# handoff comment (a line starting `handoff`, `## Handoff` or `🤖 Handoff`) follows it.
# Exit 0: claimed (prints the wake id); 2: another wake holds it (prints its id); 1: usage or API error.
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

set_dry_run "$@"
mapfile -d '' -t ARGS < <(strip_dry_run "$@")
ISSUE="" WAKE_ID="${WAKE_ID:-}" SESSION="${AUTOPILOT_SESSION_URL:-}"
i=0
while [ $i -lt ${#ARGS[@]} ]; do
  case "${ARGS[$i]}" in
    --wake) i=$((i + 1)); WAKE_ID="${ARGS[$i]}" ;;
    --session) i=$((i + 1)); SESSION="${ARGS[$i]}" ;;
    *) ISSUE="${ARGS[$i]}" ;;
  esac
  i=$((i + 1))
done
[[ "$ISSUE" =~ ^[0-9]+$ ]] || die "usage: claim.sh <issue> [--wake <id>] [--session <url>] [--dry-run]"
[ -n "$WAKE_ID" ] || WAKE_ID="$(new_wake_id)"

# The live claim among the issue's comments: "<timestamp> <wake id> <comment id>" or nothing.
# shellcheck disable=SC2016  # jq program
live_claim() {
  gh_get "repos/$REPO/issues/$ISSUE/comments?per_page=100" --jq '
    reduce .[] as $c (null;
      if ($c.body | test("^(🤖 )?(claimed|still on it) [0-9T:Z-]+ [0-9a-f]+"; "m")) then
        ($c.body | capture("^(?:🤖 )?(?:claimed|still on it) (?<ts>[0-9T:Z-]+) (?<id>[0-9a-f]+)"; "m")) + {cid: $c.id}
      elif ($c.body | test("^(🤖 |## )?handoff"; "im")) then null
      else . end)
    | if . then "\(.ts) \(.id) \(.cid)" else empty end'
}

is_live() { [ "$(age_s "$1")" -lt 10800 ]; }

existing="$(live_claim)"   # a failed read stops here: never claim blind
if [ -n "$existing" ]; then
  read -r ts id _ <<<"$existing"
  if is_live "$ts" && [ "$id" != "$WAKE_ID" ]; then
    echo "held by $id since $ts" >&2; echo "$id"; exit 2
  fi
fi

gh_write -X POST "repos/$REPO/issues/$ISSUE/labels" -f 'labels[]=agent:claimed' >/dev/null
stamp="$(now)"
mine="$(gh_write -X POST "repos/$REPO/issues/$ISSUE/comments" -f "body=🤖 claimed $stamp $WAKE_ID${SESSION:+ $SESSION}$FOOTER" --jq '.id')"
[ "$DRY_RUN" = 1 ] && { echo "$WAKE_ID"; exit 0; }

# Re-read: the earliest live `claimed` of another wake id wins; same minute, the lower comment id.
# Only claims after the latest handoff compete: a handoff ended every claim before it.
# shellcheck disable=SC2016  # jq program
winner="$(gh_get "repos/$REPO/issues/$ISSUE/comments?per_page=100" --jq '
  reduce .[] as $c ([];
    if ($c.body | test("^(🤖 )?claimed [0-9T:Z-]+ [0-9a-f]+"; "m")) then
      . + [($c.body | capture("^(?:🤖 )?claimed (?<ts>[0-9T:Z-]+) (?<id>[0-9a-f]+)"; "m")) + {cid: $c.id}]
    elif ($c.body | test("^(🤖 |## )?handoff"; "im")) then []
    else . end)
  | sort_by(.ts, .cid) | .[0] // empty | "\(.ts) \(.id) \(.cid)"')"
read -r wts wid _ <<<"${winner:-}"
if [ -n "${wid:-}" ] && [ "$wid" != "$WAKE_ID" ] && is_live "$wts"; then
  gh_write -X DELETE "repos/$REPO/issues/comments/$mine" >/dev/null
  echo "yielded to $wid (claimed $wts)" >&2; echo "$wid"; exit 2
fi
echo "claimed #$ISSUE $stamp $WAKE_ID" >&2
echo "$WAKE_ID"
