import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('element-plus', async (orig) => ({ ...(await orig<object>()), ElMessageBox: { alert: vi.fn(async () => 'confirm') } }))

import { useEngineStore } from '../src/stores/engine'
import { useRobotStore } from '../src/stores/robot'
import { useMotionStore } from '../src/stores/motion'
import { useConnectionStore } from '../src/stores/connection'
import { useSettingsStore, SETTINGS_KEY } from '../src/stores/settings'
import { RpcClient } from '../src/rpc/client'
import { FakeWs, HELLO } from './fakeEngine'
import { EXAMPLE_SCRIPTS } from '../src/lib/examples'

const MODEL: [number, number][] = [[-360, 360], [-150, 150], [-3.5, 300], [-360, 360], [-124, 124], [-360, 360]]
const LOAD = {
  key: 'uf850', robot_name: 'uf850', dof: 6, session_id: 's1',
  joint_names: ['j1', 'j2', 'j3', 'j4', 'j5', 'j6'], effort_limits_nm: [1, 1, 1, 1, 1, 1],
  visual_urdf_relpath: 'x.urdf', home_q_deg: [0, 0, 0, 0, 0, 0], end_effectors: ['none'],
  limits_deg: MODEL, default_q_deg: [0, 0, 0, 0, 0, 0], end_effector: 'none',
  default_tcp_offset: [0, 0, 0, 0, 0, 0], default_tcp_source: 'none',
}
const tcpOf = (q: number[]) => [0, 0, 200 + q[1], 180, 0, 0]

function boot(realOk: boolean) {
  const handlers = {
    'system.hello': () => HELLO,
    'robot.load': () => LOAD,
    'tcp.set': () => ({ ok: true }),
    'payload.set': () => ({ ok: true }),
    'kin.fk': (p: Record<string, unknown>) => ({ tcp_pose: tcpOf(p.q_deg as number[]), flange_pose: tcpOf(p.q_deg as number[]) }),
    'dyn.gravity': () => ({ tau_nm: [0, 0, 0, 0, 0, 0], effort_limits_nm: [1, 1, 1, 1, 1, 1], utilization: [0, 0, 0, 0, 0, 0], over_limit: [] }),
    'robot.connect': () => {
      if (!realOk) throw { code: 5001, message: 'cannot connect' }
      return { mode: 'real', ip: '10.0.0.9', connected: true, q_deg: [5, 0, 0, 0, 0, 0], tcp_pose: tcpOf([5, 0, 0, 0, 0, 0]), state: 2, robot_mode: 0 }
    },
    'robot.disconnect': () => ({ mode: 'sim', ip: '', connected: false }),
    'robot.poll': () => ({ mode: 'real', q_deg: [7, 0, 0, 0, 0, 0], tcp_pose: tcpOf([7, 0, 0, 0, 0, 0]), state: 2, robot_mode: 0 }),
    'robot.move_joints': (p: Record<string, unknown>) => ({ q_deg: p.q_deg, tcp_pose: tcpOf(p.q_deg as number[]) }),
    'robot.jog_tcp': (p: Record<string, unknown>) => ({ q_deg: [Number(p.delta), 0, 0, 0, 0, 0], tcp_pose: tcpOf([0, 0, 0, 0, 0, 0]) }),
    'robot.stop_motion': () => ({ ok: true, state: 4 }),
    'script.start': () => ({ job_id: 'job1' }),
    'script.status': () => ({ job_id: 'job1', status: 'done', output: 'ok\n', error: '', elapsed_s: 0.1 }),
  }
  let ws: FakeWs
  return (async () => {
    await useEngineStore().connect(async () => ({ port: 1, token: 't' }), () => new RpcClient(() => (ws = new FakeWs(handlers))))
    await useRobotStore().load('uf850')
    return ws!
  })()
}

