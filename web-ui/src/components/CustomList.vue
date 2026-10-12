<script setup lang="ts">
// 自定义指标管理：新增 / 编辑 / 删除用户公式。
// 条目 = 名字 + 主图/副图归属 + 通达信公式文本，与预置同走后端公式引擎；
// 保存后自动出现在各 K 线图标题栏的选择 chips（虚线边框）里。
import { onBeforeUnmount, onUnmounted, ref } from 'vue'

import echarts, { chartAxisColor, initChart, useChartRedraw } from '../echarts-setup'
import { fetchBars, fetchKlineOption, formatError, validateFormula } from '../api'
import { detectAShareMarket } from '../market'
import { currentTheme } from '../theme'
import {
  loadCustoms,
  loadIndicatorParams,
  newCustomId,
  sanitizeCandle,
  saveCustoms,
  saveIndicatorParams,
  subscribeIndicatorParams,
  type CustomIndicator,
} from '../indicatorParams'

const customs = ref<CustomIndicator[]>(loadCustoms())
const unsubscribe = subscribeIndicatorParams(() => {
  customs.value = loadCustoms()
})
onUnmounted(unsubscribe)

// ── 新增 / 编辑表单 ────────────────────────────────────────────────────

const formOpen = ref(false)
const editingId = ref<string | null>(null)
const formName = ref('')
const formKind = ref<'overlay' | 'sub'>('overlay')
const formText = ref('')
const formError = ref('')
const validating = ref(false)
const validation = ref<{ ok: boolean; signals: string[]; values: string[]; error: string | null } | null>(null)
// 叠加 K 线显示（仅主图）：4 个输出列名[开,高,低,收]，命中后画蜡烛、不画线
const formCandleOn = ref(false)
const formCandle = ref<string[]>(['', '', '', ''])
const CANDLE_LABELS = ['开', '高', '低', '收']

function openCreate() {
  editingId.value = null
  formName.value = ''
  formKind.value = 'overlay'
  formText.value = ''
  formError.value = ''
  validation.value = null
  formCandleOn.value = false
  formCandle.value = ['', '', '', '']
  disposePreview()
  previewError.value = ''
  previewInfo.value = ''
  formOpen.value = true
}

function openEdit(c: CustomIndicator) {
  editingId.value = c.id
  formName.value = c.name
  formKind.value = c.kind
  formText.value = c.formula
  formError.value = ''
  validation.value = null
  const cd = sanitizeCandle(c.candle)
  formCandleOn.value = c.kind === 'overlay' && cd.length === 4
  formCandle.value = cd.length === 4 ? [...cd] : ['', '', '', '']
  disposePreview()
  previewError.value = ''
  previewInfo.value = ''
  formOpen.value = true
}

function onCancel() {
  formOpen.value = false
  disposePreview()
}

async function onValidate() {
  validating.value = true
  formError.value = ''
  try {
    validation.value = await validateFormula(formText.value)
    // 校验通过后自动认 K 线列（XOPEN/XCLOSE/XHIGH/XLOW 或 OPEN/CLOSE/HIGH/LOW）
    if (validation.value?.ok) {
      const vals = validation.value.values
      const find = (...names: string[]) =>
        vals.find((v) => names.some((n) => v.toUpperCase() === n)) ?? ''
      const guess = [find('XOPEN', 'OPEN'), find('XHIGH', 'HIGH'), find('XLOW', 'LOW'), find('XCLOSE', 'CLOSE')]
      if (guess.every((g) => g !== '')) {
        formCandle.value = guess as string[]
        if (formKind.value === 'overlay') formCandleOn.value = true
      }
      // 校验通过即自动预览一次（同页真实行情成图，无需跳转 K 线页）
      void onPreview()
    } else {
      clearPreview()
    }
  } catch (e) {
    validation.value = null
    formError.value = e instanceof Error ? e.message : String(e)
    clearPreview()
  } finally {
    validating.value = false
  }
}

