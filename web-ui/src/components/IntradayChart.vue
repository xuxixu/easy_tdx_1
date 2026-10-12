<script setup lang="ts">
// 分时图（ECharts）：价格线 + 渐变面积 + 均价线 + 昨收基准虚线 + 成交量副图。
// 单日模式：y 轴围绕昨收对称（分时图惯例）。
// 多日模式（dayMarks 提供每天起始索引）：y 轴自适应全段，天与天之间
// markLine 竖分隔，x 轴只在每天首点显示日期（借鉴多日分时惯例）。

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import echarts, { chartAxisColor, DOWN_COLOR, initChart, UP_COLOR, useChartRedraw } from '../echarts-setup'
import { fmt2, fmtVol } from '../format'
import type { MinutePoint } from '../types'

const props = defineProps<{
  points: MinutePoint[]
  preClose?: number | null
  /** 多日模式：每天起始索引 + 日期标签。 */
  dayMarks?: Array<{ start: number; date: string }>
  /** 成交量单位：A 股=手（万手/亿手），港美股=股（万股/亿股）。 */
  volUnitShares?: boolean
}>()

const container = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

const isMultiDay = () => (props.dayMarks?.length ?? 0) > 1

function render() {
  if (!container.value) return
  if (props.points.length === 0) return
  chart ??= initChart(container.value)
  chart.setOption(buildOption(), true)
}

