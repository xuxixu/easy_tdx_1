<script setup lang="ts">
// 信号雷达页：一键扫描策略库全部已保存策略（单标的/多标的/多策略组合），
// 把每种策略展开成"策略×标的"子任务，用最近 N 根 K 线（窗口可选，默认 5）
// 判断买/卖信号并汇总列出——方便每天跟踪"今天哪些策略有信号"。
// 后端 POST /backtest/signal-scan/run/async；取行情在提交请求内完成（标的多时
// 提交本身就要等一会儿），结果轮询拿 SignalScanResult。上次扫描结果缓存在
// localStorage，进页面先展示，避免每次都要重扫。

import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  asSignalScanResult,
  deleteSavedStrategy,
  fetchSavedStrategies,
  formatError,
  runSignalScanWithPolling,
  saveStrategy,
  sendSignalPush,
  updateSavedStrategy,
} from '../api'
import { toSymbolAuto } from '../market'
import { useBacktestStore } from '../stores/backtest'
import StrategyEditor, { type StrategyForm } from '../components/StrategyEditor.vue'
import type { SavedStrategy, SignalScanResult, SignalScanRow } from '../types'

const router = useRouter()
const btStore = useBacktestStore()

const WINDOW_OPTIONS = [1, 3, 5, 10]
const STORAGE_KEY = 'easy-tdx.signal-radar.last'

const windowBars = ref(5)
const scanning = ref(false)
// 扫描可耗时数分钟；用 AbortController 让组件卸载 / 重复点击时能停掉轮询，
// 否则离开页面后仍会每 500ms 打一次 HTTP 并写入已卸载组件的 ref。
let scanAbort: AbortController | null = null
const error = ref('')
const result = ref<SignalScanResult | null>(null)
const scannedAt = ref('') // 本地时间戳（上次扫描完成时刻）
const elapsedSec = ref('') // 上次扫描总耗时（提交+计算）
const pushing = ref(false)
const pushMsg = ref('')

// ── 定向扫描：选股票 + 选策略 ────────────────────────────────────────────────
// 空 = 不限（全量扫描）；填了即按 "某只股票 × 某几个保存策略" 定向扫，
// 结果直接给出买入/卖出信号。
const symbolInput = ref('')
const strategyList = ref<SavedStrategy[]>([])
const pickedIds = ref<Set<string>>(new Set())

/** 输入的标的归一化为 MARKET:CODE（空输入 = 不限标的）。 */
function normSymbol(): string | null {
  const s = symbolInput.value.trim()
  if (!s) return null
  try {
    return toSymbolAuto(s)
  } catch {
    return null
  }
}

async function loadStrategies() {
  try {
    strategyList.value = (await fetchSavedStrategies()).strategies
  } catch {
    strategyList.value = []
  }
}

function togglePick(id: string) {
  const next = new Set(pickedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  pickedIds.value = next
}

const scanModeLabel = computed(() => {
  const sym = normSymbol()
  const n = pickedIds.value.size
  if (sym && n > 0) return `${sym} × ${n} 个策略`
  if (sym) return `${sym} × 全部策略`
  if (n > 0) return `全部标的 × ${n} 个策略`
  return '全部策略'
})

interface CachedScan {
  result: SignalScanResult
  scannedAt: string
  windowBars: number
}

onMounted(() => {
  loadStrategies()
  // 策略类型下拉（StrategyEditor 新增/修改用）的数据源
  btStore.loadStrategies().catch(() => undefined)
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const cached = JSON.parse(raw) as CachedScan
    if (cached?.result?.rows) {
      result.value = cached.result
      scannedAt.value = cached.scannedAt || ''
      if (WINDOW_OPTIONS.includes(cached.windowBars)) windowBars.value = cached.windowBars
    }
  } catch {
    // 缓存损坏则忽略，直接空态
  }
})

onBeforeUnmount(() => {
  scanAbort?.abort()
  scanAbort = null
})

