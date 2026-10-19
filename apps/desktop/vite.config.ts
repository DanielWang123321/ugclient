/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

const host = process.env.TAURI_DEV_HOST

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({ resolvers: [ElementPlusResolver()], dts: 'src/auto-imports.d.ts' }),
    Components({ resolvers: [ElementPlusResolver({ importStyle: 'css' })], dts: 'src/components.d.ts' }),
  ],
  clearScreen: false,
  server: { port: 1420, strictPort: true, host: host || false },
  envPrefix: ['VITE_', 'TAURI_ENV_*'],
  build: { target: 'es2021', chunkSizeWarningLimit: 1500 },
  test: { environment: 'jsdom', include: ['tests/**/*.spec.ts'], server: { deps: { inline: ['element-plus'] } } },
})
