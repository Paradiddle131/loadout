#!/usr/bin/env python3
"""PreToolUse hook for Bash: refuse shell commands that can make a GCP project bill.

Cloud sessions reach GCP with a credential the egress proxy injects, and unattended runs have
nobody watching the bill. IAM is the fence (cloud/gcp/README.md); this hook is the seatbelt in front
of it, so an agent never even tries a command that moves a spend fence or creates a paid resource,
including by "testing" a permission it believes it lacks: check permissions with
testIamPermissions, which only asks.

Refused: enabling an API; any IAM policy change; quota, billing and budget changes; service account
keys; write verbs on paid-only products (Compute, GKE, Composer, Cloud SQL, ...); buckets outside
Cloud Storage's Always Free regions; BigQuery reservations and capacity commitments; streaming
inserts (`bq insert`, no free tier); a `bq query` above the byte cap or with no cap at all; and the
same writes sent with curl or wget to *.googleapis.com.

Review agents (the collection's `agents/`, named bare or plugin-scoped in the hook's `agent_type`) get a
stricter rule: no live cloud call at all, read or write. A reviewer reads code; its brief already forbids
the cloud, and this enforces it: `gcloud`, `bq` and `gsutil`, curl or wget to *.googleapis.com or *.run.app,
inline Python or Node that imports Google's client libraries, and any change to the project variables
(`GCP_PROJECT`, `LEDGER_LAB_GCP_PROJECT`, `CLOUDSDK_*`, `GOOGLE_*`: set, unset, `env -u`, `export -n`).
It sees the command's own text (`bash -c`, `eval` and heredocs included), not a script that calls GCP itself.

Reads the hook's JSON on stdin; prints a deny decision on stdout or nothing. It sees shell
commands only, not code calling Google's client libraries: IAM covers those.
Cap: $GCP_MAX_BYTES_BILLED (default 1 GiB), the value cloud/gcp/status.sh writes to ~/.bigqueryrc.
"""

from __future__ import annotations

import json
import os
import re
import runpy
import shlex
import sys
from pathlib import Path

DEFAULT_CAP = 1 << 30
WRAPPERS = {
    "sudo",
    "env",
    "nohup",
    "time",
    "command",
    "exec",
    "timeout",
    "nice",
    "stdbuf",
    "xargs",
}
# Shell reserved words that come before a command (`if cmd; then cmd; fi`, `! cmd`, `{ cmd; }`): skipped, so
# the command after them is the one checked.
KEYWORDS = {"if", "then", "elif", "else", "do", "while", "until", "!", "{", "(", "time"}
TRACKS = {"alpha", "beta", "preview"}
SHELLS = {"bash", "sh", "zsh", "dash"}
SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "\n", "|&"}

# Products with no Always Free tier: any write verb on them is refused.
PAID_GROUPS = {
    "compute",
    "container",
    "composer",
    "sql",
    "redis",
    "memcache",
    "alloydb",
    "spanner",
    "bigtable",
    "filestore",
    "dataproc",
    "dataflow",
    "workbench",
    "notebooks",
    "ai",
    "ai-platform",
    "ml-engine",
    "vmware",
    "looker",
    "data-fusion",
    "datastream",
    "edge-cloud",
    "workstations",
    "netapp",
    "backup-dr",
    "dataplex",
    "metastore",
    "gemini",
}
WRITE_VERBS = {
    "create",
    "deploy",
    "update",
    "resize",
    "start",
    "resume",
    "import",
    "scale",
    "patch",
    "submit",
    "upgrade",
    "attach",
    "enable",
    "set-machine-type",
    "add",
    "restore",
    "clone",
}
FREE_STORAGE_REGIONS = {"us-central1", "us-east1", "us-west1"}
RESERVATION_FLAGS = ("--reservation", "--capacity_commitment", "--bi_reservation")
GOOGLEAPIS = re.compile(r"https?://[\w.-]*googleapis\.com/\S*", re.IGNORECASE)
SENSITIVE_API = re.compile(
    r"serviceusage\.googleapis\.com/.*:(batchEnable|enable)\b|:setIamPolicy\b|"
    r"cloudquotas\.googleapis\.com/.*quotaPreferences|billingbudgets\.googleapis\.com|"
    r"cloudbilling\.googleapis\.com|bigqueryreservation\.googleapis\.com|/insertAll\b|"
    r"iam\.googleapis\.com/.*/keys\b|"
    r"(compute|container|composer|sqladmin|redis|alloydb|spanner|dataproc|dataflow|notebooks)"
    r"\.googleapis\.com",
    re.IGNORECASE,
)
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

