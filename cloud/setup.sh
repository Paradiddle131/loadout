#!/bin/bash
# Setup for Claude Code on the web. The environment's Setup field calls only this, naming the target repo
# (cloud/README.md has the guarded line); a session that started without it (no ~/.claude/cloud-target)
# runs the same command itself, which then also runs the session-start hook.
# Runs as root after the clones and before Claude Code starts. Its result is cached as a file snapshot
# (days) when it finishes within ~5 minutes; only an edit of the Setup field, an allowlist change or the
# expiry re-runs it. So it records a stamp of itself (and of the target's own setup) in
# ~/.claude/cloud-setup.stamp, and the session-start hook re-runs it when the fresh clone's stamp differs.
# Snapshots keep files, not processes: point into the clones, never copy, and leave daemons to the
# session-start hook. Must exit 0, or the session fails to start.
set -u
TARGET=${1:-}
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CLOUD="$ROOT/cloud"
# CLOUD_ROOTS: where clones may live (override only to test this script elsewhere).
find_clone() {
  find ${CLOUD_ROOTS:-/home/user /root /workspace} -maxdepth 3 -type d -name "$1" 2>/dev/null |
    while read -r d; do [ -d "$d/.git" ] && echo "$d" && break; done
}
REPO=$([ -n "$TARGET" ] && find_clone "$TARGET")
echo "collection: $ROOT  target ${TARGET:-none}: ${REPO:-MISSING}"

# 1. The standing rules and the cloud conditions, imported from the clone (cloud/memory.sh).
bash "$CLOUD/memory.sh"

# 2. This collection's plugins (skills, and the cloud hooks), loaded in place from the clone, plus pinned
#    third-party plugins. A directory marketplace reads the clone, so a merged change reaches the next session.
if command -v claude >/dev/null; then
  market=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$ROOT/.claude-plugin/marketplace.json")
  # A snapshot can hold marketplaces from an older setup: this clone under another name (a renamed marketplace,
  # whose add would fail), or a directory that is gone (a repo no longer attached). Drop them and their plugins.
  claude plugin marketplace list --json 2>/dev/null | python3 -c '
import json, os, sys
root, market = sys.argv[1], sys.argv[2]
for m in json.load(sys.stdin):
    path = m.get("path") or ""
    if m.get("source") == "directory" and m["name"] != market and (path == root or not os.path.isdir(path)):
        print(m["name"])' "$ROOT" "$market" | while read -r stale; do
    claude plugin list --json 2>/dev/null | python3 -c 'import json,sys; [print(p["id"]) for p in json.load(sys.stdin) if p.get("id","").endswith("@"+sys.argv[1])]' "$stale" |
      while read -r id; do claude plugin uninstall "$id" >/dev/null 2>&1; done
    claude plugin marketplace remove "$stale" >/dev/null 2>&1 && echo "plugins: removed stale marketplace $stale"
  done
  claude plugin marketplace add "$ROOT" >/dev/null 2>&1 || echo "plugins: marketplace add FAILED"
  for p in $(python3 -c 'import json,sys; print(" ".join(p["name"] for p in json.load(open(sys.argv[1]))["plugins"]))' "$ROOT/.claude-plugin/marketplace.json"); do
    claude plugin install "$p@$market" >/dev/null 2>&1 || echo "plugins: $p FAILED"
  done
  echo "plugins: $(claude plugin list 2>/dev/null | grep -c "@$market") from $market"
  # A plugin can install and still fail to load a part (a hook, a skill path): say so, never pass it silently.
  claude plugin list --json 2>/dev/null | python3 -c '
import json, sys
for p in json.load(sys.stdin):
    for e in p.get("errors") or []:
        print("plugins: %s: %s" % (p["id"], e))'

  # Third-party plugins, one per line in cloud/plugins.txt, each cloned at its pinned tag.
  while read -r name url tag post; do
    case "$name" in ''|'#'*) continue;; esac
    dir="$HOME/.local/share/$name"
    if ! git -C "$dir" tag --points-at HEAD 2>/dev/null | grep -qx "$tag"; then
      rm -rf "$dir" && git -c advice.detachedHead=false clone -q --depth 1 --branch "$tag" "$url" "$dir" ||
        { echo "$name: clone of $tag FAILED"; continue; }
    fi
    claude plugin marketplace add "$dir" >/dev/null 2>&1 || echo "$name: marketplace add FAILED"
    claude plugin install "$name@$name" >/dev/null 2>&1 && echo "$name: $tag" || echo "$name: install FAILED"
    if [ -n "$post" ]; then (cd "$dir" && sh -c "$post" >/dev/null 2>&1) || echo "$name: $post FAILED"; fi
  done < "$CLOUD/plugins.txt"
