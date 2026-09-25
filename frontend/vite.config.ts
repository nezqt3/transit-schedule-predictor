import { fileURLToPath, URL } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type ProxyOptions } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendTarget = env.BACKEND_PROXY_TARGET ?? 'http://127.0.0.1:8000'

  const proxy: Record<string, ProxyOptions> = {
    // Единая точка входа для фронта: REST и будущий WS идут через /api.
    '/api': { changeOrigin: true, target: backendTarget, ws: true },
    '/docs': { changeOrigin: true, target: backendTarget },
    '/redoc': { changeOrigin: true, target: backendTarget },
    '/openapi.json': { changeOrigin: true, target: backendTarget },
  }

  return {
    plugins: [react()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      allowedHosts: true,
      host: true,
      hmr: env.VITE_HMR_HOST
        ? { host: env.VITE_HMR_HOST, port: Number(env.VITE_HMR_PORT ?? 5173) }
        : undefined,
      port: Number(env.FRONTEND_DEV_PORT ?? 5173),
      proxy,
      strictPort: true,
    },
    preview: {
      host: true,
      port: Number(env.FRONTEND_PREVIEW_PORT ?? 4173),
    },
    build: {
      chunkSizeWarningLimit: 700,
      reportCompressedSize: false,
      rollupOptions: {
        output: {
          // Графики тянут за собой ~300 kB — выносим в отдельный чанк,
          // чтобы react-часть перекачивалась между деплоями.
          manualChunks: (id) => {
            if (!id.includes('node_modules')) return null
            if (/recharts|victory-vendor|d3-/u.test(id)) return 'charts'
            return 'vendor'
          },
        },
      },
      sourcemap: mode !== 'production',
      target: 'es2022',
    },
  }
})