ADVICE = (
    " Spend fences (APIs, IAM, quotas, billing, budgets) and paid products are the owner's"
    " to change, from their own shell; an agent asks them in the handoff instead."
    " To check whether a permission is held, call testIamPermissions (it only asks),"
    " never the action itself. If this command is only text, write it with the Write tool."
)


def cap() -> int:
    try:
        return int(os.environ.get("GCP_MAX_BYTES_BILLED", DEFAULT_CAP))
    except ValueError:
        return DEFAULT_CAP


def bigqueryrc_has_cap() -> bool:
    rc = Path(os.environ.get("HOME", "~")).expanduser() / ".bigqueryrc"
    try:
        return "--maximum_bytes_billed" in rc.read_text()
    except OSError:
        return False


def tokenize(command: str) -> list[str] | None:
    lex = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = "#"
    try:
        return list(lex)
    except ValueError:
        return None


def segments(tokens: list[str]) -> list[list[str]]:
    out, cur = [], []
    for t in tokens:
        if t in SEPARATORS or set(t) <= set(";&|()\n"):
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        out.append(cur)
    return out


def program(seg: list[str]) -> tuple[str, list[str]] | None:
    """The command a segment runs, past env assignments and wrappers like `timeout 30`."""
    i = 0
    while i < len(seg):
        t = seg[i]
        if (
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t)
            or t.startswith("-")
            or t.isdigit()
        ):
            i += 1
            continue
        name = os.path.basename(t)
        if t in KEYWORDS or name in WRAPPERS or re.fullmatch(r"\d+[smhd]?", t):
            i += 1
            continue
        return name, seg[i + 1 :]
    return None


def words(args: list[str]) -> list[str]:
    return [a for a in args if not a.startswith("-") and a not in TRACKS]


def flag(args: list[str], name: str) -> str | None:
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def check_gcloud(args: list[str]) -> str | None:
    w = words(args)
    if not w:
        return None
    head = w[0]
    if head == "services" and "enable" in w[1:3]:
        return "enabling an API"
    if any(
        v in w
        for v in (
            "add-iam-policy-binding",
            "remove-iam-policy-binding",
            "set-iam-policy",
        )
    ):
        return "an IAM policy change"
    if head == "billing" and any(
        v in w for v in ("create", "update", "delete", "link", "unlink")
    ):
        return "a billing or budget change"
    if (head == "quotas" or "quota" in w[:2]) and any(
        v in w for v in ("create", "update")
    ):
        return "a quota change"
    if w[:4] == ["iam", "service-accounts", "keys", "create"]:
        return "a service account key"
    if head in PAID_GROUPS and any(
        v in WRITE_VERBS or v.split("-")[0] in WRITE_VERBS for v in w[1:]
    ):
        return f"a write on `gcloud {head}`, a product with no free tier"
    if w[:3] == ["storage", "buckets", "create"]:
        loc = (flag(args, "--location") or "").lower()
        if loc not in FREE_STORAGE_REGIONS:
            return "a bucket outside Cloud Storage's free regions (us-central1, us-east1, us-west1)"
    return None


def check_gsutil(args: list[str]) -> str | None:
    w = words(args)
    if w[:1] == ["mb"]:
        loc = (flag(args, "-l") or "").lower()
        if loc not in FREE_STORAGE_REGIONS:
            return "a bucket outside Cloud Storage's free regions (us-central1, us-east1, us-west1)"
    return None


