"""Transport-independent JSON-RPC 2.0 dispatcher with token auth and version negotiation."""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import Callable
from typing import Any

from . import API_VERSION, __version__
from .api import connection, dyn, kin, motion, robot, script
from .backend import factory
from .errors import (
    API_VERSION_MISMATCH,
    AUTH_FAILED,
    INTERNAL_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    RpcError,
    invalid_params,
)
from .session import SessionStore

log = logging.getLogger("ugclient_core")
Handler = Callable[[dict[str, Any], SessionStore], Any]

METHODS: dict[str, Handler] = {
    "robot.list": robot.robot_list,
    "robot.info": robot.robot_info,
    "robot.load": robot.robot_load,
    "tcp.set": robot.tcp_set,
    "payload.set": robot.payload_set,
    "kin.fk": kin.fk,
    "kin.ik": kin.ik,
    "kin.jacobian": kin.jacobian,
    "dyn.gravity": dyn.gravity,
    "dyn.rnea": dyn.rnea,
    "dyn.mass_matrix": dyn.mass_matrix,
    "check.pose": dyn.check_pose,
    "motion.jog_tcp": motion.jog_tcp,
    "motion.align": motion.align,
    # Sim/Real connection + backend-routed motion (real path is mocked in tests; needs hardware validation)
    "robot.connect": connection.connect,
    "robot.disconnect": connection.disconnect,
    "robot.connection_status": connection.status,
    "robot.poll": connection.poll,
    "robot.move_joints": connection.move_joints,
    "robot.move_tcp": connection.move_tcp,
    "robot.jog_tcp": connection.jog_tcp,
    "robot.stop_motion": connection.stop_motion,
    "script.start": script.start,
    "script.status": script.status,
    "script.stop": script.stop,
}


def hello_info() -> dict[str, Any]:
    import pinocchio

    return {
        "api_version": API_VERSION,
        "core_version": __version__,
        **factory.catalog().versions(),
        "pinocchio_version": pinocchio.__version__,
        "capabilities": ["kin", "dyn", "motion", "connection", "script"],
        "backend": dict(factory.BACKEND_NAMES),
    }


class Connection:
    """State for one client connection. ``system.hello`` with the token must come first."""

    def __init__(self, token: str, store: SessionStore, on_shutdown: Callable[[], None] | None = None) -> None:
        self.token = token
        self.store = store
        self.authed = False
        self.on_shutdown = on_shutdown

    def _call(self, method: str, params: dict[str, Any]) -> Any:
        if method == "system.hello":
            if not secrets.compare_digest(str(params.get("token", "")), self.token):
                raise RpcError(AUTH_FAILED, "invalid token")
            want = str(params.get("api_version", API_VERSION))
            if want.split(".")[0] != API_VERSION.split(".")[0]:
                raise RpcError(API_VERSION_MISMATCH, f"client wants API {want}, core provides {API_VERSION}")
            self.authed = True
            return hello_info()
        if not self.authed:
            raise RpcError(AUTH_FAILED, "call system.hello with the token first")
        if method == "ping":
            return "pong"
        if method == "system.shutdown":
            if self.on_shutdown:
                self.on_shutdown()
            return {"ok": True}
        fn = METHODS.get(method)
        if fn is None:
            raise RpcError(METHOD_NOT_FOUND, f"method not found: {method}")
        return fn(params, self.store)

    def handle_obj(self, req: Any) -> dict[str, Any] | None:
        rid = req.get("id") if isinstance(req, dict) else None
        try:
            if not isinstance(req, dict) or req.get("jsonrpc") != "2.0" or not isinstance(req.get("method"), str):
                raise RpcError(INVALID_REQUEST, "invalid request")
            params = req.get("params", {})
            if params is None:
                params = {}
            if not isinstance(params, dict):
                raise invalid_params("params must be an object")
            result = self._call(req["method"], params)
            if "id" not in req:
                return None
            return {"jsonrpc": "2.0", "id": rid, "result": result}
        except RpcError as e:
            return {"jsonrpc": "2.0", "id": rid, "error": e.to_dict()}
        except Exception as e:
            log.exception("internal error")
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": INTERNAL_ERROR, "message": str(e)}}

    def handle_text(self, text: str) -> str | None:
        try:
            req = json.loads(text)
        except json.JSONDecodeError:
            return json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": PARSE_ERROR, "message": "parse error"}})
        if isinstance(req, list):
            out = [r for r in (self.handle_obj(x) for x in req) if r is not None]
            return json.dumps(out) if out else None
        resp = self.handle_obj(req)
        return json.dumps(resp) if resp is not None else None