else
  echo "plugins: claude CLI not found; read skills from the clone by path"
fi

# 3. Settings: no agent attribution on commits and PRs. Drop hook entries whose script no longer exists (a hook
#    from a repo that left the environment would fail every turn), and entries that run this collection's own hook
#    scripts from any clone (an older setup wrote them here; the cloud plugin registers them now, so they would
#    run twice).
python3 - <<'EOF'
import json, os, pathlib, shlex
OWN = ("/cloud/hooks/session-start.sh", "/cloud/hooks/save-work.sh", "/cloud/gcp/guard.py")
p = pathlib.Path.home() / ".claude/settings.json"
s = json.loads(p.read_text()) if p.exists() and p.read_text().strip() else {}
s["attribution"] = {"commit": "", "pr": "", "sessionUrl": False}
def alive(h):
    words = shlex.split(h.get("command", ""))
    scripts = [w for w in words[1:2] if w.startswith("/")]
    return not scripts or (os.path.exists(scripts[0]) and not scripts[0].endswith(OWN))
for event, matchers in list(s.get("hooks", {}).items()):
    for m in matchers:
        m["hooks"] = [h for h in m.get("hooks", []) if alive(h)]
    s["hooks"][event] = [m for m in matchers if m["hooks"]]
    if not s["hooks"][event]:
        del s["hooks"][event]
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(s, indent=2) + "\n")
EOF
echo "settings: attribution off"

# 3b. gitleaks, pinned and checksum-checked, for the secret scan in this repo's pre-commit hook.
GITLEAKS_VERSION=8.21.2 GITLEAKS_SHA256=5bc41815076e6ed6ef8fbecc9d9b75bcae31f39029ceb55da08086315316e3ba
if ! ~/.local/bin/gitleaks version 2>/dev/null | grep -qx "$GITLEAKS_VERSION"; then
  tgz=$(mktemp) && curl -fsSL -o "$tgz" "https://github.com/gitleaks/gitleaks/releases/download/v$GITLEAKS_VERSION/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" &&
    echo "$GITLEAKS_SHA256  $tgz" | sha256sum -c --quiet && mkdir -p ~/.local/bin && tar -xzf "$tgz" -C ~/.local/bin gitleaks &&
    echo "gitleaks: $GITLEAKS_VERSION" || echo "gitleaks: install FAILED"
  rm -f "$tgz"
fi

# 4. The target, for the session-start hook (multi-repo sessions skip repo hooks).
[ -n "$REPO" ] && echo "$REPO" > ~/.claude/cloud-target

# 5. Docker Hub rate-limits anonymous pulls (429): pull through Google's public mirror. A running
#    dockerd (a healed session) rereads registry-mirrors on SIGHUP.
if command -v dockerd >/dev/null && [ "$(id -u)" = 0 ] && [ ! -f /etc/docker/daemon.json ]; then
  mkdir -p /etc/docker
  echo '{"registry-mirrors": ["https://mirror.gcr.io"]}' > /etc/docker/daemon.json
  pid=$(cat /var/run/docker.pid 2>/dev/null) && kill -HUP "$pid" 2>/dev/null && echo "docker: mirror reloaded"
fi

# 6. The target's own setup, if any (tools only it needs).
if [ -n "$REPO" ] && [ -f "$REPO/docs/agents/cloud-setup.local.sh" ]; then
  bash "$REPO/docs/agents/cloud-setup.local.sh" "$REPO" || echo "target setup: FAILED"
fi

# 7. The stamp the session-start hook compares against the clone's (keep in step with setup_stamp there).
cat "$CLOUD/setup.sh" "$CLOUD/plugins.txt" ${REPO:+"$REPO/docs/agents/cloud-setup.local.sh"} 2>/dev/null |
  sha256sum | cut -d' ' -f1 > ~/.claude/cloud-setup.stamp

# 8. Heal: run from inside a session that started without this setup, the session-start hook never ran
#    either; run it now. Plugins installed here load at the next session start.
if [ -n "${CLAUDECODE:-}" ] && [ -z "${CLOUD_SETUP_REFRESH:-}" ]; then
  bash "$CLOUD/hooks/session-start.sh" </dev/null
  echo "cloud setup: healed this session; read skills from the clone by path until the next session"
fi

echo "cloud setup: done"
exit 0
