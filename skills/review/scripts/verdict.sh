#!/usr/bin/env bash
# Posts a review verdict on a PR as a marker comment, with the reviewers' raw output, so a merge can be checked
# against a posted verdict instead of one the author retells (cloud/hooks/merge-guard.py reads it).
#
# Usage: verdict.sh <pr> --tier routine|standard|sensitive [--result pass|fail] \
#          --reviewers "<names>" --reviewed <sha> --file <verifier output> \
#          --cycle <n> --dupes <n> --nits <n> --lens "<name> model=<m> effort=<e> tokens=<n> seconds=<n> findings=<n>"... \
#          [--depth none|light|focused|full] [--owner "<the owner's words>"] [--repost] [--dry-run]
#   The round's plan is plan.py's, computed here from what GitHub names (the PR's head, its default branch and that
#   branch's tip, the PR's newest trusted review record) and REVIEW.md on that tip; plan.py's header has the rules and
#   the table of its inputs. --depth raises the plan's depth above the paths' floor, never below it, except under
#   --owner (light at least). Above routine, --reviewers must name every planned lens and finding-verifier, and each
#   planned lens's --lens effort must be at least its planned effort; extra lenses are accepted. The depth goes on the marker (depth=), and depth, floor and
#   planned on the round line.
#   --owner quotes the owner's instruction that set this round's depth (the review skill's owner override): --depth is
#   then taken as given (light, focused or full), below the floor too; the marker carries override=<depth>, which
#   the merge guard accepts below the floor, and the record quotes the words. A --repost carries the reposted
#   record's override= and takes no --owner.
#   --reviewers is every agent that ran in the round, the verifier included, split by commas or blanks.
#   --cycle (1 for a first review), --dupes (findings the verifier merged), --nits and one --lens per agent named in
#   --reviewers, no other, say what the round cost and found (required above routine; record.py review-round checks
#   them and refuses a malformed or missing value): model and effort as the agent call set them, tokens and seconds
#   as the harness printed the agent's usage when it returned (its total tokens; its duration in ms / 1000, rounded),
#   findings what it raised (for the verifier, what it kept). The must-fix count comes from the `Blocking:` line, and
#   the verifier's `Dismissals: re-ran <n>, promoted <m>` line adds both numbers: an output whose header lacks it, holds
#   two, or promotes more than it re-ran is refused.
#   They go on the record's round line (record.py has its shape; the merge guard ignores it) and in a table below.
#   In a clone of this collection (its default branch holds bin/check-review-version), the default branch's copy of
#   that check runs on the head first and refuses a review-path change whose version is not bumped.
#   --repost posts an earlier round's verdict again on a head that differs from --reviewed only by clean merges of the
#   default branch (the same --reviewers and output): no agent ran, so it takes no --cycle, --dupes, --nits or --lens,
#   and its round line says repost=1 with no usage, so an audit counts that round's cost once.
#   Run it from a clone of the PR's repo (git 2.38 or later): it reads the tier from the PR head's paths.
#   --tier may be higher than tier.sh gives for the PR head's paths, never lower.
#   --reviewed is the commit the reviewers read (required for standard and sensitive): the PR's head must be it,
#   or differ from it only by clean merges of the default branch (each merge's tree is what
#   `git merge-tree --write-tree` gives for its parents), so a commit nobody reviewed refuses the verdict.
#   --file (standard and sensitive) is finding-verifier's output, read as GitHub will store it (record.py § stored):
#   its header is its first lines (agents/finding-verifier.md § Output), and its first non-blank line
#   `VERDICT: PASS|FAIL <sha>` and the next, `Reviewed: <sha>` (a sha may be abbreviated to 7 or more characters),
#   must both name --reviewed, and the result is that VERDICT; a --result that differs is refused, and so is an
#   output with any other line, fenced or not and however indented, that starts with `VERDICT:`, `Reviewed:` or
#   `Blocking:`.
#   The line after `Reviewed:` must be the verifier's `Blocking:` line (blocking.py has the shape and its limits):
#   `none` for a PASS; for a FAIL the must-fix findings it lists, each heading a `###` block below, with a harm of two
#   words or more not made only of blocking.py's filler words. The lead acts on the line (the review skill).
#   A finding block's `- class: patched, not fixed (<settled id>)` line prints a notice on stderr, never a refusal.
#   --tier routine needs no reviewer: --reviewers, --reviewed and --file are optional, --result defaults to pass,
#   the comment says the tier needs gates only, and the session that wrote the change may run it, since the
#   paths decide the tier. It is accepted whenever the paths' depth floor is none (a routine change, or a standard
#   one a REVIEW.md line or `Depth: none` lets merge on gates alone), and records depth=none; such a change needs
#   no review record at all. Above routine the author may run it too, posting the verifier's output unedited.
#
# Posts `🤖 Review: <result> (<tier> tier)` with, on its second line,
#   the review marker (lib.sh has the format), with sha=<head>, state, tier=<tier>, reviewed=<sha> and depth=<d>
# then the head, the reviewed commit, the reviewers and the raw output under <details> (clipped with a note to
# fit GitHub's comment limit); reads the comment back and fails (exit 1) when its body is not the one sent.
#
# Honest limits: the record guards against forgetting, not against a dishonest author. The same account that
# writes the change posts the verdict; the script cannot tell a real reviewer's output from a typed one, only
# keep the output beside the verdict where the owner can read it.
set -euo pipefail
export LC_ALL=C # bash's [[:space:]] in the header patterns and blocking.py's blanks agree only in the C locale
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
usage='usage: verdict.sh <pr> --tier routine|standard|sensitive [--result pass|fail] --reviewers "<names>" --reviewed <sha> --file <verifier output> --cycle <n> --dupes <n> --nits <n> --lens "<name> model=<m> effort=<e> tokens=<n> seconds=<n> findings=<n>"... [--depth <d>] [--owner "<words>"] [--repost] [--dry-run]'
pr='' tier='' result='' reviewers='' reviewed='' file='' cycle='' dupes='' nits='' repost='' depth='' owner='' has_owner=''
lens=()
while [ $# -gt 0 ]; do
  case "$1" in
    --tier) tier=${2:-}; shift 2 ;;
    --result) result=${2:-}; shift 2 ;;
    --reviewers) reviewers=${2:-}; shift 2 ;;
    --reviewed) reviewed=${2:-}; shift 2 ;;
    --file) file=${2:-}; shift 2 ;;
    --cycle) cycle=${2:-}; shift 2 ;;
    --dupes) dupes=${2:-}; shift 2 ;;
    --nits) nits=${2:-}; shift 2 ;;
    --depth) depth=${2:-}; shift 2 ;;
    --owner) owner=${2:-}; has_owner=1; shift 2 ;;
    --lens) lens+=(--lens "${2:-}"); shift 2 ;;
    --repost) repost=--repost; shift ;;
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
case "$depth" in '' | none | light | focused | full) ;; *) die "--depth is none, light, focused or full. $usage" ;; esac
case "$result" in '' | pass | fail) ;; *) die "--result is pass or fail. $usage" ;; esac
if [ "$tier" != routine ]; then
  [ -n "$reviewers" ] || die "--reviewers names who reviewed (a $tier change needs a reviewer)."
  [ -n "$file" ] && [ -s "$file" ] || die "--file is the reviewers' raw output, and it must not be empty (a $tier change needs a reviewer)."
  [[ "$reviewed" =~ ^[0-9a-f]{40}$ ]] || die "--reviewed is the full sha of the commit the reviewers read (a $tier change needs it)."
  # The verifier's own lines decide the result and the commit (agents/finding-verifier.md § Output).
  # shellcheck disable=SC2016 # a literal backtick around the sha, not an expansion
  sha_re='`?([0-9a-f]{7,40})`?'
  verdict_re="^[[:space:]]*VERDICT: (PASS|FAIL) ${sha_re}[[:space:]]*\$"
  reviewed_re="^[[:space:]]*Reviewed: ${sha_re}[[:space:]]*\$"
  # blocking.py picks the header lines as it reads the rest: the first lines of the output as GitHub will store it,
  # refusing any other header-shaped line, so a dropped character or a decoy cannot make two readers pick different lines.
  why=$(mktemp)
  header=$(python3 "$here/blocking.py" --header "$file" 2>"$why") || {
    reason=$(cat "$why"); rm -f "$why"
    die "the verifier's output is refused: ${reason:-blocking.py cannot read --file $file} (agents/finding-verifier.md § Output); rerun the verifier."
  }
  rm -f "$why"
  verdict_line=$(sed -n 1p <<<"$header") reviewed_line=$(sed -n 2p <<<"$header")
  shape="--file is not finding-verifier's output: it needs a \`VERDICT: PASS|FAIL <sha>\` line and a \`Reviewed: <sha>\` line"
  [[ "$verdict_line" =~ $verdict_re ]] ||
    die "$shape (its verdict line: '${verdict_line:-none}')."
  said=$(tr '[:upper:]' '[:lower:]' <<<"${BASH_REMATCH[1]}") verdict_sha=${BASH_REMATCH[2]}
  [[ "$reviewed_line" =~ $reviewed_re ]] ||
    die "$shape (its reviewed line: '${reviewed_line:-none}')."
  for s in "$verdict_sha" "${BASH_REMATCH[1]}"; do
    [[ "$reviewed" == "$s"* ]] ||
      die "the verifier's output names commit $s, but --reviewed is $reviewed: record the verdict of the commit the verifier read."
  done
  [ -z "$result" ] || [ "$result" = "$said" ] ||
    die "--result $result contradicts the verifier's VERDICT line, which says $said: the record carries the verifier's verdict."
  result=$said
  # A must-fix blocks only by the harm it names: the verifier's `Blocking:` line lists each with its harm.
  why=$(mktemp)
  blocking=$(python3 "$here/blocking.py" "$file" 2>"$why") || {
    reason=$(cat "$why"); rm -f "$why"
    die "the verifier's output is refused: ${reason:-blocking.py failed} (agents/finding-verifier.md § Output); rerun the verifier."
  }
  rm -f "$why"
  [[ "$blocking" =~ ^[0-9]+$ ]] || die "blocking.py printed no count for --file $file"
  case "$said:$blocking" in
    fail:0) die "the verifier says FAIL but its \`Blocking:\` line lists no must-fix: a FAIL rests on a must-fix that names its harm; rerun the verifier." ;;
    pass:0 | fail:*) ;;
    *) die "the verifier says PASS but its \`Blocking:\` line lists $blocking must-fix finding(s); rerun the verifier." ;;
  esac
  # A re-raise of a settled must-fix's class: a notice, not a refusal (the review skill sends the item to its rethink).
  patched=$(python3 "$here/blocking.py" --patched "$file" 2>/dev/null || true)
  while read -r ids settled; do
    [ -n "$ids" ] || continue
    echo "notice: the verifier marks $ids patched, not fixed (it re-raises the class of settled $settled): send the item to its rethink (the review skill, step 5), not another patch." >&2
  done <<<"$patched"
  # The round's cost and shape: checked here, before anything is read from GitHub or posted.
  why=$(mktemp)
  round_out=$(python3 "$here/record.py" review-round --reviewers "$reviewers" --cycle "$cycle" --dupes "$dupes" \
    --nits "$nits" --mustfix "$blocking" --dismissals "$file" ${lens[@]+"${lens[@]}"} ${repost:+"$repost"} 2>"$why") || {
    reason=$(cat "$why"); rm -f "$why"
    die "${reason#record.py: }. $usage"
  }
  rm -f "$why"
