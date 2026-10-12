<script setup lang="ts">
// 市场情绪（/sentiment）：盘中宽度分时 + 涨停家数历史，回答"今天市场冷还是热"。
// 数据两层：采样器分钟快照（/market/sentiment/*，随使用逐渐积累）
//          + vipdoc 离线回补的逐日涨停/跌停家数（/market/limitup-history，即时可用）。
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import echarts, { chartAxisColor, DOWN_COLOR, initChart, UP_COLOR, useChartRedraw } from '../echarts-setup'
import {
  fetchBars,
  fetchBoardFundHistory,
  fetchLimitUpEcology,
  fetchLimitUpHistory,
  fetchMarketStat,
  fetchOverseasRank,
  fetchSentimentHistory,
  fetchSentimentToday,
  formatError,
  runLlmChatWithPolling,
  type OverseasRank,
} from '../api'
import { fmtAmount, fmtPctSigned } from '../format'
import { marketLabel } from '../market'
import { useMarketStore } from '../stores/market'
import type {
  BoardFundDay,
  LimitUpHistoryRow,
  MarketStat,
  SentimentDay,
  SentimentSample,
} from '../types'

const marketStore = useMarketStore()
// 港美股无采样器/涨停历史/资金数据，用全市场榜单快照做实时情绪
const isEx = computed(() => !marketStore.isAShareMode)
const exRank = ref<OverseasRank | null>(null)
const exError = ref('')

const exUpRatio = computed(() => {
  const r = exRank.value
  if (!r || r.status !== 'ready' || !r.total) return null
  const denom = (r.up ?? 0) + (r.down ?? 0)
  return denom > 0 ? (100 * (r.up ?? 0)) / denom : null
})
const exMood = computed(() => {
  const v = exUpRatio.value
  if (v === null) return { label: '—', cls: 'flat' }
  if (v >= 70) return { label: '普涨 · 情绪高潮', cls: 'up' }
  if (v >= 55) return { label: '偏暖', cls: 'up' }
  if (v > 45) return { label: '均衡', cls: 'flat' }
  if (v > 30) return { label: '偏冷', cls: 'down' }
  return { label: '普跌 · 情绪冰点', cls: 'down' }
})
const exBreadth = computed(() => {
  const r = exRank.value
  if (!r || r.status !== 'ready' || !r.total) return null
  const total = r.total || 1
  return {
    up: ((r.up ?? 0) / total) * 100,
    flat: ((r.flat ?? 0) / total) * 100,
    down: ((r.down ?? 0) / total) * 100,
  }
})