// ── 同页预览（验证通过后，用真实行情渲染实际效果）────────────────────
// 走与各 K 线图同一条服务端路径：fetchBars 取日 K + /chart/kline-option
// 组装 option，前端只做 setOption。标的可改（默认 SH:600000 近 N 根）。

const previewSymbol = ref('SH:600000')
const previewCount = ref(150)
const previewLoading = ref(false)
const previewError = ref('')
const previewInfo = ref('')
const previewChartEl = ref<HTMLDivElement>()
let previewChart: echarts.ECharts | null = null
let previewOption: Record<string, unknown> | null = null
/** 预览时的公式快照：文本/位置变化后提示重新预览，避免看旧图。 */
const previewKey = ref('')

function previewDirty(): boolean {
  if (!previewOption) return false
  return previewKey.value !== `${formKind.value}@@${formText.value}@@${formCandleOn.value ? formCandle.value.join(',') : ''}`
}

/** 解析预览标的：支持 "SH:600000" 或裸 "600000"（A 股自动识别市场）。 */
function parsePreviewSymbol(): { market: string; code: string } {
  const s = previewSymbol.value.trim().toUpperCase()
  if (!s) throw new Error('请填写预览标的（如 SH:600000）')
  if (s.includes(':')) {
    const [m, c] = s.split(':')
    if (!m || !c) throw new Error(`无法解析标的：${previewSymbol.value}`)
    return { market: m, code: c }
  }
  if (!/^\d{6}$/.test(s)) throw new Error('A 股请填 6 位代码，或带市场前缀（如 SH:600000）')
  return { market: detectAShareMarket(s), code: s }
}

async function onPreview() {
  if (validation.value?.ok !== true) {
    previewError.value = '请先点“验证语法”，通过后才能预览'
    return
  }
  if (!formText.value.trim()) {
    previewError.value = '公式为空，无法预览'
    return
  }
  previewLoading.value = true
  previewError.value = ''
  try {
    const { market, code } = parsePreviewSymbol()
    const n = Math.min(Math.max(previewCount.value || 150, 30), 800)
    const bars = await fetchBars(market, code, 'DAY')
    if (bars.length < 5) throw new Error(`标的 ${market}:${code} 仅取到 ${bars.length} 根 K 线，不足以预览`)
    const sliced = bars.slice(-n)
    const candleCols =
      formKind.value === 'overlay' && formCandleOn.value
        ? formCandle.value.map((c) => c.trim()).filter((c) => c !== '')
        : []
    const resp = await fetchKlineOption({
      bars: sliced.map((b) => ({
        datetime: b.datetime,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
        vol: b.vol,
      })),
      items: [
        {
          id: 'preview',
          formula: formText.value,
          pane: formKind.value === 'overlay' ? 'main' : 'sub',
          display: {},
          colors: {},
          dashed: [],
          bar_cols: [],
          candle_cols: candleCols,
        },
      ],
      axis_color: chartAxisColor() ?? currentTheme.value.vars['--border'] ?? '#2a2e3a',
    })
    previewOption = resp.option
    previewKey.value = `${formKind.value}@@${formText.value}@@${formCandleOn.value ? formCandle.value.join(',') : ''}`
    previewInfo.value = `${market}:${code} 日K近 ${sliced.length} 根（${sliced[0].datetime.slice(0, 10)} ~ ${sliced[sliced.length - 1].datetime.slice(0, 10)}）`
    renderPreview()
  } catch (e) {
    previewOption = null
    previewInfo.value = ''
    previewError.value = formatError(e)
  } finally {
    previewLoading.value = false
  }
}

function renderPreview() {
  if (!previewChartEl.value || !previewOption) return
  previewChart ??= initChart(previewChartEl.value)
  const opt = { ...(previewOption as Record<string, unknown>) }
  opt['tooltip'] = { trigger: 'axis', axisPointer: { type: 'cross' } }
  previewChart.setOption(opt as never, true)
}

