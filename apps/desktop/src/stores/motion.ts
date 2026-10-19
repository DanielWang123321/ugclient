// Simulated motion control (no real robot): click = one step, hold = continuous, release/STOP = state 4.
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useEngineStore } from './engine'
import { useRobotStore } from './robot'
import { i18n } from '../i18n'
import { RpcError } from '../rpc/client'
import type { FkResult, JogResult } from '../rpc/types'
import { MOTION, STATE, approach, rate, stepSize, type JogTarget } from '../lib/motion'
import { checkBoundary, hasTcpBounds, violationAxis, type Boundary, type Violation } from '../lib/boundary'
import { useSettingsStore } from './settings'
import { useConnectionStore } from './connection'
import { fmt } from '../lib/units'

const IK_UNREACHABLE = 3001
const IK_NOT_CONVERGED = 3002
const JOINT_LIMIT = 3003

const MAX_DT_S = 0.5

class MotionError extends Error {}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now())

export const useMotionStore = defineStore('motion', () => {
  const engine = useEngineStore()
  const robot = useRobotStore()
  const speed = ref<number>(MOTION.defaultSpeedPct)
  const state = ref<number>(STATE.ready)
  const active = ref<JogTarget | null>(null)
  let token = 0

  const settings = useSettingsStore()
  const conn = useConnectionStore()

  function boundary(): Boundary {
    const model = robot.info?.limits_deg ?? robot.q.map(() => [-360, 360] as [number, number])
    return settings.boundaryFor(robot.key, model)
  }

  function violationError(v: Violation): MotionError {
    const t = i18n.global.t
    const unit = v.kind === 'joint' ? '°' : ' mm'
    return new MotionError(t('motion.errBoundary', { axis: violationAxis(v), side: t(`motion.${v.side}`), limit: `${fmt(v.limit, 1)}${unit}` }))
  }

  /** Throw if moving to nextQ (and its TCP pose) leaves the safety boundary. */
  async function guard(nextQ: number[], nextTcp?: number[] | null) {
    const b = boundary()
    let tcp = nextTcp ?? null
    if (!tcp && hasTcpBounds(b)) {
      tcp = (await engine.call<FkResult>('kin.fk', { session_id: robot.sessionId, q_deg: nextQ })).tcp_pose
    }
    const v = checkBoundary(b, robot.q, nextQ, robot.fk?.tcp_pose ?? null, tcp)
    if (v) throw violationError(v)
  }

  function describe(e: unknown): string {
    const t = i18n.global.t
    if (e instanceof MotionError) return e.message
    if (e instanceof RpcError) {
      if (e.code === JOINT_LIMIT) return t('motion.errLimit')
      if (e.code === IK_UNREACHABLE || e.code === IK_NOT_CONVERGED) return t('motion.errUnreachable')
    }
    return e instanceof Error ? e.message : String(e)
  }

  /** Apply one increment (mm or deg, signed). Throws MotionError/RpcError when the move is impossible. */
  async function applyDelta(t: JogTarget, delta: number) {
    if (conn.isReal()) {
      // Real mode: same jog semantics, executed by the sidecar on the arm; state is read back.
      if (t.kind === 'joint') {
        const want = [...robot.q]; want[t.index] += delta
        await guard(want)
        const r = await engine.call<JogResult>('robot.move_joints', { session_id: robot.sessionId, q_deg: want })
        void robot.setQ(r.q_deg); return
      }
      const r = await engine.call<JogResult>('robot.jog_tcp', { session_id: robot.sessionId, axis: t.axis, delta })
      await guard(r.q_deg, r.tcp_pose)
      void robot.setQ(r.q_deg); return
    }
    if (t.kind === 'joint') {
      const i = t.index
      const want = [...robot.q]
      want[i] += delta
      const v = checkBoundary(boundary(), robot.q, want)
      if (v?.kind === 'joint') {
        // stop exactly on the bound if we were inside it, then report
        const inside = v.side === 'max' ? robot.q[i] <= v.limit : robot.q[i] >= v.limit
        if (inside) {
          const onBound = [...robot.q]
          onBound[i] = v.limit
          await guard(onBound)
          void robot.setQ(onBound)
        }
        throw violationError(v)
      }
      await guard(want)
      void robot.setQ(want)
      return
    }
    const r = await engine.call<JogResult>('motion.jog_tcp', {
      session_id: robot.sessionId, q_deg: [...robot.q], axis: t.axis, delta,
    })
    await guard(r.q_deg, r.tcp_pose)
    void robot.setQ(r.q_deg)
  }

  async function fail(e: unknown) {
    stop()
    try {
      await ElMessageBox.alert(describe(e), i18n.global.t('motion.errTitle'), { type: 'warning' })
    } catch {
      /* dialog closed */
    }
  }

  /** Single click: one step (Settings > Jog, default 1 mm / 1 deg). */
  async function step(t: JogTarget, dir: 1 | -1) {
    if (!robot.sessionId) return
    const my = ++token
    state.value = STATE.moving
    active.value = t
    try {
      await applyDelta(t, dir * stepSize(t, { mm: settings.stepMm, deg: settings.stepDeg }))
      if (my === token) stop()
    } catch (e) {
      await fail(e)
    }
  }

  /** Press-and-hold: move continuously until stop(). */
  async function startContinuous(t: JogTarget, dir: 1 | -1) {
    if (!robot.sessionId) return
    const my = ++token
    state.value = STATE.moving
    active.value = t
    let last = now()
    while (my === token) {
      await sleep(MOTION.tickMs)
      if (my !== token) break
      const tNow = now()
      const dt = Math.min(MAX_DT_S, (tNow - last) / 1000) // cap so a stalled tick never jumps far
      last = tNow
      try {
        await applyDelta(t, dir * rate(t, speed.value) * dt)
      } catch (e) {
        if (my === token) await fail(e)
        return
      }
    }
  }

  /** Interpolate all joints to a target at the joint speed (Home / Align). */
  async function moveTo(target: number[]) {
    if (conn.isReal()) {
      const my = ++token
      state.value = STATE.moving; active.value = null
      try {
        await guard(target)
        const r = await engine.call<JogResult>('robot.move_joints', { session_id: robot.sessionId, q_deg: target })
        if (my === token) { void robot.setQ(r.q_deg); stop() }
      } catch (e) { if (my === token) await fail(e) }
      return
    }
    const my = ++token
    state.value = STATE.moving
    active.value = null
    let last = now()
    while (my === token) {
      await sleep(MOTION.tickMs)
      if (my !== token) return
      const tNow = now()
      const dt = Math.min(MAX_DT_S, (tNow - last) / 1000)
      last = tNow
      const r = approach(robot.q, target, MOTION.maxAngularDegS * (speed.value / 100) * dt)
      try {
        await guard(r.q)
      } catch (e) {
        if (my === token) await fail(e)
        return
      }
      if (my !== token) return
      void robot.setQ(r.q)
      if (r.done) {
        if (my === token) stop()
        return
      }
    }
  }

  type GoTarget = 'home' | 'align'

  /** Joint target for Home (all zeros) or Align (sidecar). Shows the error and returns null if unreachable. */
  async function resolveTarget(kind: GoTarget): Promise<number[] | null> {
    if (kind === 'home') return robot.q.map(() => 0)
    try {
      const r = await engine.call<JogResult>('motion.align', { session_id: robot.sessionId, q_deg: [...robot.q] })
      return r.q_deg
    } catch (e) {
      await fail(e instanceof RpcError && e.code === IK_UNREACHABLE ? new MotionError(i18n.global.t('motion.errAlign')) : e)
      return null
    }
  }

  /** Click on Home / Align: one joint-space step (at most the angular click step per joint) toward the target, then state 4. */
  async function goStep(kind: GoTarget) {
    if (!robot.sessionId) return
    const my = ++token
    const target = await resolveTarget(kind)
    if (!target || my !== token) return
    state.value = STATE.moving
    active.value = null
    const next = approach(robot.q, target, settings.stepDeg).q
    try {
      await guard(next)
    } catch (e) {
      await fail(e)
      return
    }
    if (conn.isReal()) {
      const r = await engine.call<JogResult>('robot.move_joints', { session_id: robot.sessionId, q_deg: next })
      await robot.setQ(r.q_deg)
    } else {
      await robot.setQ(next)
    }
    if (my === token) stop()
  }

  /** Hold on Home / Align: move continuously toward the target at joint speed until release (stop) or arrival. */
  async function goStart(kind: GoTarget) {
    if (!robot.sessionId) return
    const my = ++token
    const target = await resolveTarget(kind)
    if (!target || my !== token) return // released while the target was being computed
    await moveTo(target)
  }

  const home = () => goStart('home')
  const align = () => goStart('align')

  /** Release / STOP: cancel any motion and enter state 4. */
  function stop() {
    token++
    active.value = null
    state.value = STATE.stopped
    if (conn.isReal()) void engine.call('robot.stop_motion', { session_id: robot.sessionId }).catch(() => {})
  }

  return { speed, state, active, step, startContinuous, goStep, goStart, home, align, stop, moveTo }
})
