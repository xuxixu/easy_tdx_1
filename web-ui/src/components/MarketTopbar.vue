<script setup lang="ts">
// 全局顶栏：市场切换 + 交易时段 + 手动刷新 + 主题 / 全局异常入口。
//
// 为什么是"全局"而不是放进各页面的 toolbar：
// 现有布局是「左导航 + 右内容」，没有任何全局横条，市场切换器无处安放；
// 而市场是一个正交于页面的概念——用户可能想从「自选行情」直接跳到「单标的回测」
// 且保持美股，塞进单个页面的 toolbar 就断了。
//
// 各页面自己的 session-bar / toolbar 保持原样（它们管的是本页数据的刷新节奏，
// 语义不同），全局顶栏只管"当前在看哪个市场"。
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { fetchMarketSession } from '../api'
import ErrorLogModal from './ErrorLogModal.vue'
import ThemeModal from './ThemeModal.vue'
import { errorUnread, errors } from '../errors'
import { currentTheme } from '../theme'
import {
  A_SHARE_MARKETS,
  currencyLabel,
  isAShare,
  marketLabel,
  US_SESSION_LABELS,
  usSession,
} from '../market'
import type { Market } from '../market'
import { useMarketStore } from '../stores/market'

const marketStore = useMarketStore()

/** 顶栏展示三个区：A股 / 港股 / 美股（沪深北统一为 A 股）。 */
const REGIONS = [
  { key: 'A', label: 'A股', markets: [...A_SHARE_MARKETS] },
  { key: 'HK', label: '港股', markets: ['HK'] },
  { key: 'US', label: '美股', markets: ['US'] },
] as const

function pickRegion(key: 'A' | 'HK' | 'US') {
  if (key === 'A') {
    // 回到上次的 A 股市场（默认沪市）
    const last = (['SH', 'SZ', 'BJ'] as Market[]).includes(marketStore.market)
      ? marketStore.market
      : (localStorage.getItem('easytdx.lastAshare') as Market | null)
    marketStore.setMarket(last && ['SH', 'SZ', 'BJ'].includes(last) ? last : 'SH')
    return
  }
  // 港美股依赖扩展栈；栈不可用时按钮已禁用，这里再挡一道防止脚本直调
  if (!marketStore.exAvailable) return
  marketStore.setMarket(key)
}

// ── 交易时段（按市场用各自时区）──────────────────────────────────────────────
// A股 09:15-11:30 / 13:00-15:05；港股 09:30-12:00 / 13:00-16:00；
// 美股四态见 usSession（盘前/盘中/盘后/夜盘）。
const SESSIONS: Record<Exclude<Market, 'US'>, { tz: string; windows: [number, number][] }> = {
  SH: { tz: 'Asia/Shanghai', windows: [[555, 690], [780, 905]] },
  SZ: { tz: 'Asia/Shanghai', windows: [[555, 690], [780, 905]] },
  BJ: { tz: 'Asia/Shanghai', windows: [[555, 690], [780, 905]] },
  HK: { tz: 'Asia/Hong_Kong', windows: [[570, 720], [780, 960]] },
}

const inSession = ref(false)
const usSessionLabel = ref('')

function refreshSession() {
  const m = marketStore.market
  if (m === 'US') {
    const s = usSession()
    usSessionLabel.value = US_SESSION_LABELS[s]
    inSession.value = s === 'open'
    return
  }
  usSessionLabel.value = ''
  const cfg = SESSIONS[m as Exclude<Market, 'US'>]
  const now = new Date().toLocaleString('en-US', { timeZone: cfg.tz })
  const d = new Date(now)
  const day = d.getDay()
  if (day === 0 || day === 6) {
    inSession.value = false
    return
  }
  const mins = d.getHours() * 60 + d.getMinutes()
  inSession.value = cfg.windows.some(([a, b]) => mins >= a && mins <= b)
}

const sessionLabel = computed(() => {
  if (marketStore.market === 'US') return usSessionLabel.value || '夜盘'
  return inSession.value ? '交易中' : '休市'
})

/** 市场说明文案：股票数 + 计价货币。 */
const marketMeta = computed(() => {
  const n = marketStore.symbolCount
  const cur = currencyLabel(marketStore.market)
  if (!n) return cur
  return `${n.toLocaleString()} 只 · ${cur}`
})

