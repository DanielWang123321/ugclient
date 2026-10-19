"""Script worker process: executes one user script with an `arm` proxy.

Run as ``python -m ugclient_core.script_worker <codefile>`` (or, in the frozen
sidecar, ``ugclient-core --script-worker <codefile>``). The parent sidecar
passes UGCLIENT_ARM_SOCKET=host:port; every arm call is one JSON line over that
socket and is executed by the parent against the active (sim or real) backend.
This process can therefore be terminated by the UI at any time, even if the
user code is blocked in time.sleep() or an SDK call.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import types


class _ArmProxy:
    def __init__(self) -> None:
        host, port = os.environ["UGCLIENT_ARM_SOCKET"].rsplit(":", 1)
        self._sock = socket.create_connection((host, int(port)), timeout=5)
        self._r = self._sock.makefile("r", encoding="utf-8")
        self._w = self._sock.makefile("w", encoding="utf-8")

    def _call(self, method: str, *args):
        self._w.write(json.dumps({"method": method, "args": list(args)}) + "\n")
        self._w.flush()
        line = self._r.readline()
        if not line:
            raise RuntimeError("arm channel closed (script stopped?)")
        resp = json.loads(line)
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "arm call failed"))
        return resp.get("result")

    def get_joints(self):
        return self._call("get_joints")

    def get_tcp(self):
        return self._call("get_tcp")

    def get_state(self):
        return self._call("get_state")

    def set_joints(self, q_deg, speed_pct=None):
        return self._call("set_joints", list(q_deg), speed_pct)

    def move_to(self, q_deg, speed_pct=None):
        return self._call("move_to", list(q_deg), speed_pct)

    def move_tcp(self, pose, speed_pct=None):
        return self._call("move_tcp", list(pose), speed_pct)

    def jog_tcp(self, axis, delta):
        return self._call("jog_tcp", axis, delta)

    def home(self):
        return self._call("home")

    def stop(self):
        return self._call("stop")


def main(argv: list[str] | None = None) -> int:
    path = (argv if argv is not None else sys.argv[1:])[0]
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)  # console output streams live, also when frozen
        except (AttributeError, ValueError):
            pass
    arm = _ArmProxy()
    mod = types.ModuleType("ugclient_sdk")
    mod.arm = arm  # type: ignore[attr-defined]
    sys.modules["ugclient_sdk"] = mod
    with open(path, encoding="utf-8") as f:
        code = f.read()
    exec(compile(code, path, "exec"), {"__name__": "__main__", "__builtins__": __builtins__, "arm": arm})  # noqa: S102
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
