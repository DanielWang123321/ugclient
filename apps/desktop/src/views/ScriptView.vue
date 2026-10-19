<script setup lang="ts">
// Python script page: edit / open / save-as, Run & Stop, stdout+stderr console.
// Scripts run in the sidecar worker (killable); `arm` is preloaded and routed to sim or real.
import { onBeforeUnmount, ref } from 'vue'
import { useEngineStore } from '../stores/engine'
import { useRobotStore } from '../stores/robot'
import { useConnectionStore } from '../stores/connection'
import { EXAMPLE_SCRIPTS } from '../lib/examples'
import type { ScriptStatus } from '../rpc/types'

const engine = useEngineStore()
const robot = useRobotStore()
const conn = useConnectionStore()
const code = ref(EXAMPLE_SCRIPTS.joint)
const example = ref('joint')
const timeoutS = ref(30)
const status = ref<ScriptStatus | null>(null)
const running = ref(false)
let jobId = ''
let timer: ReturnType<typeof setInterval> | null = null
const fileInput = ref<HTMLInputElement | null>(null)

function pickExample(k: string) { example.value = k; code.value = EXAMPLE_SCRIPTS[k] }
function openFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) void f.text().then((txt) => (code.value = txt))
}
function saveFile() {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([code.value], { type: 'text/x-python' }))
  a.download = 'ugclient_script.py'
  a.click()
  URL.revokeObjectURL(a.href)
}
async function poll() {
  if (!jobId) return
  try {
    status.value = await engine.call<ScriptStatus>('script.status', { job_id: jobId })
    if (status.value.status !== 'running') { running.value = false; stopPoll() }
  } catch { stopPoll(); running.value = false }
}
function stopPoll() { if (timer) clearInterval(timer); timer = null }
async function run() {
  if (running.value) return
  status.value = null
  const r = await engine.call<{ job_id: string }>('script.start', { session_id: robot.sessionId, code: code.value, timeout_s: timeoutS.value })
  jobId = r.job_id
  running.value = true
  timer = setInterval(() => void poll(), 300)
  void poll()
}
async function kill() {
  if (jobId) await engine.call('script.stop', { job_id: jobId })
  void poll()
}
onBeforeUnmount(stopPoll)
</script>

<template>
  <div class="script dark-panel" data-test="script-view">
    <div class="toolbar">
      <b>{{ $t('script.title') }}</b>
      <span class="mode">{{ conn.mode === 'real' ? $t('conn.real') : $t('conn.simulation') }}</span>
      <span class="sp" />
      <el-select :model-value="example" size="small" style="width: 150px" @update:model-value="pickExample">
        <el-option :label="$t('script.jointExample')" value="joint" />
        <el-option :label="$t('script.tcpExample')" value="tcp" />
      </el-select>
      <el-button size="small" data-test="script-open" @click="fileInput?.click()">{{ $t('script.open') }}</el-button>
      <input ref="fileInput" type="file" accept=".py,text/x-python" hidden @change="openFile">
      <el-button size="small" data-test="script-save" @click="saveFile">{{ $t('script.save') }}</el-button>
      <span class="tmo">{{ $t('script.timeout') }}</span>
      <el-input-number v-model="timeoutS" size="small" :min="1" :max="3600" style="width: 90px" />
      <el-button size="small" type="primary" :disabled="running" data-test="script-run" @click="run">{{ $t('script.run') }}</el-button>
      <el-button size="small" type="danger" :disabled="!running" data-test="script-stop" @click="kill">{{ $t('script.stop') }}</el-button>
    </div>
    <textarea v-model="code" class="editor" data-test="script-editor" spellcheck="false" />
    <div class="console-h">
      <span>{{ $t('script.console') }}</span>
      <span class="st" :class="status?.status" data-test="script-status">
        {{ status ? $t(`script.${status.status === 'running' ? 'running' : status.status}`) : $t('script.idle') }}
        <template v-if="status?.error"> — {{ status.error }}</template>
      </span>
    </div>
    <pre class="console" data-test="script-console">{{ status?.output ?? '' }}</pre>
  </div>
</template>

<style scoped>
.script { height: 100%; display: flex; flex-direction: column; background: #1f2023; border-radius: 16px; padding: 16px; box-sizing: border-box; color: #e6e7ea; }
.toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.toolbar .sp { flex: 1; }
.mode { font-size: 11px; color: #4cd28a; background: #2a2b2f; border-radius: 4px; padding: 2px 8px; }
.tmo { font-size: 12px; color: #9a9ca3; }
.editor { flex: 1; min-height: 180px; margin: 12px 0; background: #141518; color: #e6e7ea; border: 1px solid #333; border-radius: 8px;
  padding: 12px; font: 13px/1.5 Consolas, "JetBrains Mono", monospace; resize: none; outline: none; }
.console-h { display: flex; justify-content: space-between; font-size: 12px; color: #9a9ca3; }
.console-h .st.error { color: #f04a4d; } .console-h .st.done { color: #4cd28a; }
.console { height: 180px; overflow-y: auto; background: #141518; border: 1px solid #333; border-radius: 8px; padding: 10px;
  font: 12px/1.5 Consolas, monospace; white-space: pre-wrap; margin: 8px 0 0; }
</style>
