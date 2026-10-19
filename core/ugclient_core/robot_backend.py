"""Robot backends behind one interface: simulation (Pinocchio session) and real robot (xArm SDK).

The real-robot path is deliberately isolated here: it is the ONLY module that imports
``xarm`` (lazily, inside the default factory). Everything else talks to the
:class:`ArmBackend` protocol, so tests can inject fakes for both endpoints and no
real-robot code leaks into the sim-only kinematics / motion modules.
Units at this boundary: joints deg, TCP pose [x,y,z mm, roll,pitch,yaw deg].
"""
from __future__ import annotations

import enum
from typing import Any, Callable, Protocol

import numpy as np

from . import units
from .errors import BACKEND_UNAVAILABLE, RpcError


class Mode(enum.Enum):
    SIM = "sim"
    CONNECTING = "connecting"
    REAL = "real"
    DISCONNECTING = "disconnecting"


class ConnectionStateMachine:
    """Sim <-> Real transitions. Only a *successful* connect reaches REAL.

    sim --begin_connect--> connecting --connect_ok--> real
    connecting --connect_fail--> sim
    real --begin_disconnect--> disconnecting --> sim
    """

    _ALLOWED = {
        Mode.SIM: {Mode.CONNECTING},
        Mode.CONNECTING: {Mode.REAL, Mode.SIM},
        Mode.REAL: {Mode.DISCONNECTING},
        Mode.DISCONNECTING: {Mode.SIM, Mode.REAL},
    }

    def __init__(self) -> None:
        self.mode = Mode.SIM
        self.ip = ""
        self.last_error = ""

    def transition(self, to: Mode) -> None:
        if to not in self._ALLOWED[self.mode]:
            raise RpcError(BACKEND_UNAVAILABLE, f"invalid mode transition {self.mode.value} -> {to.value}")
        self.mode = to

    def begin_connect(self, ip: str) -> None:
        self.transition(Mode.CONNECTING)
        self.ip, self.last_error = ip, ""

    def connect_ok(self) -> None:
        self.transition(Mode.REAL)

    def connect_fail(self, msg: str) -> None:
        self.transition(Mode.SIM)
        self.last_error = msg


class ArmBackend(Protocol):
    name: str
    def get_joints_deg(self) -> list[float]: ...
    def get_tcp_pose(self) -> list[float]: ...
    def get_state(self) -> int: ...
    def get_mode(self) -> int: ...
    def set_joints_deg(self, q_deg: list[float], speed_pct: float | None = None) -> None: ...
    def move_tcp_pose(self, pose: list[float], speed_pct: float | None = None) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


class SimBackend:
    """ArmBackend over a Pinocchio RobotSession. Holds the sim's current q."""

    name = "sim"

    def __init__(self, session) -> None:  # RobotSession (avoid import cycle at runtime typing only)
        self._s = session
        self._q_deg = [0.0] * session.info.dof
        self._state = 2

    def get_joints_deg(self) -> list[float]:
        return list(self._q_deg)

    def get_tcp_pose(self) -> list[float]:
        q = units.deg_to_rad(np.array(self._q_deg))
        return units.pose_si_to_api(self._s.kin.fk(q, "tcp"))

    def get_state(self) -> int:
        return self._state

    def get_mode(self) -> int:
        return 0

    def set_joints_deg(self, q_deg, speed_pct=None) -> None:
        if len(q_deg) != self._s.info.dof:
            raise RpcError(BACKEND_UNAVAILABLE, f"expected {self._s.info.dof} joints, got {len(q_deg)}")
        self._q_deg = [float(v) for v in q_deg]
        self._state = 2

    def move_tcp_pose(self, pose, speed_pct=None) -> None:
        from .api.kin import solve_ik  # local: kin imports session types only

        sols = self._s.kin.ik(units.pose_api_to_si(np.array(pose, dtype=float)), "tcp",
                              units.deg_to_rad(np.array(self._q_deg)), "nearest", 1e-5, np.radians(0.01))
        if not sols:
            from .errors import IK_NOT_CONVERGED
            raise RpcError(IK_NOT_CONVERGED, "no IK solution found (target may be unreachable)")
        self._q_deg = units.rad_to_deg(sols[0].q).tolist()
        self._state = 2

    def jog_tcp(self, axis: str, delta: float) -> list[float]:
        """One base-frame TCP increment; returns new joints. Reuses the sim jog solver."""
        from .api.motion import jog_tcp as _jog

        r = _jog({"session_id": self._s.session_id, "q_deg": list(self._q_deg), "axis": axis, "delta": delta},
                 _SessionLookup(self._s))
        self._q_deg = [float(v) for v in r["q_deg"]]
        return list(self._q_deg)

    def stop(self) -> None:
        self._state = 4  # xArm-style: STOP = state 4 (same convention as the sim UI)

    def close(self) -> None:
        pass


class _SessionLookup:
    """Minimal store shim so api.motion.jog_tcp can find the one sim session."""
    def __init__(self, session): self._s = session
    def get(self, _sid): return self._s


