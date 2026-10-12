<script setup lang="ts">
// 个股日K图：candlestick + 成交量 + 可选主图指标（MA/BOLL/EMA）
// + 可选副图指标（MACD/KDJ/RSI）。指标由父组件传选择，前端本地计算
// （indicators.ts，与后端 MyTT 同口径）。

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import echarts, { chartAxisColor, DOWN_COLOR, initChart, UP_COLOR, useChartRedraw } from '../echarts-setup'
import { boll, ema, macd as calcMacd, kdj as calcKdj, rsi as calcRsi } from '../indicators'
import {
  DEFAULT_INDICATOR_PARAMS,
  maColors,
  rsiColors,
  type IndicatorParams,
} from '../indicatorParams'
import { fmt2, fmtAmount, fmtVol } from '../format'
import type { Bar } from '../types'

/** 主图指标（可多选叠加；'none' 表示主图不画指标线）。 */
export type Overlay = 'ma' | 'boll' | 'ema'
/** 副图指标（'none' 表示不画副图）。 */
export type SubPane = 'none' | 'macd' | 'kdj' | 'rsi'

const props = defineProps<{
  bars: Bar[]
  /** 单个主图指标（兼容旧调用点；与 overlays 同时给出时以 overlays 为准）。 */
  overlay?: Overlay | 'none'
  /** 主图叠加列表（v1.33：支持 MA+EMA+BOLL 同时显示）。 */
  overlays?: Overlay[]
  subPane?: SubPane
  /** 指标参数（不传 = 默认口径）。由指标编辑器写入 localStorage 后经父组件传入。 */
  params?: IndicatorParams
  /** 首根 K 线的前收盘（首根涨跌幅基准；缺省用该根开盘价）。 */
  preClose?: number | null
  /** 成交量单位：A 股=手（万手/亿手），港美股=股（万股/亿股）。 */
  volUnitShares?: boolean
}>()

/** 生效参数：显式 prop > 默认。 */
const eff = computed<IndicatorParams>(() => props.params ?? DEFAULT_INDICATOR_PARAMS)
/**
 * 生效的主图叠加列表：显式 overlays prop 优先；其次单个 overlay prop
 * （兼容弹窗快捷切换）；否则取 params 里的多选列表，最后兜底单值。
 */
const effOverlays = computed<Overlay[]>(() => {
  const clean = (list: Array<Overlay | 'none'>): Overlay[] =>
    list.filter((o): o is Overlay => o !== 'none')
  if (Array.isArray(props.overlays)) return clean(props.overlays)
  if (props.overlay) return clean([props.overlay])
  const list = eff.value.overlays
  if (Array.isArray(list) && list.length > 0) return clean(list)
  return clean([eff.value.overlay])
})
const effSubPane = computed<SubPane>(() => props.subPane ?? eff.value.subPane)

const container = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

const closes = computed(() => props.bars.map((b) => b.close))
const highs = computed(() => props.bars.map((b) => b.high))
const lows = computed(() => props.bars.map((b) => b.low))

/** 成交量格式化（A 股手 / 港美股股）。 */
function fmtVolUnit(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '-'
  if (!props.volUnitShares) return fmtVol(v)
  const n = Math.abs(v)
  if (n >= 1e8) return `${(v / 1e8).toFixed(2)}亿股`
  if (n >= 1e4) return `${(v / 1e4).toFixed(2)}万股`
  return String(Math.round(v))
}

interface LineSpec {
  name: string
  data: Array<number | null>
  color: string
  dashed?: boolean
}

/** 主图指标线：按叠加列表依次产出（MA+EMA+BOLL 可同时出现）。 */
const overlayLines = computed<LineSpec[]>(() => {
  const c = closes.value
  const p = eff.value
  const out: LineSpec[] = []
  for (const kind of effOverlays.value) {
    if (kind === 'ma') {
      p.maPeriods.forEach((n, i) => {
        out.push({ name: `MA${n}`, data: maLocal(c, n), color: maColors(i) })
      })
    } else if (kind === 'ema') {
      out.push({ name: `EMA${p.emaFast}`, data: ema(c, p.emaFast), color: '#22d3ee' })
      out.push({ name: `EMA${p.emaSlow}`, data: ema(c, p.emaSlow), color: '#c084fc' })
    } else if (kind === 'boll') {
      const { mid, upper, lower } = boll(c, p.bollN, p.bollP)
      out.push({ name: 'BOLL中轨', data: mid, color: '#f0a020' })
      out.push({ name: 'BOLL上轨', data: upper, color: '#94a3b8', dashed: true })
      out.push({ name: 'BOLL下轨', data: lower, color: '#94a3b8', dashed: true })
    }
  }
  return out
})

