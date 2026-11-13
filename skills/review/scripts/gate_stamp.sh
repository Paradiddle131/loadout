#!/usr/bin/env bash
# Runs a repo's gates on the head commit and records the result there as a GitHub commit status, so a merge
# can be checked against a recorded result instead of a typed claim (cloud/hooks/merge-guard.py reads it).
#
# Usage: gate_stamp.sh [--context loadout/gates] [--dry-run] -- <command...>
#   e.g. gate_stamp.sh -- make check
#
# 1. Refuses a dirty tree (tracked or untracked changes): the result must be of the commit it is recorded on.
# 2. Refuses a head GitHub does not have (push first): a status can only go on a commit the remote holds.
# 3. Runs the command, its output shown as it runs.
# 4. Refuses to record when the command moved HEAD or changed a tracked file: the result would not be the head's.
# 5. Posts `success` (exit 0) or `failure` under the context on the head, described by the command and the last
#    line of its output; prints a block a PR body can quote; exits with the command's exit code (2 when this
#    script refused before running it, 3 when the command passed but its result could not be recorded).
#
# Honest limits: the status guards against forgetting, not against a dishonest author. The same account that
# runs the gates posts it, and nothing stops that account posting `success` by hand. It says the command ran
# green on this commit in this session; it says nothing about what the command covers.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
context=loadout/gates
while [ $# -gt 0 ]; do
  case "$1" in
    --context) context=${2:?--context needs a value}; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --) shift; break ;;
    *) echo "usage: gate_stamp.sh [--context loadout/gates] [--dry-run] -- <command...>" >&2; exit 2 ;;
  esac
done
[ $# -gt 0 ] || { echo "usage: gate_stamp.sh [--context loadout/gates] [--dry-run] -- <command...>" >&2; exit 2; }
# shellcheck source=lib.sh
. "$here/lib.sh"

cd "$(git rev-parse --show-toplevel)"
dirty=$(git status --porcelain --untracked-files=normal)
[ -z "$dirty" ] || die "the tree has uncommitted changes, so the result would not be the head commit's: commit them, or set them aside with \`git stash push -u -m <tag>\`.
$dirty"
head=$(git rev-parse HEAD)
remote_sha=$(gh_get "repos/$REPO/commits/$head" --jq '.sha' 2>/dev/null || true)
[ "$remote_sha" = "$head" ] || die "GitHub has no commit $head in $REPO: push the branch first, then run the gates."

printf -v shown ' %q' "$@"
shown=${shown# }
out=$(mktemp)
trap 'rm -f "$out"' EXIT
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
rc=$code
recorded="recorded as \`$context: $state\`"
if ! post_status "$head" "$context" "$state" "$shown: ${summary:-no output}"; then
  echo "gate_stamp: could not record $context on $head (see the error above): the result is NOT recorded." >&2
  [ "$code" = 0 ] && rc=3
  recorded="NOT recorded (\`$context: $state\` failed to post)"
fi

note=
[ "$DRY_RUN" = 1 ] && note=' (dry run: not posted)'
fence='```'
while grep -qF -- "$fence" "$out"; do fence="$fence\`"; done
cat <<EOF

Gates on $head, $recorded$note:

${fence}text
\$ $shown
exit $code
$(tail -n 20 "$out")
${fence}
EOF
exit "$rc"
