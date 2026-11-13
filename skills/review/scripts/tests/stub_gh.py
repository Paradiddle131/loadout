#!/usr/bin/env python3
"""A stub `gh` for the review scripts' and the merge guard's tests: `gh api` against files, never GitHub.

State lives in $STUB_DIR:
- pr.json: what `repos/<o>/<r>/pulls/<n>` answers; pulls.json: what `pulls?...` answers.
- known.txt: the commit shas GitHub "has" (one per line), for `repos/<o>/<r>/commits/<sha>`.
- statuses.json: {sha: {context: state}}; status posts add to it, `commits/<sha>/status` reads it.
- comment.txt: the last comment body posted; `issues/comments/<id>` reads it back.
- calls.jsonl: every call as {"method", "endpoint", "fields"}.
STUB_FAIL=<text>: a call whose endpoint contains it fails the way gh does on an HTTP error.
STUB_MANGLE=1: the comment read back differs from the one posted.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

d = Path(os.environ["STUB_DIR"])
args = sys.argv[1:]
if not args or args[0] != "api":
    sys.exit(f"stub gh: only `gh api` is stubbed, got {args}")
args = args[1:]
method, fields, jq, ep = None, {}, None, ""
i = 0
while i < len(args):
    a = args[i]
    if a in ("-X", "--method"):
        method = args[i + 1]
        i += 2
    elif a in ("-f", "-F", "--field", "--raw-field"):
        k, v = args[i + 1].split("=", 1)
        if a in ("-F", "--field") and v.startswith("@"):
            v = Path(v[1:]).read_text()
        fields[k] = v
        i += 2
    elif a in ("--jq", "-q"):
        jq = args[i + 1]
        i += 2
    else:
        ep = a
        i += 1
method = method or ("POST" if fields else "GET")
with (d / "calls.jsonl").open("a") as log:
    log.write(json.dumps({"method": method, "endpoint": ep, "fields": fields}) + "\n")
fail = os.environ.get("STUB_FAIL")
if fail and fail in ep:
    sys.stderr.write("gh: Server Error (HTTP 502)\n")
    sys.exit(1)


def load(name: str, default: object) -> object:
    p = d / name
    return json.loads(p.read_text()) if p.exists() else default


statuses = load("statuses.json", {})
if method == "POST" and (m := re.search(r"/statuses/([0-9a-f]+)$", ep)):
    statuses.setdefault(m.group(1), {})[fields["context"]] = fields["state"]
    (d / "statuses.json").write_text(json.dumps(statuses))
    out = {"state": fields["state"], "context": fields["context"]}
elif method == "POST" and re.search(r"/issues/\d+/comments$", ep):
    (d / "comment.txt").write_text(fields["body"])
    n = ep.split("/")[-2]
    out = {"id": 7, "html_url": f"https://github.com/example-owner/example-repo/pull/{n}#issuecomment-7"}
elif method == "GET" and "/issues/comments/" in ep:
    body = (d / "comment.txt").read_text()
    out = {"id": 7, "body": body + ("\nedited" if os.environ.get("STUB_MANGLE") else "")}
elif method == "GET" and (m := re.search(r"/commits/([0-9a-f]+)/status", ep)):
    got = statuses.get(m.group(1), {})
    out = {"sha": m.group(1), "statuses": [{"context": c, "state": s} for c, s in got.items()]}
elif method == "GET" and (m := re.search(r"/commits/([0-9a-f]+)$", ep)):
    known = (d / "known.txt").read_text().split() if (d / "known.txt").exists() else []
    if m.group(1) not in known:
        sys.stderr.write("gh: No commit found for SHA (HTTP 422)\n")
        sys.exit(1)
    out = {"sha": m.group(1)}
elif method == "GET" and "/pulls?" in ep:
    out = load("pulls.json", [])
elif method == "GET" and re.search(r"/pulls/\d+$", ep):
    out = load("pr.json", {})
else:
    sys.exit(f"stub gh: no route for {method} {ep}")
text = json.dumps(out)
if jq:
    text = subprocess.run(["jq", "-r", jq], input=text, capture_output=True, text=True, check=True).stdout
print(text.rstrip("\n"))