else
  [ -z "$file" ] || [ -r "$file" ] || die "cannot read --file $file"
  [ -z "$reviewed" ] || [[ "$reviewed" =~ ^[0-9a-f]{40}$ ]] || die "--reviewed is a full sha"
  [ -z "$cycle$dupes$nits$repost" ] && [ ${#lens[@]} = 0 ] ||
    die "the routine tier runs no reviewer, so it takes no --cycle, --dupes, --nits, --lens or --repost."
  round_out=''
fi

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || die "run verdict.sh from a clone of $REPO"
head=$(pr_head "$pr")
default=$(pr_default_branch "$pr")
# The plan: plan.py reads its own inputs from GitHub and force-fetches the default branch's tip GitHub names.
plan_args=(record --pr "$pr" --tier "$tier" ${depth:+--depth "$depth"} ${has_owner:+--owner "$owner"})
if [ "$tier" = routine ]; then
  plan_args+=(--routine)
else
  plan_args+=(--reviewers "$reviewers" ${lens[@]+"${lens[@]}"} ${repost:+--repost --reviewed "$reviewed"})
fi
why=$(mktemp)
plan_out=$(python3 "$here/plan.py" ${plan_args[@]+"${plan_args[@]}"} 2>"$why") || {
  reason=$(cat "$why"); rm -f "$why"
  die "${reason#plan.py: }"
}
rm -f "$why"
plan_head='' plan_depth='' plan_pairs='' plan_override='' plan_record=''
while read -r k v; do
  case "$k" in
    head) plan_head=$v ;; depth) plan_depth=$v ;; pairs) plan_pairs=$v ;; override) plan_override=$v ;;
    record) plan_record=$v ;;
  esac