async function onScan() {
  if (scanning.value) return
  scanAbort?.abort()
  scanAbort = new AbortController()
  scanning.value = true
  error.value = ''
  const t0 = Date.now()
  try {
    const sym = normSymbol()
    if (symbolInput.value.trim() && !sym) {
      throw new Error('股票格式不对（A股6位/港股4-5位/美股字母，或 MARKET:CODE）')
    }
    const req: { window_bars: number; symbols?: string[]; strategy_ids?: string[] } = {
      window_bars: windowBars.value,
    }
    if (sym) req.symbols = [sym]
    if (pickedIds.value.size > 0) req.strategy_ids = [...pickedIds.value]
    const state = await runSignalScanWithPolling(req, undefined, undefined, undefined, scanAbort.signal)
    result.value = asSignalScanResult(state)
    scannedAt.value = new Date().toLocaleString('zh-CN', { hour12: false })
    elapsedSec.value = ((Date.now() - t0) / 1000).toFixed(1)
    const cached: CachedScan = {
      result: result.value,
      scannedAt: scannedAt.value,
      windowBars: windowBars.value,
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cached))
  } catch (e) {
    // 组件卸载/被新扫描取代导致的取消：静默返回，不要弹错误
    if ((e as Error)?.name === 'AbortError') return
    error.value = formatError(e)
  } finally {
    scanning.value = false
  }
}

async function onPush() {
  if (pushing.value || !result.value) return
  pushing.value = true
  pushMsg.value = ''
  try {
    const r = await sendSignalPush(
      result.value.rows as unknown as Array<Record<string, unknown>>,
      windowBars.value,
    )
    if (r.ok) {
      pushMsg.value = `✓ 已推送：${r.title}（${r.sent}/${r.total} 通道）`
    } else {
      pushMsg.value = `✗ 推送失败：${r.error ?? '通道不可达，请先去「推送设置」填 key'}`
    }
  } catch (e) {
    pushMsg.value = `✗ 推送失败：${formatError(e)}`
  } finally {
    pushing.value = false
  }
}

// ── 子任务详情弹窗：点击结果行弹出当前子任务 ────────────────────────────────

const detailRow = ref<SignalScanRow | null>(null)
const pushingOne = ref(false)

function openDetail(r: SignalScanRow) {
  detailRow.value = r
}

async function onPushOne() {
  if (pushingOne.value || !detailRow.value) return
  pushingOne.value = true
  pushMsg.value = ''
  try {
    const r = await sendSignalPush(
      [detailRow.value] as unknown as Array<Record<string, unknown>>,
      windowBars.value,
    )
    pushMsg.value = r.ok
      ? `✓ 已推送：${r.title}（${r.sent}/${r.total} 通道）`
      : `✗ 推送失败：${r.error ?? '通道不可达，请先去「推送设置」填 key'}`
  } catch (e) {
    pushMsg.value = `✗ 推送失败：${formatError(e)}`
  } finally {
    pushingOne.value = false
  }
}

// ── 右侧策略管理：新增 / 修改 / 删除（与策略库页同后端） ─────────────────────

const editorOpen = ref(false)
const editingStrategy = ref<SavedStrategy | null>(null)
const deletingId = ref<string | null>(null)
const stratMsg = ref('')

function openCreate() {
  editingStrategy.value = null
  editorOpen.value = true
}

function openEdit(s: SavedStrategy) {
  editingStrategy.value = s
  editorOpen.value = true
}

function strategyLabelOf(name: string): string {
  return btStore.strategies.find((x) => x.name === name)?.label ?? name
}