function clearPreview() {
  previewOption = null
  previewInfo.value = ''
  previewError.value = ''
  previewKey.value = ''
  previewChart?.clear()
}

function disposePreview() {
  previewChart?.dispose()
  previewChart = null
  previewOption = null
}

useChartRedraw(() => {
  previewChart?.dispose()
  previewChart = null
  renderPreview()
})

onBeforeUnmount(disposePreview)

function onSave() {
  formError.value = ''
  const name = formName.value.trim().slice(0, 20)
  if (!name) {
    formError.value = '请填写显示名'
    return
  }
  if (!formText.value.trim()) {
    formError.value = '请填写公式文本'
    return
  }
  const candle =
    formKind.value === 'overlay' && formCandleOn.value
      ? sanitizeCandle(formCandle.value)
      : []
  if (formCandleOn.value && formKind.value === 'overlay' && candle.length !== 4) {
    formError.value = '叠加K线需选齐开/高/低/收 4 个输出列（先点“验证语法”）'
    return
  }
  const list = [...customs.value]
  if (editingId.value) {
    const i = list.findIndex((x) => x.id === editingId.value)
    if (i < 0) {
      formError.value = '该条目已被删除'
      return
    }
    list[i] = { ...list[i], name, kind: formKind.value, formula: formText.value, candle }
  } else {
    list.push({ id: newCustomId(), name, kind: formKind.value, formula: formText.value, candle })
  }
  saveCustoms(list)
  disposePreview()
  formOpen.value = false
}

/** 保存并叠加显示：语法通过后按“位置”叠加（主图进主图叠加，副图切副图区），各 K 线面板自动刷新。 */
async function onSaveAndOverlay() {
  formError.value = ''
  if (validation.value?.ok !== true) await onValidate()
  if (validation.value?.ok !== true) {
    formError.value = '语法未通过，无法叠加显示'
    return
  }
  const name = formName.value.trim().slice(0, 20)
  if (!name) {
    formError.value = '请填写显示名'
    return
  }
  const id = editingId.value ?? newCustomId()
  const kind = formKind.value
  const candle = kind === 'overlay' && formCandleOn.value ? sanitizeCandle(formCandle.value) : []
  if (editingId.value) {
    const list = [...customs.value]
    const i = list.findIndex((x) => x.id === editingId.value)
    if (i < 0) {
      formError.value = '该条目已被删除'
      return
    }
    list[i] = { ...list[i], name, kind, formula: formText.value, candle }
    saveCustoms(list)
  } else {
    saveCustoms([...customs.value, { id, name, kind, formula: formText.value, candle }])
  }
  const p = loadIndicatorParams()
  if (kind === 'overlay') {
    if (!p.overlays.includes(id)) {
      p.overlays = [...p.overlays, id]
      p.overlay = p.overlays[0] ?? 'ma'
    }
  } else if (p.subPane !== id) {
    p.subPane = id
  }
  saveIndicatorParams(p)
  disposePreview()
  formOpen.value = false
  packMsg.value = `已保存并叠加到${kind === 'overlay' ? '主图' : '副图'}，到任意K线图查看`
}

// ── 删除（两段确认；同时清理选择态残留） ────────────────────────────────

const confirmDel = ref<string | null>(null)

function onDelete(id: string) {
  if (confirmDel.value !== id) {
    confirmDel.value = id
    return
  }
  confirmDel.value = null
  saveCustoms(customs.value.filter((x) => x.id !== id))
  // 选择态残留清理：删掉的 id 不再参与叠加/副图
  const p = loadIndicatorParams()
  const overlays = (p.overlays ?? []).filter((o) => o !== id)
  const subPane = p.subPane === id ? 'none' : p.subPane
  if (overlays.length !== (p.overlays ?? []).length || subPane !== p.subPane) {
    p.overlays = overlays
    p.overlay = overlays[0] ?? 'ma'
    p.subPane = subPane
    saveIndicatorParams(p)
  }
}