done <<<"$plan_out"
[ "$plan_head" = "$head" ] || die "PR $pr's head moved while the plan was read: run again"
for c in "$head" ${reviewed:+"$reviewed"}; do
  git cat-file -e "$c^{commit}" 2>/dev/null || git fetch -q origin "$c" 2>/dev/null ||
    die "commit $c is not in this clone and cannot be fetched"
done

paths=$(bash "$here/tier.sh" --base "origin/$default" --head "$head") || die "tier.sh could not read PR $pr's paths"
# In a clone of this collection, the review path's version bump is checked here too, so a commit made without the
# pre-commit hook (a file pushed through an API, a clone without core.hooksPath) cannot reach a record unbumped.
# The default branch decides that this is the collection and supplies the checker (with the reader it imports), so a
# head that deletes or rewrites the checker is checked all the same.
if git cat-file -e "origin/$default:bin/check-review-version" 2>/dev/null &&
  git cat-file -e "origin/$default:skills/review/SKILL.md" 2>/dev/null; then
  checker=$(mktemp -d)
  git archive "origin/$default" bin/check-review-version skills/review/scripts/record.py | tar -x -C "$checker" ||
    { rm -rf "$checker"; die "cannot read the review path's version check from origin/$default"; }
  bumped=$(python3 "$checker/bin/check-review-version" --base "origin/$default" --head "$head" 2>&1) ||
    { rm -rf "$checker"; die "the review path's version check refuses PR $pr's head: $bumped"; }
  rm -rf "$checker"
