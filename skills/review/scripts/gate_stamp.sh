#!/usr/bin/env bash
# Runs a repo's gates on a PR's head commit and records the result on the PR as a marker comment, so a merge
# can be checked against a recorded result instead of a typed claim (cloud/hooks/merge-guard.py reads it).
#
# Usage: gate_stamp.sh [--pr <n>] [--dry-run] -- <command...>
#   e.g. gate_stamp.sh -- make check
#   --pr defaults to the open PR whose head is the current branch; with none, open the draft PR first.
#
# 1. Refuses a dirty tree (tracked or untracked changes): the result must be of the commit it is recorded for.
# 2. Refuses unless the PR's head on GitHub is this clone's HEAD (push first, or pull).
# 3. Runs the command, its output shown as it runs.
# 4. Refuses to record when the command moved HEAD or changed a tracked file: the result would not be the head's.
# 5. Posts `🤖 Gates: success|failure` with the marker `<!-- loadout:gates sha=<head> state=... -->`, the
#    command, its exit code and the output's tail; reads the comment back and fails if it differs.
# 6. Prints a block a PR body can quote; exits with the command's exit code (2 when this script refused before
#    running it, 3 when the command passed but its record could not be posted).
#
# Honest limits: the record guards against forgetting, not against a dishonest author. The same account that
# runs the gates posts it, and nothing stops that account typing a marker by hand. It says the command ran on
# this commit in this session; it says nothing about what the command covers.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
usage="usage: gate_stamp.sh [--pr <n>] [--dry-run] -- <command...>"
pr=''
while [ $# -gt 0 ]; do
  case "$1" in
    --pr) pr=${2:-}; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --) shift; break ;;
    *) echo "$usage" >&2; exit 2 ;;
  esac
done
[ $# -gt 0 ] || { echo "$usage" >&2; exit 2; }
# shellcheck source=lib.sh
. "$here/lib.sh"

cd "$(git rev-parse --show-toplevel)"
dirty=$(git status --porcelain --untracked-files=normal)
[ -z "$dirty" ] || die "the tree has uncommitted changes, so the result would not be the head commit's: commit them, or set them aside with \`git stash push -u -m <tag>\`.
$dirty"
head=$(git rev-parse HEAD)
[ -n "$pr" ] || pr=$(pr_for_branch)
[ -n "$pr" ] || die "no open PR has this branch as its head: push it and open the draft PR first, or pass --pr <n>."
[[ "$pr" =~ ^[0-9]+$ ]] || die "--pr is a PR number. $usage"
pr_sha=$(pr_head "$pr")
[ "$pr_sha" = "$head" ] || die "PR $pr's head on GitHub is $pr_sha, but this clone is at $head: push (or pull) so they match, then run the gates."

printf -v shown ' %q' "$@"
shown=${shown# }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
out=$tmp/out
set +e
"$@" 2>&1 | tee "$out"
code=${PIPESTATUS[0]}
set -e

[ "$(git rev-parse HEAD)" = "$head" ] || die "the command moved HEAD from $head; nothing recorded. Run the gates on a settled head."
changed=$(git status --porcelain --untracked-files=no)
[ -z "$changed" ] || die "the command changed tracked files, so its result is not the head's; nothing recorded:
$changed"

# The last non-empty line, without colour codes.
summary=$(sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g; s/[[:space:]]+$//' "$out" | grep -v '^$' | tail -n 1 || true)
state=failure
[ "$code" = 0 ] && state=success
build_record --kind gates --sha "$head" --state "$state" --title "🤖 Gates: $state" \
  --line "- Head commit: \`$head\`" --line "- Command: \`$shown\`" --line "- Exit code: $code" \
  --line "- Last line: ${summary:-no output}" --file "$out" --details "Output (raw)" --tail >"$tmp/body.md"

rc=$code
recorded="recorded on PR $pr"
if ! url=$(post_record "$pr" "$tmp/body.md"); then
  echo "gate_stamp: the gates record on PR $pr was NOT posted (see the error above)." >&2
  [ "$code" = 0 ] && rc=3
  recorded="NOT recorded"
fi
[ "$DRY_RUN" = 1 ] && recorded="not posted (dry run)"

fence='```'
while grep -qF -- "$fence" "$out"; do fence="$fence\`"; done
cat <<EOF

Gates on $head: $state, $recorded${url:+ ($url)}:

${fence}text
\$ $shown
exit $code
$(tail -n 20 "$out")
${fence}
EOF
exit "$rc"
