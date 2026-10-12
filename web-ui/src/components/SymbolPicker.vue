<script setup lang="ts">
// 选标的 + 配置日期范围（取行情由父组件在「开始回测/开始寻优」时触发）。
// 市场三选一：A 股（6 位代码智能识别沪/深/北）/ 港股（4-5 位数字）/ 美股（字母）。
// 港美股提供搜索框（服务端索引），A 股沿用旧的 6 位直输。
// 后端 /bars 仅支持 count（上限 800，约 3.2 年），固定拉满后前端按日期过滤。
// 默认：结束日=今天（最近交易日），开始日=2020-01-06。

import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { fetchBars, formatError, searchOverseasSymbols, type OverseasSymbol } from '../api'
import { detectAShareMarket, marketLabel, type Market } from '../market'
import { useBacktestStore } from '../stores/backtest'
import type { Category } from '../types'

const store = useBacktestStore()

// 代码 / 周期 / 日期通过 defineModel 与父组件双向同步：
// 既允许父组件读取（如寻优页「查看」按钮拼 URL 带上这些值），
// 也允许父组件写入（如回测页从 URL query 回填表单）。
// 未绑定时取默认值，向后兼容。
//
// 注意：defineModel 的 default 不能引用本 <script setup> 内声明的局部函数
// （编译期会被 hoist 到 setup() 外，此时函数还未定义），
// 因此日期默认值用内联字面量表达式计算。
const code = defineModel<string>('code', { default: '000001' })
const category = defineModel<Category>('category', { default: 'DAY' })
const startDate = defineModel<string>('startDate', {
  default: '2020-01-06',
})
const endDate = defineModel<string>('endDate', {
  default: new Date().toISOString().slice(0, 10),
})
// 市场（A 股三市共用 'A'，港股 'HK'，美股 'US'）。老调用方不传 = A 股。
const market = defineModel<string>('market', { default: 'A' })

const error = ref('')
// loading 由父组件控制（回测/寻优时驱动），组件自身只暴露 loadBars
const loading = ref(false)

const CATEGORIES: Category[] = ['DAY', 'WEEK', 'MONTH', 'MIN_5', 'MIN_15', 'MIN_30', 'MIN_60', 'MIN_120']

const MARKET_TABS: Array<{ value: string; label: string }> = [
  { value: 'A', label: 'A股' },
  { value: 'HK', label: '港股' },
  { value: 'US', label: '美股' },
]

// ── 港美股搜索 ──────────────────────────────────────────────────────────────

const searchText = ref('')
const searchResults = ref<OverseasSymbol[]>([])
const searchError = ref('')
const searching = ref(false)
let searchTimer = 0

function onSearchInput() {
  window.clearTimeout(searchTimer)
  searchError.value = ''
  const kw = searchText.value.trim()
  if (!kw || market.value === 'A') {
    searchResults.value = []
    return
  }
  searchTimer = window.setTimeout(async () => {
    searching.value = true
    try {
      const resp = await searchOverseasSymbols(market.value, kw, 12)
      searchResults.value = resp.data
    } catch (e) {
      // 之前这里是空 catch：搜索失败时用户只看到空列表，没有任何提示
      searchResults.value = []
      searchError.value = formatError(e)
    } finally {
      searching.value = false
    }
  }, 300)
}

// 卸载时清掉待触发的防抖定时器：否则组件（路由切换 / v-if）卸载后回调仍会
// 发出请求并写已卸载组件的 ref。
onBeforeUnmount(() => {
  window.clearTimeout(searchTimer)
})

function pickOverseas(s: OverseasSymbol) {
  code.value = s.code
  searchText.value = ''
  searchResults.value = []
}

/** 切换市场时清空代码与搜索态，避免 A 股代码残留到港美股。 */
watch(market, () => {
  code.value = ''
  searchText.value = ''
  searchResults.value = []
  error.value = ''
})

// 智能识别的市场标签（A 股按 6 位规则；港美股直接显示）。
const detectedMarket = computed(() => {
  if (market.value === 'HK') return '港股'
  if (market.value === 'US') return '美股'
  return code.value && /^\d{6}$/.test(code.value) ? marketLabel(detectAShareMarket(code.value)) : ''
})

const codePlaceholder = computed(() =>
  market.value === 'A' ? '6位代码（市场自动识别）' : market.value === 'HK' ? '如 00700（可上方搜索）' : '如 AAPL（可上方搜索）',
)

/** 取行情（由父组件在点击「开始回测/开始寻优」时调用）。
 * 成功返回 true，失败返回 false（并把错误写入 store.error 供父组件感知）。 */
