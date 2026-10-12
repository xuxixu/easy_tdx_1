<script setup lang="ts">
// 策略类型页：浏览全部策略类型（内置只读 + 自定义可增删改）。
//
// 内置类型是 Python 代码，只能查看（说明/参数 schema/预设网格）；
// 自定义类型是"基于内置的命名预设包"（新名称 + 默认参数 + 可选网格），
// 注册进注册表后与内置同等可用（回测/寻优表单/信号扫描），支持新增/编辑/删除。
import { computed, onMounted, ref } from 'vue'

import {
  createCustomType,
  deleteCustomType,
  fetchCustomTypes,
  fetchSavedStrategies,
  fetchStrategies,
  formatError,
  updateCustomType,
} from '../api'
import type { CustomStrategyType, StrategySchema } from '../types'

const strategies = ref<StrategySchema[]>([])
const customRecords = ref<CustomStrategyType[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [a, b] = await Promise.all([fetchStrategies(), fetchCustomTypes()])
    strategies.value = a.strategies
    customRecords.value = b.items
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

const customTypes = computed(() => strategies.value.filter((s) => s.custom))
const builtinTypes = computed(() => strategies.value.filter((s) => !s.custom))

const filteredBuiltin = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return builtinTypes.value
  return builtinTypes.value.filter(
    (s) =>
      s.label.toLowerCase().includes(q) ||
      s.name.toLowerCase().includes(q) ||
      s.description.toLowerCase().includes(q),
  )
})

// ── 详情弹窗 ─────────────────────────────────────────────────────────────────

const detail = ref<StrategySchema | null>(null)

function gridText(s: StrategySchema): string {
  const g = s.preset_grid ?? {}
  const keys = Object.keys(g)
  if (keys.length === 0) return '—'
  return keys.map((k) => `${k}: [${g[k].join(', ')}]`).join('；')
}

/** 自定义类型的基准内置策略名（存储记录里取）。 */
function baseOf(name: string): string {
  return customRecords.value.find((x) => x.name === name)?.base ?? '—'
}

// ── 新增 / 编辑自定义类型 ───────────────────────────────────────────────────

interface TypeForm {
  label: string
  base: string
  description: string
  paramsText: string
  gridText: string
}

const formOpen = ref(false)
const editingName = ref<string | null>(null)
const form = ref<TypeForm>({ label: '', base: 'ma_cross', description: '', paramsText: '{}', gridText: '{}' })
const formError = ref('')
const formSaving = ref(false)

function baseSchema(name: string): StrategySchema | undefined {
  return builtinTypes.value.find((s) => s.name === name)
}

/** 把基准默认参数填入表单（编辑现有自定义类型时回填它的值）。 */
function fillForm(name: string | null) {
  if (!name) {
    const b = baseSchema(form.value.base) ?? builtinTypes.value[0]
    form.value = {
      label: '',
      base: b?.name ?? 'ma_cross',
      description: '',
      paramsText: JSON.stringify(
        Object.fromEntries((b?.params ?? []).map((p) => [p.name, p.default])),
        null,
        2,
      ),
      gridText: '{}',
    }
  } else {
    const rec = customRecords.value.find((x) => x.name === name)
    const s = strategies.value.find((x) => x.name === name)
    if (!rec || !s) return
    form.value = {
      label: s.label,
      base: rec.base,
      description: s.description,
      paramsText: JSON.stringify(rec.default_params, null, 2),
      gridText: JSON.stringify(rec.preset_grid ?? {}, null, 2),
    }
  }
  formError.value = ''
}

function openCreate() {
  editingName.value = null
  fillForm(null)
  formOpen.value = true
}

function openEdit(s: StrategySchema) {
  editingName.value = s.name
  fillForm(s.name)
  formOpen.value = true
}

/** 基准切换时默认参数跟随重置（避免旧基准的参数残留导致 400）。 */
function onBaseChange() {
  const b = baseSchema(form.value.base)
  if (!b) return
  form.value.paramsText = JSON.stringify(
    Object.fromEntries(b.params.map((p) => [p.name, p.default])),
    null,
    2,
  )
  formError.value = ''
}

