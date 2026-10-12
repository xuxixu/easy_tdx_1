import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import { captureError, installErrorCapture } from './errors'
import { router } from './router'
import { initTheme } from './theme'
import './style.css'

// 首帧之前铺好主题变量（避免深/浅色闪一下），并装上全局异常捕获：
// 三者都必须在 createApp 之前/之时完成——主题要在首帧前生效，
// 异常钩子要赶在业务代码跑起来之前挂上，否则早期异常收不到。
initTheme()

const app = createApp(App)
app.use(createPinia()).use(router)
// 路由懒加载 chunk 拉取失败属于「用户看不见的失败」，单独记一笔便于排查部署问题
router.onError((e) => captureError('vue', e, '', location.href))
installErrorCapture(app)
app.mount('#app')
