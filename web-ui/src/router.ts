import { createRouter, createWebHistory } from 'vue-router'

// 只有首屏（市场看板）静态引入，其余视图一律路由级懒加载。
//
// 旧实现把 23 个视图全部静态 import，Rollup 只能打成一个 1.18MB 的主 chunk
// （gzip 397KB）：首屏必须等整套回测 / 港美股 / 中金所 / AI 设置代码全部解析
// 完才能渲染。改用 `() => import()` 后 Vite 按路由切分 chunk，首屏只加载看板
// 所需部分，其余在导航时才拉取。
import DashboardView from './views/DashboardView.vue'

// 行情终端：市场看板（/）+ 自选（/watchlist）。
// 分析工具：单标的回测（/backtest）+ 组合回测（/portfolio）+ 参数寻优（/optimize）
// + 结果对比（/compare）+ 策略库（/strategies）+ 信号雷达（/signals）
// + 设置（/settings 服务器 / /llm AI 模型）。
const routes = [
  { path: '/', name: 'dashboard', component: DashboardView },
  // 行业/概念总览（同一视图组件，路由 props 区分板块类型）
  {
    path: '/industries',
    name: 'industries',
    component: () => import('./views/BoardOverviewView.vue'),
    props: { boardType: 'HY' },
    meta: { label: '行业总览' },
  },
  {
    path: '/concepts',
    name: 'concepts',
    component: () => import('./views/BoardOverviewView.vue'),
    props: { boardType: 'GN' },
    meta: { label: '概念总览' },
  },
  // 市场热点滚动（交易日×板块涨跌矩阵：热点形成/持续/轮动/领跌）
  {
    path: '/hotspots',
    name: 'hotspots',
    component: () => import('./views/HotspotView.vue'),
    meta: { label: '热点滚动' },
  },
  // 风格轮动（同一热点视图 × FG 风格板块：大/小盘、高股息/成长…）
  {
    path: '/styles',
    name: 'styles',
    component: () => import('./views/HotspotView.vue'),
    props: { boardType: 'FG' },
    meta: { label: '风格轮动' },
  },
  // 大盘日历（指数全年红绿热力图）
  {
    path: '/calendar',
    name: 'calendar',
    component: () => import('./views/IndexCalendarView.vue'),
    meta: { label: '大盘日历' },
  },
  {
    path: '/watchlist',
    name: 'watchlist',
    component: () => import('./views/WatchlistView.vue'),
  },
  // 涨停生态（连板天梯/炸板/跌停，本地 vipdoc 离线回算）
  {
    path: '/limitup',
    name: 'limitup',
    component: () => import('./views/LimitUpView.vue'),
    meta: { label: '涨停生态' },
  },
  // 市场情绪（宽度分时 + 涨停温度计；采样器盘中逐分钟积累）
  {
    path: '/sentiment',
    name: 'sentiment',
    component: () => import('./views/SentimentView.vue'),
    meta: { label: '市场情绪' },
  },
  { path: '/backtest', name: 'backtest', component: () => import('./views/BacktestView.vue') },
  { path: '/portfolio', name: 'portfolio', component: () => import('./views/PortfolioView.vue') },
  { path: '/optimize', name: 'optimize', component: () => import('./views/OptimizeView.vue') },
  { path: '/compare', name: 'compare', component: () => import('./views/CompareView.vue') },
  { path: '/strategies', name: 'strategies', component: () => import('./views/StrategiesView.vue') },
  {
    path: '/strategy-types',
    name: 'strategy-types',
    component: () => import('./views/StrategyTypesView.vue'),
  },
  { path: '/signals', name: 'signals', component: () => import('./views/SignalRadarView.vue') },
  { path: '/settings', name: 'settings', component: () => import('./views/ServerSettingsView.vue') },
  {
    path: '/index-settings',
    name: 'index-settings',
    component: () => import('./views/IndexSettingsView.vue'),
  },
  {
    path: '/indicator-settings',
    name: 'indicator-settings',
    component: () => import('./views/IndicatorSettingsView.vue'),
    meta: { label: '技术指标' },
  },
  {
    path: '/custom-indicators',
    name: 'custom-indicators',
    component: () => import('./views/CustomIndicatorsView.vue'),
    meta: { label: '自定义指标' },
  },
  { path: '/push', name: 'push', component: () => import('./views/PushSettingsView.vue') },
  { path: '/llm', name: 'llm', component: () => import('./views/LlmSettingsView.vue') },
  // AI 解读历史（每次「直接解读」自动归档）
  {
    path: '/ai-history',
    name: 'ai-history',
    component: () => import('./views/LlmHistoryView.vue'),
  },
  // 中金所成交持仓排名（独立数据源，每日收盘后发布）
  { path: '/ccpm', name: 'ccpm', component: () => import('./views/CcpmView.vue') },
  // 美股期权结构（PCR + 成交最密集行权价）。当前为静态 mock 数据，
  // 后端尚无期权链接口；美股看板右侧栏也复用同一份数据做精简版。
  {
    path: '/us-options',
    name: 'us-options',
    component: () => import('./views/UsOptionsView.vue'),
    meta: { label: '美股期权' },
  },
  // 美股观测雷达（18 区块整页复刻，单页滚动）
  {
    path: '/us-radar',
    name: 'us-radar',
    component: () => import('./views/UsRadarView.vue'),
    meta: { label: '美股观测雷达' },
  },
  // 兜底：未注册路径（如把 API 路径当页面访问）回看板，不再渲染空白
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