function parseJsonField(text: string, field: string): Record<string, unknown> {
  let v: unknown
  try {
    v = JSON.parse(text || '{}')
  } catch {
    throw new Error(`${field}不是合法 JSON`)
  }
  if (typeof v !== 'object' || v === null || Array.isArray(v)) {
    throw new Error(`${field}须为 JSON 对象`)
  }
  return v as Record<string, unknown>
}

async function onFormSave() {
  formError.value = ''
  if (!form.value.label.trim()) {
    formError.value = '请填写类型名称'
    return
  }
  let defaults: Record<string, unknown>
  let grid: Record<string, unknown>
  try {
    defaults = parseJsonField(form.value.paramsText, '默认参数')
    grid = parseJsonField(form.value.gridText, '预设网格')
    for (const [k, v] of Object.entries(grid)) {
      if (!Array.isArray(v)) throw new Error(`预设网格 '${k}' 须为列表`)
    }
  } catch (e) {
    formError.value = formatError(e)
    return
  }
  formSaving.value = true
  try {
    const payload = {
      label: form.value.label.trim(),
      base: form.value.base,
      description: form.value.description.trim(),
      default_params: defaults as Record<string, number | string | boolean>,
      preset_grid: grid as Record<string, Array<number | string>>,
    }
    if (editingName.value) {
      await updateCustomType(editingName.value, payload)
    } else {
      await createCustomType(payload)
    }
    formOpen.value = false
    editingName.value = null
    await load()
  } catch (e) {
    formError.value = formatError(e)
  } finally {
    formSaving.value = false
  }
}

// ── 删除自定义类型 ───────────────────────────────────────────────────────────

const deletingName = ref<string | null>(null)

async function onDelete(s: StrategySchema) {
  // 引用计数：前端数一下已保存策略里用该类型的条数，写进确认框
  let inUse = 0
  try {
    const saved = await fetchSavedStrategies()
    inUse = saved.strategies.filter((x) => x.strategy === s.name).length
  } catch {
    inUse = 0
  }
  const warn = inUse > 0
    ? `确定删除自定义类型「${s.label}」？\n\n有 ${inUse} 条已保存策略引用了它，删除后这些策略在信号扫描时会报错（历史业绩快照保留）。`
    : `确定删除自定义类型「${s.label}」？此操作不可撤销。`
  if (!confirm(warn)) return
  deletingName.value = s.name
  try {
    await deleteCustomType(s.name)
    await load()
  } catch (e) {
    error.value = formatError(e)
  } finally {
    deletingName.value = null
  }
}
</script>

