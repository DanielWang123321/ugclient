"""Script RPCs: script.start / script.status / script.stop (see scripting.py)."""

from __future__ import annotations

from typing import Any

from ..errors import invalid_params
from ..session import SessionStore
from .connection import active_backend


def _runner(store: SessionStore):
    if store.script_runner is None:
        from ..scripting import ScriptRunner

        # Backend is resolved per-call (not captured) so a script follows sim/real switches.
        store.script_runner = ScriptRunner(lambda: active_backend(store, {"session_id": store.last_session_id}))
    return store.script_runner


def start(params: dict[str, Any], store: SessionStore) -> dict[str, Any]:
    code = params.get("code")
    if not isinstance(code, str) or not code.strip():
        raise invalid_params("code is required")
    if params.get("session_id"):
        store.last_session_id = str(params["session_id"])
    return {"job_id": _runner(store).start(code, float(params.get("timeout_s", 30.0)))}


def status(params: dict[str, Any], store: SessionStore) -> dict[str, Any]:
    return _runner(store).status(str(params.get("job_id", "")))


def stop(params: dict[str, Any], store: SessionStore) -> dict[str, Any]:
    _runner(store).stop(str(params.get("job_id", "")))
    return {"ok": True}
