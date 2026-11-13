#!/usr/bin/env bash
# Posts a review verdict on a PR as a marker comment, with the reviewers' raw output, so a merge can be checked
# against a posted verdict instead of one the author retells (cloud/hooks/merge-guard.py reads it).
#
# Usage: verdict.sh <pr> --tier routine|standard|sensitive --result pass|fail \
#          --reviewers "<names>" --reviewed <sha> --file <reviewer output> [--dry-run]
#   Run it from a clone of the PR's repo (git 2.38 or later): it reads the tier from the PR head's paths.
#   --tier may be higher than tier.sh gives for the PR head's paths, never lower.
#   --reviewed is the commit the reviewers read (required for standard and sensitive): the PR's head must be it,
#   or differ from it only by clean merges of the default branch (each merge's tree is what
#   `git merge-tree --write-tree` gives for its parents), so a commit nobody reviewed refuses the verdict.
#   --tier routine needs no reviewer: --reviewers, --reviewed and --file are optional, --result defaults to pass,
#   the comment says the tier needs gates only, and the session that wrote the change may run it, since the
#   paths decide the tier.
#
# Posts `🤖 Review: <result> (<tier> tier)` with the marker
#   <!-- loadout:review sha=<head> state=success|failure tier=<tier> reviewed=<sha> -->
# then the head, the reviewed commit, the reviewers and the raw output under <details> (clipped with a note to
# fit GitHub's comment limit); reads the comment back and fails (exit 1) when its body is not the one sent.
#
# Honest limits: the record guards against forgetting, not against a dishonest author. The same account that
# writes the change posts the verdict; the script cannot tell a real reviewer's output from a typed one, only
# keep the output beside the verdict where the owner can read it.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
usage='usage: verdict.sh <pr> --tier routine|standard|sensitive --result pass|fail --reviewers "<names>" --reviewed <sha> --file <reviewer output> [--dry-run]'
pr='' tier='' result='' reviewers='' reviewed='' file=''
while [ $# -gt 0 ]; do
  case "$1" in
    --tier) tier=${2:-}; shift 2 ;;
    --result) result=${2:-}; shift 2 ;;
    --reviewers) reviewers=${2:-}; shift 2 ;;
    --reviewed) reviewed=${2:-}; shift 2 ;;
    --file) file=${2:-}; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -*) echo "$usage" >&2; exit 2 ;;
    *) [ -z "$pr" ] || { echo "$usage" >&2; exit 2; }; pr=$1; shift ;;
  esac
done
# shellcheck source=lib.sh
. "$here/lib.sh"

rank() { case "$1" in routine) echo 0 ;; standard) echo 1 ;; sensitive) echo 2 ;; *) echo 9 ;; esac; }
[[ "$pr" =~ ^[0-9]+$ ]] || die "the first argument is the PR number. $usage"
case "$tier" in routine | standard | sensitive) ;; *) die "--tier is routine, standard or sensitive. $usage" ;; esac
[ "$tier" != routine ] || result=${result:-pass}
case "$result" in pass | fail) ;; *) die "--result is pass or fail. $usage" ;; esac
if [ "$tier" != routine ]; then
  [ -n "$reviewers" ] || die "--reviewers names who reviewed (a $tier change needs a reviewer)."
  [ -n "$file" ] && [ -s "$file" ] || die "--file is the reviewers' raw output, and it must not be empty (a $tier change needs a reviewer)."
  [[ "$reviewed" =~ ^[0-9a-f]{40}$ ]] || die "--reviewed is the full sha of the commit the reviewers read (a $tier change needs it)."
else
  [ -z "$file" ] || [ -r "$file" ] || die "cannot read --file $file"
  [ -z "$reviewed" ] || [[ "$reviewed" =~ ^[0-9a-f]{40}$ ]] || die "--reviewed is a full sha"
fi

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || die "run verdict.sh from a clone of $REPO"
head=$(pr_head "$pr")
default=$(default_branch)
git fetch -q origin "$default" || die "cannot fetch origin/$default, which the tier and the merge check read"
for c in "$head" ${reviewed:+"$reviewed"}; do
  git cat-file -e "$c^{commit}" 2>/dev/null || git fetch -q origin "$c" 2>/dev/null ||
    die "commit $c is not in this clone and cannot be fetched"
done

paths=$(bash "$here/tier.sh" --base "origin/$default" --head "$head") || die "tier.sh could not read PR $pr's paths"
computed=${paths%%$'\n'*}
[ "$(rank "$tier")" -ge "$(rank "$computed")" ] ||
  die "PR $pr's paths make it $computed, so --tier $tier is too low:
$paths"

reviewed=${reviewed:-$head}
merged_note=''
if [ "$reviewed" != "$head" ]; then
  c=$head n=0
  while [ "$c" != "$reviewed" ]; do
    n=$((n + 1))
    read -r -a parents <<<"$(git rev-list --parents -n 1 "$c")"
    [ "${#parents[@]}" = 3 ] && [ "$n" -le 20 ] ||
      die "PR $pr's head $head holds commit $c, which nobody reviewed (only clean merges of $default may follow $reviewed): review the head."
    git merge-base --is-ancestor "${parents[2]}" "origin/$default" ||
      die "PR $pr's head merges ${parents[2]}, which is not on $default: review the head."
    tree=$(git merge-tree --write-tree "${parents[1]}" "${parents[2]}" 2>/dev/null | head -n 1) && [ -n "$tree" ] ||
      die "merging $default into ${parents[1]} conflicts, so merge $c holds changes nobody reviewed: review the head."
    [ "$tree" = "$(git rev-parse "$c^{tree}")" ] ||
      die "merge $c is not the clean merge of its parents (its tree differs), so it holds changes nobody reviewed: review the head."
    c=${parents[1]}
  done
  merged_note=" (the head differs from it only by clean merges of $default)"
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
state=failure
[ "$result" = pass ] && state=success
lines=(--line "- Head commit: \`$head\`" --line "- Reviewed commit: \`$reviewed\`$merged_note"
  --line "- Tier from the paths: $computed" --line "- Reviewers: ${reviewers:-none}")
[ "$tier" != routine ] || lines+=(--line "- The routine tier needs gates only: no reviewer was required.")
build_record --kind review --sha "$head" --state "$state" --tier "$tier" --reviewed "$reviewed" \
  --title "🤖 Review: $result ($tier tier)" "${lines[@]}" ${file:+--file "$file"} \
  --details "Reviewer output (raw)" >"$tmp/body.md"
url=$(post_record "$pr" "$tmp/body.md") || exit 1
echo "verdict: PR $pr, head $head: review $result ($tier tier)${url:+, $url}"
