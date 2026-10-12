<script setup lang="ts">
// 个股日K图：K 线 + 指标全部由后端组装 option（pyecharts），
// 前端只做 setOption + 本地 tooltip 合并 + 主题重建。
// 指标选择（主图叠加 id + 副图 id + 参数 + 自定义公式）经父组件传入，
// 后端公式引擎计算、pyecharts 组装；K 线随选择一起 POST，无需二次拉取。
// 后端不可用时诚实降级（错误提示，不阻塞）。

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import echarts, { DOWN_COLOR, initChart, UP_COLOR, useChartRedraw } from '../echarts-setup'
import { fetchKlineOption, formatError } from '../api'
import {
  DEFAULT_INDICATOR_PARAMS,
  loadCustoms,
  subscribeIndicatorParams,
  type CustomIndicator,
  type IndicatorParams,
} from '../indicatorParams'
import { presetById } from '../presetFormulas'
import { currentTheme } from '../theme'
import { fmt2, fmtAmount, fmtVol } from '../format'
import type { Bar, KlineChartItem } from '../types'

const props = defineProps<{
  bars: Bar[]
  /** 单个主图指标（兼容旧调用点；与 overlays 同时给出时以 overlays 为准）。 */
  overlay?: string
  /** 主图叠加指标 id 列表（预置 + 自定义）。 */
  overlays?: string[]
  /** 副图指标 id（预置 + 自定义，'none' = 不画副图）。 */
  subPane?: string
  /** 指标参数（不传 = 默认口径）。由「系统 → 技术指标」管理页写入 localStorage 后经父组件传入。 */
  params?: IndicatorParams
  /** 首根 K 线的前收盘（首根涨跌幅基准；缺省用该根开盘价）。 */
  preClose?: number | null
  /** 成交量单位：A 股=手（万手/亿手），港美股=股（万股/亿股）。 */
  volUnitShares?: boolean
}>()

/** 生效参数：显式 prop > 默认。 */
const eff = computed<IndicatorParams>(() => props.params ?? DEFAULT_INDICATOR_PARAMS)
/** 生效的主图叠加 id 列表（显式 overlays prop 优先，否则取全局选择）。 */
const selOverlays = computed<string[]>(() => {
  if (Array.isArray(props.overlays)) return props.overlays.filter((o) => o !== 'none')
  if (props.overlay && props.overlay !== 'none') return [props.overlay]
  return (eff.value.overlays ?? []).filter((o) => o !== 'none')
})
/** 生效的副图 id（显式 subPane prop 优先，否则取全局选择）。 */
const selSub = computed<string>(() => props.subPane ?? eff.value.subPane ?? 'none')

// ── 服务端 option（异步） ────────────────────────────────────────────────

const indError = ref('')
let indSeq = 0
let indTimer: ReturnType<typeof setTimeout> | null = null
let indAbort: AbortController | null = null
let customsCache: CustomIndicator[] = loadCustoms()
const unsubCustoms = subscribeIndicatorParams(() => {
  customsCache = loadCustoms()
  scheduleRefresh()
})

function selectionKey(): string {
  const bars = props.bars
  return JSON.stringify({
    n: bars.length,
    f: bars[0]?.datetime,
    l: bars[bars.length - 1]?.datetime,
    o: selOverlays.value,
    s: selSub.value,
    p: eff.value,
    t: currentTheme.value.id,
  })
}
let activeKey = ''

function scheduleRefresh() {
  if (indTimer) clearTimeout(indTimer)
  indTimer = setTimeout(() => {
    void doRefresh()
  }, 150)
}

