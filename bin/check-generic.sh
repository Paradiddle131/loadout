#!/usr/bin/env bash
# Fails when shared content names its owner's world: the owner's GitHub login, a sibling clone (the repos
# worked on next to this one) written as a path or `owner/name`, a date, or an issue or PR number.
# A sibling counts only beside a slash and in its own case, so one named after a common word (`pull`)
# leaves the word itself free. Skills, ways, the cloud notes and the scripts here are read by anyone who
# uses this repo, so they say <owner> and <repo> and leave evidence to the PR that changed them.
# Checked: tracked text files outside tests/ (fixture data); a binary
# file (an image) is skipped, since grep would match its bytes and print no line to fix.
# Extra words, one per line (a name, an employer, a hostname): $GENERIC_DENY_FILE
# (default ~/.config/<this repo's folder name>/deny), kept outside the repo.
# Usage: bin/check-generic.sh [file...]   (no arguments: every checked file)
set -euo pipefail
cd "$(dirname "$0")/.."

words=() siblings=()
owner=$( (git remote get-url origin 2>/dev/null || true) | sed -nE 's#.*github\.com[:/]([^/]+)/.*#\1#p')
[ -n "$owner" ] && words+=("$owner")
# This repo's own name comes from origin (a worktree's folder may be named otherwise); a folder whose git
# data is this repo's own (its main clone, or another worktree of it) is no sibling.
self=$( (git remote get-url origin 2>/dev/null || true) | sed -nE 's#.*/([^/]+)$#\1#p' | sed 's/\.git$//')
common=$(cd "$(git rev-parse --git-common-dir)" && pwd -P)
for d in ../*/; do
  name=$(basename "$d")
  [ -e "$d/.git" ] || continue
  [ "$name" = "$(basename "$PWD")" ] || [ "$name" = "$self" ] && continue
  theirs=$(cd "$d" && cd "$(git rev-parse --git-common-dir 2>/dev/null || echo .)" && pwd -P)
  [ "$theirs" = "$common" ] && continue
  siblings+=("$name")
done
deny=${GENERIC_DENY_FILE:-$HOME/.config/$(basename "$PWD")/deny}
[ -f "$deny" ] && while IFS= read -r w; do [ -n "$w" ] && words+=("$w"); done <"$deny"

files=()
if [ $# -gt 0 ]; then files=("$@"); else
  while IFS= read -r f; do files+=("$f"); done < <(git ls-files | grep -vE '(^|/)tests/' | grep -vx 'bin/check-generic.sh')
fi
[ ${#files[@]} -gt 0 ] || { echo "check-generic: no files to check"; exit 0; }

patterns=('\b20[0-9]{2}-[01][0-9]-[0-3][0-9]\b' '(^|[^&[:alnum:]/])[[:alnum:]_.-]*#[0-9]+\b')
# shellcheck disable=SC2016 # sed escapes regex metacharacters; nothing to expand
esc() { printf '%s' "$1" | sed 's/[.[\*^$()+?{|]/\\&/g'; }
for w in ${words[@]+"${words[@]}"}; do patterns+=("\\b$(esc "$w")\\b"); done
path_patterns=()
for w in ${siblings[@]+"${siblings[@]}"}; do
  e=$(esc "$w")
  path_patterns+=("(^|[^[:alnum:]_.-])$e/|/$e([^[:alnum:]_.-]|\$)")
done

found=0
scan() { # scan <grep case flag> <pattern...>
  local flag=$1 p hits; shift
  for p in "$@"; do
    if hits=$(grep -HnI "$flag" -E -- "$p" "${files[@]}" 2>/dev/null); then
      printf '%s\n' "$hits"
      found=1
    fi
  done
}
scan -i "${patterns[@]}"
if [ ${#path_patterns[@]} -gt 0 ]; then scan --no-ignore-case "${path_patterns[@]}"; fi
if [ "$found" = 1 ]; then
  echo "check-generic: name <owner> / <repo> instead, and put dates and issue numbers in the PR." >&2
  exit 1
fi
echo "check-generic: ${#files[@]} files, $((${#words[@]} + ${#siblings[@]})) owner-specific words, none found"
