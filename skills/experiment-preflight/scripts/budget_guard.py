#!/usr/bin/env python3
"""A hard stop for a measured pass: run count, cost and infrastructure failures, enforced by exit code.

Usage (limits are fixed when the state is created; a later call that names different ones is refused):

    budget_guard.py --state S --max-runs N [--max-cost X] [--max-infra-failures 2] --go TEXT init
    budget_guard.py --state S start                  # reserve one run; exit 3 once any limit is reached
    budget_guard.py --state S record --outcome ok|wrong|infra [--cost C]
    budget_guard.py --state S status

Exit codes: 0 go on, 3 a limit is reached (stop the pass), 2 refused (missing or corrupt state,
limits that differ from the state's, a missing cost under a cost limit). Any non-zero exit stops the
loop, so every failure of the guard itself stops the pass rather than letting it run unguarded.
`start` reserves its slot under the lock, so concurrent workers never start more than N runs.
`record` without `start` also counts. `--go` holds a quote of or link to the owner's go and is kept
in the state; more than two infrastructure failures need a `--go` that names that number.
The state path is resolved first, so a link and its target share one lock and one count.
Stdlib only; POSIX (`fcntl`).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

GO, REFUSED, STOP = 0, 2, 3
SCHEMA = 1
OUTCOMES = ("ok", "wrong", "infra")
COUNTS = ("started", "recorded", *OUTCOMES)


class Refused(Exception):
    pass


def say(msg: str) -> None:
    print(f"budget_guard: {msg}", file=sys.stderr)


@contextmanager
def locked(state: Path):
    lock = state.with_name(state.name + ".lock")
    with open(lock, "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def load(state: Path) -> dict:
    if not state.exists():
        raise Refused(f"no state at {state}; run `init` with the owner's limits first")
    try:
        data = json.loads(state.read_text())
    except (OSError, ValueError) as exc:
        raise Refused(f"state {state} unreadable ({exc}); refusing to continue") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise Refused(f"state {state} is not a budget_guard state; refusing to continue")
    limits, counts = data.get("limits"), data.get("counts")
    ok = (
        isinstance(limits, dict)
        and isinstance(counts, dict)
        and _count(limits.get("max_runs"), positive=True)
        and _count(limits.get("max_infra_failures"), positive=True)
        and "max_cost" in limits
        and (limits["max_cost"] is None or _amount(limits["max_cost"]))
        and isinstance(data.get("go"), str)
        and all(_count(counts.get(k)) for k in COUNTS)
        and _amount(data.get("cost"))
        and counts["recorded"] == sum(counts[k] for k in OUTCOMES)
    )
    if not ok:
        raise Refused(f"state {state} is malformed; refusing to continue")
    return data


def _count(v, positive: bool = False) -> bool:
    return type(v) is int and v >= (1 if positive else 0)


def _amount(v) -> bool:
    return type(v) in (int, float) and math.isfinite(v) and v >= 0


def save(state: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=state.parent, prefix=state.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, state)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    dfd = os.open(state.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def reached(data: dict) -> list[str]:
    lim, c = data["limits"], data["counts"]
    out = []
    if max(c["started"], c["recorded"]) >= lim["max_runs"]:
        out.append(f"runs {max(c['started'], c['recorded'])}/{lim['max_runs']} reached")
    if c["infra"] >= lim["max_infra_failures"]:
        out.append(f"infrastructure failures {c['infra']}/{lim['max_infra_failures']} reached")
    if lim["max_cost"] is not None and data["cost"] >= lim["max_cost"]:
        out.append(f"cost {data['cost']:g}/{lim['max_cost']:g} reached")
    return out


def check_limits(args, data: dict) -> None:
    given = {
        "max_runs": args.max_runs,
        "max_cost": args.max_cost,
        "max_infra_failures": args.max_infra_failures,
    }
    for key, value in given.items():
        if value is not None and value != data["limits"][key]:
            raise Refused(
                f"--{key.replace('_', '-')} {value} differs from the state's {data['limits'][key]};"
                " a new go starts a new state file"
            )


def summary(data: dict) -> str:
    c, lim = data["counts"], data["limits"]
    cost = f" cost={data['cost']:g}" + (f"/{lim['max_cost']:g}" if lim["max_cost"] is not None else "")
    return (
        f"started={c['started']} recorded={c['recorded']}/{lim['max_runs']} ok={c['ok']}"
        f" wrong={c['wrong']} infra={c['infra']}/{lim['max_infra_failures']}{cost}"
    )


def run(args) -> int:
    state = Path(args.state).resolve()
    with locked(state):
        if args.cmd == "init":
            if state.exists():
                raise Refused(f"state {state} exists; resume with it, or start a new file for a new go")
            if args.max_runs is None:
                raise Refused("init needs --max-runs: the number in the owner's go")
            if not (args.go or "").strip():
                raise Refused("init needs --go: a quote of or link to the owner's go")
            infra = 2 if args.max_infra_failures is None else args.max_infra_failures
            if infra > 2 and str(infra) not in args.go.replace(",", " ").split():
                raise Refused(f"--max-infra-failures {infra} is above 2: the --go text must name {infra}")
            data = {
                "schema": SCHEMA,
                "go": args.go.strip(),
                "limits": {
                    "max_runs": args.max_runs,
                    "max_cost": args.max_cost,
                    "max_infra_failures": infra,
                },
                "counts": dict.fromkeys(COUNTS, 0),
                "cost": 0,
            }
            save(state, data)
            print(summary(data))
            return GO
        data = load(state)
        check_limits(args, data)
        if args.cmd == "status":
            print(summary(data))
            print(f"go: {data['go']}")
            for line in reached(data):
                print(f"STOP: {line}")
            return GO
        if args.cmd == "start":
            stop = reached(data)
            if stop:
                say("STOP: " + "; ".join(stop) + f" ({summary(data)})")
                return STOP
            data["counts"]["started"] += 1
            save(state, data)
            print(summary(data))
            return GO
        # record
        if data["limits"]["max_cost"] is not None and args.cost is None:
            raise Refused("this pass has a cost limit: record needs --cost")
        total = data["cost"] + (args.cost or 0)
        if not math.isfinite(total):
            raise Refused(f"cost total overflows ({data['cost']:g} + {args.cost:g}); refusing to continue")
        c = data["counts"]
        c[args.outcome] += 1
        c["recorded"] += 1
        c["started"] = max(c["started"], c["recorded"])
        data["cost"] = total
        save(state, data)
        stop = reached(data)
        if stop:
            say("STOP: " + "; ".join(stop) + f" ({summary(data)})")
            return STOP
        print(summary(data))
        return GO


def positive_int(text: str) -> int:
    v = int(text)
    if v < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return v


def amount(text: str) -> float:
    v = float(text)
    if not (math.isfinite(v) and v >= 0):
        raise argparse.ArgumentTypeError("must be a finite number, zero or more")
    return v


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--state", required=True, help="JSON state file, one per owner's go")
    p.add_argument("--max-runs", type=positive_int)
    p.add_argument("--max-cost", type=amount)
    p.add_argument("--max-infra-failures", type=positive_int)
    p.add_argument("--go", help="init: a quote of or link to the owner's go")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the state with its limits")
    sub.add_parser("start", help="reserve one run, or exit 3 at a limit")
    rec = sub.add_parser("record", help="record one finished run")
    rec.add_argument("--outcome", required=True, choices=OUTCOMES)
    rec.add_argument("--cost", type=amount)
    sub.add_parser("status", help="print the counts")
    args = p.parse_args(argv)
    try:
        return run(args)
    except (Refused, OSError) as exc:
        say(f"REFUSED: {exc}")
        return REFUSED


if __name__ == "__main__":
    sys.exit(main())