function firstLine(formula: string): string {
  const line = formula.split('\n').map((s) => s.trim()).find((s) => s !== '') ?? ''
  return line.length > 60 ? `${line.slice(0, 60)}…` : line
}

// ── 批量导入 / 导出 ────────────────────────────────────────────────────
// 指标包 = { version: 1, indicators: [{ name, kind, formula, ... }] }，
// 由 scripts/convert_dzh_indicators.py 生成（见 docs/dzh-indicators.md），
// 经「从文件恢复」导入。按显示名去重合并。

interface PackItem {
  name: string
  kind: 'overlay' | 'sub'
  formula: string
  candle: string[]
}

const packBusy = ref(false)
const packMsg = ref('')

function normalizePackItem(it: unknown): PackItem | null {
  if (typeof it !== 'object' || it === null) return null
  const r = it as Record<string, unknown>
  const name = typeof r.name === 'string' ? r.name.trim().slice(0, 20) : ''
  const kind = r.kind === 'sub' ? 'sub' : r.kind === 'overlay' ? 'overlay' : null
  const formula = typeof r.formula === 'string' ? r.formula.slice(0, 8000) : ''
  if (!name || !kind || !formula.trim()) return null
  return { name, kind, formula, candle: sanitizeCandle(r.candle) }
}

function mergePack(items: PackItem[]): { added: number; skipped: number; capped: number } {
  const list = [...customs.value]
  const names = new Set(list.map((x) => x.name))
  const ids = new Set(list.map((x) => x.id))
  let added = 0
  let skipped = 0
  const base = Date.now()
  items.forEach((it, i) => {
    if (names.has(it.name)) {
      skipped += 1
      return
    }
    // 批量导入同毫秒：id 必须逐条唯一，否则清洗去重会吞条目
    let id = `c${(base + i).toString(36)}${i.toString(36)}`
    while (ids.has(id)) id += 'x'
    ids.add(id)
    list.push({ id, name: it.name, kind: it.kind, formula: it.formula, candle: it.candle })
    names.add(it.name)
    added += 1
  })
  saveCustoms(list)
  const kept = loadCustoms().length
  const capped = list.length - kept
  return { added, skipped, capped }
}

function onExportBackup() {
  packMsg.value = ''
  const blob = new Blob(
    [JSON.stringify({ version: 1, indicators: customs.value }, null, 1)],
    { type: 'application/json' },
  )
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'custom-indicators-backup.json'
  a.click()
  URL.revokeObjectURL(a.href)
  packMsg.value = `已导出 ${customs.value.length} 个自定义指标为备份文件`
}

async function onImportFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  packBusy.value = true
  packMsg.value = ''
  try {
    const pack = JSON.parse(await file.text()) as { indicators?: unknown; customs?: unknown }
    const raw = Array.isArray(pack.indicators) ? pack.indicators : Array.isArray(pack.customs) ? pack.customs : []
    const clean = raw.map(normalizePackItem).filter((x): x is PackItem => x !== null)
    if (clean.length === 0) throw new Error('文件中没有可用的指标条目')
    const { added: added2, skipped: skipped2, capped: capped2 } = mergePack(clean)
    packMsg.value = `导入完成：新增 ${added2} 个，${skipped2} 个因重名跳过${capped2 > 0 ? `，${capped2} 个因超上限(100)被截断` : ''}`
  } catch (e) {
    packMsg.value = `导入失败：${e instanceof Error ? e.message : String(e)}`
  } finally {
    packBusy.value = false
  }
}
</script>

