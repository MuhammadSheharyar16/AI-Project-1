import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type ProxyOptions } from 'vite'

/** Read KEY=value pairs from the backend's .env so the tokens never have to be copied or bundled. */
function readBackendEnv(): Record<string, string> {
  const file = fileURLToPath(new URL('../backend/.env', import.meta.url))
  if (!existsSync(file)) return {}
  const out: Record<string, string> = {}
  for (const line of readFileSync(file, 'utf8').split(/\r?\n/)) {
    const match = /^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/.exec(line)
    if (match) out[match[1]] = match[2].replace(/^(['"])(.*)\1$/, '$2')
  }
  return out
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Non-VITE_ variables stay on the dev server; they are never exposed to browser code.
  const env = loadEnv(mode, process.cwd(), '')
  const backend = readBackendEnv()
  const target = env.FIREWALL_API_URL || 'http://localhost:8000'
  const apiToken = env.FIREWALL_API_TOKEN ?? backend.API_TOKEN ?? ''
  const adminToken = env.FIREWALL_ADMIN_TOKEN ?? backend.ADMIN_TOKEN ?? ''

  // The browser calls same-origin /api/*; the dev server forwards to the backend and adds the
  // auth headers. Tokens stay out of the bundle, and the backend needs no CORS change.
  const proxy: Record<string, ProxyOptions> = {
    '/api': {
      target,
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, ''),
      timeout: 600_000, // the 50-answer suite can take minutes on the free AI tier
      proxyTimeout: 600_000,
      configure: (server) => {
        server.on('proxyReq', (proxyReq) => {
          if (apiToken) proxyReq.setHeader('X-API-Key', apiToken)
          if (adminToken) proxyReq.setHeader('X-Admin-Token', adminToken)
        })
      },
    },
  }

  return {
    plugins: [react()],
    // localhost only: the proxy carries the admin token, so it must not be reachable from the LAN.
    server: { host: 'localhost', port: 5173, proxy },
    preview: { host: 'localhost', port: 4173, proxy },
  }
})