async function loadBars(): Promise<boolean> {
  // 基本校验（按市场区分代码形状）
  const c = code.value.trim().toUpperCase()
  if (market.value === 'A') {
    if (!/^\d{6}$/.test(c)) {
      error.value = '股票代码必须是 6 位数字'
      store.error = error.value
      return false
    }
  } else if (market.value === 'HK') {
    if (!/^\d{4,5}$/.test(c)) {
      error.value = '港股代码为 4-5 位数字（如 00700）'
      store.error = error.value
      return false
    }
  } else {
    if (!/^[A-Z][A-Z0-9.\-]{0,11}$/.test(c)) {
      error.value = '美股代码为字母（如 AAPL）'
      store.error = error.value
      return false
    }
  }
  if (startDate.value >= endDate.value) {
    error.value = '开始日期必须早于结束日期'
    store.error = error.value
    return false
  }

  loading.value = true
  error.value = ''
  try {
    const mkt: Market =
      market.value === 'A' ? detectAShareMarket(c) : (market.value as Market)
    const bars = await fetchBars(mkt, c, category.value, startDate.value, endDate.value)
    if (bars.length < 2) {
      error.value = `该日期范围内仅取到 ${bars.length} 根 K 线，不足以回测`
      store.error = error.value
      return false
    }
    const range = `${startDate.value} ~ ${endDate.value}`
    store.setOhlcv(bars, `${mkt}:${c} ${category.value} ${range}`)
    store.clearResult()
    return true
  } catch (e) {
    error.value = formatError(e)
    store.error = error.value
    return false
  } finally {
    loading.value = false
  }
}

// 暴露给父组件（BacktestView / OptimizeView）在「开始回测/寻优」时串联调用
defineExpose({ loadBars, loading })
</script>

<template>
  <div class="symbol-picker">
    <div class="field">
      <label>市场</label>
      <span class="seg">
        <button
          v-for="t in MARKET_TABS"
          :key="t.value"
          class="chip"
          :class="{ on: market === t.value }"
          @click="market = t.value"
        >
          {{ t.label }}
        </button>
      </span>
    </div>

    <div v-if="market !== 'A'" class="field search-field">
      <label>搜索</label>
      <input
        v-model="searchText"
        :placeholder="market === 'HK' ? '代码/名称，如 00700 腾讯' : '代码/名称，如 AAPL 苹果'"
        @input="onSearchInput"
      />
      <div v-if="searching" class="search-hint">搜索中…</div>
      <div v-else-if="searchError" class="search-hint err">{{ searchError }}</div>
      <div v-else-if="searchResults.length > 0" class="search-list">
        <div v-for="s in searchResults" :key="s.symbol" class="search-row" @click="pickOverseas(s)">
          <span class="s-name">{{ s.name || s.code }}</span>
          <span class="s-code mono">{{ s.symbol }}</span>
          <span v-if="s.sub_market" class="s-sub">{{ s.sub_market }}</span>
        </div>
      </div>
    </div>

    <div class="field code-field">
      <label>代码</label>
      <input v-model="code" :maxlength="market === 'US' ? 12 : 6" :placeholder="codePlaceholder" />
      <span v-if="detectedMarket" class="market-tag">{{ detectedMarket }}</span>
    </div>

    <div class="field">
      <label>周期</label>
      <select v-model="category">
        <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
      </select>
    </div>

    <div class="row">
      <div class="field">
        <label>开始日期</label>
        <input v-model="startDate" type="date" />
      </div>
      <div class="field">
        <label>结束日期</label>
        <input v-model="endDate" type="date" />
      </div>
    </div>

    <p v-if="error" class="err">{{ error }}</p>
    <p v-if="store.barsSource" class="ok">
      已加载：{{ store.barsSource }}（{{ store.ohlcv.length }} 根）
    </p>
  </div>
</template>

<style scoped>
.code-field {
  position: relative;
}
.code-field input {
  padding-right: 70px;
}
.market-tag {
  position: absolute;
  right: 8px;
  bottom: 8px;
  font-size: 11px;
  color: var(--text-dim);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  padding: 1px 6px;
  border-radius: 3px;
}
.seg {
  display: inline-flex;
  gap: 4px;
}
.chip {
  padding: 2px 10px;
  font-size: 12px;
}
.chip.on {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(74, 158, 255, 0.12);
}
.search-field {
  position: relative;
}
.search-hint {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 4px;
}
.search-hint.err {
  color: var(--down);
}
.search-list {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 30;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-top: 4px;
  max-height: 260px;
  overflow: auto;
  box-shadow: 0 8px 24px var(--shadow);
}
.search-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
}
.search-row:hover {
  background: var(--bg-elevated);
}
.s-name {
  font-weight: 600;
}
.s-code {
  font-size: 11px;
  color: var(--text-dim);
}
.s-sub {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-dim);
}
.err {
  color: var(--up);
  font-size: 12px;
  margin-top: 8px;
}
.ok {
  color: var(--down);
  font-size: 12px;
  margin-top: 8px;
}
</style>