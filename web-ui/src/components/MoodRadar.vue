<script setup lang="ts">
// 市场情绪雷达（借鉴 tick-stock-panel 看板 EmotionRadar）：
// 四维 0~100 —— 赚钱效应（涨跌比）/ 量能（较昨日成交）/ 动量（指数5日涨幅）/
// 趋势（上证指数相对 MA20）。中心到顶端的填充区 + 综合分。

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import echarts, { chartAxisColor, initChart, useChartRedraw } from '../echarts-setup'

const props = defineProps<{
  /** 四维分值（0~100，50 为中性）。 */
  values: { profit: number; volume: number; momentum: number; trend: number }
}>()

const container = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

const DIMS = [
  { name: '赚钱效应', max: 100 },
  { name: '量能', max: 100 },
  { name: '动量', max: 100 },
  { name: '趋势', max: 100 },
]

function render() {
  if (!container.value) return
  chart ??= initChart(container.value)
  const v = props.values
  chart.setOption(
    {
      backgroundColor: 'transparent',
      radar: {
        indicator: DIMS,
        radius: '62%',
        center: ['50%', '52%'],
        splitNumber: 4,
        axisName: { color: '#8b919e', fontSize: 11 },
        splitLine: { lineStyle: { color: chartAxisColor() } },
        splitArea: { show: false },
        axisLine: { lineStyle: { color: chartAxisColor() } },
      },
      series: [
        {
          type: 'radar',
          symbol: 'circle',
          symbolSize: 3,
          data: [
            {
              value: [v.profit, v.volume, v.momentum, v.trend],
              itemStyle: { color: '#4a9eff' },
              lineStyle: { color: '#4a9eff', width: 1.5 },
              areaStyle: { color: 'rgba(74,158,255,0.22)' },
            },
          ],
        },
      ],
    },
    true,
  )
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
watch(() => props.values, render, { deep: true })
</script>

<template>
  <div ref="container" class="mood-radar"></div>
</template>

<style scoped>
.mood-radar {
  width: 100%;
  height: 190px;
}
</style>