async function onEditorSave(form: StrategyForm) {
  stratMsg.value = ''
  try {
    if (editingStrategy.value) {
      const updated = await updateSavedStrategy(editingStrategy.value.id, {
        name: form.name,
        strategy: form.strategy,
        strategy_label: strategyLabelOf(form.strategy),
        params: JSON.parse(form.paramsText || '{}'),
        context: { ...(editingStrategy.value.context ?? {}), symbol: form.symbol },
        notes: form.notes,
        tags: form.tagsText ? form.tagsText.split(/\s+/) : [],
      })
      const i = strategyList.value.findIndex((x) => x.id === updated.id)
      if (i >= 0) strategyList.value[i] = updated
    } else {
      const created = await saveStrategy({
        name: form.name,
        kind: 'single',
        strategy: form.strategy,
        strategy_label: strategyLabelOf(form.strategy),
        params: JSON.parse(form.paramsText || '{}'),
        context: { symbol: form.symbol, category: 'DAY' },
        trade_config: {},
        snapshot: {},
        tags: form.tagsText ? form.tagsText.split(/\s+/) : [],
        notes: form.notes,
      })
      strategyList.value.unshift(created)
    }
    editorOpen.value = false
    editingStrategy.value = null
  } catch (e) {
    // 编辑器内展示：复用顶部错误条
    error.value = formatError(e)
  }
}

async function onDeleteStrategy(s: SavedStrategy) {
  if (!confirm(`确定删除「${s.name}」？此操作不可撤销。`)) return
  deletingId.value = s.id
  stratMsg.value = ''
  try {
    await deleteSavedStrategy(s.id)
    strategyList.value = strategyList.value.filter((x) => x.id !== s.id)
    const next = new Set(pickedIds.value)
    next.delete(s.id)
    pickedIds.value = next
  } catch (e) {
    stratMsg.value = formatError(e)
  } finally {
    deletingId.value = null
  }
}

// ── 筛选 ─────────────────────────────────────────────────────────────────────

type FilterKey = 'signal' | 'buy' | 'sell' | 'error' | 'all'

const activeFilter = ref<FilterKey>('signal') // 默认只看有信号的

function hasBuy(r: SignalScanRow): boolean {
  return r.recent_signals.some((s) => s.direction === 'BUY')
}
function hasSell(r: SignalScanRow): boolean {
  return r.recent_signals.some((s) => s.direction === 'SELL')
}

const filterDefs = computed(() => {
  const rows = result.value?.rows || []
  const defs: { key: FilterKey; label: string; count: number }[] = [
    { key: 'signal', label: '有信号', count: rows.filter((r) => !r.error && r.recent_signals.length > 0).length },
    { key: 'buy', label: '买入', count: rows.filter((r) => !r.error && hasBuy(r)).length },
    { key: 'sell', label: '卖出', count: rows.filter((r) => !r.error && hasSell(r)).length },
    { key: 'error', label: '失败', count: rows.filter((r) => r.error).length },
    { key: 'all', label: '全部', count: rows.length },
  ]
  return defs
})

const visibleRows = computed(() => {
  const rows = result.value?.rows || []
  switch (activeFilter.value) {
    case 'signal':
      return rows.filter((r) => !r.error && r.recent_signals.length > 0)
    case 'buy':
      return rows.filter((r) => !r.error && hasBuy(r))
    case 'sell':
      return rows.filter((r) => !r.error && hasSell(r))
    case 'error':
      return rows.filter((r) => r.error)
    default:
      return rows
  }
})

// ── 展示辅助 ─────────────────────────────────────────────────────────────────

function kindLabel(kind: SignalScanRow['kind']): string {
  return kind === 'multi' ? '多策略' : kind === 'portfolio' ? '多标的' : '单标的'
}

/** 窗口内信号序列，如 "B 08-19 · S 08-20"（B=买 S=卖）。 */
function signalSeq(r: SignalScanRow): string {
  return r.recent_signals
    .map((s) => `${s.direction === 'BUY' ? 'B' : 'S'} ${s.date.slice(5, 10)}`)
    .join(' · ')
}

/** 策略卡的标的展示（title 用）。 */
function ctxSymbol(s: SavedStrategy): string {
  const ctx = (s.context ?? {}) as Record<string, unknown>
  if (s.kind === 'multi') {
    const items = Array.isArray(ctx.items) ? ctx.items : []
    return items.length ? `${items.length} 策略组合` : '-'
  }
  if (s.kind === 'portfolio') {
    const stocks = Array.isArray(ctx.stocks) ? ctx.stocks : []
    return stocks.length ? `${stocks.length} 只` : '-'
  }
  return String(ctx.symbol ?? '-')
}

