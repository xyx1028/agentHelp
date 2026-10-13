import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发服务器把 /api 代理到 FastAPI（web.py 默认 8000 端口）；
// 生产模式不走本配置，由 FastAPI 直接托管 vite build 产出的 dist/。
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