<template>
  <div class="types-view">
    <header class="page-header">
      <div>
        <h2>策略类型</h2>
        <p class="subtitle">
          共 {{ strategies.length }} 种（内置 {{ builtinTypes.length }} / 自定义 {{ customTypes.length }}）。
          内置类型是代码实现，只能查看；自定义类型是"基于内置的命名预设包"，可新增/编辑/删除，
          建好后在回测、寻优、信号扫描里与内置一样选用。
        </p>
      </div>
      <div class="header-actions">
        <input v-model="search" class="search mono" placeholder="搜索内置类型…" />
        <button class="ghost" :disabled="loading" @click="load">
          {{ loading ? '刷新中…' : '↻ 刷新' }}
        </button>
        <button class="primary" @click="openCreate">＋ 新增自定义类型</button>
      </div>
    </header>

    <div v-if="error" class="error-banner">⚠ {{ error }}</div>

    <!-- 自定义类型 -->
    <h3 class="section-title">自定义类型 <span class="dim count">{{ customTypes.length }}</span></h3>
    <div v-if="!loading && customTypes.length === 0" class="placeholder-sm">
      还没有自定义类型，点右上角「＋ 新增」把常用参数存成可复用的类型
      （如"双均线·短线版"基于双均线交叉，默认 fast=5/slow=20）。
    </div>
    <div v-else class="card-grid">
      <article v-for="s in customTypes" :key="s.name" class="card card-custom">
        <div class="card-head">
          <span class="kind-badge custom">自定义</span>
          <h3 class="card-title">{{ s.label }}</h3>
        </div>
        <div class="card-code mono dim">{{ s.name }}</div>
        <p v-if="s.description" class="card-desc">{{ s.description }}</p>
        <div class="card-meta mono">
          默认：{{ s.params.map((p) => `${p.name}=${JSON.stringify(p.default)}`).join(' · ') || '—' }}
        </div>
        <div class="card-foot">
          <button class="ghost sm" @click="detail = s">查看</button>
          <span class="actions">
            <button class="ghost sm" @click="openEdit(s)">修改</button>
            <button class="danger sm" :disabled="deletingName === s.name" @click="onDelete(s)">
              {{ deletingName === s.name ? '…' : '删除' }}
            </button>
          </span>
        </div>
      </article>
    </div>

    <!-- 内置类型 -->
    <h3 class="section-title">内置类型 <span class="dim count">{{ filteredBuiltin.length }}</span></h3>
    <table class="types-table">
      <thead>
        <tr>
          <th>名称</th>
          <th>类型键</th>
          <th>参数</th>
          <th>说明</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in filteredBuiltin" :key="s.name" class="clickable" @click="detail = s">
          <td class="name">{{ s.label }}</td>
          <td class="mono dim">{{ s.name }}</td>
          <td class="mono dim">{{ s.params.length }} 个</td>
          <td class="desc">{{ s.description || '—' }}</td>
        </tr>
      </tbody>
    </table>
    <div v-if="!loading && filteredBuiltin.length === 0" class="placeholder-sm">
      没有匹配的类型。
    </div>

    <!-- 详情弹窗 -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal" role="dialog" aria-modal="true" aria-label="策略类型详情">
        <div class="modal-head">
          <h3>{{ detail.label }}</h3>
          <button class="close-btn" @click="detail = null">✕</button>
        </div>
        <div class="d-sub">
          <span class="kind-badge" :class="{ custom: detail.custom }">{{ detail.custom ? '自定义' : '内置' }}</span>
          <span class="mono dim">{{ detail.name }}</span>
          <span v-if="detail.custom" class="mono dim">基于 {{ baseOf(detail.name) }}</span>
        </div>
        <p v-if="detail.description" class="d-desc">{{ detail.description }}</p>
        <h4>参数（{{ detail.params.length }}）</h4>
        <table v-if="detail.params.length" class="param-table">
          <thead>
            <tr>
              <th>参数</th>
              <th>标签</th>
              <th>类型</th>
              <th>默认</th>
              <th>范围/选项</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in detail.params" :key="p.name">
              <td class="mono">{{ p.name }}</td>
              <td>{{ p.label }}</td>
              <td class="mono dim">{{ p.type }}</td>
              <td class="mono">{{ JSON.stringify(p.default) }}</td>
              <td class="mono dim">
                {{ [p.min_value ?? '', p.max_value ?? ''].some((v) => v !== '') ? `${p.min_value ?? '…'} ~ ${p.max_value ?? '…'}` : '' }}
                {{ (p.choices ?? []).join(' / ') }}
                {{ p.description ?? '' }}
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="dim">无参数（固定逻辑）</p>
        <h4>预设寻优网格</h4>
        <p class="mono grid-text">{{ gridText(detail) }}</p>
        <div v-if="detail.custom" class="modal-actions">
          <button class="ghost sm" @click="openEdit(detail); detail = null">修改</button>
        </div>
      </div>
    </div>

    <!-- 新增 / 编辑弹窗 -->
    <div v-if="formOpen" class="modal-mask" @click.self="formOpen = false">
      <div class="modal" role="dialog" aria-modal="true" aria-label="自定义类型编辑">
        <div class="modal-head">
          <h3>{{ editingName ? '修改自定义类型' : '新增自定义类型' }}</h3>
          <button class="close-btn" @click="formOpen = false">✕</button>
        </div>
        <div class="form-body">
          <label class="field">
            <span>名称 *</span>
            <input v-model="form.label" maxlength="64" placeholder="如 双均线·短线版" />
          </label>
          <label class="field">
            <span>基准内置策略 *（切换后默认参数自动重置）</span>
            <select v-model="form.base" @change="onBaseChange">
              <option v-for="b in builtinTypes" :key="b.name" :value="b.name">
                {{ b.label }}（{{ b.name }}）
              </option>
            </select>
          </label>
          <label class="field">
            <span>说明</span>
            <input v-model="form.description" maxlength="256" placeholder="如 短线快进快出，震荡市慎用" />
          </label>
          <label class="field">
            <span>默认参数 JSON *（键须为基准参数名，值须合法）</span>
            <textarea v-model="form.paramsText" class="mono" rows="5" spellcheck="false" />
          </label>
          <label class="field">
            <span>预设寻优网格 JSON（可选，参数名 → 取值列表）</span>
            <textarea v-model="form.gridText" class="mono" rows="3" spellcheck="false" />
          </label>
          <div v-if="formError" class="form-err">{{ formError }}</div>
          <div class="modal-actions">
            <button class="ghost sm" @click="formOpen = false">取消</button>
            <button class="primary sm" :disabled="formSaving" @click="onFormSave">
              {{ formSaving ? '保存中…' : editingName ? '保存修改' : '新增' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.types-view {
  height: 100%;
  overflow-y: auto;
  padding: 16px 20px 32px;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.page-header h2 {
  font-size: 16px;
  font-weight: 600;
}
.subtitle {
  font-size: 12px;
  color: var(--text-dim);
  margin-top: 4px;
  max-width: 720px;
  line-height: 1.6;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.search {
  width: 200px;
  padding: 6px 10px;
  font-size: 12px;
}
.primary {
  font-size: 13px;
  padding: 7px 16px;
  background: var(--accent);
  border: 1px solid var(--accent);
  color: #fff;
  font-weight: 600;
  border-radius: var(--radius);
  cursor: pointer;
}
.ghost {
  font-size: 12px;
  padding: 6px 12px;
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
.section-title {
  font-size: 14px;
  font-weight: 600;
  margin: 18px 0 10px;
}
.section-title .count {
  font-weight: 400;
  font-size: 12px;
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
.placeholder-sm {
  color: var(--text-dim);
  font-size: 12.5px;
  padding: 14px 4px;
  line-height: 1.7;
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}
.card {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.card-custom {
  border-color: rgba(245, 158, 11, 0.35);
}
.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-title {
  font-size: 14px;
  font-weight: 600;
}
.card-code {
  font-size: 11px;
}
.card-desc {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
}
.card-meta {
  font-size: 11px;
  color: var(--text-dim);
  word-break: break-all;
}
.card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 6px;
}
.actions {
  display: flex;
  gap: 8px;
}
.kind-badge {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 4px;
  background: rgba(74, 158, 255, 0.15);
  color: var(--accent);
  white-space: nowrap;
}
.kind-badge.custom {
  background: rgba(245, 158, 11, 0.18);
  color: #f59e0b;
}
.danger {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  border-radius: var(--radius);
  cursor: pointer;
}
.danger:hover:not(:disabled) {
  border-color: var(--up);
  color: var(--up);
}
.types-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.types-table th,
.types-table td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
.types-table th {
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 600;
}
.types-table tr.clickable {
  cursor: pointer;
}
.types-table tr.clickable:hover td {
  background: var(--bg-elevated);
}
.types-table .name {
  font-weight: 600;
  white-space: nowrap;
}
.types-table .desc {
  color: var(--text-muted);
  font-size: 12px;
  max-width: 520px;
}
.mono {
  font-family: var(--font-mono);
}
.dim {
  color: var(--text-dim);
}
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
  width: 640px;
  max-width: calc(100vw - 32px);
  max-height: 86vh;
  overflow-y: auto;
  box-shadow: 0 16px 48px var(--shadow);
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
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
.d-sub {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 8px;
}
.d-desc {
  font-size: 12.5px;
  color: var(--text-muted);
  line-height: 1.6;
  margin-bottom: 10px;
}
.modal h4 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  margin: 12px 0 8px;
}
.param-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.param-table th,
.param-table td {
  padding: 6px 8px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
.param-table th {
  color: var(--text-dim);
  font-weight: 600;
}
.grid-text {
  font-size: 12px;
  word-break: break-all;
}
.form-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.field {
  display: block;
  font-size: 12px;
}
.field span {
  display: block;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.field input,
.field select,
.field textarea {
  width: 100%;
  padding: 6px 8px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 12.5px;
}
.field textarea {
  resize: vertical;
}
.form-err {
  color: var(--up);
  font-size: 12px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>