/** 跳转单标的回测页回填该子策略（query 模式与策略库「载入」一致）。
 *  symbolMarket 必须带上：只传裸 code 时回测页默认按 A 股识别，
 *  港美股会被误判成 SZ 报"A股代码应为6位数字"（与板块成分股误标 SZ 同类）。 */
function onLoad(r: SignalScanRow) {
  const raw = r.symbol.includes(':') ? r.symbol : toSymbolAuto(r.symbol)
  const [mkt, codeOnly] = raw.includes(':') ? raw.split(':') : ['A', raw]
  const upMkt = (mkt || '').toUpperCase()
  router.push({
    path: '/backtest',
    query: {
      strategy: r.strategy,
      params: JSON.stringify(r.params),
      symbol: codeOnly || undefined,
      symbolMarket: ['HK', 'US'].includes(upMkt) ? upMkt : 'A',
      category: r.category || undefined,
      endDate: new Date().toISOString().slice(0, 10),
    },
  })
}
</script>

<template>
  <div class="radar-view">
    <header class="page-header">
      <div>
        <h2>信号雷达</h2>
        <p class="subtitle">
          一键扫描策略库全部已保存策略，列出最近 K 线内出现买入/卖出信号的策略。
          <template v-if="scannedAt">
            上次扫描 {{ scannedAt }}<template v-if="elapsedSec">（{{ elapsedSec }}s）</template>。
          </template>
        </p>
      </div>
      <div class="header-actions">
        <label class="window-picker">
          窗口
          <select v-model="windowBars" :disabled="scanning">
            <option v-for="w in WINDOW_OPTIONS" :key="w" :value="w">{{ w }} 根</option>
          </select>
        </label>
        <button class="primary" :disabled="scanning" @click="onScan">
          {{ scanning ? '扫描中…' : `⚡ 扫描（${scanModeLabel}）` }}
        </button>
        <button
          v-if="result"
          class="ghost"
          :disabled="pushing || scanning"
          title="经推送设置里启用的通道发出买入/卖出信号"
          @click="onPush"
        >
          {{ pushing ? '推送中…' : '📣 推送信号' }}
        </button>
      </div>
    </header>

    <!-- 定向扫描：股票 + 策略多选（都不选 = 全量） -->
    <div class="target-bar">
      <input
        v-model="symbolInput"
        class="symbol-input mono"
        placeholder="股票（可空）：600519 / 00700 / AAPL / HK:00700"
      />
      <span class="target-list">
        <button
          v-for="s in strategyList"
          :key="s.id"
          class="chip"
          :class="{ on: pickedIds.has(s.id) }"
          :title="`${s.strategy_label || s.strategy} · ${ctxSymbol(s)}`"
          @click="togglePick(s.id)"
        >
          {{ s.name }}
        </button>
        <span v-if="strategyList.length === 0" class="dim">策略库为空，先去「策略库」新增或去回测页保存</span>
      </span>
    </div>

    <div v-if="error" class="error-banner">⚠ {{ error }}</div>
    <div v-if="pushMsg" class="push-msg" :class="{ ok: pushMsg.startsWith('✓') }">{{ pushMsg }}</div>

    <!-- 扫描中：提交请求内要逐标的取行情，需要等待 -->
    <div v-if="scanning" class="scanning-box">
      <span class="spinner"></span>
      正在扫描：逐标的取最近 800 根 K 线并计算信号（标的较多时约需几十秒，请稍候）…
    </div>

    <!-- 主区 + 右侧策略管理 -->
    <div class="content">
      <div class="main-col">
    <template v-if="result && !scanning">
      <!-- 汇总卡片 -->
      <div class="stat-cards">
        <div class="stat">
          <span class="k">子任务</span>
          <span class="v">{{ result.total }}</span>
        </div>
        <div class="stat">
          <span class="k">买入信号</span>
          <span class="v buy">{{ result.buy_count }}</span>
        </div>
        <div class="stat">
          <span class="k">卖出信号</span>
          <span class="v sell">{{ result.sell_count }}</span>
        </div>
        <div class="stat">
          <span class="k">失败</span>
          <span class="v dim">{{ result.error_count }}</span>
        </div>
      </div>

      <p class="hint">
        窗口 = 最近 {{ windowBars }} 根 {{ result.rows[0]?.category === 'DAY' ? '交易日' : 'K 线' }}；
        盘中最后一根 K 线未收盘，信号为盘中即时值，收盘后为准。
      </p>

      <!-- 筛选 tab -->
      <nav class="tabs">
        <button
          v-for="f in filterDefs"
          :key="f.key"
          :class="['tab', { active: activeFilter === f.key }]"
          @click="activeFilter = f.key"
        >
          {{ f.label }}<span class="tab-count">{{ f.count }}</span>
        </button>
      </nav>

      <div v-if="visibleRows.length === 0" class="placeholder">
        <p>{{ activeFilter === 'signal' ? '窗口内没有任何买卖信号。' : '该筛选下没有子任务。' }}</p>
        <p class="hint">可切换更大的窗口（如 10 根）或点「一键扫描」重新检查。</p>
      </div>

      <table v-else class="radar-table">
        <thead>
          <tr>
            <th>策略</th>
            <th>类型</th>
            <th>子策略 / 参数</th>
            <th>标的</th>
            <th>最新信号</th>
            <th>窗口内信号</th>
            <th class="num">最新收盘</th>
            <th>仓位</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in visibleRows" :key="`${r.strategy_id}-${i}`" :class="{ errored: r.error }" class="clickable" @click="openDetail(r)">
            <td class="name" :title="r.strategy_name">{{ r.strategy_name }}</td>
            <td><span class="kind-badge" :class="r.kind">{{ kindLabel(r.kind) }}</span></td>
            <td class="sub-strat">
              {{ r.strategy_label || r.strategy }}
              <span class="params">{{ JSON.stringify(r.params) }}</span>
            </td>
            <td class="sym">{{ r.symbol }}</td>
            <td v-if="r.error" class="err" colspan="4">⚠ {{ r.error }}</td>
            <template v-else>
              <td>
                <span v-if="r.latest_signal" class="signal-tag" :class="r.latest_signal">
                  {{ r.latest_signal === 'BUY' ? '买入' : '卖出' }}
                </span>
                <span v-else class="none-tag">—</span>
              </td>
              <td class="seq">{{ signalSeq(r) || '—' }}</td>
              <td class="num">{{ r.last_close != null ? r.last_close.toFixed(2) : '-' }}</td>
              <td>
                <span v-if="r.position" class="pos-tag" :class="r.position">
                  {{ r.position === 'holding' ? '持仓' : '空仓' }}
                </span>
              </td>
            </template>
            <td @click.stop>
              <button v-if="!r.error" class="ghost sm" @click="onLoad(r)">载入</button>
            </td>
          </tr>
        </tbody>
      </table>
    </template>

    <div v-if="!result && !scanning && !error" class="placeholder">
      <p>还没有扫描结果。</p>
      <p class="hint">
        点右上角「⚡ 一键扫描」，把策略库里保存的单策略与组合策略全部检查一遍，
        列出最近 {{ windowBars }} 根 K 线内出现买卖信号的策略。每天收盘后扫一次即可跟踪。
      </p>
    </div>
      </div><!-- /.main-col -->

      <!-- 右侧策略管理：新增 / 修改 / 删除（与策略库同一后端） -->
      <aside class="strat-panel">
        <div class="strat-head">
          <h3>策略 <span class="dim count">{{ strategyList.length }}</span></h3>
          <button class="primary sm" @click="openCreate">＋ 新增</button>
        </div>
        <p class="strat-hint">点行勾选参与扫描；✎ 修改、删 删除。</p>
        <div v-if="stratMsg" class="strat-err">⚠ {{ stratMsg }}</div>
        <div v-if="strategyList.length === 0" class="strat-empty">
          策略库为空，点「＋ 新增」建第一条。
        </div>
        <ul v-else class="strat-list">
          <li
            v-for="s in strategyList"
            :key="s.id"
            class="strat-row"
            :class="{ picked: pickedIds.has(s.id) }"
            :title="`${s.strategy_label || s.strategy} · ${ctxSymbol(s)}`"
            @click="togglePick(s.id)"
          >
            <span class="s-pick">{{ pickedIds.has(s.id) ? '☑' : '☐' }}</span>
            <span class="s-main">
              <span class="s-name">{{ s.name }}</span>
              <span class="s-sub dim">{{ s.strategy_label || s.strategy }} · {{ ctxSymbol(s) }}</span>
            </span>
            <span class="s-ops" @click.stop>
              <button class="mini" title="修改" @click="openEdit(s)">✎</button>
              <button
                class="mini del"
                title="删除"
                :disabled="deletingId === s.id"
                @click="onDeleteStrategy(s)"
              >
                {{ deletingId === s.id ? '…' : '删' }}
              </button>
            </span>
          </li>
        </ul>
      </aside>
    </div><!-- /.content -->

    <!-- 子任务详情弹窗 -->
    <div v-if="detailRow" class="modal-mask" @click.self="detailRow = null">
      <div class="modal" role="dialog" aria-modal="true" aria-label="子任务详情">
        <div class="modal-head">
          <h3>子任务详情</h3>
          <button class="close-btn" @click="detailRow = null">✕</button>
        </div>
        <div class="d-signal">
          <span v-if="detailRow.error" class="err-text">⚠ {{ detailRow.error }}</span>
          <span v-else-if="detailRow.latest_signal" class="signal-tag" :class="detailRow.latest_signal">
            {{ detailRow.latest_signal === 'BUY' ? '买入' : '卖出' }}
          </span>
          <span v-else class="none-tag">窗口内无信号</span>
          <span class="dim sym">{{ detailRow.symbol }}</span>
        </div>
        <dl class="d-grid">
          <dt>所属策略</dt><dd>{{ detailRow.strategy_name }}</dd>
          <dt>类型</dt><dd>{{ kindLabel(detailRow.kind) }}</dd>
          <dt>子策略</dt><dd>{{ detailRow.strategy_label || detailRow.strategy }}</dd>
          <dt>参数</dt><dd class="mono">{{ JSON.stringify(detailRow.params) }}</dd>
          <dt>周期</dt><dd class="mono">{{ detailRow.category }}</dd>
          <dt>最新信号日期</dt><dd class="mono">{{ detailRow.signal_date || '—' }}</dd>
          <dt>窗口内信号</dt><dd class="mono">{{ signalSeq(detailRow) || '—' }}</dd>
          <dt>最新收盘</dt>
          <dd class="mono">{{ detailRow.last_close != null ? detailRow.last_close.toFixed(2) : '-' }}</dd>
          <dt>末根日期</dt><dd class="mono">{{ detailRow.last_bar_date || '—' }}</dd>
          <dt>仓位</dt>
          <dd>{{ detailRow.position ? (detailRow.position === 'holding' ? '持仓' : '空仓') : '—' }}</dd>
        </dl>
        <div class="modal-actions">
          <button v-if="!detailRow.error" class="ghost sm" @click="onLoad(detailRow)">载入回测</button>
          <button
            v-if="!detailRow.error && detailRow.latest_signal"
            class="ghost sm"
            :disabled="pushingOne"
            @click="onPushOne"
          >
            {{ pushingOne ? '推送中…' : '📣 推送该条' }}
          </button>
          <button class="primary sm" @click="detailRow = null">关闭</button>
        </div>
      </div>
    </div>

    <!-- 新增 / 修改策略（与策略库页同款编辑器） -->
    <StrategyEditor
      v-if="editorOpen"
      :editing="editingStrategy"
      @save="onEditorSave"
      @close="editorOpen = false; editingStrategy = null"
    />
  </div>