async function loadEx() {
  exError.value = ''
  try {
    exRank.value = await fetchOverseasRank(marketStore.market)
    lastRefresh.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (e) {
    exError.value = formatError(e)
  }
}

watch(
  () => marketStore.market,
  () => {
    if (isEx.value) loadEx()
    else load()
  },
)

const today = ref<{ date: number; count?: number; samples: SentimentSample[] } | null>(null)
const histDays = ref<SentimentDay[]>([])
const luHistory = ref<LimitUpHistoryRow[]>([])
const stat = ref<MarketStat | null>(null)
const error = ref('')
const loading = ref(false)
const lastRefresh = ref('')

async function load() {
  loading.value = today.value === null
  error.value = ''
  try {
    const [t, h, lu, st] = await Promise.all([
      fetchSentimentToday(),
      fetchSentimentHistory(60),
      fetchLimitUpHistory(60),
      fetchMarketStat().catch(() => null),
    ])
    today.value = t
    histDays.value = h.days
    luHistory.value = lu
    stat.value = st
    lastRefresh.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
  // loading 复位触发 v-else-if 切换后，图表容器才挂载到 DOM
  await nextTick()
  render()
}

// ── 温度卡（今日实时 = /market/stat；缺省回退最后一条采样） ───────────────────

const latest = computed(() => {
  const s = today.value?.samples ?? []
  return s.length > 0 ? s[s.length - 1] : null
})

const upRatio = computed(() => {
  const s = stat.value
  if (s && s.up_count + s.down_count > 0) {
    return (100 * s.up_count) / (s.up_count + s.down_count)
  }
  return latest.value?.up_ratio ?? null
})

const limitUpNow = computed(() => stat.value?.limit_up_count ?? latest.value?.limit_up_count ?? null)
const limitDownNow = computed(
  () => stat.value?.limit_down_count ?? latest.value?.limit_down_count ?? null,
)
const amountNow = computed(() => stat.value?.total_amount ?? latest.value?.total_amount ?? null)

/** 情绪判定：上涨占比 + 涨跌停差 粗分五档 */
const mood = computed(() => {
  const r = upRatio.value
  if (r === null) return { label: '—', cls: 'flat' }
  if (r >= 70) return { label: '普涨 · 情绪高潮', cls: 'up' }
  if (r >= 55) return { label: '偏暖', cls: 'up' }
  if (r > 45) return { label: '均衡', cls: 'flat' }
  if (r > 30) return { label: '偏冷', cls: 'down' }
  return { label: '普跌 · 情绪冰点', cls: 'down' }
})

// ── 图表 ─────────────────────────────────────────────────────────────────────

const todayEl = ref<HTMLDivElement>()
const histEl = ref<HTMLDivElement>()
let todayChart: echarts.ECharts | null = null
let histChart: echarts.ECharts | null = null

function hm(minute: number): string {
  return `${String(Math.floor(minute / 100)).padStart(2, '0')}:${String(minute % 100).padStart(2, '0')}`
}

function render() {
  renderToday()
  renderHistory()
}

function renderToday() {
  if (!todayEl.value) return
  todayChart ??= initChart(todayEl.value)
  const samples = today.value?.samples ?? []
  const x = samples.map((s) => hm(s.minute))
  todayChart.setOption(
    {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      legend: { data: ['上涨家数', '下跌家数', '涨停家数'], top: 0 },
      grid: { left: 60, right: 60, top: 30, bottom: 30 },
      xAxis: { type: 'category', data: x, boundaryGap: false },
      yAxis: [
        { type: 'value', name: '家数', scale: true, splitLine: { lineStyle: { color: chartAxisColor() } } },
        { type: 'value', name: '涨停', scale: true, position: 'right', splitLine: { show: false } },
      ],
      series: [
        {
          name: '上涨家数',
          type: 'line',
          data: samples.map((s) => s.up_count),
          showSymbol: false,
          lineStyle: { color: UP_COLOR, width: 2 },
          itemStyle: { color: UP_COLOR },
          areaStyle: { color: 'rgba(239,65,70,0.08)' },
        },
        {
          name: '下跌家数',
          type: 'line',
          data: samples.map((s) => s.down_count),
          showSymbol: false,
          lineStyle: { color: DOWN_COLOR, width: 2 },
          itemStyle: { color: DOWN_COLOR },
        },
        {
          name: '涨停家数',
          type: 'line',
          yAxisIndex: 1,
          data: samples.map((s) => s.limit_up_count),
          showSymbol: false,
          lineStyle: { color: '#f5a623', width: 1.5, type: 'dashed' },
          itemStyle: { color: '#f5a623' },
        },
      ],
    },
    true,
  )
}

function renderHistory() {
  if (!histEl.value) return
  histChart ??= initChart(histEl.value)
  // 基底 = vipdoc 回补的逐日涨跌停；采样聚合有值的日期叠加上涨占比线
  const lu = luHistory.value
  const sampled = new Map(histDays.value.map((d) => [d.date, d]))
  const x = lu.map((r: LimitUpHistoryRow) => String(r.date).replace(/^(\d{4})(\d{2})(\d{2})$/, '$2-$3'))
  const ratios = lu.map((r) => {
    const d = sampled.get(r.date)
    return d && d.n >= 10 ? d.up_ratio : null // 样本不足的交易日不画占比线
  })
  histChart.setOption(
    {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      legend: { data: ['涨停家数', '跌停家数', '上涨占比%'], top: 0 },
      grid: { left: 50, right: 55, top: 30, bottom: 30 },
      xAxis: { type: 'category', data: x },
      yAxis: [
        { type: 'value', name: '家数', splitLine: { lineStyle: { color: chartAxisColor() } } },
        { type: 'value', name: '上涨占比%', position: 'right', max: 100, splitLine: { show: false } },
      ],
      series: [
        {
          name: '涨停家数',
          type: 'bar',
          data: lu.map((r) => r.limit_up),
          itemStyle: { color: UP_COLOR },
          barMaxWidth: 8,
        },
        {
          name: '跌停家数',
          type: 'bar',
          data: lu.map((r) => -r.limit_down),
          itemStyle: { color: DOWN_COLOR },
          barMaxWidth: 8,
          tooltip: { valueFormatter: (v: number) => String(Math.abs(Number(v))) },
        },
        {
          name: '上涨占比%',
          type: 'line',
          yAxisIndex: 1,
          data: ratios,
          connectNulls: false,
          showSymbol: false,
          lineStyle: { color: '#f5a623', width: 2 },
          itemStyle: { color: '#f5a623' },
        },
      ],
    },
    true,
  )
}

function onResize() {
  todayChart?.resize()
  histChart?.resize()
  volChart?.resize()
}

// 主题切换：ECharts 主题在建图那一刻就定死了，改 CSS 变量对它无效，
// 只能 dispose 后按新主题重建（init 处已改走 initChart，主题感知）。
useChartRedraw(() => {
  todayChart?.dispose()
  histChart?.dispose()
  volChart?.dispose()
  todayChart = histChart = volChart = null
  render()
  // 量能图重放上一次算好的 option（不重新请求 MIN_5 K 线）
  if (volEl.value && volOption) {
    volChart = initChart(volEl.value)
    volChart.setOption(volOption, true)
  }
})

// ── ⑧ 量能仪表盘：两市累计成交额（最近交易日）vs 近 5 日同期均值 ─────────────

const volEl = ref<HTMLDivElement>()
let volChart: echarts.ECharts | null = null
/** 量能 option 留一份：切主题时 dispose 后直接重放，不必重拉两次 MIN_5 K 线。 */
let volOption: echarts.EChartsCoreOption | null = null
const volRatio = ref<number | null>(null)
const volDate = ref('')
const fundDays = ref<BoardFundDay[]>([])

async function loadVolume() {
  try {
    const start = new Date(Date.now() - 14 * 86400_000).toISOString().slice(0, 10)
    const [sh, sz] = await Promise.all([
      fetchBars('SH', '000001', 'MIN_5', start),
      fetchBars('SZ', '399001', 'MIN_5', start),
    ])
    // 按日期聚合上证指数+深证成指的 5 分钟 amount（元；成指成分口径，
    // 非深市全市场——仅用于与自身近 5 日同期均值做相对比较）
    const byDate = new Map<string, Map<string, number>>()
    for (const b of [...sh, ...sz]) {
      const d = b.datetime.slice(0, 10)
      const t = b.datetime.slice(11, 16)
      if (!d || !t) continue
      const slot = byDate.get(d) ?? new Map<string, number>()
      slot.set(t, (slot.get(t) ?? 0) + Number(b.amount ?? 0))
      byDate.set(d, slot)
    }
    const dates = [...byDate.keys()].sort()
    if (dates.length < 2) return
    volDate.value = dates[dates.length - 1]
    const cur = byDate.get(volDate.value)!
    const prevDates = dates.slice(-6, -1)
    const times = [...cur.keys()].sort()

    const cumAt = (m: Map<string, number>, upto: number): number => {
      let s = 0
      for (let i = 0; i <= upto; i++) s += m.get(times[i]) ?? 0
      return s / 1e12 // 万亿
    }
    const todayCurve = times.map((_, i) => cumAt(cur, i))
    const baseCurve = times.map((_, i) => {
      let s = 0
      let n = 0
      for (const d of prevDates) {
        const m = byDate.get(d)
        if (!m) continue
        s += cumAt(m, i)
        n += 1
      }
      return n ? s / n : null
    })

    const lastT = todayCurve[todayCurve.length - 1]
    const lastB = baseCurve[baseCurve.length - 1]
    volRatio.value = lastB && lastB > 0 ? ((lastT - lastB) / lastB) * 100 : null

    volOption = {
        backgroundColor: 'transparent',
        tooltip: {
          trigger: 'axis',
          valueFormatter: (v: number | string) => fmtAmount(Number(v) * 1e12),
        },
        legend: { data: ['最近交易日累计', '近 5 日同期均值'], top: 0 },
        grid: { left: 60, right: 20, top: 30, bottom: 30 },
        xAxis: { type: 'category', data: times },
        yAxis: {
          type: 'value',
          name: '万亿',
          scale: true,
          splitLine: { lineStyle: { color: chartAxisColor() } },
          axisLabel: { formatter: (v: number) => v.toFixed(1) },
        },
        series: [
          {
            name: '最近交易日累计',
            type: 'line',
            data: todayCurve,
            showSymbol: false,
            lineStyle: { color: UP_COLOR, width: 2 },
            itemStyle: { color: UP_COLOR },
            areaStyle: { color: 'rgba(239,65,70,0.08)' },
          },
          {
            name: '近 5 日同期均值',
            type: 'line',
            data: baseCurve,
            showSymbol: false,
            lineStyle: { color: '#8b919e', width: 1.5, type: 'dashed' },
            itemStyle: { color: '#8b919e' },
          },
        ],
      }
    volChart ??= initChart(volEl.value!)
    volChart.setOption(volOption, true)
  } catch {
    volRatio.value = null // 量能图独立降级
  }
}

async function loadFund() {
  try {
    fundDays.value = await fetchBoardFundHistory(15)
  } catch {
    fundDays.value = [] // 资金日历独立降级
  }
}


let timer = 0

// ── ⑩ AI 盘面复盘：自动汇总上方数据 → LLM 生成 → 自动归档「AI 解读历史」 ─────

const aiReply = ref('')
const aiBusy = ref(false)
const aiError = ref('')
const aiModel = ref('')
// AI 解读长轮询的中止句柄（卸载 / 重复触发时停掉轮询）
let aiAbort: AbortController | null = null

async function buildDigest(): Promise<string> {
  const lines: string[] = []
  const s = stat.value
  if (s) {
    const denom = Math.max(s.up_count + s.down_count, 1)
    lines.push(
      `上涨 ${s.up_count} 家 / 下跌 ${s.down_count} 家（上涨占比 ${((100 * s.up_count) / denom).toFixed(1)}%），` +
        `涨停 ${s.limit_up_count} 家，跌停 ${s.limit_down_count} 家，两市成交 ${fmtAmount(s.total_amount)}。`,
    )
  }
  if (volRatio.value !== null) {
    lines.push(`量能：沪深指数（上证指数+深证成指）当日成交额较近 5 日同期均值 ${fmtPctSigned(volRatio.value)}。`)
  }
  try {
    const eco = await fetchLimitUpEcology()
    const sm = eco.summary
    lines.push(`连板高度 ${sm.max_streak} 板（首板 ${sm.first_board}、二板 ${sm.second_board}、3 板以上 ${sm.plus3}），炸板率 ${sm.blown_rate ?? '-'}%。`)
  } catch {
    // 涨停生态不可用时跳过该维度
  }
  const lu = luHistory.value.slice(-5)
  if (lu.length) {
    lines.push(
      `近 5 日涨停家数：${lu.map((r) => `${String(r.date).slice(4, 6)}-${String(r.date).slice(6, 8)} ${r.limit_up}`).join('；')}。`,
    )
  }
  const sampled = histDays.value.filter((d) => d.n >= 10).slice(-5)
  if (sampled.length) {
    lines.push(
      `采样上涨占比：${sampled.map((d) => `${String(d.date).slice(4, 6)}-${String(d.date).slice(6, 8)} ${d.up_ratio}%`).join('；')}。`,
    )
  }
  if (lines.length === 0) return ''
  return `以下是最新的 A 股盘面数据摘要：\n${lines.join('\n')}\n\n` +
    '请以资深市场分析师的口吻写一段 200~400 字的盘面复盘，依次覆盖：1) 市场情绪与赚钱效应；' +
    '2) 量能特征（放量/缩量及其含义）；3) 涨停梯队与炸板率反映的题材热度与分歧；4) 结尾一句风险提示。' +
    '直接给观点和逻辑，不要复述数据。'
}

async function generateReview() {
  // 上一轮还在跑时先掐掉，避免并发两条轮询链互相覆盖结果
  aiAbort?.abort()
  aiAbort = new AbortController()
  aiBusy.value = true
  aiError.value = ''
  aiReply.value = ''
  try {
    const digest = await buildDigest()
    if (!digest) {
      aiError.value = '暂无盘面数据可生成复盘'
      return
    }
    // AI 解读是长轮询（默认 20 分钟超时、1.5s 一次），必须能随组件卸载中止，
    // 否则离开页面后仍会持续请求并把结果写进已卸载组件的 ref。
    const state = await runLlmChatWithPolling(
      digest,
      null,
      undefined,
      undefined,
      undefined,
      aiAbort.signal,
    )
    if (state.status === 'failed') {
      throw new Error(String((state as { error?: string }).error ?? 'AI 解读任务失败'))
    }
    const result = state.result as { reply?: string; model?: string }
    aiReply.value = result.reply ?? ''
    aiModel.value = result.model ?? ''
  } catch (e) {
    if ((e as Error)?.name === 'AbortError') return // 卸载/被新请求取代：静默
    aiError.value = formatError(e)
  } finally {
    aiBusy.value = false
  }
}

onMounted(async () => {
  if (isEx.value) await loadEx()
  else {
    await load()
    loadVolume()
    loadFund()
  }
  timer = window.setInterval(() => {
    if (document.hidden) return
    if (isEx.value) loadEx()
    else load()
  }, 60_000)
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  aiAbort?.abort()
  aiAbort = null
  window.clearInterval(timer)
  window.removeEventListener('resize', onResize)
  todayChart?.dispose()
  histChart?.dispose()
  volChart?.dispose()
})
</script>

<template>
  <div class="sentiment-view">
    <div class="view-head">
      <h2>市场情绪</h2>
      <span class="dim head-sub">宽度 · 涨停温度计</span>
      <span class="tb-spacer"></span>
      <span v-if="lastRefresh" class="dim refresh-ts">{{ lastRefresh }}</span>
      <button class="manual-refresh" @click="isEx ? loadEx() : load()">↻ 刷新</button>
    </div>

    <!-- 港美股：实时情绪（榜单快照；无采样/涨停/资金历史） -->
    <template v-if="isEx">
      <div v-if="exError" class="err card">
        加载失败：{{ exError }}
        <button @click="loadEx">重试</button>
      </div>
      <div v-else-if="!exRank || exRank.status === 'building'" class="loading">
        全市场快照构建中…{{ exRank?.progress ? `（${exRank.progress}）` : '' }}
      </div>
      <template v-else>
        <div class="stat-strip">
          <div class="stat-card card">
            <div class="stat-title">上涨占比</div>
            <div class="stat-main mono" :class="exMood.cls">
              {{ exUpRatio === null ? '-' : exUpRatio.toFixed(1) + '%' }}
            </div>
            <div class="stat-sub" :class="exMood.cls">{{ exMood.label }}</div>
          </div>
          <div class="stat-card card">
            <div class="stat-title">涨 / 平 / 跌（{{ exRank.total }} 只）</div>
            <div class="stat-main">
              <span class="up">{{ exRank.up }}</span>
              <span class="dim"> / </span>
              <span>{{ exRank.flat }}</span>
              <span class="dim"> / </span>
              <span class="down">{{ exRank.down }}</span>
            </div>
          </div>
        </div>
        <div v-if="exBreadth" class="card breadth-card">
          <div class="breadth-bar">
            <div class="seg up" :style="{ width: `${exBreadth.up}%` }"></div>
            <div class="seg flat" :style="{ width: `${exBreadth.flat}%` }"></div>
            <div class="seg down" :style="{ width: `${exBreadth.down}%` }"></div>
          </div>
          <div class="dim breadth-hint">
            {{ marketLabel(marketStore.market) }}实时宽度 · 分时采样/涨停温度计/资金日历暂只支持 A 股
          </div>
        </div>
      </template>
    </template>

    <template v-else>
    <div v-if="error" class="err card">
      加载失败：{{ error }}
      <button @click="load">重试</button>
    </div>
    <div v-else-if="loading" class="loading">加载中…</div>

    <template v-else>
      <!-- 温度卡 -->
      <div class="stat-strip">
        <div class="stat-card card">
          <div class="stat-title">上涨占比</div>
          <div class="stat-main mono" :class="mood.cls">{{ upRatio === null ? '-' : upRatio.toFixed(1) + '%' }}</div>
          <div class="stat-sub" :class="mood.cls">{{ mood.label }}</div>
        </div>
        <div class="stat-card card">
          <div class="stat-title">涨停 / 跌停</div>
          <div class="stat-main">
            <span class="up">{{ limitUpNow ?? '-' }}</span>
            <span class="dim"> / </span>
            <span class="down">{{ limitDownNow ?? '-' }}</span>
          </div>
        </div>
        <div class="stat-card card">
          <div class="stat-title">今日总成交</div>
          <div class="stat-main">{{ fmtAmount(amountNow) }}</div>
        </div>
        <div class="stat-card card">
          <div class="stat-title">今日采样点</div>
          <div class="stat-main">{{ today?.count ?? 0 }} <span class="unit">个</span></div>
          <div class="stat-sub dim">交易时段每分钟一条 · 持续积累</div>
        </div>
      </div>

      <!-- 今日宽度分时 -->
      <div class="section">
        <div class="sec-title">今日宽度分时</div>
        <div class="card chart-card">
          <div ref="todayEl" class="chart"></div>
          <div v-if="(today?.samples?.length ?? 0) === 0" class="empty-hint dim">
            今日尚无采样数据。采样器在交易时段每分钟落一条，服务持续运行后曲线自动成形。
          </div>
        </div>
      </div>

      <!-- 量能仪表盘 -->
      <div class="section">
        <div class="sec-title">
          量能 · 沪深指数成交额（上证指数 + 深证成指 MIN_5 合计，最近交易日{{ volDate ? ` ${volDate.slice(5)}` : '' }} vs 近 5 日同期均值
          <span v-if="volRatio !== null" :class="volRatio > 0 ? 'up' : 'down'">{{ fmtPctSigned(volRatio) }}</span>）
          <span class="dim">· 非全市场口径，全市场总成交见顶部「今日总成交」</span>
        </div>
        <div class="card chart-card">
          <div ref="volEl" class="chart"></div>
        </div>
      </div>

      <!-- 板块主力资金日历 -->
      <div class="section">
        <div class="sec-title">行业主力资金 · 每日净流入 Top 10（交易日 14:45 后采样，需积累）</div>
        <div class="card fund-card">
          <div v-for="d in fundDays" :key="d.date" class="fund-row">
            <span class="mono dim fund-date">{{ String(d.date).slice(4, 6) }}-{{ String(d.date).slice(6, 8) }}</span>
            <span v-for="b in d.boards" :key="b.code" class="fund-chip mono">
              {{ b.name }}
              <span :class="b.main_net >= 0 ? 'up' : 'down'">
                {{ b.main_net >= 0 ? '+' : '-' }}{{ (Math.abs(b.main_net) / 1e8).toFixed(1) }}亿
              </span>
            </span>
          </div>
          <div v-if="fundDays.length === 0" class="empty-hint dim">
            尚无采样：每个交易日的 14:45 后自动记录一次行业主力净流入排行（涨幅前 50 名口径），持续运行后日历成形。
          </div>
        </div>
      </div>

      <!-- AI 盘面复盘 -->
      <div class="section">
        <div class="sec-title-ai">
          AI 盘面复盘
          <button class="gen-btn" :disabled="aiBusy" @click="generateReview">
            {{ aiBusy ? '生成中…（约 1~3 分钟）' : aiReply ? '重新生成' : '生成 AI 复盘' }}
          </button>
          <span v-if="aiModel" class="dim">{{ aiModel }}</span>
        </div>
        <div class="card ai-card">
          <div v-if="aiBusy" class="dim">模型基于上方情绪 / 量能 / 涨停数据生成中…</div>
          <div v-else-if="aiError" class="up">{{ aiError }}</div>
          <div v-else-if="aiReply" class="ai-reply">{{ aiReply }}</div>
          <div v-else class="dim">
            汇总本页情绪 / 量能 / 涨停数据交给已配置的模型生成复盘，自动归档到「AI 解读历史」。
          </div>
        </div>
      </div>

      <!-- 近 60 日情绪 -->
      <div class="section">
        <div class="sec-title">近 60 日 · 涨停/跌停家数（vipdoc 回补）与上涨占比（采样积累）</div>
        <div class="card chart-card">
          <div ref="histEl" class="chart-lg"></div>
          <div v-if="luHistory.length === 0" class="empty-hint dim">
            未检测到本地 vipdoc 数据，历史涨停家数不可用。
          </div>
        </div>
      </div>
    </template><!-- /A股内容 -->
    </template><!-- /A股分支 -->
  </div>
</template>

<style scoped>
.sentiment-view {
  height: 100%;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.view-head,
.stat-strip,
.err,
.loading,
.section {
  flex-shrink: 0;
}
.view-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.view-head h2 {
  font-size: 17px;
  font-weight: 700;
}
.head-sub {
  font-size: 12px;
}
.tb-spacer {
  flex: 1;
}
.refresh-ts {
  font-family: var(--font-mono);
  font-size: 11.5px;
}
.manual-refresh {
  font-size: 12px;
  padding: 4px 10px;
}
.err {
  color: var(--up);
  display: flex;
  align-items: center;
  gap: 10px;
}
.loading {
  padding: 40px 0;
  text-align: center;
  color: var(--text-dim);
}
.stat-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.stat-card {
  padding: 10px 14px;
}
.stat-title {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.stat-main {
  font-size: 17px;
  font-weight: 700;
}
.unit {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-muted);
}
.stat-sub {
  font-size: 11.5px;
  margin-top: 2px;
}
.stat-sub.up,
.stat-main.up {
  color: var(--up);
}
.breadth-card {
  padding: 12px 14px;
}
.breadth-bar {
  display: flex;
  height: 10px;
  border-radius: 3px;
  overflow: hidden;
  margin: 4px 0 8px;
}
.seg.up {
  background: var(--up);
}
.seg.flat {
  background: var(--text-dim);
}
.seg.down {
  background: var(--down);
}
.breadth-hint {
  font-size: 11.5px;
}.stat-sub.down,
.stat-main.down {
  color: var(--down);
}
.stat-sub.flat,
.stat-main.flat {
  color: var(--text-muted);
}
.section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sec-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-muted);
}
.sec-title-ai {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-muted);
}
.gen-btn {
  font-size: 11.5px;
  padding: 3px 12px;
}
.gen-btn:disabled {
  opacity: 0.6;
}
.fund-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  padding: 10px 12px;
}
.fund-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.fund-date {
  width: 44px;
  flex-shrink: 0;
}
.fund-chip {
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
}
.ai-card {
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
}
.chart-card {
  padding: 8px;
  position: relative;
}
.chart {
  height: 260px;
}
.chart-lg {
  height: 300px;
}
.empty-hint {
  position: absolute;
  inset: 0;
  pointer-events: none;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  padding: 0 40px;
  text-align: center;
}
@media (max-width: 1024px) {
  .stat-strip {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
