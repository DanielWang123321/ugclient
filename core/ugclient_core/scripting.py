"""Script execution: user Python runs in a killable worker subprocess (script_worker.py).

Scripts may use either style (identical behaviour in sim and real modes)::

    arm.set_joints([0, -30, -60, 0, 60, 0])      # preloaded object
    from ugclient_sdk import arm; arm.move_tcp([300, 0, 200, 180, 0, 0])

The worker talks back over a loopback socket; the parent executes each arm call
on the *currently active* backend, so flipping Sim/Real re-routes a running
script UI's next call and the same script works in both modes. Stop / timeout
terminates the subprocess, which kills even code blocked in time.sleep().
Only one script runs at a time.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import uuid
from pathlib import Path
from typing import Any, Callable

from .errors import BACKEND_UNAVAILABLE, RpcError


class ScriptStopped(Exception):
    pass


class ArmFacade:
    """Parent-side `arm` implementation: delegates to whichever backend is active."""

    _ALLOWED = {"get_joints", "get_tcp", "get_state", "set_joints", "move_to", "move_tcp", "jog_tcp", "home", "stop"}

    def __init__(self, backend_getter: Callable[[], Any], stop_event: threading.Event | None = None) -> None:
        self._get = backend_getter
        self._stop = stop_event or threading.Event()

    def dispatch(self, method: str, args: list) -> Any:
        if method not in self._ALLOWED:
            raise RpcError(BACKEND_UNAVAILABLE, f"arm method {method!r} is not available to scripts")
        return getattr(self, method)(*args)

    def _b(self):
        if self._stop.is_set():
            raise ScriptStopped("script stopped")
        return self._get()

    def get_joints(self): return self._b().get_joints_deg()
    def get_tcp(self): return self._b().get_tcp_pose()
    def get_state(self): return self._b().get_state()

    def set_joints(self, q_deg, speed_pct=None):
        b = self._b(); b.set_joints_deg([float(v) for v in q_deg], speed_pct); return b.get_joints_deg()

    def move_to(self, q_deg, speed_pct=None):
        return self.set_joints(q_deg, speed_pct)

    def move_tcp(self, pose, speed_pct=None):
        b = self._b(); b.move_tcp_pose([float(v) for v in pose], speed_pct); return b.get_tcp_pose()

    def jog_tcp(self, axis: str, delta: float):
        b = self._b()
        if hasattr(b, "jog_tcp"):
            return b.jog_tcp(axis, float(delta))
        pose = b.get_tcp_pose()
        idx = {"x": 0, "y": 1, "z": 2, "roll": 3, "pitch": 4, "yaw": 5}[axis]
        pose[idx] += float(delta)
        b.move_tcp_pose(pose)
        return b.get_joints_deg()

    def home(self):
        b = self._b(); return self.set_joints([0.0] * len(b.get_joints_deg()))

    def stop(self):
        self._b().stop()


def install_sdk_module(arm) -> types.ModuleType:  # kept for in-process users/tests
    mod = types.ModuleType("ugclient_sdk")
    mod.arm = arm  # type: ignore[attr-defined]
    sys.modules["ugclient_sdk"] = mod
    return mod


class ScriptRunner:
    def __init__(self, backend_getter: Callable[[], Any]) -> None:
        self._get_backend = backend_getter
        self._jobs: dict[str, dict[str, Any]] = {}
        self._current: str | None = None

    # -- arm socket server (one per running script) ---------------------------------
    def _serve_arm(self, job, server: socket.socket) -> None:
        try:
            conn, _ = server.accept()
        except OSError:
            return
        facade = ArmFacade(self._get_backend, job["stop"])
        r, w = conn.makefile("r", encoding="utf-8"), conn.makefile("w", encoding="utf-8")
        for line in r:
            try:
                req = json.loads(line)
                result = facade.dispatch(str(req.get("method", "")), req.get("args") or [])
                resp = {"ok": True, "result": result}
            except Exception as e:  # report backend/script errors to the worker, keep serving
                resp = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            try:
                w.write(json.dumps(resp) + "\n"); w.flush()
            except OSError:
                break

    def start(self, code: str, timeout_s: float = 30.0) -> str:
        if self._current and self._jobs[self._current]["status"] == "running":
            raise RpcError(BACKEND_UNAVAILABLE, "a script is already running (stop it first)")
        job_id = uuid.uuid4().hex[:12]
        job: dict[str, Any] = {"id": job_id, "status": "running", "output": [], "error": "",
                               "lock": threading.Lock(), "stop": threading.Event(), "started": time.time()}
        self._jobs[job_id] = job
        self._current = job_id

        server = socket.socket()
        server.bind(("127.0.0.1", 0)); server.listen(1)
        job["server"] = server
        threading.Thread(target=self._serve_arm, args=(job, server), daemon=True).start()

        fd, path = tempfile.mkstemp(suffix=".py", prefix="ugclient-script-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)
        job["file"] = path
        env = {**os.environ, "UGCLIENT_ARM_SOCKET": f"127.0.0.1:{server.getsockname()[1]}",
               "PYTHONPATH": os.pathsep.join([str(Path(__file__).resolve().parent.parent),
                                               os.environ.get("PYTHONPATH", "")])}
        proc = subprocess.Popen([sys.executable, "-u", "-m", "ugclient_core.script_worker", path],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        job["proc"] = proc

        def collect() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                with job["lock"]:
                    job["output"].append(line)
                    if sum(len(x) for x in job["output"]) > 200_000:
                        job["output"] = job["output"][-500:]
            code_ = proc.wait()
            server.close()
            Path(path).unlink(missing_ok=True)
            if job["status"] == "running":
                if job["stop"].is_set():
                    job["status"] = "stopped"
                elif code_ == 0:
                    job["status"] = "done"
                else:
                    job["status"] = "error"
                    lines = [ln.strip() for ln in "".join(job["output"]).splitlines() if ln.strip()]
                    detail = lines[-1] if lines else ""
                    job["error"] = f"script exited with code {code_}: {detail}" if detail else f"script exited with code {code_}"

        threading.Thread(target=collect, daemon=True).start()

        def watchdog() -> None:
            try:
                proc.wait(timeout=max(0.1, float(timeout_s)))
            except subprocess.TimeoutExpired:
                job["error"] = f"timeout after {timeout_s:g} s"
                self.stop(job_id)

        threading.Thread(target=watchdog, daemon=True).start()
        return job_id

    def stop(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            raise RpcError(BACKEND_UNAVAILABLE, f"script job {job_id!r} not found")
        job["stop"].set()
        proc = job.get("proc")
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    def status(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if not job:
            raise RpcError(BACKEND_UNAVAILABLE, f"script job {job_id!r} not found")
        with job["lock"]:
            out = "".join(job["output"])
        return {"job_id": job_id, "status": job["status"], "output": out, "error": job["error"],
                "elapsed_s": round(time.time() - job["started"], 3)}