</template>

<style scoped>
.radar-view {
  height: 100%;
  overflow-y: auto;
  padding: 16px 20px 32px;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-header h2 {
  font-size: 16px;
  font-weight: 600;
}
.subtitle {
  font-size: 12px;
  color: var(--text-dim);
  margin-top: 4px;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.target-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.symbol-input {
  width: 280px;
  padding: 5px 10px;
  font-size: 12px;
}
.target-list {
  display: inline-flex;
  gap: 4px;
  flex-wrap: wrap;
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
.window-picker {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
}
.window-picker select {
  background: var(--bg-panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 5px 8px;
  font-size: 12px;
  cursor: pointer;
}
.primary {
  font-size: 13px;
  padding: 7px 18px;
  background: var(--accent);
  border: 1px solid var(--accent);
  color: #fff;
  font-weight: 600;
  border-radius: var(--radius);
  cursor: pointer;
}
.primary:hover:not(:disabled) {
  filter: brightness(1.1);
}
.primary:disabled {
  opacity: 0.6;
  cursor: default;
}
.error-banner {
  background: rgba(239, 65, 70, 0.12);
  border: 1px solid var(--up);
  color: var(--up);
  padding: 10px 14px;
  border-radius: var(--radius);
  margin-bottom: 16px;
  font-size: 13px;
}
.push-msg {
  padding: 8px 14px;
  border-radius: var(--radius);
  margin-bottom: 12px;
  font-size: 12.5px;
  background: rgba(244, 67, 54, 0.08);
  color: var(--red, #f44336);
}
.push-msg.ok {
  background: rgba(76, 175, 80, 0.12);
  color: var(--green, #4caf50);
}
.scanning-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  font-size: 13px;
}
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  height: 50%;
  color: var(--text-dim);
  gap: 8px;
}
.placeholder .hint,
.hint {
  font-size: 12px;
  color: var(--text-dim);
  max-width: 560px;
  line-height: 1.6;
}

/* 汇总卡片 */
.stat-cards {
  display: flex;
  gap: 14px;
  margin-bottom: 10px;
}
.stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 3px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 14px;
}
.stat .k {
  font-size: 12px;
  color: var(--text-dim);
}
.stat .v {
  font-size: 22px;
  font-weight: 700;
  font-family: var(--font-mono);
}
.stat .v.buy {
  color: var(--up);
}
.stat .v.sell {
  color: var(--down);
}
.stat .v.dim {
  color: var(--text-dim);
}

/* 筛选 tab（与策略库页同风格） */
.tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border);
  margin: 14px 0 12px;
}
.tab {
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}
.tab:hover {
  color: var(--text);
}
.tab.active {
  color: var(--text);
  border-bottom-color: var(--accent);
}
.tab-count {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--border);
  color: var(--text-dim);
  font-weight: 400;
}
.tab.active .tab-count {
  background: rgba(74, 158, 255, 0.18);
  color: var(--accent);
}

