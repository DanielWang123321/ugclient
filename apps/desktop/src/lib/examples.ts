// Built-in script examples (work identically in Simulation and Real mode).
export const EXAMPLE_SCRIPTS: Record<string, string> = {
  joint: `# Joint move (deg) — Simulation and Real use the same API
from ugclient_sdk import arm

print("start joints:", arm.get_joints())
arm.set_joints([0, -30, -60, 0, 60, 0])
print("after move:", arm.get_joints())
arm.home()
print("home:", arm.get_joints())
`,
  tcp: `# TCP move (mm / deg) — Simulation and Real use the same API
from ugclient_sdk import arm

print("start TCP:", arm.get_tcp())
arm.move_tcp([300, 0, 200, 180, 0, 0])
print("target TCP:", arm.get_tcp())
arm.jog_tcp("z", 10)
print("after Z+10 jog:", arm.get_tcp())
`,
}
