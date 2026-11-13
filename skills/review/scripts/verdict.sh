#!/usr/bin/env bash
# Posts a review verdict on a PR, with the reviewers' raw output, and records it on the PR's head commit as the
# GitHub commit status `loadout/review`, so a merge can be checked against a posted verdict instead of one the
# author retells (cloud/hooks/merge-guard.py reads it).
#
# Usage: verdict.sh <pr> --tier routine|standard|sensitive --result pass|fail \
#          --reviewers "<names>" --file <reviewer output> [--dry-run]
#   --tier routine needs no reviewer: --reviewers and --file are optional, --result defaults to pass, and the
#   comment says the tier needs gates only.
#
# 1. Reads the PR's head commit now; the verdict names it, and the status goes on it, so a later push leaves the
#    new head without a verdict.
# 2. Posts one comment that starts with `🤖 Review`, naming the tier, result, reviewers and head, with the raw
#    output under <details> (clipped with a note when the comment would pass GitHub's size limit).
# 3. Reads the comment back and fails (exit 1, no status) when its body is not the one sent.
# 4. Posts `loadout/review`: success for pass, failure for fail, linking the comment.
#
# Honest limits: the status guards against forgetting, not against a dishonest author. The same account that
# writes the change posts the verdict; the script cannot tell a real reviewer's output from a typed one, only
# keep the output beside the verdict where the owner can read it.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
usage='usage: verdict.sh <pr> --tier routine|standard|sensitive --result pass|fail --reviewers "<names>" --file <reviewer output> [--dry-run]'
pr='' tier='' result='' reviewers='' file=''
while [ $# -gt 0 ]; do
  case "$1" in
    --tier) tier=${2:-}; shift 2 ;;
    --result) result=${2:-}; shift 2 ;;
    --reviewers) reviewers=${2:-}; shift 2 ;;
    --file) file=${2:-}; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -*) echo "$usage" >&2; exit 2 ;;
    *) [ -z "$pr" ] || { echo "$usage" >&2; exit 2; }; pr=$1; shift ;;
  esac
done
# shellcheck source=lib.sh
. "$here/lib.sh"

[[ "$pr" =~ ^[0-9]+$ ]] || die "the first argument is the PR number. $usage"
case "$tier" in routine | standard | sensitive) ;; *) die "--tier is routine, standard or sensitive. $usage" ;; esac
[ "$tier" != routine ] || result=${result:-pass}
case "$result" in pass | fail) ;; *) die "--result is pass or fail. $usage" ;; esac
if [ "$tier" != routine ]; then
  [ -n "$reviewers" ] || die "--reviewers names who reviewed (a $tier change needs a reviewer)."
  [ -n "$file" ] && [ -s "$file" ] || die "--file is the reviewers' raw output, and it must not be empty (a $tier change needs a reviewer)."
elif [ -n "$file" ]; then
  [ -r "$file" ] || die "cannot read --file $file"
fi

head=$(gh_get "repos/$REPO/pulls/$pr" --jq '.head.sha') || die "cannot read PR $pr in $REPO"
[[ "$head" =~ ^[0-9a-f]{40}$ ]] || die "PR $pr in $REPO has no head commit I can read (got '$head')"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
body=$tmp/body.md
python3 - "$tier" "$result" "${reviewers:-none}" "$head" "${file:-}" "$COMMENT_MAX" >"$body" <<'EOF'
import re, sys
tier, result, reviewers, head, path, limit = sys.argv[1:7]
limit = int(limit)
raw = open(path, encoding="utf-8", errors="replace").read() if path else ""
lines = [
    f"🤖 Review: {result} ({tier} tier)",
    "",
    f"- Head commit: `{head}`",
    f"- Reviewers: {reviewers}",
]
if tier == "routine":
    lines.append("- The routine tier needs gates only: no reviewer was required.")
head_text = "\n".join(lines) + "\n"
if not raw.strip():
    sys.stdout.write(head_text)
    sys.exit()
fence = "```"
while fence in raw:
    fence += "`"
def body(text, note=""):
    return (head_text + "\n<details><summary>Reviewer output (raw)</summary>\n\n"
            + note + fence + "text\n" + text + ("" if text.endswith("\n") else "\n") + fence + "\n\n</details>\n")
out = body(raw)
if len(out) > limit:
    keep = len(raw)
    while True:
        note = f"Clipped to fit GitHub's comment size: the first {keep} of {len(raw)} characters.\n\n"
        out = body(raw[:keep], note)
        if len(out) <= limit:
            break
        keep = max(0, keep - (len(out) - limit))
sys.stdout.write(out)
EOF

if [ "$DRY_RUN" = 1 ]; then
  gh_write -X POST "repos/$REPO/issues/$pr/comments" -F "body=@$body" >/dev/null
  echo "dry-run: comment body follows" >&2
  cat "$body" >&2
  url=
else
  sent=$(gh api -X POST "repos/$REPO/issues/$pr/comments" -F "body=@$body") || die "posting the verdict comment on PR $pr failed"
  id=$(jq -r '.id // empty' <<<"$sent")
  [ -n "$id" ] || die "GitHub answered the comment post without an id: $sent"
  url=$(jq -r '.html_url // empty' <<<"$sent")
  gh_get "repos/$REPO/issues/comments/$id" >"$tmp/back.json" || die "cannot read back comment $id"
  python3 - "$tmp/back.json" "$body" <<'EOF' || die "comment $id on PR $pr does not hold the body that was sent (read back above); no status recorded. Fix or delete it."
import json, sys
back = json.load(open(sys.argv[1])).get("body") or ""
sent = open(sys.argv[2], encoding="utf-8").read()
norm = lambda s: s.replace("\r\n", "\n").rstrip("\n")
if norm(back) != norm(sent):
    sys.stderr.write(back[:2000] + "\n")
    sys.exit(1)
EOF
fi

state=failure
[ "$result" = pass ] && state=success
post_status "$head" loadout/review "$state" "$tier review: $result by ${reviewers:-none}" "$url" ||
  die "the comment is posted, but recording loadout/review on $head failed"
echo "verdict: PR $pr, head $head: loadout/review $state ($tier tier)${url:+, $url}"