/* 结果表 */
.radar-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.radar-table th,
.radar-table td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.radar-table th {
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 600;
}
.radar-table .num {
  text-align: right;
  font-family: var(--font-mono);
}
.radar-table .name {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
.radar-table .sym {
  font-family: var(--font-mono);
  font-weight: 600;
  white-space: nowrap;
}
.radar-table .sub-strat {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sub-strat .params {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-dim);
  margin-left: 6px;
}
.radar-table .seq {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}
.radar-table .err {
  color: var(--up);
  font-size: 12px;
}
.radar-table tr.errored {
  opacity: 0.75;
}

/* 徽章 */
.kind-badge {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 4px;
  background: rgba(74, 158, 255, 0.15);
  color: var(--accent);
  white-space: nowrap;
}
.kind-badge.portfolio {
  background: rgba(140, 110, 220, 0.18);
  color: #b39ddb;
}
.kind-badge.multi {
  background: rgba(245, 158, 11, 0.18);
  color: #f59e0b;
}
.signal-tag {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 4px;
  font-weight: 600;
  white-space: nowrap;
}
/* A股习惯：买入红、卖出绿 */
.signal-tag.BUY {
  background: rgba(239, 65, 70, 0.14);
  color: var(--up);
}
.signal-tag.SELL {
  background: rgba(24, 160, 88, 0.16);
  color: var(--down);
}
.none-tag {
  color: var(--text-dim);
}
.pos-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}
.pos-tag.holding {
  background: rgba(239, 65, 70, 0.12);
  color: var(--up);
}
.pos-tag.flat {
  background: var(--border);
  color: var(--text-dim);
}
.ghost {
  font-size: 12px;
  padding: 4px 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  cursor: pointer;
}
.ghost:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}
.sm {
  font-size: 12px;
  padding: 4px 12px;
}
.primary.sm {
  font-size: 12px;
  padding: 4px 12px;
  background: var(--accent);
  border: 1px solid var(--accent);
  color: #fff;
  font-weight: 600;
  border-radius: var(--radius);
  cursor: pointer;
}

