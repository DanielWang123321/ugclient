"""Per-robot sessions holding cached Pinocchio models, TCP and payload state."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import numpy as np

from .backend import factory
from .backend.factory import Backends
from .errors import SESSION_NOT_FOUND, RpcError


@dataclass
class RobotSession:
    session_id: str
    backends: Backends
    tcp_offset_si: np.ndarray = field(default_factory=lambda: np.zeros(6))
    payload: dict = field(default_factory=lambda: {"mass_kg": 0.0, "com_mm": [0.0, 0.0, 0.0]})
    sim_backend: object = None  # robot_backend.SimBackend, created lazily (avoids an import cycle)

    @property
    def info(self):
        return self.backends.info

    @property
    def kin(self):
        return self.backends.kin

    @property
    def dyn(self):
        return self.backends.dyn


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, RobotSession] = {}
        # Sim/Real connection + script runner live on the store so every RPC
        # handler (and tests constructing a bare store) sees the same routing.
        from .robot_backend import ConnectionManager

        self.connection = ConnectionManager()
        self.script_runner = None
        self.last_session_id: str | None = None

    def create(self, key: str, end_effector: str = "none") -> RobotSession:
        info = factory.catalog().info(key, end_effector)
        s = RobotSession(session_id=uuid.uuid4().hex[:12], backends=factory.create(info))
        self._sessions[s.session_id] = s
        self.last_session_id = s.session_id
        return s

    def get(self, session_id: object) -> RobotSession:
        s = self._sessions.get(str(session_id))
        if s is None:
            raise RpcError(SESSION_NOT_FOUND, f"session {session_id!r} not found")
        return s
