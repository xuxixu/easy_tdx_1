<script setup lang="ts">
// A 股 K 线面板（看板右侧常驻）：默认当前市场指数，可输 6 位代码切换。
//
// 与外盘看板（OverseasDashboard）的 K 线面板是同一概念的不同实现：
// A 股代码无歧义（6 位直输 + detectAShareMarket），不需要服务端搜索框。
import { computed, ref, watch } from 'vue'

import { fetchBars, fetchSymbolName, formatError } from '../api'
import { loadIndicatorParams, type IndicatorParams } from '../indicatorParams'
import { detectAShareMarket, MARKET_DEFAULT_INDEX, marketLabel, type Market } from '../market'
import type { Bar } from '../types'
import IndicatorEditor from './IndicatorEditor.vue'
import StockDialog from './StockDialog.vue'
import StockKline from './StockKline.vue'

const props = defineProps<{ market: Market }>()

interface Focal {
  market: string
  code: string
  name: string
}

const focal = ref<Focal>({ ...MARKET_DEFAULT_INDEX[props.market] })

watch(
  () => props.market,
  (m) => {
    focal.value = { ...MARKET_DEFAULT_INDEX[m] }
    inputCode.value = ''
    loadBars()
  },
)

const inputCode = ref('')
const inputError = ref('')

const bars = ref<Bar[]>([])
const barsError = ref('')
const barsLoading = ref(false)
const kCategory = ref<'DAY' | 'WEEK' | 'MONTH'>('DAY')
const K_CATS: Array<{ value: 'DAY' | 'WEEK' | 'MONTH'; label: string }> = [
  { value: 'DAY', label: '日K' },
  { value: 'WEEK', label: '周K' },
  { value: 'MONTH', label: '月K' },
]

const indParams = ref<IndicatorParams>(loadIndicatorParams())
const showIndEditor = ref(false)
const dialog = ref<Focal | null>(null)

const title = computed(
  () => `${marketLabel(props.market)}指数 · ${focal.value.name}`,
)

async function loadBars() {
  barsLoading.value = true
  barsError.value = ''
  try {
    const fetched = await fetchBars(
      focal.value.market,
      focal.value.code,
      kCategory.value,
      undefined,
      undefined,
    )
    if (fetched.length === 0) throw new Error('无K线数据')
    bars.value = fetched.slice(-250)
  } catch (e) {
    bars.value = []
    barsError.value = formatError(e)
  } finally {
    barsLoading.value = false
  }
}

watch(kCategory, loadBars)

async function applyCode() {
  const c = inputCode.value.trim()
  inputError.value = ''
  if (!/^\d{6}$/.test(c)) {
    inputError.value = '请输入 6 位 A 股代码'
    return
  }
  const mkt = detectAShareMarket(c)
  const name = (await fetchSymbolName(mkt, c)) || c
  setFocal(mkt, c, name)
  inputCode.value = ''
}

/** 外部切换标的（看板指数卡点击）。 */
function setFocal(market: string, code: string, name: string) {
  focal.value = { market, code, name }
  loadBars()
}

defineExpose({ setFocal })

loadBars()
</script>

<template>
  <div class="card k-panel">
    <div class="k-head">
      <h3>{{ title }} <span class="dim mono code">{{ focal.market }}{{ focal.code }}</span></h3>
      <span class="k-cats">
        <button
          v-for="c in K_CATS"
          :key="c.value"
          class="chip"
          :class="{ on: kCategory === c.value }"
          @click="kCategory = c.value"
        >
          {{ c.label }}
        </button>
      </span>
      <button class="chip ind-edit" title="编辑指标参数" @click="showIndEditor = true">⚙ 指标</button>
      <button class="chip" title="打开分时/盘口弹窗" @click="dialog = { ...focal }">分时/盘口 ⌗</button>
    </div>
    <div class="k-search">
      <input
        v-model="inputCode"
        class="code-input"
        maxlength="6"
        placeholder="输入 6 位代码切换（如 600519）"
        @keyup.enter="applyCode"
      />
      <button class="chip" @click="applyCode">查看</button>
      <span v-if="inputError" class="err">{{ inputError }}</span>
    </div>
    <div v-if="barsLoading" class="loading">加载中…</div>
    <div v-else-if="barsError" class="err">{{ barsError }}</div>
    <StockKline v-else :bars="bars" :params="indParams" />
    <IndicatorEditor v-if="showIndEditor" v-model="indParams" @close="showIndEditor = false" />
    <StockDialog
      v-if="dialog"
      :market="dialog.market"
      :code="dialog.code"
      :name="dialog.name"
      @close="dialog = null"
    />
  </div>
</template>

<style scoped>
.k-panel {
  min-width: 0;
  margin-bottom: 10px;
}
.k-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.k-head h3 {
  margin-right: auto;
}
.k-head .code {
  font-size: 11px;
  font-weight: 400;
}
.k-cats {
  display: inline-flex;
  gap: 4px;
}
.chip {
  padding: 2px 8px;
  font-size: 11px;
}
.chip.on {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(74, 158, 255, 0.12);
}
.k-search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
}
.code-input {
  width: 220px;
  padding: 5px 10px;
  font-size: 12px;
}
.err {
  color: var(--up);
  font-size: 12px;
}
.loading {
  color: var(--text-dim);
  padding: 12px 0;
  font-size: 12px;
}
.dim {
  color: var(--text-dim);
}
</style>