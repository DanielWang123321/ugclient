// User settings (Settings dialog), persisted to localStorage.
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { MOTION, sanitizeStep } from '../lib/motion'
import { normalizeBoundary, type Boundary } from '../lib/boundary'

export const SETTINGS_KEY = 'ugclient.settings'

export interface SessionConfig {
  robot: string
  endEffector: string
  tcpOffset: number[]
  payload: { mass_kg: number; com_mm: number[] }
  q: number[]
}

interface Stored {
  stepMm?: number
  stepDeg?: number
  boundaries?: Record<string, Partial<Boundary>>
  defaultRobot?: string
  restoreSession?: boolean
  robotIp?: string
  session?: SessionConfig | null
}

function read(): Stored {
  try {
    return JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? '{}') as Stored
  } catch {
    return {}
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const s = read()
  const stepMm = ref(sanitizeStep(s.stepMm, MOTION.stepMmRange, MOTION.stepMm))
  const stepDeg = ref(sanitizeStep(s.stepDeg, MOTION.stepDegRange, MOTION.stepDeg))
  const boundaries = ref<Record<string, Partial<Boundary>>>(s.boundaries ?? {})
  const defaultRobot = ref(s.defaultRobot ?? 'uf850')
  const restoreSession = ref(s.restoreSession ?? false)
  const session = ref<SessionConfig | null>(s.session ?? null)
  const robotIp = ref(s.robotIp ?? '')

  function save() {
    const data: Stored = {
      stepMm: stepMm.value, stepDeg: stepDeg.value, boundaries: boundaries.value,
      defaultRobot: defaultRobot.value, restoreSession: restoreSession.value, session: session.value, robotIp: robotIp.value,
    }
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(data))
  }
  watch([stepMm, stepDeg, boundaries, defaultRobot, restoreSession, session, robotIp], save, { deep: true })

  function setStepMm(v: unknown) {
    stepMm.value = sanitizeStep(v, MOTION.stepMmRange, stepMm.value)
  }
  function setStepDeg(v: unknown) {
    stepDeg.value = sanitizeStep(v, MOTION.stepDegRange, stepDeg.value)
  }

  /** Effective boundary for a model: stored values clamped inside the model's joint limits. */
  function boundaryFor(key: string, model: [number, number][]): Boundary {
    return normalizeBoundary(boundaries.value[key], model)
  }
  function setBoundary(key: string, b: Boundary, model: [number, number][]) {
    boundaries.value = { ...boundaries.value, [key]: normalizeBoundary(b, model) }
  }
  function resetBoundary(key: string) {
    const next = { ...boundaries.value }
    delete next[key]
    boundaries.value = next
  }

  return {
    stepMm, stepDeg, boundaries, defaultRobot, restoreSession, session, robotIp,
    setStepMm, setStepDeg, boundaryFor, setBoundary, resetBoundary, save,
  }
})
