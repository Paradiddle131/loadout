#!/usr/bin/env python3
"""A stub `gh` for the review scripts' and the merge guard's tests: `gh api` against files, never GitHub.

State lives in $STUB_DIR:
- pr.json: what `repos/<o>/<r>/pulls/<n>` answers; pulls.json: what `pulls?...` answers.
- comments.json: the PR's comments; a post appends one (author_association OWNER), and
  `issues/<n>/comments?per_page=P&page=N` and `issues/comments/<id>` read them.
- calls.jsonl: every call as {"method", "endpoint", "fields"}.
STUB_FAIL=<text>: a call whose endpoint contains it fails the way gh does on an HTTP error.
STUB_MANGLE=1: a comment read back by id differs from the one posted.
STUB_SLEEP=<seconds>: every call waits that long first (a slow GitHub).
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
    elif a == "--paginate":
        sys.stderr.write("stub gh: --paginate is refused, as the cloud proxy refuses the links it follows\n")
        sys.exit(1)
    else:
        ep = a
        i += 1
method = method or ("POST" if fields else "GET")
if os.environ.get("STUB_SLEEP"):
    import time

    time.sleep(float(os.environ["STUB_SLEEP"]))
with (d / "calls.jsonl").open("a") as log:
    log.write(json.dumps({"method": method, "endpoint": ep, "fields": fields}) + "\n")
fail = os.environ.get("STUB_FAIL")
if fail and fail in ep:
    sys.stderr.write("gh: Server Error (HTTP 502)\n")
    sys.exit(1)


def load(name: str, default: object) -> object:
    p = d / name
    return json.loads(p.read_text()) if p.exists() else default


comments = load("comments.json", [])
if method == "POST" and re.search(r"/issues/\d+/comments$", ep):
    n = ep.split("/")[-2]
    new = {"id": 1000 + len(comments), "body": fields["body"], "author_association": "OWNER",
           "created_at": f"2000-01-01T00:{len(comments):02d}:00Z",
           "html_url": f"https://github.com/example-owner/example-repo/pull/{n}#issuecomment-{1000 + len(comments)}"}
    new["updated_at"] = new["created_at"]
    comments.append(new)
    (d / "comments.json").write_text(json.dumps(comments))
    out: object = new
elif method == "GET" and (m := re.search(r"/issues/comments/(\d+)$", ep)):
    [c] = [c for c in comments if c["id"] == int(m.group(1))]
    out = {**c, "body": c["body"] + ("\nedited" if os.environ.get("STUB_MANGLE") else "")}
elif method == "GET" and re.search(r"/issues/\d+/comments\?", ep):
    q = dict(kv.split("=", 1) for kv in ep.split("?", 1)[1].split("&"))
    per, page = int(q.get("per_page", 30)), int(q.get("page", 1))
    out = comments[(page - 1) * per: page * per]
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