/** 选择态 → 服务端条目（公式文本 + 展示映射已决议，后端只算只装）。 */
function buildItems(): KlineChartItem[] {
  const p = eff.value
  const customById = new Map(customsCache.map((c) => [c.id, c]))
  const items: KlineChartItem[] = []
  const pushPreset = (id: string, pane: 'main' | 'sub') => {
    const preset = presetById(id)
    if (!preset) return
    const cols = preset.columns(p)
    const display: Record<string, string> = {}
    const colors: Record<string, string> = {}
    for (let i = 0; i < cols.length; i++) {
      display[cols[i]] = preset.displayName(cols[i])
      colors[cols[i]] = preset.colorFor(cols[i], i)
    }
    items.push({
      id,
      formula: preset.buildFormula(p),
      pane,
      display,
      colors,
      dashed: cols.filter((c) => preset.dashedFor(c)),
      bar_cols: cols.filter((c) => preset.isBar(c)),
    })
  }
  for (const id of selOverlays.value) {
    if (presetById(id)) {
      pushPreset(id, 'main')
      continue
    }
    const c = customById.get(id)
    // 自定义列名未知（算完才知道）：发空映射，后端按原文名 + 兜底色
    if (c && c.kind === 'overlay')
      items.push({ id, formula: c.formula, pane: 'main', display: {}, colors: {}, dashed: [], bar_cols: [], candle_cols: c.candle ?? [] })
  }
  const subId = selSub.value
  if (subId !== 'none') {
    if (presetById(subId)) pushPreset(subId, 'sub')
    else {
      const c = customById.get(subId)
      if (c && c.kind === 'sub') items.push({ id: subId, formula: c.formula, pane: 'sub', display: {}, colors: {}, dashed: [], bar_cols: [], candle_cols: [] })
    }
  }
  return items
}

/** 服务端 option（不含 tooltip/title，render 里合并本地项）。 */
const serverOpt = ref<Record<string, unknown> | null>(null)

async function doRefreshServer(seq: number, bars: Bar[], key: string) {
  const items = buildItems()
  indAbort = new AbortController()
  try {
    const resp = await fetchKlineOption(
      {
        bars: bars.map((b) => ({ datetime: b.datetime, open: b.open, high: b.high, low: b.low, close: b.close, vol: b.vol })),
        items,
        axis_color: currentTheme.value.vars['--border'] ?? '#2a2e3a',
      },
      indAbort.signal,
    )
    if (seq !== indSeq) return
    activeKey = key
    serverOpt.value = resp.option
    indError.value = ''
    render()
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    if (seq !== indSeq) return
    activeKey = key
    serverOpt.value = null
    indError.value = formatError(e)
    render()
  }
}

async function doRefresh() {
  const seq = ++indSeq
  indAbort?.abort()
  const bars = props.bars
  const key = selectionKey()
  if (bars.length === 0) {
    if (seq !== indSeq) return
    activeKey = key
    serverOpt.value = null
    indError.value = ''
    render()
    return
  }
  if (key === activeKey && serverOpt.value) return
  serverOpt.value = null
  await doRefreshServer(seq, bars, key)
}

/** 成交量格式化（A 股手 / 港美股股）。 */
function fmtVolUnit(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '-'
  if (!props.volUnitShares) return fmtVol(v)
  const n = Math.abs(v)
  if (n >= 1e8) return `${(v / 1e8).toFixed(2)}亿股`
  if (n >= 1e4) return `${(v / 1e4).toFixed(2)}万股`
  return String(Math.round(v))
}

const container = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function render() {
  if (!container.value || props.bars.length === 0) return
  chart ??= initChart(container.value)
  // option 后端已组装好，这里只合并本地项（tooltip + Y 轴 2 位小数）后照画
  if (!serverOpt.value) return
  const opt = { ...(serverOpt.value as Record<string, unknown>) }
  opt['tooltip'] = {
    trigger: 'axis',
    axisPointer: { type: 'cross' },
    formatter: makeTooltipFormatter(props.bars),
  }
  // 价格轴 2 位小数（formatter 是函数，过不了 JSON，后端只给空 axisLabel）
  if (Array.isArray(opt['yAxis']) && opt['yAxis'].length > 0) {
    const yAxes = [...(opt['yAxis'] as Array<Record<string, unknown>>)]
    const y0 = { ...(yAxes[0] ?? {}) }
    y0['axisLabel'] = {
      ...((y0['axisLabel'] as Record<string, unknown> | undefined) ?? {}),
      formatter: (v: number) => fmt2(v),
    }
    yAxes[0] = y0
    opt['yAxis'] = yAxes
  }
  chart.setOption(opt as never, true)
}

