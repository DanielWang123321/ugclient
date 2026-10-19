<script setup lang="ts">
// Simulation | Real Robot switch (left panel, next to the robot model section, as in UFACTORY Studio).
// Picking "Real" reveals the IP field; the mode only flips after the arm answers.
import { ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useConnectionStore } from '../stores/connection'
import { useSettingsStore } from '../stores/settings'

const conn = useConnectionStore()
const settings = useSettingsStore()
const { t } = useI18n()
const showIp = ref(false)
const ip = ref(settings.robotIp)

async function pickReal() {
  if (conn.mode === 'real') return
  showIp.value = true
  ip.value = settings.robotIp
}
async function doConnect() {
  if (await conn.connectReal(ip.value)) {
    showIp.value = false
  } else {
    try { await ElMessageBox.alert(t('conn.connectFailed', { ip: ip.value }) + (conn.lastError ? `\n${conn.lastError}` : ''),
      t('conn.real'), { type: 'error' }) } catch { /* closed */ }
  }
}
async function pickSim() {
  showIp.value = false
  if (conn.mode === 'real') await conn.disconnectReal()
}
</script>

<template>
  <div data-test="mode-switch">
    <div class="seg">
      <button :class="{ on: conn.mode === 'sim' && !showIp }" data-test="mode-sim" @click="pickSim">{{ $t('conn.simulation') }}</button>
      <button :class="{ on: conn.mode === 'real' }" data-test="mode-real" :disabled="conn.connecting" @click="pickReal">{{ $t('conn.real') }}</button>
    </div>
    <div v-if="showIp && conn.mode !== 'real'" class="iprow">
      <el-input v-model="ip" :placeholder="$t('conn.ip')" data-test="robot-ip" size="small" @keyup.enter="doConnect" />
      <el-button size="small" type="primary" :loading="conn.connecting" data-test="robot-connect" @click="doConnect">{{ $t('conn.connect') }}</el-button>
    </div>
    <div v-if="conn.mode === 'real'" class="iprow">
      <span class="realip">{{ settings.robotIp }}</span>
      <el-button size="small" data-test="robot-disconnect" @click="pickSim">{{ $t('conn.disconnect') }}</el-button>
    </div>
    <p v-if="showIp && conn.mode !== 'real'" class="hint">{{ $t('conn.ipHint') }}</p>
  </div>
</template>

<style scoped>
.seg { display: flex; background: #2a2b2f; border-radius: 8px; padding: 3px; margin-bottom: 8px; }
.seg button { flex: 1; background: none; border: 0; color: #9a9ca3; font: inherit; font-size: 12px; padding: 6px 0; border-radius: 6px; cursor: pointer; }
.seg button.on { background: #3b6ef5; color: #fff; }
.iprow { display: flex; gap: 6px; align-items: center; margin: 6px 0; }
.realip { flex: 1; font-size: 12px; color: #4cd28a; }
.hint { color: #9a9ca3; font-size: 11px; line-height: 1.4; margin: 4px 0 0; }
</style>
