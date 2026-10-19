from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["--script-worker"]:
        # Frozen sidecar: scripting.py re-launches this binary as the script worker.
        from .script_worker import main as worker_main

        return worker_main(args[1:])
    ap = argparse.ArgumentParser(prog="ugclient-core")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--token", default=os.environ.get("UGCLIENT_TOKEN"))
    ap.add_argument("--version", action="store_true")
    a = ap.parse_args(args)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")
    if a.version:
        from .rpc import hello_info

        print(hello_info())
        return 0
    if a.host not in ("127.0.0.1", "localhost", "::1"):
        print("refusing to bind a non-loopback address", file=sys.stderr)
        return 2
    from .server import run

    try:
        asyncio.run(run(a.host, a.port, a.token))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
