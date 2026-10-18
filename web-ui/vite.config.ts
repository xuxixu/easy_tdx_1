import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
// dev server 把 /api 请求代理到后端 FastAPI（默认 8000 端口），
// 解决开发期跨域；生产环境由 FastAPI 同源托管 dist。
export default defineConfig({
  plugins: [vue()],
  build: {
    // 路由已全部懒加载（router.ts），主 chunk 从 1183 kB 降到 ~94 kB。
    // 剩下的 echarts chunk 约 664 kB（gzip 221 kB）是「5 类图表 + Canvas 渲染器
    // + 6 个交互组件」的固有体积，且首屏市场看板就要用雷达图，无法再推迟加载。
    // 这里把告警线提到 700 kB 只针对这一个体量已知的库，其它 chunk 的增长仍会报警。
    chunkSizeWarningLimit: 700,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
