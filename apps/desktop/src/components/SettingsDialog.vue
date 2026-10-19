<script setup lang="ts">
// Settings dialog: Jog, Safety boundary (per robot model), General, About. Persisted by the settings store.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '../stores/settings'
import { useRobotStore } from '../stores/robot'
import { useEngineStore } from '../stores/engine'
import { MOTION } from '../lib/motion'
import type { Boundary } from '../lib/boundary'
import pkg from '../../package.json'

const visible = defineModel<boolean>({ default: false })
const { locale } = useI18n()
const settings = useSettingsStore()
const robot = useRobotStore()
const engine = useEngineStore()
const tab = ref('jog')

const model = computed<[number, number][]>(() => robot.info?.limits_deg ?? [])
const b = ref<Boundary>(settings.boundaryFor(robot.key, model.value))
watch([() => robot.key, model, visible], () => (b.value = settings.boundaryFor(robot.key, model.value)))
function commit() {
  settings.setBoundary(robot.key, b.value, model.value)
  b.value = settings.boundaryFor(robot.key, model.value)
}
function reset() {
  settings.resetBoundary(robot.key)
  b.value = settings.boundaryFor(robot.key, model.value)
}
const AX = ['X', 'Y', 'Z']
</script>

<template>
  <el-dialog v-model="visible" :title="$t('settings.title')" width="560px" class="dark-panel dark-dialog" append-to-body>
    <el-tabs v-model="tab" class="stabs" data-test="settings-dialog">
      <el-tab-pane :label="$t('settings.jog')" name="jog">
        <div class="row">
          <span>{{ $t('settings.stepMm') }}</span>
          <el-input-number
            :model-value="settings.stepMm" :min="MOTION.stepMmRange[0]" :max="MOTION.stepMmRange[1]" :step="0.1" :precision="2"
            data-test="step-mm" @change="(v: number | undefined) => settings.setStepMm(v)"
          />
          <i>mm</i>
        </div>
        <div class="row">
          <span>{{ $t('settings.stepDeg') }}</span>
          <el-input-number
            :model-value="settings.stepDeg" :min="MOTION.stepDegRange[0]" :max="MOTION.stepDegRange[1]" :step="0.1" :precision="2"
            data-test="step-deg" @change="(v: number | undefined) => settings.setStepDeg(v)"
          />
          <i>°</i>
        </div>
        <p class="hint">{{ $t('settings.jogHint', { ms: MOTION.longPressMs, lin: MOTION.maxLinearMmS, ang: MOTION.maxAngularDegS }) }}</p>
      </el-tab-pane>

      <el-tab-pane :label="$t('settings.safety')" name="safety">
        <p class="hint">{{ $t('settings.safetyHint', { model: robot.key }) }}</p>
        <div class="grid">
          <span />
          <b>{{ $t('motion.min') }}</b>
          <b>{{ $t('motion.max') }}</b>
          <template v-for="(a, i) in AX" :key="a">
            <span>TCP {{ a }} (mm)</span>
            <el-input-number
              v-model="b.tcpMin[i]" :controls="false" :precision="1" :value-on-clear="null" :placeholder="$t('settings.unbounded')"
              :data-test="`tcp-min-${a}`" @change="commit"
            />
            <el-input-number
              v-model="b.tcpMax[i]" :controls="false" :precision="1" :value-on-clear="null" :placeholder="$t('settings.unbounded')"
              :data-test="`tcp-max-${a}`" @change="commit"
            />
          </template>
          <template v-for="(l, i) in model" :key="i">
            <span>J{{ i + 1 }} (°) <i class="lim">[{{ l[0].toFixed(1) }}, {{ l[1].toFixed(1) }}]</i></span>
            <el-input-number v-model="b.jointMin[i]" :controls="false" :precision="1" :min="l[0]" :max="l[1]" @change="commit" />
            <el-input-number v-model="b.jointMax[i]" :controls="false" :precision="1" :min="l[0]" :max="l[1]" @change="commit" />
          </template>
        </div>
        <el-button size="small" class="reset" @click="reset">{{ $t('settings.resetBoundary') }}</el-button>
      </el-tab-pane>

      <el-tab-pane :label="$t('settings.general')" name="general">
        <div class="row">
          <span>{{ $t('settings.language') }}</span>
          <el-radio-group v-model="locale">
            <el-radio-button value="zh">中文</el-radio-button>
            <el-radio-button value="en">English</el-radio-button>
          </el-radio-group>
        </div>
        <div class="row">
          <span>{{ $t('settings.defaultRobot') }}</span>
          <el-select v-model="settings.defaultRobot" style="width: 160px">
            <el-option v-for="r in robot.robots" :key="r.key" :label="r.key" :value="r.key" />
          </el-select>
        </div>
        <div class="row">
          <span>{{ $t('conn.ip') }}</span>
          <el-input v-model="settings.robotIp" style="width: 160px" placeholder="192.168.1.10" data-test="settings-robot-ip" />
        </div>
        <div class="row">
          <span>{{ $t('settings.restoreSession') }}</span>
          <el-switch v-model="settings.restoreSession" data-test="restore-session" />
        </div>
        <p class="hint">{{ $t('settings.restoreHint') }}</p>
      </el-tab-pane>

      <el-tab-pane :label="$t('settings.about')" name="about">
        <div class="kv">
          <i>UGClient</i><b>{{ pkg.version }}</b>
          <i>ugclient-core</i><b>{{ engine.hello?.core_version ?? '—' }}</b>
          <i>ufactory_genesis</i><b>{{ engine.hello ? `${engine.hello.ufactory_genesis_version} (${engine.hello.ufactory_genesis_commit})` : '—' }}</b>
          <i>Pinocchio</i><b>{{ engine.hello?.pinocchio_version ?? '—' }}</b>
          <i>{{ $t('settings.license') }}</i><b>MIT</b>
        </div>
        <p class="hint">{{ $t('app.personal') }}</p>
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<style scoped>
.row { display: flex; align-items: center; gap: 12px; margin: 10px 0; }
.row > span { width: 170px; color: #9a9ca3; }
.row i { font-style: normal; color: #9a9ca3; }
.hint { color: #9a9ca3; font-size: 12px; line-height: 1.5; }
.grid { display: grid; grid-template-columns: 1fr 120px 120px; gap: 6px 10px; align-items: center; max-height: 360px; overflow-y: auto; }
.grid > span { color: #9a9ca3; font-size: 12px; }
.grid b { font-weight: 500; font-size: 12px; }
.grid :deep(.el-input-number) { width: 120px; }
.lim { font-style: normal; color: #6f7177; font-size: 10px; }
.reset { margin-top: 12px; }
.kv { display: grid; grid-template-columns: 140px 1fr; gap: 10px 8px; font-size: 13px; }
.kv i { font-style: normal; color: #9a9ca3; }
.kv b { font-weight: 500; color: #fff; }
.stabs :deep(.el-tabs__item) { color: #9a9ca3; }
.stabs :deep(.el-tabs__item.is-active) { color: #fff; }
.stabs :deep(.el-tabs__nav-wrap::after) { background: #303136; }
</style>