fi
computed=${paths%%$'\n'*}
# A routine record is accepted on a change whose depth floor is none (plan.py checked it), whatever its tier.
[ "$tier" = routine ] || [ "$(rank "$tier")" -ge "$(rank "$computed")" ] ||
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
[ -z "$repost" ] || [ -n "$merged_note" ] ||
  die "--repost is for a head that differs from --reviewed only by clean merges of $default; the head is the reviewed commit, so record its round."

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
state=failure
[ "$result" = pass ] && state=success
lines=(--line "- Head commit: \`$head\`" --line "- Reviewed commit: \`$reviewed\`$merged_note"
  --line "- Tier from the paths: $computed" --line "- Depth: $plan_depth (${plan_pairs// /, })"
  --line "- Reviewers: ${reviewers:-none}")
if [ -n "$plan_override" ] && [ -n "$repost" ]; then
  lines+=(--line "- Owner override: depth $plan_override, carried from the reposted round's record${plan_record:+ ($plan_record)}, which quotes the owner")
elif [ -n "$plan_override" ]; then
  lines+=(--line "- Owner override: depth $plan_override, by the owner's words: \"$owner\"")
fi
[ "$tier" != routine ] || lines+=(--line "- The routine tier needs gates only: no reviewer was required.")
round=()
read -r -a plan_pair_list <<<"$plan_pairs"
if [ -n "$round_out" ]; then
  read -r -a pairs <<<"${round_out%%$'\n'*}"
  for p in ${pairs[@]+"${pairs[@]}"}; do round+=(--round "$p"); done
  if [ -n "$repost" ]; then
    lines+=(--line "- Round: a re-post of the reviewed commit's verdict after clean merges of $default; no reviewer ran")
  else
    lines+=(--line "- Round: cycle $cycle; must-fix $blocking, nits $nits, duplicates merged $dupes")
    while IFS= read -r l; do lines+=(--line "$l"); done <<<"${round_out#*$'\n'}"
  fi
fi
for p in ${plan_pair_list[@]+"${plan_pair_list[@]}"}; do round+=(--round "$p"); done
build_record --kind review --sha "$head" --state "$state" --tier "$tier" --reviewed "$reviewed" --depth "$plan_depth" \
  ${plan_override:+--override "$plan_override"} \
  ${round[@]+"${round[@]}"} \
  --title "🤖 Review: $result ($tier tier)" ${lines[@]+"${lines[@]}"} ${file:+--file "$file"} \
  --details "Reviewer output (raw)" >"$tmp/body.md"
url=$(post_record "$pr" "$tmp/body.md") || exit 1
echo "verdict: PR $pr, head $head: review $result ($tier tier)${url:+, $url}"