// OHLC/指标全部两位小数（用户约定：价格一律 2 位）。
// 首行补当日涨跌幅（该 K 线收盘相对前收）+ 成交量/额，
// 与主流行情悬浮窗一致；实时模式下最后一根为盘中未收盘 K 线，
// 其涨跌幅即当前涨跌幅（数据源即最新报价）。
// 本地 tooltip：服务端 option 里没有 tooltip，render 时合并。
function makeTooltipFormatter(bars: Bar[]) {
  return (params: unknown) => {
    const arr = params as Array<{ dataIndex: number; seriesName?: string; value?: unknown; data?: unknown }>
    if (!arr.length) return ''
    const i = arr[0].dataIndex
    const b = bars[i]
    if (!b) return ''
    // 分钟线显示到分钟（MM-DD HH:mm），日线及以上只显示日期
    const intraday = b.datetime.length > 13 && b.datetime.slice(11, 16) !== '00:00'
    const headDate = intraday ? b.datetime.slice(0, 16).replace('T', ' ').slice(5) : b.datetime.slice(0, 10)
    const prevClose = i > 0 ? bars[i - 1].close : (props.preClose ?? b.open)
    const pct = prevClose > 0 ? ((b.close / prevClose - 1) * 100) : null
    const color = b.close >= b.open ? UP_COLOR : DOWN_COLOR
    const pctText = pct === null ? '-' : `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`
    const head = [
      `<b>${headDate}</b>`,
      `开 <span style="color:${color}">${fmt2(b.open)}</span>　高 <span style="color:${color}">${fmt2(b.high)}</span>`,
      `低 <span style="color:${color}">${fmt2(b.low)}</span>　收 <b style="color:${color}">${fmt2(b.close)}</b>`,
      `涨跌 <b style="color:${color}">${pctText}</b>　量 ${fmtVolUnit(b.vol)}　额 ${fmtAmount(b.amount)}`,
    ]
    const rest = arr
      .filter((x) => x.seriesName && x.seriesName !== 'K线' && x.seriesName !== '成交量')
      .filter((x) => x.value != null && Number.isFinite(Number(x.value)))
      .map((x) => `${x.seriesName} ${fmt2(Number(x.value))}`)
    return [...head, ...rest].join('<br/>')
  }
}

function resize() {
  chart?.resize()
}

// 主题切换：ECharts 主题在建图那一刻就定死了，改 CSS 变量对它无效，
// 只能 dispose 后按新主题重建（轴色由后端按新主题重烘，顺带重拉）。
useChartRedraw(() => {
  chart?.dispose()
  chart = null
  scheduleRefresh()
})

onMounted(() => {
  render()
  scheduleRefresh()
  window.addEventListener('resize', resize)
})
onBeforeUnmount(() => {
  unsubCustoms()
  if (indTimer) clearTimeout(indTimer)
  indAbort?.abort()
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
// 选择/参数变化走异步刷新（防抖 + 过期丢弃）；bars 引用替换、
// overlays 原地增删（deep 兜底，只遍历小数组）都覆盖。
watch(
  () => [props.bars, props.overlay, props.overlays, props.subPane, props.params],
  scheduleRefresh,
)
watch(() => props.overlays, scheduleRefresh, { deep: true })
watch(() => [props.preClose, props.volUnitShares], render)
</script>

<template>
  <div class="kline-wrap">
    <div ref="container" class="stock-kline"></div>
    <div v-if="indError" class="ind-err">指标计算失败（仅显示 K 线）：{{ indError }}</div>
  </div>
</template>

<style scoped>
.kline-wrap {
  min-width: 0;
}
.stock-kline {
  width: 100%;
  height: 520px;
}
.ind-err {
  padding: 4px 0;
  font-size: 11px;
  color: var(--warn);
}
</style>