def check_bq(args: list[str]) -> str | None:
    w = words(args)
    if not w:
        return None
    if w[0] in ("mk", "update") and any(a.startswith(RESERVATION_FLAGS) for a in args):
        return "a BigQuery reservation or capacity commitment"
    if w[0] == "insert":
        return "a streaming insert (`bq insert`), which has no free tier; load or DML instead"
    if w[0] == "query" and "--dry_run" not in args:
        value = flag(args, "--maximum_bytes_billed")
        if value is None and not bigqueryrc_has_cap():
            return "a query with no byte cap (pass --maximum_bytes_billed or start from cloud/gcp/status.sh's ~/.bigqueryrc)"
        if value is not None:
            try:
                over = int(value) > cap()
            except ValueError:
                over = True
            if over:
                return f"a query capped above {cap()} bytes"
    return None


def check_http(args: list[str]) -> str | None:
    urls = [m.group(0) for a in args for m in GOOGLEAPIS.finditer(a)]
    if not urls:
        return None
    method = (
        flag(args, "-X") or flag(args, "--request") or flag(args, "--method") or ""
    ).upper()
    sends = any(
        a.startswith(("-d", "--data", "--json", "-F", "--form", "--post-"))
        for a in args
    )
    if method in WRITE_METHODS or sends:
        for u in urls:
            if SENSITIVE_API.search(u) and ":testIamPermissions" not in u:
                return f"a write to {u.split('?')[0]}"
    return None


CHECKS = {
    "gcloud": check_gcloud,
    "bq": check_bq,
    "gsutil": check_gsutil,
    "curl": check_http,
    "wget": check_http,
    "http": check_http,
}


HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
SHELL_LINE = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:sudo\s+)?(?:bash|sh|zsh|dash)\b"
)


