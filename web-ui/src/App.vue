<script setup lang="ts">
// 根组件：侧边栏终端外壳 + 路由出口。
// 布局借鉴专业看盘终端（侧边栏分组导航 + 底部实时连接状态徽标）。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { fetchMeta } from './api'
import MarketTopbar from './components/MarketTopbar.vue'
import { useMarketStore } from './stores/market'
import { useQuoteStore } from './stores/quotes'
import { marketLabel } from './market'

const quoteStore = useQuoteStore()
const marketStore = useMarketStore()
const route = useRoute()

// 涨停生态暂只支持 A 股（涨跌停制度/连板统计无港美股来源），
// 港美股模式下显示降级提示而不是空白页。
const ASHARE_ONLY_ROUTES = new Set(['limitup'])
const showAshareNotice = computed(
  () =>
    !marketStore.isAShareMode &&
    typeof route.name === 'string' &&
    ASHARE_ONLY_ROUTES.has(route.name),
)

// 应用版本号（GET /meta），品牌区展示；取不到（旧后端/源码未装包）则不显示
const appVersion = ref('')
onMounted(async () => {
  quoteStore.connect()
  appVersion.value = (await fetchMeta()).version
})
// 卸载时关闭全局 SSE：否则 App 被卸载（HMR / 微前端 / app.unmount）时
// EventSource 与内部重连定时器都不回收，永久占一条连接。
onBeforeUnmount(() => {
  quoteStore.close()
})

const sseLabel: Record<string, string> = {
  connecting: '连接中',
  open: '实时',
  retrying: '重连中',
  closed: '离线',
}
</script>

