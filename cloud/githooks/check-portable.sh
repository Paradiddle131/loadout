#!/usr/bin/env bash
# Fails when a repo's content names its GitHub owner literally. Code, config and docs that act on the repo take
# <owner>/<repo> from the origin remote, and links to its own tracker are relative (../../issues), so a fork
# builds, syncs and links against itself (ways/portable.md). The owner comes from `git remote get-url origin`.
# By default it checks the lines the staged commit adds, so a literal already in the repo never blocks unrelated
# work; --all checks every tracked file, for an audit. History keeps its facts: ledgers, changelogs and
# lockfiles are not checked. A deliberate literal goes in with `git commit --no-verify`.
# The pre-commit hook of the repos a cloud session works on (cloud/githooks/) runs it; this repo has its own,
# stricter guard (bin/check-generic.sh).
# Usage: cloud/githooks/check-portable.sh [--all] [repo-dir]   (repo-dir defaults to the current directory)
set -euo pipefail
all=0
[ "${1:-}" = --all ] && { all=1; shift; }
cd "$(git -C "${1:-.}" rev-parse --show-toplevel)"

owner=$(git remote get-url origin 2>/dev/null | sed -nE 's#.*github\.com[:/]([^/]+)/.*#\1#p' || true)
[ -n "$owner" ] || { echo "check-portable: no GitHub origin remote; nothing to check"; exit 0; }
history=(':(exclude,glob)**/LEDGER.md' ':(exclude,glob)**/ledger.d/**' ':(exclude,glob)**/CHANGELOG*'
  ':(exclude,glob)**/*.lock' ':(exclude,glob)**/package-lock.json' ':(exclude,glob)**/pnpm-lock.yaml')

if [ "$all" = 1 ]; then
  hits=$(git grep -nIiwF -e "$owner" -- . "${history[@]}" || true)
  scope="$(git ls-files -- . "${history[@]}" | wc -l) tracked files"
else
  # Added lines of the staged diff as file:line:text; a login is [A-Za-z0-9-], so it is safe in a regex.
  hits=$(git diff --cached -U0 --no-color --no-ext-diff --diff-filter=ACMR -- . "${history[@]}" |
    awk -v o="$(printf '%s' "$owner" | tr '[:upper:]' '[:lower:]')" '
      /^\+\+\+ / { f = substr($0, 7); next }
      /^@@ /     { split($3, a, ","); n = substr(a[1], 2) + 0; next }
      /^\+/      { l = substr($0, 2)
                   if (tolower(l) ~ ("(^|[^[:alnum:]_])" o "([^[:alnum:]_]|$)")) print f ":" n ": " l
                   n++ }')
  scope="the staged changes"
fi

if [ -n "$hits" ]; then
  printf '%s\n' "$hits"
  echo "check-portable: name the owner through the origin remote (git remote get-url origin) or link the tracker relatively (../../issues)." >&2
  exit 1
fi
echo "check-portable: $scope, no literal owner"