/* 主区 + 右侧策略栏 */
.content {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 12px;
  align-items: start;
}
.main-col {
  min-width: 0;
}
@media (max-width: 1280px) {
  .content {
    grid-template-columns: 1fr;
  }
}

/* 结果行可点击 */
.radar-table tr.clickable {
  cursor: pointer;
}
.radar-table tr.clickable:hover td {
  background: var(--bg-elevated);
}

/* 右侧策略管理 */
.strat-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
  position: sticky;
  top: 0;
  max-height: calc(100vh - 220px);
  overflow-y: auto;
}
.strat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.strat-head h3 {
  font-size: 14px;
  font-weight: 600;
}
.strat-head .count {
  font-weight: 400;
  font-size: 12px;
}
.strat-hint {
  font-size: 11px;
  color: var(--text-dim);
  margin: 6px 0 8px;
}
.strat-err {
  font-size: 12px;
  color: var(--up);
  margin-bottom: 8px;
}
.strat-empty {
  font-size: 12px;
  color: var(--text-dim);
  padding: 12px 4px;
}
.strat-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.strat-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 12px;
}
.strat-row:hover {
  background: var(--bg-elevated);
}
.strat-row.picked {
  border-color: var(--accent);
  background: rgba(74, 158, 255, 0.08);
}
.s-pick {
  color: var(--accent);
  flex-shrink: 0;
}
.s-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.s-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.s-sub {
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.s-ops {
  display: inline-flex;
  gap: 4px;
  flex-shrink: 0;
}
.mini {
  padding: 1px 7px;
  font-size: 11px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  cursor: pointer;
}
.mini:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}
.mini.del:hover:not(:disabled) {
  border-color: var(--up);
  color: var(--up);
}

/* 子任务详情弹窗 */
.modal-mask {
  position: fixed;
  inset: 0;
  background: var(--overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 20px;
  width: 480px;
  max-width: calc(100vw - 32px);
  max-height: 86vh;
  overflow-y: auto;
  box-shadow: 0 16px 48px var(--shadow);
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.modal-head h3 {
  font-size: 15px;
  font-weight: 600;
}
.close-btn {
  padding: 2px 8px;
  font-size: 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  cursor: pointer;
}
.close-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.d-signal {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.d-signal .sym {
  font-family: var(--font-mono);
  font-weight: 600;
}
.err-text {
  color: var(--up);
  font-size: 12px;
}
.d-grid {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 6px 12px;
  font-size: 12.5px;
  margin: 0 0 14px;
}
.d-grid dt {
  color: var(--text-dim);
}
.d-grid dd {
  margin: 0;
  word-break: break-all;
}
.d-grid .mono {
  font-family: var(--font-mono);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
