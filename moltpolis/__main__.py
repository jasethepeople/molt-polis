"""molt-polis — The Living Commonwealth. CLI.

    python -m moltpolis run       [--dir runs/default] [--seed N] [-v]
    python -m moltpolis census    [--dir runs/default]     # exit 1 on FAIL
    python -m moltpolis chronicle [--dir runs/default]
    python -m moltpolis serve     [--dir runs/default] [--port 8600]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_run(args) -> int:
    from .run import run
    run(args.seed, args.dir, args.verbose)
    return 0


def cmd_census(args) -> int:
    from .census import audit, render
    report = audit(args.dir)
    out = Path(args.dir)
    (out / "census-report.json").write_text(json.dumps(report, indent=2))
    md = render(report)
    (out / "census-report.md").write_text(md)
    print(md.splitlines()[2].strip() if len(md.splitlines()) > 2 else "")
    print(f"census -> {out / 'census-report.md'}")
    return 0 if report["summary"]["verdict"] == "PASS" else 1


def cmd_chronicle(args) -> int:
    from .chronicle import render
    out = Path(args.dir) / "chronicle.md"
    out.write_text(render(args.dir))
    print(f"chronicle -> {out}")
    return 0


def cmd_serve(args) -> int:
    from .observatory import serve
    serve(args.dir, args.port)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="moltpolis")
    sub = ap.add_subparsers(required=True)

    r = sub.add_parser("run")
    r.add_argument("--dir", default="runs/default")
    r.add_argument("--seed", type=int, default=7)
    r.add_argument("-v", "--verbose", action="store_true")
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("census")
    c.add_argument("--dir", default="runs/default")
    c.set_defaults(fn=cmd_census)

    ch = sub.add_parser("chronicle")
    ch.add_argument("--dir", default="runs/default")
    ch.set_defaults(fn=cmd_chronicle)

    o = sub.add_parser("serve")
    o.add_argument("--dir", default="runs/default")
    o.add_argument("--port", type=int, default=8600)
    o.set_defaults(fn=cmd_serve)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
