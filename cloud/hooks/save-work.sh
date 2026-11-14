#!/usr/bin/env bash
# Pushes each clone's unsaved work to origin, so a session cut off by a usage limit (or a reclaimed container)
# loses nothing: uncommitted changes, untracked files and commits on no remote branch, from every worktree of
# every git clone under SAVE_WORK_ROOTS (default /home/user), go to `claude/wip/<branch>-<session>`.
# It never touches a working tree, its index or HEAD: the snapshot is built in a temporary index and pushed as
# a commit whose parent is HEAD; a clone with nothing new is skipped, so most sessions push nothing.
# Untracked files that look like secrets (.env*, keys, credentials) or are over SAVE_WORK_MAX_KB are left out, and
# gitleaks (cloud/setup.sh installs it) scans the commits about to be pushed: on a finding, or a scan that fails,
# that clone's push is skipped with a SKIPPED line in the log and on stderr, and the work stays only in the container.
#
# Hooks (the cloud plugin's hooks.json): StopFailure, a turn ended by an API error such as `rate_limit`, runs it
# at once; PostToolUse runs `--periodic`, which acts at most every SAVE_WORK_EVERY_S (default 1200) and in the
# background. `bash save-work.sh --now` runs it by hand. Its log: ~/.claude/save-work.log.
# Recover: git ls-remote origin 'refs/heads/claude/wip/*', then git fetch origin <ref> and cherry-pick or diff it.
# Then it flushes the friction log (bin/friction flush, at most FRICTION_FLUSH_S, default 40 s; its notice goes
# to the log), whatever the pushes did; the flush never changes the exit status.
set -u
mode=${1:-}
[ -t 0 ] || cat >/dev/null # the hook's JSON input: unused
STAMP="$HOME/.claude/save-work.stamp"
LOG="$HOME/.claude/save-work.log"
EVERY=${SAVE_WORK_EVERY_S:-1200}
MAX_KB=${SAVE_WORK_MAX_KB:-10240}
ROOTS=${SAVE_WORK_ROOTS:-/home/user}
FRICTION="$(dirname "${BASH_SOURCE[0]}")/../../bin/friction"
GITLEAKS=$(command -v gitleaks || { [ -x "$HOME/.local/bin/gitleaks" ] && echo "$HOME/.local/bin/gitleaks"; } || true)

if [ "$mode" = "--periodic" ]; then
  now=$(date +%s)
  last=$(cat "$STAMP" 2>/dev/null || echo 0)
  [ $((now - last)) -lt "$EVERY" ] && exit 0
fi
mkdir -p "$(dirname "$STAMP")"
date +%s >"$STAMP"

session=${CLAUDE_CODE_SESSION_ID:-$(hostname)}
session=${session:0:8}

snapshot() { # <worktree>
  local wt=$1 branch head idx tree commit ref
  head=$(git -C "$wt" rev-parse -q --verify HEAD) || return 0
  branch=$(git -C "$wt" symbolic-ref --short -q HEAD || echo "detached-${head:0:8}")
  case $branch in claude/wip/*) return 0 ;; esac
  git -C "$wt" remote get-url origin >/dev/null 2>&1 || return 0
  idx=$(mktemp)
  cp "$(git -C "$wt" rev-parse --path-format=absolute --git-path index)" "$idx" 2>/dev/null || rm -f "$idx"
  GIT_INDEX_FILE=$idx git -C "$wt" add -u . 2>/dev/null
  git -C "$wt" ls-files --others --exclude-standard -z | while IFS= read -r -d '' f; do
    case ${f##*/} in .env* | *.pem | *.key | *.p12 | *credentials* | *secret* | id_rsa* | id_ed25519*) continue ;; esac
    [ "$(du -k "$wt/$f" 2>/dev/null | cut -f1)" -le "$MAX_KB" ] 2>/dev/null || continue
    GIT_INDEX_FILE=$idx git -C "$wt" add -- "$f" 2>/dev/null
  done
  tree=$(GIT_INDEX_FILE=$idx git -C "$wt" write-tree 2>/dev/null)
  rm -f "$idx"
  [ -n "$tree" ] || return 0
  if [ "$tree" != "$(git -C "$wt" rev-parse "HEAD^{tree}")" ]; then
    commit=$(git -C "$wt" commit-tree -p HEAD -m "wip: unsaved work on $branch, $(date -u +%FT%H:%MZ)" "$tree") || return 0
  elif [ -n "$(git -C "$wt" rev-list -1 HEAD --not --remotes=origin 2>/dev/null)" ]; then
    commit=$head
  else
    return 0
  fi
  ref="claude/wip/${branch//\//-}-$session"
  if [ -z "$GITLEAKS" ]; then
    echo "$(date -u +%FT%H:%MZ) UNSCANNED $wt ($branch): gitleaks is not installed, so this push was NOT scanned for secrets" >>"$LOG"
  else
    # Every commit the push would add to the remote: the snapshot and any commit on no origin branch.
    "$GITLEAKS" detect --source "$wt" --log-opts="$commit --not --remotes=origin" --no-banner --redact \
      --exit-code 3 >>"$LOG" 2>&1
    case $? in
      0) ;;
      3)
        echo "$(date -u +%FT%H:%MZ) SKIPPED $wt ($branch): gitleaks found a secret in the work to push, so nothing went to $ref; remove it and save again (redacted findings in $LOG)" | tee -a "$LOG" >&2
        return 0 ;;
      *)
        echo "$(date -u +%FT%H:%MZ) SKIPPED $wt ($branch): the gitleaks scan failed, so nothing went to $ref (see $LOG)" | tee -a "$LOG" >&2
        return 0 ;;
    esac
  fi
  if timeout 90 git -C "$wt" push -q --force --no-verify origin "$commit:refs/heads/$ref" 2>>"$LOG"; then
    echo "$(date -u +%FT%H:%MZ) $wt ($branch) -> $ref ${commit:0:8}" >>"$LOG"
  else
    echo "$(date -u +%FT%H:%MZ) $wt ($branch): push to $ref failed" >>"$LOG"
  fi
}

run() {
  local gitdir repo wt
  for gitdir in $ROOTS/*/.git; do
    [ -e "$gitdir" ] || continue
    repo=${gitdir%/.git}
    git -C "$repo" worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p' | while IFS= read -r wt; do
      [ -d "$wt" ] && snapshot "$wt"
    done
  done
}

flush() {
  local out
  [ -f "$FRICTION" ] || return 0
  out=$(timeout "${FRICTION_FLUSH_S:-40}" python3 "$FRICTION" flush 2>&1 </dev/null)
  [ -z "$out" ] || echo "$(date -u +%FT%H:%MZ) $out" >>"$LOG"
}

if [ "$mode" = "--periodic" ]; then
  ({ run; flush; } >/dev/null 2>&1 &)
else
  run
  flush
fi
exit 0
