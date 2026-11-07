#!/usr/bin/env bash
# file_issue.sh [--epic <n>] --title "<imperative>" --context "<decisions, files>" --do "<what>"
#               --acceptance "<command or test>" [--blocked-by "<#n or none>"] [--label <l>]...
#               [--before <issue>] [--dry-run]
# The skill's issue template: a sub-issue of its epic, placed before
# <issue> when given (else last); with no --epic, a plain issue. Prints the new issue's number.
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

set_dry_run "$@"
mapfile -d '' -t ARGS < <(strip_dry_run "$@")
EPIC="" TITLE="" CONTEXT="" DO="" ACCEPT="" BLOCKED="none" BEFORE="" LABELS=()
i=0
while [ $i -lt ${#ARGS[@]} ]; do
  key="${ARGS[$i]}"; i=$((i + 1)); val="${ARGS[$i]:-}"
  case "$key" in
    --epic) EPIC="$val" ;; --title) TITLE="$val" ;; --context) CONTEXT="$val" ;;
    --do) DO="$val" ;; --acceptance) ACCEPT="$val" ;; --blocked-by) BLOCKED="$val" ;;
    --label) LABELS+=("$val") ;; --before) BEFORE="$val" ;;
    *) die "unknown argument $key" ;;
  esac
  i=$((i + 1))
done
{ [ -z "$EPIC" ] || [[ "$EPIC" =~ ^[0-9]+$ ]]; } && [ -n "$TITLE" ] && [ -n "$CONTEXT" ] && [ -n "$DO" ] && [ -n "$ACCEPT" ] \
  || die 'usage: file_issue.sh [--epic <n>] --title ... --context ... --do ... --acceptance ... [--blocked-by ...] [--label l]... [--before <issue>] [--dry-run]'

bullets() { printf '%s\n' "$1" | sed 's/^/- /'; }
BODY="## Context
$(bullets "$CONTEXT")

## Do
$(bullets "$DO")

## Acceptance
$(bullets "$ACCEPT")

## Blocked by
$(bullets "$BLOCKED")$FOOTER"

args=(-f "title=$TITLE" -f "body=$BODY")
for l in "${LABELS[@]+"${LABELS[@]}"}"; do args+=(-f "labels[]=$l"); done
[ "$DRY_RUN" = 1 ] && printf '%s\n---\n' "$BODY" >&2
created="$(gh_write -X POST "repos/$REPO/issues" "${args[@]}")"
number="$(jq -r '.number // "<new>"' <<<"$created")"
id="$(jq -r '.id // "<new-id>"' <<<"$created")"
[ -n "$EPIC" ] || { echo "$number"; exit 0; }
gh_write -X POST "repos/$REPO/issues/$EPIC/sub_issues" -F "sub_issue_id=$id" >/dev/null
if [ -n "$BEFORE" ]; then
  before_id="$(gh_get "repos/$REPO/issues/$BEFORE" --jq '.id')"
  gh_write -X PATCH "repos/$REPO/issues/$EPIC/sub_issues/priority" -F "sub_issue_id=$id" -F "before_id=$before_id" >/dev/null
fi
echo "$number"