describe('sim/real connection', () => {
  beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })

  it('failed connect stays in simulation and records the error', async () => {
    await boot(false)
    const conn = useConnectionStore()
    expect(await conn.connectReal('10.0.0.9')).toBe(false)
    expect(conn.mode).toBe('sim')
    expect(conn.lastError).toMatch(/cannot connect/)
  })

  it('successful connect flips to real, persists IP, and poll reads back joints', async () => {
    await boot(true)
    const conn = useConnectionStore()
    const robot = useRobotStore()
    expect(await conn.connectReal('10.0.0.9')).toBe(true)
    expect(conn.mode).toBe('real')
    expect(robot.q[0]).toBe(5) // read back from the arm at connect time
    expect(useSettingsStore().robotIp).toBe('10.0.0.9')
    expect(JSON.parse(localStorage.getItem(SETTINGS_KEY)!).robotIp).toBe('10.0.0.9')
    await conn.disconnectReal()
    expect(conn.mode).toBe('sim')
  })

  it('jog and STOP route to the real arm while in real mode (mocked endpoint)', async () => {
    const ws = await boot(true)
    const conn = useConnectionStore(); const motion = useMotionStore(); const robot = useRobotStore()
    await conn.connectReal('10.0.0.9')
    await robot.setQ([0, 0, 0, 0, 0, 0])
    await motion.step({ kind: 'joint', index: 0 }, 1)
    expect(ws.sent.find((c) => c.method === 'robot.move_joints')).toBeTruthy()
    expect(ws.sent.find((c) => c.method === 'motion.jog_tcp')).toBeFalsy() // no sim-only jog RPC in real mode
    motion.stop()
    expect(ws.sent.find((c) => c.method === 'robot.stop_motion')).toBeTruthy()
  })

  it('script RPC surface and examples use the same arm API for both modes', async () => {
    const ws = await boot(true)
    const engine = useEngineStore()
    const { job_id } = await engine.call<{ job_id: string }>('script.start', { session_id: 's1', code: EXAMPLE_SCRIPTS.joint })
    const st = await engine.call<{ status: string; output: string }>('script.status', { job_id })
    expect(st.status).toBe('done')
    expect(EXAMPLE_SCRIPTS.joint).toContain('arm.set_joints')
    expect(EXAMPLE_SCRIPTS.tcp).toContain('arm.move_tcp')
    expect(ws.sent.map((c) => c.method)).toContain('script.start')
  })
})

describe('script page (sim)', () => {
  beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })
  it('pose moved by a script in simulation is mirrored into the UI and kept on the control page', async () => {
    const ws = await boot(true)
    const { mount } = await import('@vue/test-utils')
    const ScriptView = (await import('../src/views/ScriptView.vue')).default
    const { i18n } = await import('../src/i18n')
    const w = mount(ScriptView, { global: { plugins: [i18n] } })
    const vm = w.vm as unknown as { run: () => Promise<void>; poll: () => Promise<void> }
    await vm.run()
    await vm.poll()
    // sim pose sync: UI pose pushed before start, then read back from robot.poll (q[0] = 7 in the fake)
    expect(ws.sent.find((c) => c.method === 'robot.move_joints')).toBeTruthy()
    expect(useRobotStore().q[0]).toBe(7)
    w.unmount() // leaving the script page keeps the store pose
    expect(useRobotStore().q[0]).toBe(7)
  })
  it('Run/Stop sit at the left of the toolbar, before the example/open/save controls', async () => {
    await boot(true)
    const { mount } = await import('@vue/test-utils')
    const ScriptView = (await import('../src/views/ScriptView.vue')).default
    const { i18n } = await import('../src/i18n')
    const w = mount(ScriptView, { global: { plugins: [i18n] } })
    const html = w.find('.toolbar').html()
    expect(html.indexOf('script-run')).toBeLessThan(html.indexOf('script-open'))
    expect(html.indexOf('script-stop')).toBeLessThan(html.indexOf('script-open'))
  })
})
