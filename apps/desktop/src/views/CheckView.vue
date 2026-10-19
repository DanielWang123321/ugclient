<script setup lang="ts">
// Check page shell, laid out exactly like the approved v8 mockup (1600x1000 reference):
// a light 3D scene fills the window, dark rounded panels float on top.
import RobotPanel from '../components/RobotPanel.vue'
import TcpPanel from '../components/TcpPanel.vue'
import PayloadPanel from '../components/PayloadPanel.vue'
import Viewport from '../components/Viewport.vue'
import MotionBar from '../components/MotionBar.vue'
import InfoPanel from '../components/InfoPanel.vue'
import AppFooter from '../components/AppFooter.vue'
import LangSwitch from '../components/LangSwitch.vue'
import { ref } from 'vue'
import { useMotionStore } from '../stores/motion'
import ScriptView from './ScriptView.vue'
const page = ref<'control' | 'script'>('control')

const motion = useMotionStore()

// Screen area covered by the panels, so the robot is centred in the free part of the scene.
const insets = { left: 284, right: 274, top: 0, bottom: 260 }
</script>

<template>
  <div class="check">
    <div class="scene"><Viewport :insets="insets" /></div>
    <aside class="panel left dark-panel">
      <RobotPanel />
      <div class="sep" />
      <TcpPanel />
      <div class="sep" />
      <PayloadPanel />
      <div class="grow" />
      <AppFooter />
    </aside>
    <aside class="panel right dark-panel"><InfoPanel /></aside>
    <MotionBar v-if="page === 'control'" class="bar" />
    <div v-if="page === 'script'" class="scriptwrap"><ScriptView /></div>
    <div class="pagetab">
      <button :class="{ on: page === 'control' }" data-test="page-control" @click="page = 'control'">{{ $t('tabs.check') }}</button>
      <button :class="{ on: page === 'script' }" data-test="page-script" @click="page = 'script'">{{ $t('script.title') }}</button>
    </div>
    <div class="topright">
      <LangSwitch />
      <button class="stop" data-test="stop" @click="motion.stop()">STOP</button>
    </div>
  </div>
</template>

<style scoped>
/* values copied from mockup-bottom-panel.html (v8) */
.check { position: relative; width: 100%; height: 100%; overflow: hidden; background: #f7f8f9; color: #e6e7ea;
  font: 13px "Inter", "Noto Sans", Arial, sans-serif; }
.scene { position: absolute; inset: 0; }
.panel { position: absolute; background: #1f2023; border-radius: 16px; padding: 16px; box-sizing: border-box; }
.left { left: 12px; top: 12px; bottom: 12px; width: 260px; display: flex; flex-direction: column; overflow-y: auto; }
.right { right: 12px; top: 12px; bottom: 12px; width: 250px; overflow-y: auto; }
.bar { position: absolute; left: 284px; right: 274px; bottom: 12px; }
.sep { border-top: 1px solid #333; margin: 14px 0; flex: none; }
.grow { flex: 1; min-height: 14px; }
.scriptwrap { position: absolute; left: 284px; right: 274px; top: 64px; /* below the floating page tabs, STOP and language switch */ bottom: 12px; z-index: 5; }
.pagetab { position: absolute; top: 16px; left: 296px; z-index: 9; display: flex; background: #1f2023; border-radius: 8px; padding: 3px; }
.pagetab button { background: none; border: 0; color: #9a9ca3; font: inherit; font-size: 12px; padding: 6px 14px; border-radius: 6px; cursor: pointer; }
.pagetab button.on { background: #3b6ef5; color: #fff; }
.topright { position: absolute; top: 16px; right: 286px; z-index: 9; display: flex; align-items: center; gap: 12px; }
.stop { background: #e5383b; color: #fff; font: inherit; font-weight: 700;
  letter-spacing: 1px; padding: 10px 30px; font-size: 15px; border: 0; border-radius: 6px; cursor: pointer; box-shadow: 0 0 0 2px rgba(229, 56, 59, .35); }
.stop:hover { background: #f04a4d; }
</style>