function maLocal(data: number[], n: number): Array<number | null> {
  const out: Array<number | null> = []
  let sum = 0
  for (let i = 0; i < data.length; i++) {
    sum += data[i]
    if (i >= n) sum -= data[i - n]
    out.push(i >= n - 1 ? sum / n : null)
  }
  return out
}

function render() {
  if (!container.value || props.bars.length === 0) return
  chart ??= initChart(container.value)
  chart.setOption(buildOption(), true)
}

function buildOption(): echarts.EChartsCoreOption {
  const bars = props.bars
  const dates = bars.map((b) => b.datetime.slice(0, 10))
  const ohlc = bars.map((b) => [b.open, b.close, b.low, b.high])
  const sub = effSubPane.value
  const hasSub = sub !== 'none'
  const start = Math.max(0, 100 - (120 / bars.length) * 100)

  // 布局：K 区 / 量区 /（可选）副图区
  const grids = [
    { left: 56, right: 16, top: 28, height: hasSub ? '48%' : '60%' },
    { left: 56, right: 16, top: hasSub ? '64%' : '74%', height: hasSub ? '13%' : '18%' },
  ]
  const xAxes: echarts.EChartsCoreOption[] = [
    { type: 'category', gridIndex: 0, data: dates, boundaryGap: true, axisLabel: { show: false }, axisTick: { show: false } },
    { type: 'category', gridIndex: 1, data: dates, boundaryGap: true, axisTick: { show: false } },
  ]
  const yAxes: echarts.EChartsCoreOption[] = [
    { gridIndex: 0, scale: true, axisLabel: { formatter: (v: number) => fmt2(v) }, splitLine: { lineStyle: { color: chartAxisColor() } } },
    { gridIndex: 1, axisLabel: { show: false }, splitLine: { show: false } },
  ]
  if (hasSub) {
    grids.push({ left: 56, right: 16, top: '81%', height: '13%' } as never)
    xAxes.push({ type: 'category', gridIndex: 2, data: dates, boundaryGap: true, axisTick: { show: false } })
    yAxes.push({ gridIndex: 2, scale: true, axisLabel: { fontSize: 10 }, splitLine: { show: false } })
  }

  const series: echarts.EChartsCoreOption[] = [
    {
      name: 'K线',
      type: 'candlestick',
      xAxisIndex: 0,
      yAxisIndex: 0,
      data: ohlc,
      itemStyle: {
        color: UP_COLOR,
        color0: DOWN_COLOR,
        borderColor: UP_COLOR,
        borderColor0: DOWN_COLOR,
      },
    },
    ...overlayLines.value.map(
      (l) =>
        ({
          name: l.name,
          type: 'line',
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: l.data,
          showSymbol: false,
          connectNulls: false,
          lineStyle: { width: 1, color: l.color, type: l.dashed ? 'dashed' : 'solid' },
          itemStyle: { color: l.color },
        }) as never,
    ),
    {
      name: '成交量',
      type: 'bar',
      xAxisIndex: 1,
      yAxisIndex: 1,
      data: bars.map((b) => ({
        value: b.vol,
        itemStyle: { color: b.close >= b.open ? UP_COLOR : DOWN_COLOR },
      })),
      barWidth: '60%',
    },
  ]

  // 副图指标（参数取自指标编辑器）
  const c = closes.value
  const ip = eff.value
  if (sub === 'macd') {
    const { dif, dea, hist } = calcMacd(c, ip.macdFast, ip.macdSlow, ip.macdSignal)
    series.push(
      {
        name: 'DIF',
        type: 'line',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: dif,
        showSymbol: false,
        lineStyle: { width: 1, color: '#f0a020' },
      },
      {
        name: 'DEA',
        type: 'line',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: dea,
        showSymbol: false,
        lineStyle: { width: 1, color: '#4a9eff' },
      },
      {
        name: 'MACD',
        type: 'bar',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: hist.map((v) => ({
          value: v,
          itemStyle: { color: (v ?? 0) >= 0 ? UP_COLOR : DOWN_COLOR },
        })),
        barWidth: '50%',
      },
    )
  } else if (sub === 'kdj') {
    const { k, d, j } = calcKdj(highs.value, lows.value, c, ip.kdjN)
    series.push(
      {
        name: 'K',
        type: 'line',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: k,
        showSymbol: false,
        lineStyle: { width: 1, color: '#f0a020' },
      },
      {
        name: 'D',
        type: 'line',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: d,
        showSymbol: false,
        lineStyle: { width: 1, color: '#4a9eff' },
      },
      {
        name: 'J',
        type: 'line',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: j,
        showSymbol: false,
        lineStyle: { width: 1, color: '#c084fc' },
      },
    )
  } else if (sub === 'rsi') {
    for (let i = 0; i < ip.rsiPeriods.length; i++) {
      const n = ip.rsiPeriods[i]
      series.push({
        name: `RSI${n}`,
        type: 'line',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: calcRsi(c, n),
        showSymbol: false,
        lineStyle: { width: 1, color: rsiColors(i) },
      })
    }
  }

  const legendNames = ['K线', ...overlayLines.value.map((l) => l.name)]
  if (hasSub) {
    legendNames.push(sub === 'macd' ? 'DIF,DEA' : sub === 'kdj' ? 'K,D,J' : 'RSI')
  }

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      // OHLC/指标全部两位小数（用户约定：价格一律 2 位）。
      // 首行补当日涨跌幅（该 K 线收盘相对前收）+ 成交量/额，
      // 与主流行情悬浮窗一致；实时模式下最后一根为盘中未收盘 K 线，
      // 其涨跌幅即当前涨跌幅（数据源即最新报价）。
      formatter: (params: unknown) => {
        const arr = params as Array<{ dataIndex: number; seriesName?: string; value?: unknown; data?: unknown }>
        if (!arr.length) return ''
        const i = arr[0].dataIndex
        const b = bars[i]
        if (!b) return ''
        const prevClose = i > 0 ? bars[i - 1].close : (props.preClose ?? b.open)
        const pct = prevClose > 0 ? ((b.close / prevClose - 1) * 100) : null
        const color = b.close >= b.open ? UP_COLOR : DOWN_COLOR
        const pctText = pct === null ? '-' : `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`
        const head = [
          `<b>${b.datetime.slice(0, 10)}</b>`,
          `开 <span style="color:${color}">${fmt2(b.open)}</span>　高 <span style="color:${color}">${fmt2(b.high)}</span>`,
          `低 <span style="color:${color}">${fmt2(b.low)}</span>　收 <b style="color:${color}">${fmt2(b.close)}</b>`,
          `涨跌 <b style="color:${color}">${pctText}</b>　量 ${fmtVolUnit(b.vol)}　额 ${fmtAmount(b.amount)}`,
        ]
        const rest = arr
          .filter((x) => x.seriesName && x.seriesName !== 'K线' && x.seriesName !== '成交量')
          .filter((x) => x.value != null && Number.isFinite(Number(x.value)))
          .map((x) => `${x.seriesName} ${fmt2(Number(x.value))}`)
        return [...head, ...rest].join('<br/>')
      },
    },
    legend: { data: legendNames, top: 0, textStyle: { fontSize: 11 } },
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, ...(hasSub ? [2] : [])], start, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1, ...(hasSub ? [2] : [])], bottom: 4, start, end: 100, height: 16 },
    ],
    series,
  }
}

function resize() {
  chart?.resize()
}

// 主题切换：ECharts 主题在建图那一刻就定死了，改 CSS 变量对它无效，
// 只能 dispose 后按新主题重建（render 内已改成 initChart + 主题感知）。
useChartRedraw(() => {
  chart?.dispose()
  chart = null
  render()
})

onMounted(() => {
  render()
  window.addEventListener('resize', resize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
// 注意：必须把 props.overlays 纳入监听。父组件（个股/板块弹窗）的 MA/BOLL/EMA
// 勾选按钮是**原地修改**指标参数对象后经 computed 传下来的，props.overlays 变了
// 但 props.params 的引用没变——只监听 params 会导致"chip 高亮变了、图不动"。
watch(() => [props.bars, props.overlay, props.overlays, props.subPane, props.params], render)
// overlays 是数组，原地增删元素时引用可能不变，单独用 deep 监听兜底
// （只深度遍历这个小数组，不碰体量大的 bars）。
watch(() => props.overlays, render, { deep: true })
watch(() => [props.preClose, props.volUnitShares], render)
</script>

<template>
  <div ref="container" class="stock-kline"></div>
</template>

<style scoped>
.stock-kline {
  width: 100%;
  height: 520px;
}
</style>