<template>
  <div class="custom-list">
    <div v-if="customs.length === 0" class="empty">暂无自定义指标，点下方「新增」编写第一条（与预置同走后端公式引擎）。</div>
    <div v-for="c in customs" :key="c.id" class="c-row">
      <span class="c-name">{{ c.name }}</span>
      <span class="c-kind">{{ c.kind === 'overlay' ? '主图' : '副图' }}</span>
      <span v-if="c.candle.length === 4" class="c-kind">K线</span>
      <span class="c-formula mono">{{ firstLine(c.formula) }}</span>
      <span class="c-ops">
        <button class="mini" @click="openEdit(c)">编辑</button>
        <button
          class="mini danger"
          :class="{ confirm: confirmDel === c.id }"
          @click="onDelete(c.id)"
          @blur="confirmDel = null"
        >
          {{ confirmDel === c.id ? '确认删除？' : '删除' }}
        </button>
      </span>
    </div>

    <div v-if="!formOpen" class="f-foot">
      <button class="ghost" @click="openCreate">＋ 新增自定义指标</button>
      <button class="ghost" @click="onExportBackup">导出备份</button>
      <label class="ghost file">
        从文件恢复
        <input type="file" accept="application/json,.json" hidden @change="onImportFile" />
      </label>
    </div>
    <div v-if="packMsg" class="pack-msg">{{ packMsg }}</div>

    <div v-else class="c-form">
      <label class="field">
        <span>显示名（图例/chips，最多 20 字）</span>
        <input v-model="formName" maxlength="20" placeholder="如  Dual thrust 通道" spellcheck="false" />
      </label>
      <div class="field">
        <span>位置</span>
        <span class="seg">
          <button class="chip" :class="{ on: formKind === 'overlay' }" @click="formKind = 'overlay'">
            主图叠加
          </button>
          <button class="chip" :class="{ on: formKind === 'sub' }" @click="formKind = 'sub'">
            副图
          </button>
        </span>
        <span class="tip">副图数值列默认画线，列名含 HIST/柱/量画 bar</span>
      </div>
      <label class="field">
        <span>公式（输出列即图例项）</span>
        <textarea v-model="formText" rows="5" class="mono" spellcheck="false" />
      </label>
      <div v-if="formKind === 'overlay'" class="field">
        <span>叠加K线显示（四列画成主图蜡烛、不再画线，如平均K线）</span>
        <span class="seg">
          <button class="chip" :class="{ on: !formCandleOn }" @click="formCandleOn = false">
            画线
          </button>
          <button class="chip" :class="{ on: formCandleOn }" @click="formCandleOn = true">
            叠加K线
          </button>
        </span>
        <span v-if="formCandleOn" class="candle-grid">
          <label v-for="(lb, i) in CANDLE_LABELS" :key="lb" class="candle-cell">
            <span>{{ lb }}</span>
            <select v-model="formCandle[i]">
              <option value="">— 选择输出列 —</option>
              <option v-for="col in validation?.values ?? []" :key="col" :value="col">{{ col }}</option>
            </select>
          </label>
        </span>
        <span v-if="formCandleOn" class="tip">先点“验证语法”，自动认 XOPEN/XCLOSE/XHIGH/XLOW；中间变量需先加输出别名（如 KO:XOPEN;）再选</span>
      </div>
      <div v-if="validation" class="valid" :class="{ bad: !validation.ok }">
        <template v-if="validation.ok">
          ✓ 语法通过
          <span v-if="validation.values.length">数值：{{ validation.values.join('、') }}</span>
          <span v-if="validation.signals.length">信号：{{ validation.signals.join('、') }}</span>
        </template>
        <template v-else>✕ {{ validation.error }}</template>
      </div>
      <div v-if="validation?.ok" class="preview">
        <div class="preview-bar">
          <span class="preview-title">实际效果预览（真实行情）</span>
          <label class="preview-sym">
            <span>标的</span>
            <input v-model="previewSymbol" class="mono" spellcheck="false" placeholder="SH:600000" />
          </label>
          <label class="preview-sym">
            <span>根数</span>
            <select v-model.number="previewCount">
              <option :value="80">近 80 根</option>
              <option :value="150">近 150 根</option>
              <option :value="250">近 250 根</option>
              <option :value="400">近 400 根</option>
            </select>
          </label>
          <button class="btn-ghost preview-btn" :disabled="previewLoading" @click="onPreview">
            {{ previewLoading ? '加载中…' : '预览效果' }}
          </button>
        </div>
        <div v-if="previewInfo" class="preview-info">{{ previewInfo }}</div>
        <div v-if="previewDirty()" class="preview-stale">公式/位置已改动，图中为旧版本效果，请重新验证或点“预览效果”刷新</div>
        <div v-if="previewError" class="error-banner">⚠ {{ previewError }}</div>
        <div ref="previewChartEl" class="preview-chart"></div>
        <div v-if="!previewInfo && !previewError && !previewLoading" class="tip">点“验证语法”通过后自动加载此图；换标的/根数后点“预览效果”刷新</div>
      </div>
      <div v-if="formError" class="error-banner">⚠ {{ formError }}</div>
      <div class="actions">
        <button class="btn-ghost" :disabled="validating" @click="onValidate">
          {{ validating ? '校验中…' : '验证语法' }}
        </button>
        <button class="btn-ghost" @click="onCancel">取消</button>
        <button class="btn-ghost" @click="onSave">保存</button>
        <button class="btn-primary" :disabled="validating" @click="onSaveAndOverlay">{{ formKind === 'overlay' ? '保存并叠加到主图' : '保存并叠加到副图' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.empty {
  font-size: 12px;
  color: var(--text-dim);
}
.c-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
}
.c-name {
  font-weight: 700;
  white-space: nowrap;
}
.c-kind {
  font-size: 11px;
  padding: 1px 8px;
  border: 1px dashed var(--accent);
  border-radius: 10px;
  color: var(--accent);
  white-space: nowrap;
}
.c-formula {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-dim);
  font-size: 11.5px;
}
.c-ops {
  display: inline-flex;
  gap: 4px;
  margin-left: auto;
}
.mini {
  padding: 2px 8px;
  font-size: 11px;
}
.mini.danger.confirm {
  border-color: var(--down);
  color: var(--down);
}
.f-foot {
  display: flex;
  justify-content: flex-start;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 2px;
}
.file {
  cursor: pointer;
}
.pack-msg {
  font-size: 12px;
  color: var(--accent);
}
.ghost {
  padding: 6px 14px;
  font-size: 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  cursor: pointer;
}
.ghost:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.c-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 12px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
}
.field input,
.field textarea {
  font-size: 12px;
  padding: 6px 10px;
}
.field textarea {
  resize: vertical;
  line-height: 1.6;
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
.candle-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}
.candle-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
}
.candle-cell select {
  font-size: 12px;
  padding: 4px 6px;
  max-width: 100%;
}
.tip {
  font-size: 11px;
  color: var(--text-dim);
}
.valid {
  font-size: 12px;
  color: var(--up);
}
.valid.bad {
  color: var(--down);
}
.error-banner {
  font-size: 12px;
  color: var(--down);
}
.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.actions .btn-ghost,
.actions .btn-primary {
  flex: 1 1 40%;
}
.btn-primary {
  flex: 1;
  padding: 9px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 13px;
}
.btn-ghost {
  flex: 1;
  padding: 9px;
  background: transparent;
  border: 1px solid var(--accent);
  color: var(--accent);
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 13px;
}
.btn-primary:disabled,
.btn-ghost:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  padding: 8px 10px;
}
.preview-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.preview-title {
  font-size: 12px;
  font-weight: 700;
}
.preview-sym {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
}
.preview-sym input {
  width: 120px;
  font-size: 12px;
  padding: 4px 8px;
}
.preview-sym select {
  font-size: 12px;
  padding: 4px 6px;
}
.preview-btn {
  flex: 0 0 auto;
  padding: 4px 12px;
  font-size: 12px;
}
.preview-info {
  font-size: 11px;
  color: var(--text-dim);
}
.preview-stale {
  font-size: 11px;
  color: var(--warn, #e0a020);
}
.preview-chart {
  width: 100%;
  height: 360px;
  min-height: 280px;
}
</style>
