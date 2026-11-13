#!/usr/bin/env bash
# Shared by gate_stamp.sh and verdict.sh. Run them from the root (or any folder) of the repo whose change is
# being recorded. REST through `gh api` only (some proxies refuse GraphQL).
# DRY_RUN=1 (or --dry-run) runs every read and prints every write as the `gh api` call it would make.
#
# The records are GitHub commit statuses on the head commit (`loadout/gates`, `loadout/review`), which the
# cloud plugin's merge guard (cloud/hooks/merge-guard.py) reads before it lets a merge through.
# They guard against forgetting, not against a dishonest author: the same account that runs the gates and the
# review posts the statuses, and anyone holding that account can post `success` by hand.
set -euo pipefail

# owner/name of the repo, from `origin` unless REVIEW_REPO is set (https, ssh or a proxy's URL form).
origin_repo() {
  git remote get-url origin 2>/dev/null | sed -E 's#/+$##; s#\.git$##; s#^.*[:/]([^/:]+/[^/]+)$#\1#'
}
REPO="${REVIEW_REPO:-$(origin_repo || true)}"
DRY_RUN="${DRY_RUN:-0}"
# GitHub refuses a status description over 140 characters and a comment body over 65536.
STATUS_DESC_MAX=140
# shellcheck disable=SC2034  # used by verdict.sh
COMMENT_MAX=65536

die() { echo "error: $*" >&2; exit 2; }

[ -n "$REPO" ] || die "no origin remote; set REVIEW_REPO=owner/name"

# A read: always runs.
gh_get() { gh api "$@"; }

# A write: prints under DRY_RUN (and answers `{}`), else runs; the response goes to stdout.
gh_write() {
  if [ "$DRY_RUN" = 1 ]; then
    { printf 'dry-run: gh api'; printf ' %q' "$@"; printf '\n'; } >&2
    echo '{}'
  else
    gh api "$@"
  fi
}

# The first N characters of a string (characters, not bytes, so a multi-byte character is never split).
clip() { # <max> <text>
  python3 -c 'import sys; m = int(sys.argv[1]); t = sys.argv[2]; print(t if len(t) <= m else t[: m - 1] + "…")' "$1" "$2"
}

# Records <state> under <context> on <sha>, with <description> (clipped) and an optional <target_url>.
post_status() { # <sha> <context> <state> <description> [target_url]
  local args=(-X POST "repos/$REPO/statuses/$1" -f "context=$2" -f "state=$3" -f "description=$(clip "$STATUS_DESC_MAX" "$4")")
  [ -z "${5:-}" ] || args+=(-f "target_url=$5")
  gh_write "${args[@]}" --jq '.state // empty' >/dev/null
}
