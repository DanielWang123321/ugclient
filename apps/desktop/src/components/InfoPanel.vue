<script setup lang="ts">
// Read-only robot state, laid out like the right panel of the v8 mockup.
import { computed } from 'vue'
import { useRobotStore } from '../stores/robot'
import { useMotionStore } from '../stores/motion'
import { useConnectionStore } from '../stores/connection'
const conn = useConnectionStore()
import { STATE } from '../lib/motion'
import { fmt } from '../lib/units'
const robot = useRobotStore()
const motion = useMotionStore()
const displayState = computed(() => (conn.mode === 'real' && conn.realState !== null ? conn.realState : motion.state))
const stateKey = computed(() =>
  displayState.value === STATE.moving ? 'moving' : displayState.value === STATE.stopped ? 'stopped' : 'ready',
)
const tcpLabels = ['X', 'Y', 'Z', 'Roll', 'Pitch', 'Yaw']
const half = computed(() => Math.ceil(robot.q.length / 2))
// two columns: left J1..Jn/2, right the rest (as in the mockup)
const jointOrder = computed(() => {
  const out: number[] = []
  for (let r = 0; r < half.value; r++) {
    out.push(r)
    if (r + half.value < robot.q.length) out.push(r + half.value)
    else out.push(-1)
  }
  return out
})
</script>

<template>
  <div data-test="info-panel">
    <h3>{{ $t('info.state') }} <span class="tag">{{ $t('info.readOnly') }}</span></h3>
    <div class="kv">
      <i>{{ $t('info.state') }}</i>
      <b :class="stateKey" data-test="sim-state">{{ $t(`info.${stateKey}`) }} ({{ displayState }})</b>
      <i>{{ $t('info.mode') }}</i><b class="wide" data-test="info-mode">{{ conn.mode === 'real' ? $t('conn.real') : $t('conn.simulation') }} · {{ $t('info.position') }}</b>
      <i>{{ $t('info.payload') }}</i><b>{{ fmt(robot.payload.mass_kg, 2) }} kg</b>
      <i>{{ $t('robot.mounting') }}</i><b>{{ $t('robot.floor') }}</b>
    </div>
    <div class="sep" />
    <h3>{{ $t('info.tcp') }}</h3>
    <div class="kv ro">
      <template v-for="k in [0, 3, 1, 4, 2, 5]" :key="k">
        <i>{{ tcpLabels[k] }}</i>
        <b>{{ robot.fk ? `${fmt(robot.fk.tcp_pose[k], 1)}${k < 3 ? ' mm' : '°'}` : '—' }}</b>
      </template>
    </div>
    <div class="sep" />
    <h3>{{ $t('info.joints') }}</h3>
    <div class="kv ro">
      <template v-for="(i, n) in jointOrder" :key="n">
        <template v-if="i >= 0"><i>J{{ i + 1 }}</i><b :data-test="`q${i + 1}`">{{ fmt(robot.q[i], 1) }}°</b></template>
        <template v-else><i /><b /></template>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* values copied from mockup-bottom-panel.html (v8) */
h3 { margin: 0 0 12px; font-size: 15px; font-weight: 600; }
.tag { font-size: 10px; color: #888; background: #2a2b2f; border-radius: 3px; padding: 2px 6px; margin-left: 6px; font-weight: 400; }
.kv { display: grid; grid-template-columns: auto 1fr auto 1fr; gap: 12px 8px; font-size: 12px; }
.kv b { font-weight: 500; color: #fff; white-space: nowrap; }
.kv i { font-style: normal; color: #9a9ca3; }
.ro { color: #fff; font-variant-numeric: tabular-nums; }
.sep { border-top: 1px solid #333; margin: 14px 0; }
.kv b.wide { grid-column: span 3; white-space: normal; }
.kv b.ready { color: #4cd28a; }
.kv b.moving { color: #6a8ff7; }
.kv b.stopped { color: #f0a63a; }
</style>
