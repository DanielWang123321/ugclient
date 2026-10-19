<script setup lang="ts">
import { useRobotStore } from '../stores/robot'
import ModeSwitch from './ModeSwitch.vue'
const robot = useRobotStore()
async function onModel(k: string) {
  await robot.select(k, 'none')
}
async function onEe(ee: string) {
  await robot.select(robot.key, ee)
}
</script>

<template>
  <div>
    <div class="panel-title">{{ $t('robot.title') }}</div>
    <ModeSwitch />
    <el-form label-position="left" label-width="96px" size="small">
      <el-form-item :label="$t('robot.model')">
        <el-select :model-value="robot.key" data-test="robot-select" @update:model-value="onModel">
          <el-option v-for="r in robot.robots" :key="r.key" :label="r.key" :value="r.key" />
        </el-select>
      </el-form-item>
      <el-form-item :label="$t('robot.endEffector')">
        <el-select :model-value="robot.endEffector" data-test="ee-select" @update:model-value="onEe">
          <el-option
            v-for="e in robot.info?.end_effectors ?? ['none']"
            :key="e"
            :label="$t(`ee.${e}`)"
            :value="e"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="$t('robot.mounting')">
        <el-select model-value="floor" disabled>
          <el-option :label="$t('robot.floor')" value="floor" />
        </el-select>
      </el-form-item>
    </el-form>
    <div class="hint">{{ $t('robot.eeHint') }}</div>
  </div>
</template>