let sessionTimer = 0
onMounted(async () => {
  refreshSession()
  sessionTimer = window.setInterval(refreshSession, 60_000)
  await marketStore.loadMeta()
  // 元信息到位后可能改变可用性（扩展栈是否连上），再刷一次时段标签
  refreshSession()
  void fetchMarketSession().catch(() => undefined)
})

onUnmounted(() => {
  window.clearInterval(sessionTimer)
})

// ── 主题 / 全局异常入口 ─────────────────────────────────────────────────────
// 挂在「休市 · 交易中」这一组右侧：它们是「当前终端会话」层面的开关
// （配色、页面级故障），既不属于某个市场，也不属于某一页，放这里全局可见。
const themeOpen = ref(false)
const errOpen = ref(false)
</script>

<template>
  <header class="topbar">
    <div class="seg">
      <button
        v-for="r in REGIONS"
        :key="r.key"
        class="seg-btn"
        :class="{
          active:
            r.key === 'A' ? isAShare(marketStore.market) : marketStore.market === r.key,
        }"
        :disabled="r.key !== 'A' && !marketStore.exAvailable"
        :title="
          r.key !== 'A' && !marketStore.exAvailable
            ? `${r.label}行情不可用：扩展市场协议栈（端口 7727）未连接`
            : r.key === 'A'
              ? `A股（当前${marketLabel(marketStore.market)}）`
              : r.label
        "
        @click="pickRegion(r.key)"
      >
        {{ r.label }}
      </button>
    </div>

    <div class="topbar-right">
      <span class="market-meta">{{ marketMeta }}</span>
      <span class="sep" />
      <span class="dot" :class="{ live: inSession }" />
      <span class="session">{{ sessionLabel }}</span>
      <span class="sep" />
      <button
        class="tool"
        :title="`主题：${currentTheme.label}（点击切换）`"
        aria-label="切换主题"
        @click="themeOpen = true"
      >
        🎨
      </button>
      <button
        class="tool"
        :class="{ hot: errorUnread > 0 }"
        :title="
          errors.length
            ? `全局异常：${errors.length} 条记录${errorUnread ? `，${errorUnread} 条未读` : ''}（点击查看/复制/清空）`
            : '全局异常：暂无记录（点击查看）'
        "
        aria-label="查看全局异常"
        @click="errOpen = true"
      >
        🐛
        <span v-if="errorUnread" class="badge">{{ errorUnread > 99 ? '99+' : errorUnread }}</span>
      </button>
    </div>

    <ThemeModal v-if="themeOpen" @close="themeOpen = false" />
    <ErrorLogModal v-if="errOpen" @close="errOpen = false" />
  </header>
</template>

<style scoped>
.topbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  height: 38px;
  padding: 0 14px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
}
.seg {
  display: flex;
  gap: 2px;
  padding: 2px;
  background: var(--bg-elevated);
  border-radius: 6px;
}
.seg-btn {
  padding: 4px 14px;
  font-size: 12px;
  color: var(--text-muted);
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.seg-btn:hover:not(:disabled):not(.active) {
  color: var(--text);
  background: var(--bg-panel);
}
.seg-btn.active {
  color: #fff;
  background: var(--accent);
  font-weight: 600;
}
.seg-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--text-dim);
}
.market-meta {
  font-variant-numeric: tabular-nums;
}
.sep {
  width: 1px;
  height: 12px;
  background: var(--border);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-dim);
}
.dot.live {
  background: var(--up);
  box-shadow: 0 0 4px var(--up);
}
.session {
  min-width: 30px;
}

/* 主题 / 全局异常入口：与「交易中·休市」同一组的图标按钮 */
.tool {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 20px;
  padding: 0;
  font-size: 12px;
  line-height: 1;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  opacity: 0.75;
}
.tool:hover {
  background: var(--bg-elevated);
  border-color: var(--border);
  opacity: 1;
}
/* 有未读异常时点一下就跳出来提醒，否则用户永远不知道后台报过错 */
.tool.hot {
  opacity: 1;
  border-color: var(--up);
}
.tool.hot:hover {
  border-color: var(--up);
}
.badge {
  position: absolute;
  top: -5px;
  right: -7px;
  min-width: 13px;
  padding: 0 3px;
  font-size: 9px;
  line-height: 13px;
  font-family: var(--font-mono);
  text-align: center;
  color: #fff;
  background: var(--up);
  border-radius: 7px;
  font-variant-numeric: tabular-nums;
}
</style>