<template>
  <div class="app">
    <MarketTopbar />
    <div class="app-row">
      <aside class="sidebar">
        <div class="brand">
          <span class="brand-name">easy-tdx</span>
          <span class="brand-sub">
            行情终端
            <span v-if="appVersion" class="brand-ver">v{{ appVersion }}</span>
          </span>
        </div>
        <nav class="side-nav">
          <div class="nav-group">行情</div>
          <RouterLink to="/" exact-active-class="active">市场看板</RouterLink>
          <RouterLink to="/industries" active-class="active">行业总览</RouterLink>
          <RouterLink to="/concepts" active-class="active">概念总览</RouterLink>
          <RouterLink to="/hotspots" active-class="active">热点滚动</RouterLink>
          <RouterLink to="/calendar" active-class="active">大盘日历</RouterLink>
          <RouterLink
            v-if="marketStore.isAShareMode"
            to="/limitup"
            active-class="active"
          >涨停生态</RouterLink>
          <span v-else class="nav-disabled" title="涨停生态暂只支持沪/深/北（港美股无涨跌停制度）">涨停生态</span>
          <RouterLink to="/sentiment" active-class="active">市场情绪</RouterLink>
          <RouterLink to="/watchlist" active-class="active">自选行情</RouterLink>
          <RouterLink to="/ccpm" active-class="active">期货持仓排名</RouterLink>
          <RouterLink to="/us-options" active-class="active">美股期权</RouterLink>
          <RouterLink to="/us-radar" active-class="active">美股观测雷达</RouterLink>
          <div class="nav-group">分析</div>
          <RouterLink to="/backtest" active-class="active">单标的回测</RouterLink>
          <RouterLink to="/portfolio" active-class="active">组合回测</RouterLink>
          <RouterLink to="/optimize" active-class="active">参数寻优</RouterLink>
          <RouterLink to="/compare" active-class="active">结果对比</RouterLink>
          <RouterLink to="/strategies" active-class="active">策略库</RouterLink>
          <RouterLink to="/strategy-types" active-class="active">策略类型</RouterLink>
          <RouterLink to="/signals" active-class="active">信号雷达</RouterLink>
          <RouterLink to="/ai-history" active-class="active">AI 解读历史</RouterLink>
          <div class="nav-group">系统</div>
          <RouterLink to="/settings" active-class="active">服务器设置</RouterLink>
          <RouterLink to="/index-settings" active-class="active">指数设置</RouterLink>
          <RouterLink to="/indicator-settings" active-class="active">技术指标</RouterLink>
          <RouterLink to="/custom-indicators" active-class="active">自定义指标</RouterLink>
          <RouterLink to="/push" active-class="active">推送设置</RouterLink>
          <RouterLink to="/llm" active-class="active">AI 设置</RouterLink>
        </nav>
        <div class="side-footer">
          <span class="dot" :class="quoteStore.status"></span>
          <span class="sse-label">{{ sseLabel[quoteStore.status] ?? '离线' }}</span>
          <span v-if="quoteStore.lastTs" class="sse-ts">{{ quoteStore.lastTs.slice(11, 19) }}</span>
          <span v-if="quoteStore.quoteCount" class="sse-n">×{{ quoteStore.quoteCount }}</span>
        </div>
      </aside>
      <main class="app-main">
        <div v-if="showAshareNotice" class="ashare-notice">
          「{{ route.meta?.label ?? '本页' }}」暂只支持 A 股数据（板块 / 涨跌停 /
          情绪采样无港美股来源）。当前为{{ marketLabel(marketStore.market) }}模式：
          可用「市场看板」（指数K线+榜单）、「自选行情」、「单标的回测」。
        </div>
        <RouterView />
      </main>
    </div>
    <!-- 全局风险提示：所有页面常驻（行情/回测/个股相关内容均在此覆盖范围） -->
    <footer class="global-disclaimer">
      本工具输出（行情数据 / 指标 / 回测 / 选股扫描 / AI 解读）仅供量化研究与学习，
      不构成任何投资建议或个股推荐；历史表现不代表未来，股市有风险，据此操作风险自负。
    </footer>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.app-row {
  flex: 1;
  display: flex;
  min-height: 0;
}
.global-disclaimer {
  flex-shrink: 0;
  padding: 5px 16px;
  background: var(--bg-panel);
  border-top: 1px solid var(--border);
  font-size: 10.5px;
  color: var(--text-dim);
  text-align: center;
  letter-spacing: 0.2px;
}
.sidebar {
  width: 186px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border-right: 1px solid var(--border);
}
.brand {
  padding: 16px 18px 14px;
  border-bottom: 1px solid var(--border);
}
.brand-name {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.4px;
  color: var(--text);
}
.brand-sub {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  color: var(--text-dim);
  letter-spacing: 0.2px;
}
/* 版本号做成小标签：原先是一串灰色小字，和信息栏混在一起分不出主次 */
.brand-ver {
  margin-left: 5px;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 9.5px;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent);
  font-variant-numeric: tabular-nums;
}
.side-nav {
  flex: 1;
  overflow-y: auto;
  /* 左右留 8px：选中项做成圆角块（而非通栏），视觉上更像现代终端侧栏 */
  padding: 4px 8px 16px;
}
.nav-group {
  padding: 16px 10px 6px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--text-dim);
  letter-spacing: 1.2px;
}
/* 分组之间加一条极淡分隔线：5 个分组连着排时不容易看清边界 */
.nav-group:not(:first-child) {
  margin-top: 6px;
  border-top: 1px solid var(--hairline);
}
.side-nav a {
  display: block;
  padding: 7.5px 10px;
  border-radius: 6px;
  color: var(--text-muted);
  text-decoration: none;
  font-size: 13px;
  transition:
    background 0.14s ease,
    color 0.14s ease;
}
.side-nav a:hover {
  color: var(--text);
  background: var(--bg-elevated);
}
.side-nav a.active {
  /* 淡色底 + accent 文字：比「通栏 + 左侧竖条」更收敛，长列表里不抢注意力 */
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 13%, transparent);
  font-weight: 500;
}
.nav-disabled {
  display: block;
  padding: 7.5px 10px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-dim);
  opacity: 0.42;
  cursor: not-allowed;
}
.side-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-dim);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-dim);
}
.dot.open {
  background: var(--up);
  box-shadow: 0 0 4px var(--up);
}
.dot.connecting {
  background: var(--warn);
}
/* 退避重连中：与「连接中」区分开（呼吸动画），否则用户只看到「离线」 */
.dot.retrying {
  background: var(--warn);
  animation: sse-pulse 1.4s ease-in-out infinite;
}
@keyframes sse-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}
.sse-ts {
  margin-left: auto;
  font-family: var(--font-mono);
}
.sse-n {
  color: var(--text-dim);
}
.app-main {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.app-main > :last-child {
  flex: 1;
  min-height: 0;
}
.ashare-notice {
  flex-shrink: 0;
  margin: 10px 16px 0;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--warn);
  background: var(--warn-soft);
  border: 1px solid var(--warn-line);
  border-radius: var(--radius);
}
</style>
