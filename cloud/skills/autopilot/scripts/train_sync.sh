#!/usr/bin/env bash
# train_sync.sh [--dry-run]: the skill's "Sync the train" step (train delivery only).
# Fetches the base branch and the train, reads the newest train PR and acts on its case; prints the case name
# (`open`, `open-moved` when the base was merged in, `merged`, `merged-rebuilt`, `closed`, `none`) on
# stdout and exits 0. Exit 3: a merge or cherry-pick conflict (aborted; the wake comments it and
# does an upkeep-only wake). Exit 1: a refused push or an API error (the wake redoes the step).
# Run from the repo root. Under --dry-run the fetches and reads run; checkouts, merges and pushes print.
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
set_dry_run "$@"

git fetch origin "$BASE" >/dev/null 2>&1
if git fetch origin "$TRAIN" >/dev/null 2>&1; then T="$(git rev-parse "origin/$TRAIN")"; else T=""; fi
MAIN="$(git rev-parse "origin/$BASE")"
PR="$(train_pr)"
state="$(jq -r '.state // "none"' <<<"$PR")"
merged_at="$(jq -r '.merged_at // empty' <<<"$PR")"
M="$(jq -r '.head.sha // empty' <<<"$PR")"
number="$(jq -r '.number // empty' <<<"$PR")"

push_lease() {  # push with the lease on T (plain -u push when the branch is absent)
  if [ -n "$T" ]; then
    git_write push "--force-with-lease=$TRAIN:$T" -u origin "$TRAIN"
  else
    git_write push -u origin "$TRAIN"
  fi
}

case_open() {
  git_write checkout -B "$TRAIN" "origin/$TRAIN"
  if git merge-base --is-ancestor "$MAIN" "$T"; then echo open; return; fi
  if ! git_write merge --no-edit "origin/$BASE"; then
    git merge --abort || true
    echo "conflict merging origin/$BASE into $TRAIN (train PR #$number)" >&2; exit 3
  fi
  git_write push -u origin "$TRAIN"
  echo open-moved
}

if [ "$state" = open ]; then
  case_open
elif [ "$state" = closed ] && [ -n "$merged_at" ]; then
  if [ -n "$T" ] && [ "$T" != "$MAIN" ] && git merge-base --is-ancestor "$MAIN" "$T"; then
    case_open | sed 's/^open/merged-rebuilt/'   # another wake rebuilt the train already
  else
    git_write checkout -B "$TRAIN" "origin/$BASE"
    picks=()
    if [ -n "$T" ] && [ -n "$M" ]; then   # the train's commits past the merged head, not yet on the base
      mapfile -t picks < <(git rev-list --reverse --no-merges "$M..$T" "^$MAIN")
    fi
    if [ ${#picks[@]} -gt 0 ] && ! git_write cherry-pick "${picks[@]}"; then
      git cherry-pick --abort || true
      echo "conflict cherry-picking $M..$T onto origin/$BASE (merged PR #$number)" >&2; exit 3
    fi
    push_lease
    echo merged
  fi
elif [ "$state" = closed ]; then
  git_write checkout -B "$TRAIN" "origin/$BASE"
  push_lease
  echo closed   # the wake removes `in-train` from the PR's issues and comments on each
else
  git_write checkout -B "$TRAIN" "origin/$BASE"
  push_lease
  echo none
fi
