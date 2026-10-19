"""Connection state machine + script routing, with BOTH endpoints mocked.

No real robot is used here: RealBackend gets a fake XArmAPI, the sim endpoint
is a fake ArmBackend (plus one integration test through the real RPC layer).
"""

import time

import pytest

from ugclient_core.errors import RpcError
from ugclient_core.robot_backend import ConnectionManager, Mode, RealBackend
from ugclient_core.scripting import ArmFacade, ScriptRunner, ScriptStopped  # noqa: F401


class FakeXArmAPI:
    def __init__(self, ip, fail=False):
        self.ip, self.fail = ip, fail
        self.q = [0.0] * 6
        self.pose = [300.0, 0.0, 200.0, 180.0, 0.0, 0.0]
        self.state, self.disconnected, self.stopped_state = 2, False, None

    def connect(self):
        if self.fail:
            raise ConnectionError("no route to host")
        return 0

    def get_servo_angle(self):
        return (9, None) if self.fail else (0, list(self.q))

    def get_position(self):
        return 0, list(self.pose)

    def get_state(self):
        return (0, self.state)

    def get_mode(self):
        return (0, 0)

    def set_servo_angle(self, angle, **kw):
        self.q = list(angle)
        return 0

    def set_position(self, pose, **kw):
        self.pose = list(pose)
        return 0

    def set_state(self, s):
        self.stopped_state = s
        self.state = s
        return 0

    def motion_enable(self, on):
        return 0

    def clean_error(self):
        return 0

    def clean_warn(self):
        return 0

    def disconnect(self):
        self.disconnected = True


def make_manager(fail=False):
    holder = {}

    def factory(ip, api_factory=None):
        api = FakeXArmAPI(ip, fail=fail)
        holder["api"] = api
        return RealBackend(ip, lambda _ip: api)

    return ConnectionManager(real_factory=factory), holder


def test_failed_connect_stays_in_sim_and_reports_error():
    mgr, _ = make_manager(fail=True)
    with pytest.raises(RpcError):
        mgr.connect_real("10.0.0.9")
    assert mgr.mode is Mode.SIM
    assert mgr.status()["connected"] is False
    assert mgr.sm.last_error  # surfaced to the UI popup


def test_successful_connect_then_clean_disconnect():
    mgr, holder = make_manager()
    backend = mgr.connect_real("10.0.0.9")
    assert mgr.mode is Mode.REAL
    backend.set_joints_deg([1, 2, 3, 4, 5, 6])
    assert holder["api"].q == [1, 2, 3, 4, 5, 6]
    backend.stop()
    assert holder["api"].stopped_state == 4  # STOP = state 4 also on the real path
    mgr.disconnect_real()
    assert mgr.mode is Mode.SIM and holder["api"].disconnected


def test_empty_ip_is_rejected_before_any_transition():
    mgr, _ = make_manager()
    with pytest.raises(RpcError):
        mgr.connect_real("  ")
    assert mgr.mode is Mode.SIM


class FakeBackend:
    name = "fake"

    def __init__(self, label):
        self.label, self.q, self.pose, self._state = label, [0.0] * 6, [300, 0, 200, 180, 0, 0], 2

    def get_joints_deg(self):
        return list(self.q)

    def get_tcp_pose(self):
        return list(self.pose)

    def get_state(self):
        return self._state

    def get_mode(self):
        return 0

    def set_joints_deg(self, q, speed_pct=None):
        self.q = list(q)

    def move_tcp_pose(self, pose, speed_pct=None):
        self.pose = list(pose)

    def stop(self):
        self._state = 4

    def close(self):
        pass


def _run(runner, code, timeout=5.0):
    jid = runner.start(code, timeout_s=timeout)
    for _ in range(100):
        st = runner.status(jid)
        if st["status"] != "running":
            return st
        time.sleep(0.05)
    raise AssertionError("script did not finish")


def test_script_routes_to_whichever_backend_is_active():
    sim, real = FakeBackend("sim"), FakeBackend("real")
    active = {"b": sim}
    runner = ScriptRunner(lambda: active["b"])
    st = _run(runner, "from ugclient_sdk import arm\narm.set_joints([1,2,3,4,5,6])\nprint('joints', arm.get_joints())")
    assert st["status"] == "done" and "joints [1.0" in st["output"]
    assert sim.q == [1, 2, 3, 4, 5, 6] and real.q == [0.0] * 6
    active["b"] = real  # user switched to Real: the SAME script now drives the real endpoint
    st = _run(runner, "arm.move_to([6,5,4,3,2,1])\narm.move_tcp([310,0,200,180,0,0])")
    assert st["status"] == "done"
    assert real.q == [6, 5, 4, 3, 2, 1] and real.pose[0] == 310


def test_stuck_script_is_killable_and_reports_error_and_stdout():
    runner = ScriptRunner(lambda: FakeBackend("sim"))
    jid = runner.start("print('hello', flush=True)\nwhile True:\n    pass", timeout_s=30)
    time.sleep(0.3)
    runner.stop(jid)
    st = runner.status(jid)
    for _ in range(50):
        if st["status"] != "running":
            break
        time.sleep(0.05)
        st = runner.status(jid)
    assert st["status"] == "stopped" and "hello" in st["output"]
    st2 = _run(runner, "raise ValueError('boom')")
    assert st2["status"] == "error" and "boom" in st2["error"]


def test_script_timeout_kills_job():
    runner = ScriptRunner(lambda: FakeBackend("sim"))
    st = _run(runner, "import time\ntime.sleep(30)", timeout=0.5)
    assert st["status"] in ("stopped", "error")  # watchdog stopped it


# --- Integration through the RPC layer (sim endpoint is the real Pinocchio session) ---


def test_rpc_connect_failure_stays_sim(client):
    r = client.raw("robot.connect", {"ip": "192.0.2.1"})
    assert "error" in r  # xarm-python-sdk not installed / unreachable: must not switch
    assert client.call("robot.connection_status")["mode"] == "sim"


def test_rpc_script_runs_against_sim_model(client):
    sid = client.call("robot.load", robot="uf850")["session_id"]
    jid = client.call(
        "script.start", session_id=sid, code="arm.set_joints([0, -30, -60, 0, 60, 0])\nprint(arm.get_tcp())"
    )["job_id"]
    for _ in range(100):
        st = client.call("script.status", job_id=jid)
        if st["status"] != "running":
            break
        time.sleep(0.05)
    assert st["status"] == "done", st
    poll = client.call("robot.poll", session_id=sid)
    assert poll["mode"] == "sim" and poll["q_deg"] == pytest.approx([0, -30, -60, 0, 60, 0])


# --- packaged (PyInstaller) sidecar: script worker dispatch ------------------------------------


def test_worker_cmd_frozen_uses_sidecar_flag(monkeypatch):
    import sys

    from ugclient_core import scripting

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert scripting._worker_cmd("/tmp/x.py") == [sys.executable, "--script-worker", "/tmp/x.py"]
    monkeypatch.delattr(sys, "frozen")
    assert scripting._worker_cmd("/tmp/x.py")[1:4] == ["-u", "-m", "ugclient_core.script_worker"]


def test_main_dispatches_script_worker(monkeypatch):
    from ugclient_core import __main__ as entry
    from ugclient_core import script_worker

    seen = {}
    monkeypatch.setattr(script_worker, "main", lambda argv: seen.setdefault("argv", argv) and 0)
    assert entry.main(["--script-worker", "/tmp/x.py"]) == 0
    assert seen["argv"] == ["/tmp/x.py"]