function buildOption(): echarts.EChartsCoreOption {
  const pts = props.points
  const multi = isMultiDay()
  // 基准（量柱首色与 tooltip 涨跌幅）：单日用昨收，多日用全段首价
  const base = !multi && props.preClose && props.preClose > 0 ? props.preClose : pts[0]?.price ?? 0

  const times = pts.map((p) => p.datetime.slice(11, 16))
  const prices = pts.map((p) => p.price)

  // 均价线：累计成交额近似 = Σ(price×vol)，均价 = cumAmount / cumVol
  let cumAmt = 0
  let cumVol = 0
  const avgPrices = pts.map((p) => {
    cumAmt += p.price * Math.max(p.vol, 0)
    cumVol += Math.max(p.vol, 0)
    return cumVol > 0 ? cumAmt / cumVol : p.price
  })

  // y 轴范围：单日围绕昨收对称；多日自适应全段
  const hi = Math.max(...prices)
  const lo = Math.min(...prices)
  let yMax: number
  let yMin: number
  if (multi) {
    const pad = (hi - lo) * 0.08 || hi * 0.002
    yMax = hi + pad
    yMin = lo - pad
  } else {
    const hi2 = Math.max(base, hi)
    const lo2 = Math.min(base, lo)
    const pad = Math.max((hi2 - lo2) * 0.1, base * 0.0025)
    yMax = hi2 + pad
    yMin = lo2 - pad
  }

  // 量柱颜色：与前一分钟价格比较（红涨绿跌），首柱与基准比
  const volColors = pts.map((p, i) => {
    const prev = i > 0 ? pts[i - 1].price : base
    return p.price >= prev ? UP_COLOR : DOWN_COLOR
  })

  // x 轴刻度：单日在关键时点；多日只在每天首点显示 MM-DD
  const markStarts = new Map((props.dayMarks ?? []).map((m) => [m.start, m.date]))
  const labelInterval = multi
    ? (index: number) => markStarts.has(index)
    : (index: number) => [0, 60, 120, 121, 180, 239].includes(index)
  const labelFormatter = multi
    ? (v: string) => {
        const idx = times.indexOf(v)
        const d = markStarts.get(idx)
        return d ? d.slice(5) : ''
      }
    : (v: string) => v

  // 成交量格式化：A 股手 / 港美股股
  const fmtVolUnit = (v: number): string => {
    if (!Number.isFinite(v) || v <= 0) return '0'
    if (props.volUnitShares) {
      if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿股`
      if (v >= 1e4) return `${(v / 1e4).toFixed(2)}万股`
      return String(Math.round(v))
    }
    return fmtVol(v)
  }

  // 每点相对基准的涨跌幅（%）：分时图 hover 的核心信息，主流行情都显示
  const pcts = base > 0 ? pts.map((p) => ((p.price / base - 1) * 100)) : pts.map(() => 0)
  // 右轴：与主图同量纲的涨跌幅刻度（右侧百分比，与左侧价格一一对应）
  const pctAxisMax = Math.max(...pcts.map(Math.abs), 0.05)

  // 多日分隔线 + 单日昨收基准线
  const markLines: Array<Record<string, unknown>> = multi
    ? (props.dayMarks ?? [])
        .filter((m) => m.start > 0)
        .map((m) => ({ xAxis: m.start - 0.5, lineStyle: { color: chartAxisColor(), type: 'dashed', width: 1 } }))
    : [{ yAxis: base, lineStyle: { color: '#5c6370', type: 'dashed', width: 1 } }]

  return {
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: (params: unknown) => {
        const arr = params as Array<{ dataIndex: number }>
        const i = arr[0]?.dataIndex ?? 0
        const p = pts[i]
        if (!p) return ''
        const pct = pcts[i]
        const color = pct >= 0 ? UP_COLOR : DOWN_COLOR
        const pctText = base > 0 ? `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%` : '-'
        return [
          `${p.datetime.slice(5, 16)}`,
          `价 <b style="color:${color}">${fmt2(p.price)}</b>`,
          `涨跌 <b style="color:${color}">${pctText}</b>`,
          `均 ${fmt2(avgPrices[i])}`,
          `量 ${fmtVolUnit(p.vol)}`,
        ].join('<br/>')
      },
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 56, right: 52, top: 16, height: '58%' },
      { left: 56, right: 52, top: '74%', height: '20%' },
    ],
    xAxis: [
      {
        type: 'category',
        gridIndex: 0,
        data: times,
        boundaryGap: false,
        axisLabel: { show: false },
        axisTick: { show: false },
      },
      {
        type: 'category',
        gridIndex: 1,
        data: times,
        boundaryGap: false,
        axisTick: { show: false },
        axisLabel: { interval: labelInterval, formatter: labelFormatter },
      },
    ],
    yAxis: [
      {
        gridIndex: 0,
        min: yMin,
        max: yMax,
        axisLabel: { formatter: (v: number) => fmt2(v) },
        splitLine: { lineStyle: { color: chartAxisColor() } },
      },
      // 右轴涨跌幅（与价格轴线性对应，仅单日有意义）
      {
        gridIndex: 0,
        // grid 有两个（主图 + 成交量副图），ECharts 按 gridIndex % 2 推导轴的
        // 默认 position，gridIndex 0 会落成 'left'、正好压在价格轴上——右轴
        // 必须显式声明，否则两个轴叠在左边（grid 右边距就是给它留的位）。
        position: 'right',
        min: -pctAxisMax,
        max: pctAxisMax,
        axisLabel: {
          show: !multi && base > 0,
          formatter: (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`,
          color: '#6b7280',
          fontSize: 9,
        },
        splitLine: { show: false },
      },
      {
        gridIndex: 1,
        axisLabel: { show: false },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '价格',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: prices,
        showSymbol: false,
        lineStyle: { width: 1.3, color: '#4a9eff' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(74,158,255,0.25)' },
              { offset: 1, color: 'rgba(74,158,255,0.02)' },
            ],
          },
        },
        markLine: {
          silent: true,
          symbol: 'none',
          label: { show: false },
          data: markLines,
        },
      },
      {
        name: '均价',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: avgPrices,
        showSymbol: false,
        lineStyle: { width: 1, color: '#f0a020' },
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        // yAxis 数组顺序：[0]价格(主图) [1]涨跌幅(主图右) [2]成交量(副图)。
        // 这里曾写成 1 —— 插进右轴后 1 变成了涨跌幅轴（量程仅 ±pctAxisMax），
        // 成交量值远超量程被画到图外，副图整块空白；同时 xAxis 属 grid 1 而
        // yAxis 属 grid 0 的错配会让 axisPointer.link 读到不存在的轴而抛错。
        yAxisIndex: 2,
        data: pts.map((p, i) => ({
          value: p.vol,
          itemStyle: { color: volColors[i] },
        })),
        barWidth: '60%',
      },
    ],
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
watch(() => [props.points, props.dayMarks], render)
</script>

<template>
  <div ref="container" class="intraday-chart"></div>
</template>

<style scoped>
.intraday-chart {
  width: 100%;
  height: 440px;
}
</style>
