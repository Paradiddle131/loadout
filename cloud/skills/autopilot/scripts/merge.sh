#!/usr/bin/env bash
# merge.sh <pr> [--dry-run]: the skill's merge step.
# Squash-merges the PR at the head it read, and only when every condition holds:
# open, not a draft, based on the default branch, no hold (`needs-owner`, `needs-review`,
# `needs-local-verify`, $AUTOPILOT_HOLD_LABELS, a `[speculative` title), commit statuses
# `loadout/gates` and `loadout/review` both `success` on that head, and the head not behind the base.
# The merge names the head sha, so a push after the reads makes GitHub refuse it.
# Prints the case on stdout. Exit 0: `merged` (and the merge sha on stderr); 3: `held`, `draft`,
# `stacked` or `unreviewed` (the reason on stderr; nothing written); 4: `behind` (merge the base
# in, push, gate and review the new head); 1: usage or API error, or GitHub refused the merge.
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

set_dry_run "$@"
mapfile -d '' -t ARGS < <(strip_dry_run "$@")
PR="${ARGS[0]:-}"
[[ "$PR" =~ ^[0-9]+$ ]] && [ ${#ARGS[@]} -eq 1 ] || die "usage: merge.sh <pr> [--dry-run]"
HOLDS="needs-owner needs-review needs-local-verify ${AUTOPILOT_HOLD_LABELS:-}"

stop() { echo "$2" >&2; echo "$1"; exit "${3:-3}"; }

pr="$(gh_get "repos/$REPO/pulls/$PR")"   # a failed read stops here
[ "$(jq -r '.number // empty' <<<"$pr")" = "$PR" ] || die "the read of PR #$PR is not the PR; nothing merged"
[ "$(jq -r '.state' <<<"$pr")" = open ] || die "PR #$PR is not open"
HEAD="$(jq -r '.head.sha // empty' <<<"$pr")"
[[ "$HEAD" =~ ^[0-9a-f]{40}$ ]] || die "PR #$PR has no head sha; nothing merged"
[ "$(jq -r '.draft' <<<"$pr")" = false ] || stop draft "PR #$PR is a draft: mark it ready first"
base="$(jq -r '.base.ref' <<<"$pr")"
[ "$base" = "$BASE" ] || stop stacked "PR #$PR targets $base: it merges after its base, retargeted to $BASE"
case "$(jq -r '.title' <<<"$pr")" in
  "[speculative"*) stop held "PR #$PR is speculative: it waits for its packet's answer" ;;
esac
# shellcheck disable=SC2016  # jq program
hold="$(jq -r --arg holds "$HOLDS" '($holds | split(" ") | map(select(. != ""))) as $h
  | [.labels[].name | select(. as $l | $h | index([$l]))][0] // empty' <<<"$pr")"
[ -z "$hold" ] || stop held "PR #$PR carries $hold"

status() {   # the latest state of one commit status context on the head, or `missing`
  gh_get "repos/$REPO/commits/$HEAD/status?per_page=100" \
    --jq "[.statuses[] | select(.context == \"$1\") | .state][0] // \"missing\""
}
gates="$(status loadout/gates)"
review="$(status loadout/review)"
[ "$gates" = success ] && [ "$review" = success ] \
  || stop unreviewed "PR #$PR head ${HEAD:0:7}: loadout/gates $gates, loadout/review $review"

behind="$(gh_get "repos/$REPO/compare/$BASE...$HEAD" --jq '.behind_by')"
[[ "$behind" =~ ^[0-9]+$ ]] || die "could not compare PR #$PR with $BASE; nothing merged"
[ "$behind" -eq 0 ] || stop behind "PR #$PR is $behind commits behind $BASE: merge it in, then gate and review again" 4

out="$(gh_write -X PUT "repos/$REPO/pulls/$PR/merge" -f merge_method=squash -f "sha=$HEAD")" \
  || die "GitHub refused the merge of PR #$PR (the head moved or it is not mergeable); nothing merged"
if [ "$DRY_RUN" != 1 ]; then
  [ "$(jq -r '.merged // false' <<<"$out")" = true ] || die "the merge of PR #$PR answered no merge; check the PR"
  echo "merged PR #$PR as $(jq -r '.sha' <<<"$out")" >&2
fi
echo merged
