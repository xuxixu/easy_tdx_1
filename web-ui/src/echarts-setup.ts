// ECharts 按需引入。只注册用到的图表类型，避免全量引入（~1MB → ~400KB）。
// 用到的：candlestick（K线）、line（净值/回撤曲线）、markPoint（买卖点标注）、heatmap（寻优热力图）。

import * as echarts from 'echarts/core'
import { BarChart, CandlestickChart, HeatmapChart, LineChart, RadarChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  RadarComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { watch } from 'vue'

import { THEMES, currentTheme, withAlpha } from './theme'
import type { ThemeDef } from './theme'

echarts.use([
  CanvasRenderer,
  CandlestickChart,
  LineChart,
  BarChart,
  HeatmapChart,
  RadarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DataZoomComponent,
  MarkPointComponent,
  MarkLineComponent,
  RadarComponent,
  VisualMapComponent,
])

// A股惯例：红涨绿跌。这两个色不随主题变——它是市场语义约定而非装饰，
// 且同一对红绿在四套主题底色上都已校验过对比度。
export const UP_COLOR = '#ef4146'
export const DOWN_COLOR = '#18a058'

/** 主题 id → ECharts 主题注册名。initChart 用它挑主题。 */
export function echartsThemeName(id = currentTheme.value.id): string {
  return `etdx-${id}`
}

/** 按当前主题建图。所有图表组件统一走这里，不要再手写 `echarts.init(el, 'dark')`。 */
export function initChart(el: HTMLElement): echarts.ECharts {
  return echarts.init(el, echartsThemeName())
}

/**
 * 把一套 UI 主题翻译成 ECharts 主题对象。
 *
 * ECharts 画在 canvas 上，读不到 CSS 变量，只能吃字面颜色——所以这里的
 * 取色源必须是 theme.ts 的同一张 token 表（而不是各组件里散写的 hex），
 * 否则切到浅色主题时坐标轴文字会是深色、糊在白底上。
 */
function echartsThemeOf(t: ThemeDef) {
  const v = t.vars
  return {
    backgroundColor: 'transparent',
    textStyle: { color: v['--text-dim'] },
    title: {
      textStyle: { color: v['--text'] },
      subtextStyle: { color: v['--text-muted'] },
    },
    legend: { textStyle: { color: v['--text-muted'] } },
    tooltip: {
      backgroundColor: withAlpha(v['--bg-elevated'], 0.96),
      borderColor: v['--border'],
      textStyle: { color: v['--text'] },
    },
    categoryAxis: {
      axisLine: { lineStyle: { color: v['--border'] } },
      axisLabel: { color: v['--text-dim'] },
      splitLine: { show: false },
    },
    valueAxis: {
      axisLine: { lineStyle: { color: v['--border'] } },
      axisLabel: { color: v['--text-dim'] },
      splitLine: { lineStyle: { color: v['--border'] } },
    },
  }
}

// echarts/core 不预置 'dark' 主题数据，四套 UI 主题各注册一个。
for (const t of THEMES) echarts.registerTheme(echartsThemeName(t.id), echartsThemeOf(t))

/** 当前主题下的轴线/分割线色（option 里手写 splitLine 的组件从这里取）。 */
export const chartAxisColor = () => currentTheme.value.vars['--border']
/** 热力图三段色（绿→中性→红）的中性档，跟随主题在深/浅底之间切换。 */
export const chartHeatNeutral = () => currentTheme.value.vars['--heat-neutral']

/**
 * 主题切换后重画图表。
 *
 * ECharts 主题在建图那一刻就写死进实例了，改 CSS 变量对它无效，只能
 * dispose 后按新主题重建。组件里统一写成：
 *
 *   useChartRedraw(() => { chart?.dispose(); chart = null; render() })
 */
export function useChartRedraw(redraw: () => void): void {
  watch(() => currentTheme.value.id, redraw)
}

export default echarts