def split_heredocs(command: str) -> tuple[str, list[str]]:
    """The command without its heredoc bodies, and the bodies a shell will run.

    A body fed to a shell (`bash <<EOF`) is commands and is checked; any other body (a file
    written with `cat > f <<EOF`, a script for python) is text, and its quotes would only
    confuse the parse.
    """
    lines, kept, run = command.split("\n"), [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        for m in HEREDOC.finditer(line):
            strip, delim = m.group(1) == "-", m.group(3)
            body = []
            while (
                i < len(lines)
                and (lines[i].lstrip("\t") if strip else lines[i]) != delim
            ):
                body.append(lines[i])
                i += 1
            i += 1  # the delimiter line
            if SHELL_LINE.match(line):
                run.append("\n".join(body))
    return "\n".join(kept), run


def verdict(command: str, depth: int = 0) -> str | None:
    command, bodies = split_heredocs(command)
    for body in bodies if depth < 3 else []:
        reason = verdict(body, depth + 1)
        if reason:
            return reason
    tokens = tokenize(command)
    if tokens is None:
        if re.search(r"\b(gcloud|bq|gsutil)\b|googleapis\.com", command):
            return (
                "a command this guard cannot parse (unbalanced quotes) that names GCP"
            )
        return None
    for seg in segments(tokens):
        prog = program(seg)
        if not prog:
            continue
        name, args = prog
        if name in CHECKS:
            reason = CHECKS[name](args)
            if reason:
                return reason
        if depth < 3 and (name in SHELLS and "-c" in args or name == "eval"):
            inner = (
                args[args.index("-c") + 1]
                if name in SHELLS and args.index("-c") + 1 < len(args)
                else " ".join(args)
            )
            reason = verdict(inner, depth + 1)
            if reason:
                return reason
    return None


AGENTS_DIR = Path(__file__).resolve().parents[2] / "agents"
CLOUD_TOOLS = {"gcloud", "bq", "gsutil"}
HTTP_TOOLS = {"curl", "wget", "http", "https", "xh"}
CLOUD_HOST = re.compile(r"(googleapis\.com|\.run\.app)\b", re.IGNORECASE)
CLIENT_LIBS = re.compile(r"google\.cloud|googleapiclient|google\.auth|@google-cloud/|google-auth-library")
PROJECT_VAR = re.compile(r"GCP_PROJECT|LEDGER_LAB_GCP_PROJECT|CLOUDSDK_[A-Z0-9_]+|GOOGLE_[A-Z0-9_]+")
RUNTIME = re.compile(r"(?:^|[\s;&|(/])(?:python[0-9.]*|node|deno|bun)(?=[\s;&|)]|$)", re.MULTILINE)
REVIEWER_ADVICE = (
    " Review agents make no live cloud call, read or write, and leave the project variables as the session set"
    " them. Report the check as `unverified`, naming this refusal (`refused by the GCP guard`), so the verifier"
    " carries it onto the round's record."
)


def review_agent(event: dict) -> str | None:
    """The review agent the hook fired in, or None: `agent_type` names one of `agents/*.md`, bare or plugin-scoped."""
    kind = event.get("agent_type")
    if not isinstance(kind, str) or not kind:
        return None
    name = kind.rsplit(":", 1)[-1]
    return name if (AGENTS_DIR / f"{name}.md").is_file() else None


def reviewer_verdict(command: str, depth: int = 0) -> str | None:
    """What a review agent may not run: a live cloud call or a change to the project variables."""
    if CLIENT_LIBS.search(command) and RUNTIME.search(command):  # `-c` code or a heredoc fed to it
        return "inline code that loads Google's client libraries"
    command, bodies = split_heredocs(command)
    for body in bodies if depth < 3 else []:
        if reason := reviewer_verdict(body, depth + 1):
            return reason
    tokens = tokenize(command)
    if tokens is None:
        if re.search(r"\b(gcloud|bq|gsutil)\b|googleapis\.com|\.run\.app", command) or PROJECT_VAR.search(command):
            return "a command this guard cannot parse (unbalanced quotes) that names GCP"
        return None
    for seg in segments(tokens):
        for i, t in enumerate(seg):
            if re.fullmatch(rf"(?:{PROJECT_VAR.pattern})=.*", t):
                return f"a change to `{t.split('=', 1)[0]}`"
            if t in ("-u", "--unset") and i + 1 < len(seg) and PROJECT_VAR.fullmatch(seg[i + 1]):
                return f"unsetting `{seg[i + 1]}`"
            if t.startswith("--unset=") and PROJECT_VAR.fullmatch(t.split("=", 1)[1]):
                return f"unsetting `{t.split('=', 1)[1]}`"
        prog = program(seg)
        if not prog:
            continue
        name, args = prog
        if name in ("unset", "export", "declare", "typeset", "readonly") and any(
            PROJECT_VAR.fullmatch(a) for a in args
        ) and (name == "unset" or any(a.startswith(("-n", "+x")) for a in args)):
            return f"`{name}` on a project variable"
        if name in CLOUD_TOOLS:
            return f"a live `{name}` call"
        if name in HTTP_TOOLS and any(CLOUD_HOST.search(a) for a in args):
            return f"a `{name}` request to a Google Cloud host"
        if depth < 3 and (name in SHELLS and "-c" in args or name == "eval"):
            inner = (
                args[args.index("-c") + 1]
                if name in SHELLS and args.index("-c") + 1 < len(args)
                else " ".join(args)
            )
            if reason := reviewer_verdict(inner, depth + 1):
                return reason
    return None


def note_refusal(rule: str) -> None:
    """Note a refusal in the collection's friction log (bin/friction): the guard and the rule, never the command."""
    try:
        friction = Path(__file__).resolve().parents[2] / "bin/friction"
        runpy.run_path(str(friction), run_name="friction")["record_refusal"]("gcp-guard", rule)
    except Exception:  # noqa: BLE001 -- the log never changes or slows the decision
        pass


def main() -> int:
    raw = sys.stdin.read()
    try:
        event, deep = json.loads(raw), False
    except ValueError:
        return 0
    except RecursionError:  # nested past what json reads: the failure rule below, on the raw text
        event, deep = {"tool_name": "Bash", "tool_input": {"command": raw}}, True
    if event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command") or ""
    rule, advice = "spend", ADVICE
    try:
        if deep:
            raise ValueError("its input is nested too deep to read")
        reason = verdict(command)
        if not reason and review_agent(event):
            reason = reviewer_verdict(command)
            if reason:
                rule, advice = "reviewer-cloud", REVIEWER_ADVICE
    except Exception as exc:  # noqa: BLE001 -- a guard bug must not wave a GCP command through
        rule = "guard-error"
        reason = (
            f"a GCP command the guard failed on ({exc})"
            if re.search(r"gcloud|\bbq\b|googleapis", command)
            else None
        )
    if reason:
        note_refusal(rule)
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"GCP $0 guard: refused {reason}."
                        + advice,
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
