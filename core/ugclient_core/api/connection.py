"""Sim/Real connection + routed motion RPCs.

Routing rule (the single place that decides sim vs real): if the connection
manager is in REAL mode, commands go to the RealBackend and state is read back
from the arm; otherwise they go to the per-session SimBackend. Frontend jog /
Home / Align / STOP and scripts all go through here (or through ArmFacade,
which resolves the same way), so script and UI behaviour are identical.
"""
from __future__ import annotations

from typing import Any

from ..errors import invalid_params
from ..robot_backend import Mode, SimBackend
from ..session import SessionStore
from ._params import number, vec


def _sim(store: SessionStore, params: dict[str, Any]) -> SimBackend:
    s = store.get(params.get("session_id"))
    if s.sim_backend is None:
        s.sim_backend = SimBackend(s)
    return s.sim_backend


def active_backend(store: SessionStore, params: dict[str, Any]):
    """Resolve the backend for this call: real when connected, else the session's sim."""
    if store.connection.mode is Mode.REAL and store.connection.real is not None:
        return store.connection.real
    return _sim(store, params)


def connect(params: dict[str, Any], store: SessionStore) -> dict[str, Any]:
    ip = str(params.get("ip", "")).strip()
    if not ip:
        raise invalid_params("ip is required")
    backend = store.connection.connect_real(ip)  # raises (and stays in sim) on failure
    return {**store.connection.status(), "q_deg": backend.get_joints_deg(),
            "tcp_pose": backend.get_tcp_pose(), "state": backend.get_state(), "robot_mode": backend.get_mode()}


def disconnect(_: dict[str, Any], store: SessionStore) -> dict[str, Any]:
    store.connection.disconnect_real()
    return store.connection.status()


def status(_: dict[str, Any], store: SessionStore) -> dict[str, Any]:
    return store.connection.status()


def poll(params: dict[str, Any], store: SessionStore) -> dict[str, Any]:
    b = active_backend(store, params)
    return {"mode": store.connection.mode.value, "q_deg": b.get_joints_deg(), "tcp_pose": b.get_tcp_pose(),
            "state": b.get_state(), "robot_mode": b.get_mode()}


def move_joints(params: dict[str, Any], store: SessionStore) -> dict[str, Any]:
    b = active_backend(store, params)
    q = vec(params, "q_deg", len(b.get_joints_deg()))
    b.set_joints_deg(q.tolist(), params.get("speed_pct"))
    return {"q_deg": b.get_joints_deg(), "tcp_pose": b.get_tcp_pose()}


def move_tcp(params: dict[str, Any], store: SessionStore) -> dict[str, Any]:
    b = active_backend(store, params)
    pose = vec(params, "pose", 6)
    b.move_tcp_pose(pose.tolist(), params.get("speed_pct"))
    return {"q_deg": b.get_joints_deg(), "tcp_pose": b.get_tcp_pose()}


def jog_tcp(params: dict[str, Any], store: SessionStore) -> dict[str, Any]:
    b = active_backend(store, params)
    axis, delta = str(params.get("axis", "")), number(params, "delta")
    if hasattr(b, "jog_tcp"):
        q = b.jog_tcp(axis, delta)
    else:  # real: Cartesian jog from the read-back pose
        pose = b.get_tcp_pose()
        idx = {"x": 0, "y": 1, "z": 2, "roll": 3, "pitch": 4, "yaw": 5}.get(axis)
        if idx is None:
            raise invalid_params(f"unknown axis {axis!r}")
        pose[idx] += delta
        b.move_tcp_pose(pose)
        q = b.get_joints_deg()
    return {"q_deg": q, "tcp_pose": b.get_tcp_pose()}


def stop_motion(params: dict[str, Any], store: SessionStore) -> dict[str, Any]:
    active_backend(store, params).stop()
    return {"ok": True, "state": 4}
