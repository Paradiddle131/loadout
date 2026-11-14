#!/usr/bin/env bash
# merge.sh <pr> [--dry-run]: the skill's merge step.
# Squash-merges the PR at the head it read, and only when every condition holds: open, not a draft,
# based on the default branch, no hold (among the PR's labels, in any case: `needs-owner`, `needs-review`,
# `needs-local-verify`, `owner-merges`, $AUTOPILOT_HOLD_LABELS; a `[speculative` title;
# AUTOPILOT_MERGE_POLICY=owner), no commit of
# another open agent PR among its own (a stack aimed at the default branch carries held work), the
# merge guard's `--check` passing (the gates and review records on the head; the guard owns that
# rule), and the head not behind the base.
# The merge names the head sha, so a push after the reads makes GitHub refuse it.
# Also held: the latest review of any owner, member or collaborator requests changes (or the reviews cannot
# be read, paged by hand); the default
# branch is the one the PR read names. Prints the case on stdout. Exit 0: `merged` (the merge sha on
# stderr); 3: `held`, `draft`, `stacked`, `carries`, `unreviewed` or `moved` (the head moved between
# the reads and the guard's check; the reason on stderr; nothing written); 4: `behind` (merge
# the base in, push, stamp the gates and the verdict again); 1: usage or API error, or a refused merge.
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

set_dry_run "$@"
mapfile -d '' -t ARGS < <(strip_dry_run "$@")
PR="${ARGS[0]:-}"
[[ "$PR" =~ ^[0-9]+$ ]] && [ ${#ARGS[@]} -eq 1 ] || die "usage: merge.sh <pr> [--dry-run]"
HOLDS="needs-owner needs-review needs-local-verify owner-merges ${AUTOPILOT_HOLD_LABELS:-}"
GUARD="${AUTOPILOT_MERGE_GUARD:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)/cloud/hooks/merge-guard.py}"

stop() { echo "$2" >&2; echo "$1"; exit "${3:-3}"; }

[ "${AUTOPILOT_MERGE_POLICY:-}" != owner ] || stop held "the merge policy leaves the merge to the owner"
pr="$(gh_get "repos/$REPO/pulls/$PR")"   # a failed read stops here
[ "$(jq -r '.number // empty' <<<"$pr")" = "$PR" ] || die "the read of PR #$PR is not the PR; nothing merged"
[ "$(jq -r '.state' <<<"$pr")" = open ] || die "PR #$PR is not open"
HEAD="$(jq -r '.head.sha // empty' <<<"$pr")"
BASE="$(jq -r '.base.repo.default_branch // empty' <<<"$pr")"   # the repo's default branch, whatever its name
[ -n "$BASE" ] || die "the read of PR #$PR names no default branch; nothing merged"
[[ "$HEAD" =~ ^[0-9a-f]{40}$ ]] || die "PR #$PR has no head sha; nothing merged"
[ "$(jq -r '.draft' <<<"$pr")" = false ] || stop draft "PR #$PR is a draft: mark it ready first"
base="$(jq -r '.base.ref' <<<"$pr")"
[ "$base" = "$BASE" ] || stop stacked "PR #$PR targets $base: it merges after its base, retargeted to $BASE"
case "$(jq -r '.title' <<<"$pr")" in
  "[speculative"*) stop held "PR #$PR is speculative: it waits for its packet's answer" ;;
esac
# shellcheck disable=SC2016  # jq program
hold="$(jq -r --arg holds "$HOLDS" '($holds | split(" ") | map(select(. != "") | ascii_downcase)) as $h
  | [.labels[].name | select(ascii_downcase as $l | $h | index([$l]))][0] // empty' <<<"$pr")"
[ -z "$hold" ] || stop held "PR #$PR carries $hold"

# Another open agent PR whose commits are among this PR's: this PR would merge that work too.
mine="$(gh_get "repos/$REPO/pulls/$PR/commits?per_page=100" --jq '.[].sha')"
[ -n "$mine" ] || die "could not list the commits of PR #$PR; nothing merged"
others="$(gh_get "repos/$REPO/pulls?state=open&per_page=100" \
  --jq ".[] | select(.number != $PR and (.head.ref | startswith(\"claude/\"))) | .number")"
for other in $others; do
  theirs="$(gh_get "repos/$REPO/pulls/$other/commits?per_page=100" --jq '.[].sha')"
  [ -n "$theirs" ] || continue
  if grep -qxFf <(printf '%s\n' "$theirs") <<<"$mine"; then
    stop carries "PR #$PR holds commits of open PR #$other: it merges after that one, rebuilt on $BASE"
  fi
done

# Each owner's, member's or collaborator's latest verdict-bearing review: any one requesting changes holds
# the PR, and so does a failed read. Reviews are paged by hand (`--paginate` follows links proxies refuse).
pages="$(mktemp)"
for page in $(seq 1 30); do
  if ! got="$(gh_get "repos/$REPO/pulls/$PR/reviews?per_page=100&page=$page")" ||
    ! jq -e 'type == "array"' <<<"$got" >/dev/null; then
    rm -f "$pages"; stop held "PR #$PR: its reviews could not be read, so an owner's request for changes cannot be ruled out"
  fi
  printf '%s\n' "$got" >>"$pages"
  [ "$(jq length <<<"$got")" -ge 100 ] || break
  [ "$page" -lt 30 ] || { rm -f "$pages"; stop held "PR #$PR: it has more than 3000 reviews, so a request for changes cannot be ruled out"; }
done
# shellcheck disable=SC2016  # jq program
requesting="$(jq -rs 'add |
  [.[] | select((.author_association | IN("OWNER", "MEMBER", "COLLABORATOR"))
    and (.state | IN("APPROVED", "CHANGES_REQUESTED", "DISMISSED")))]
  | group_by(.user.login // .user.id // "unknown") | map(last)
  | map(select(.state == "CHANGES_REQUESTED") | (.user.login // "a reviewer")) | join(", ")' "$pages")"
rm -f "$pages"
[ -z "$requesting" ] || stop held "PR #$PR: the latest review of $requesting requests changes"

# The records rule is the merge guard's: it prints the head it checked, or refuses with its reason.
err="$(mktemp)"; trap 'rm -f "$err"' EXIT
checked="$(python3 "$GUARD" --check "$REPO#$PR" 2>"$err")" \
  || stop unreviewed "PR #$PR: the merge guard refuses: $(cat "$err")"
[ "$checked" = "$HEAD" ] || stop moved "PR #$PR: the guard checked ${checked:0:7}, not the head read (${HEAD:0:7}); run again"

behind="$(gh_get "repos/$REPO/compare/$BASE...$HEAD" --jq '.behind_by')"
[[ "$behind" =~ ^[0-9]+$ ]] || die "could not compare PR #$PR with $BASE; nothing merged"
[ "$behind" -eq 0 ] || stop behind "PR #$PR is $behind commits behind $BASE: merge it in, then stamp the gates and the verdict again" 4

out="$(gh_write -X PUT "repos/$REPO/pulls/$PR/merge" -f merge_method=squash -f "sha=$HEAD")" \
  || die "GitHub refused the merge of PR #$PR (the head moved or it is not mergeable); nothing merged"
if [ "$DRY_RUN" != 1 ]; then
  [ "$(jq -r '.merged // false' <<<"$out")" = true ] || die "the merge of PR #$PR answered no merge; check the PR"
  echo "merged PR #$PR as $(jq -r '.sha' <<<"$out")" >&2
fi
echo merged
