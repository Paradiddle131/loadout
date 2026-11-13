#!/usr/bin/env bash
# Shared by gate_stamp.sh and verdict.sh. Run them from a clone of the repo whose PR is being recorded.
# REST through `gh api` only (some proxies refuse GraphQL and `--paginate`).
# DRY_RUN=1 (or --dry-run) runs every read and prints every write as the `gh api` call it would make.
#
# A record is a PR comment: its first line is for people (`🤖 Gates: success`, `🤖 Review: pass (standard
# tier)`), its second line is one machine line, an HTML comment the merge guard (cloud/hooks/merge-guard.py)
# parses:  <!-- loadout:<gates|review> sha=<head> state=success|failure [tier=<tier>] [reviewed=<sha>] -->
# The guard counts only the newest unedited marker of each kind from the repo's owner, a member or a
# collaborator, and only when it names the PR's current head.
# Records guard against forgetting, not against a dishonest author: the same account that writes the change
# posts them, and anyone holding that account can type a marker by hand.
set -euo pipefail

# owner/name of the repo, from `origin` unless REVIEW_REPO is set (https, ssh or a proxy's URL form).
origin_repo() {
  git remote get-url origin 2>/dev/null | sed -E 's#/+$##; s#\.git$##; s#^.*[:/]([^/:]+/[^/]+)$#\1#'
}
REPO="${REVIEW_REPO:-$(origin_repo || true)}"
DRY_RUN="${DRY_RUN:-0}"
LIB_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

die() { echo "error: $*" >&2; exit 2; }

[ -n "$REPO" ] || die "no origin remote; set REVIEW_REPO=owner/name"

# A read: always runs.
gh_get() { gh api "$@"; }

# The remote's default branch, from the local clone (origin/HEAD, else origin/main or origin/master).
default_branch() {
  local b
  b=$(git symbolic-ref --short -q refs/remotes/origin/HEAD 2>/dev/null || true)
  b=${b#origin/}
  if [ -z "$b" ]; then
    for c in main master; do git rev-parse -q --verify "refs/remotes/origin/$c" >/dev/null && { b=$c; break; }; done
  fi
  [ -n "$b" ] || die "cannot tell the remote's default branch: run \`git remote set-head origin --auto\`"
  echo "$b"
}

# The open PR whose head is the current branch, or nothing.
pr_for_branch() {
  local branch
  branch=$(git symbolic-ref --short -q HEAD) || return 0
  gh_get "repos/$REPO/pulls?head=${REPO%%/*}:$branch&state=open&per_page=1" --jq '.[0].number // empty'
}

# The PR's head sha, checked to be one.
pr_head() { # <pr>
  local head
  head=$(gh_get "repos/$REPO/pulls/$1" --jq '.head.sha') || die "cannot read PR $1 in $REPO"
  [[ "$head" =~ ^[0-9a-f]{40}$ ]] || die "PR $1 in $REPO has no head commit I can read (got '$head')"
  echo "$head"
}

# Builds a record's body on stdout (record.py has the format).
build_record() { python3 "$LIB_DIR/record.py" "$@"; }

# Posts <body file> as a comment on <pr>, reads it back and fails unless it holds that body; prints its URL.
# Under DRY_RUN it prints the call and the body instead.
post_record() { # <pr> <body file>
  local sent id back
  if [ "$DRY_RUN" = 1 ]; then
    { printf 'dry-run: gh api'; printf ' %q' -X POST "repos/$REPO/issues/$1/comments" -F "body=@$2"; printf '\n'
      echo "dry-run: comment body follows"; cat "$2"; } >&2
    return 0
  fi
  sent=$(gh api -X POST "repos/$REPO/issues/$1/comments" -F "body=@$2") || { echo "error: posting the record on PR $1 failed" >&2; return 1; }
  id=$(jq -r '.id // empty' <<<"$sent")
  [ -n "$id" ] || { echo "error: GitHub answered the comment post without an id: $sent" >&2; return 1; }
  back=$(mktemp)
  if ! gh_get "repos/$REPO/issues/comments/$id" >"$back"; then
    rm -f "$back"; echo "error: cannot read back comment $id" >&2; return 1
  fi
  if ! python3 "$LIB_DIR/record.py" same "$back" "$2"; then
    rm -f "$back"
    echo "error: comment $id on PR $1 does not hold the body that was sent; it does not count as a record. Delete it and run again." >&2
    return 1
  fi
  rm -f "$back"
  jq -r '.html_url // empty' <<<"$sent"
}