def _default_xarm_factory(ip: str):
    try:
        from xarm.wrapper import XArmAPI  # xarm-python-sdk (optional dependency: pip install ugclient-core[real])
    except ImportError as e:
        raise RpcError(BACKEND_UNAVAILABLE,
                       "xarm-python-sdk is not installed in the sidecar (install ugclient-core[real])") from e
    return XArmAPI(ip)


class RealBackend:
    """ArmBackend over xarm-python-sdk. `api_factory(ip) -> XArmAPI-like` is injectable for tests.

    NOT validated against hardware in this change (no robot available): only mocked.
    """

    name = "real"

    def __init__(self, ip: str, api_factory: Callable[[str], Any] | None = None) -> None:
        self.ip = ip
        self._api = (api_factory or _default_xarm_factory)(ip)

    # xArm SDK returns (code, value) tuples; code != 0 is an error.
    @staticmethod
    def _unwrap(ret, what: str):
        if isinstance(ret, tuple):
            code, val = ret[0], ret[1] if len(ret) > 1 else None
            if code != 0:
                raise RpcError(BACKEND_UNAVAILABLE, f"real robot {what} failed (SDK code {code})")
            return val
        return ret

    def connect(self) -> None:
        api = self._api
        try:
            if hasattr(api, "connect"):
                self._unwrap(api.connect(), "connect")
            # A connection check that actually talks to the arm: state + joints must read back.
            _ = self.get_state()
            _ = self.get_joints_deg()
            if hasattr(api, "clean_error"): api.clean_error()
            if hasattr(api, "clean_warn"): api.clean_warn()
            if hasattr(api, "motion_enable"): api.motion_enable(True)
            if hasattr(api, "set_state"): api.set_state(0)
        except RpcError:
            raise
        except Exception as e:  # SDK raises / returns odd types depending on version
            raise RpcError(BACKEND_UNAVAILABLE, f"cannot connect to robot at {self.ip}: {e}") from e

    def get_joints_deg(self) -> list[float]:
        return [float(v) for v in self._unwrap(self._api.get_servo_angle(), "get_servo_angle")]

    def get_tcp_pose(self) -> list[float]:
        return [float(v) for v in self._unwrap(self._api.get_position(), "get_position")]

    def get_state(self) -> int:
        return int(self._unwrap(self._api.get_state(), "get_state"))

    def get_mode(self) -> int:
        try:
            return int(self._unwrap(self._api.get_mode(), "get_mode"))
        except Exception:
            return 0

    def set_joints_deg(self, q_deg, speed_pct=None) -> None:
        kwargs: dict[str, Any] = {"is_radian": False, "wait": True}
        if speed_pct is not None and hasattr(self._api, "set_servo_angle"):
            pass  # speed mapping is model-dependent; left to SDK defaults until hardware validation
        self._unwrap(self._api.set_servo_angle(angle=[float(v) for v in q_deg], **kwargs), "set_servo_angle")

    def move_tcp_pose(self, pose, speed_pct=None) -> None:
        pose = [float(v) for v in pose]
        try:
            ret = self._api.set_position(pose, wait=True)
        except TypeError:
            ret = self._api.set_position(x=pose[0], y=pose[1], z=pose[2],
                                         roll=pose[3], pitch=pose[4], yaw=pose[5], wait=True)
        self._unwrap(ret, "set_position")

    def stop(self) -> None:
        if hasattr(self._api, "set_state"):
            self._api.set_state(4)  # STOP = state 4, same convention as sim
        elif hasattr(self._api, "emergency_stop"):
            self._api.emergency_stop()

    def close(self) -> None:
        try:
            self.stop()
        finally:
            if hasattr(self._api, "disconnect"):
                self._api.disconnect()


class ConnectionManager:
    """Owns the state machine + the active real backend (sim backend is per-session, see api)."""

    def __init__(self, real_factory: Callable[[str, Any], RealBackend] | None = None) -> None:
        self.sm = ConnectionStateMachine()
        self.real: RealBackend | None = None
        self._real_factory = real_factory or (lambda ip, factory=None: RealBackend(ip, factory))

    @property
    def mode(self) -> Mode:
        return self.sm.mode

    def connect_real(self, ip: str, api_factory=None) -> RealBackend:
        ip = (ip or "").strip()
        if not ip:
            raise RpcError(BACKEND_UNAVAILABLE, "robot IP is required to switch to Real mode")
        self.sm.begin_connect(ip)
        try:
            backend = self._real_factory(ip, api_factory) if api_factory else self._real_factory(ip)
            backend.connect()
        except Exception as e:
            self.sm.connect_fail(str(e))
            raise
        self.real = backend
        self.sm.connect_ok()
        return backend

    def disconnect_real(self) -> None:
        if self.sm.mode is Mode.SIM:
            return
        self.sm.transition(Mode.DISCONNECTING)
        try:
            if self.real:
                self.real.close()
        finally:
            self.real = None
            self.sm.transition(Mode.SIM)

    def status(self) -> dict[str, Any]:
        return {"mode": self.sm.mode.value, "ip": self.sm.ip, "last_error": self.sm.last_error,
                "connected": self.sm.mode is Mode.REAL}
