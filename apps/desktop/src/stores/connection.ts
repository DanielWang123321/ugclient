// Sim / Real mode (UFACTORY Studio pattern). The UI only flips to Real after the
// sidecar confirms it can talk to the arm; on failure we stay in Simulation and
// the caller shows the error. In Real mode the robot store's q/TCP/state are
// refreshed from the real arm by pollReal().
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useEngineStore } from './engine'
import { useRobotStore } from './robot'
import { useSettingsStore } from './settings'

export type RobotMode = 'sim' | 'real'
export interface PollResult { mode: string; q_deg: number[]; tcp_pose: number[]; state: number; robot_mode: number }
export interface ConnectResult extends PollResult { ip: string; connected: boolean }

export const useConnectionStore = defineStore('connection', () => {
  const engine = useEngineStore()
  const robot = useRobotStore()
  const settings = useSettingsStore()
  const mode = ref<RobotMode>('sim')
  const connecting = ref(false)
  const lastError = ref('')
  const realState = ref<number | null>(null)
  let pollTimer: ReturnType<typeof setInterval> | null = null

  const isReal = () => mode.value === 'real'

  async function pollReal() {
    try {
      const r = await engine.call<PollResult>('robot.poll', { session_id: robot.sessionId })
      if (mode.value !== 'real') return
      realState.value = r.state
      if (r.q_deg?.length) {
        robot.q = [...r.q_deg]
        // FK in the sim session mirrors the 3D view while the arm drives; TCP shown is the read-back pose.
        await robot.refresh()
        if (r.tcp_pose?.length === 6) robot.fk = { tcp_pose: r.tcp_pose as never, flange_pose: r.tcp_pose as never }
      }
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : String(e)
    }
  }

  function startPolling() {
    stopPolling()
    pollTimer = setInterval(() => void pollReal(), 250)
  }
  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = null
  }

  /** Returns true only when the arm answered; otherwise stays in sim and lastError is set. */
  async function connectReal(ip: string): Promise<boolean> {
    const target = (ip || settings.robotIp || '').trim()
    if (!target) { lastError.value = 'IP required'; return false }
    connecting.value = true
    lastError.value = ''
    try {
      const r = await engine.call<ConnectResult>('robot.connect', { ip: target })
      settings.robotIp = target
      mode.value = 'real'
      realState.value = r.state
      if (r.q_deg?.length) { robot.q = [...r.q_deg]; await robot.refresh() }
      startPolling()
      return true
    } catch (e) {
      mode.value = 'sim' // connection check failed: do NOT switch the UI
      lastError.value = e instanceof Error ? e.message : String(e)
      return false
    } finally {
      connecting.value = false
    }
  }

  async function disconnectReal() {
    stopPolling()
    try { await engine.call('robot.disconnect', {}) } catch { /* already gone: still back to sim */ }
    mode.value = 'sim'
    realState.value = null
  }

  return { mode, connecting, lastError, realState, isReal, connectReal, disconnectReal, pollReal, startPolling, stopPolling }
})
