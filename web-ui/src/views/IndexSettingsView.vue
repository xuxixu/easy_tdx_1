<script setup lang="ts">
// 指数设置页（系统分组）：各市场指数指标的新增 / 修改 / 删除 / 排序 / 启停，
// 以及每条指数叠加的技术指标（MA/EMA/BOLL，可多选）。配置落 localStorage，
// 看板指数条与大盘日历共用同一份。
import { computed, ref } from 'vue'

import {
  INDEX_OVERLAY_OPTIONS,
  defaultIndexIndicators,
  enabledIndices,
  loadIndexIndicators,
  resetIndexIndicators,
  saveIndexIndicators,
  type IndexIndicatorItem,
  type IndexIndicatorKind,
} from '../indexIndicators'
import { A_SHARE_MARKETS, EX_MARKETS, marketLabel, type Market } from '../market'

const MARKETS: Array<{ value: Market; label: string }> = [
  ...A_SHARE_MARKETS.map((m) => ({ value: m as Market, label: marketLabel(m) })),
  ...EX_MARKETS.map((m) => ({ value: m as Market, label: marketLabel(m) })),
]

const active = ref<Market>('SH')
const cfg = ref<Record<string, IndexIndicatorItem[]>>(loadIndexIndicators())
const message = ref('')

function list(): IndexIndicatorItem[] {
  return cfg.value[active.value] ?? []
}

const visibleCount = computed(() => enabledIndices(active.value).length)

function touch(msg: string) {
  cfg.value = { ...cfg.value }
  saveIndexIndicators(cfg.value)
  message.value = msg
}

// ── 新增 / 编辑 ──────────────────────────────────────────────────────────────

interface ItemForm {
  code: string
  name: string
  overlays: IndexIndicatorKind[]
  enabled: boolean
}

const formOpen = ref(false)
const editingIdx = ref<number | null>(null)
const form = ref<ItemForm>({ code: '', name: '', overlays: [], enabled: true })
const formError = ref('')

function openCreate() {
  editingIdx.value = null
  form.value = { code: '', name: '', overlays: [], enabled: true }
  formError.value = ''
  formOpen.value = true
}

function openEdit(i: number) {
  const it = list()[i]
  if (!it) return
  editingIdx.value = i
  form.value = { code: it.code, name: it.name, overlays: [...it.overlays], enabled: it.enabled }
  formError.value = ''
  formOpen.value = true
}

function toggleOverlay(k: IndexIndicatorKind) {
  const cur = form.value.overlays
  form.value.overlays = cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k]
}

/** 代码格式校验：A股 6 位数字 / 港股字母数字 / 美股字母。 */
function codeHint(code: string): string {
  const c = code.trim().toUpperCase()
  if (!c) return '必填'
  if (active.value === 'US' && /^[A-Z][A-Z0-9.\-]{0,11}$/.test(c)) return ''
  if (active.value === 'HK' && /^[A-Z0-9]{2,8}$/.test(c)) return ''
  if ((A_SHARE_MARKETS as string[]).includes(active.value) && /^\d{6}$/.test(c)) return ''
  return active.value === 'US'
    ? '美股代码为字母（如 DJI / IXIC / SPX / NDX）'
    : active.value === 'HK'
      ? '港股代码为字母数字（如 HSI / HSCEI / HSTECH 或 00700）'
      : 'A 股代码须为 6 位数字'
}

function submitForm() {
  formError.value = ''
  const code = form.value.code.trim().toUpperCase()
  const hint = codeHint(code)
  if (hint) {
    formError.value = hint
    return
  }
  const name = form.value.name.trim() || code
  const arr = list()
  if (editingIdx.value === null) {
    if (arr.some((x) => x.code === code && x.market === marketTokenOf(active.value))) {
      formError.value = '该市场已存在同代码指数'
      return
    }
    arr.push({
      market: marketTokenOf(active.value),
      code,
      name,
      enabled: form.value.enabled,
      overlays: [...form.value.overlays],
      sort: arr.length,
    })
  } else if (editingIdx.value >= 0 && arr[editingIdx.value]) {
    const it = arr[editingIdx.value]
    const dup = arr.some((x, i) => i !== editingIdx.value && x.code === code)
    if (dup) {
      formError.value = '该市场已存在同代码指数'
      return
    }
    it.code = code
    it.name = name
    it.enabled = form.value.enabled
    it.overlays = [...form.value.overlays]
  }
  touch(editingIdx.value === null ? `已新增 ${name}` : `已修改 ${name}`)
  formOpen.value = false
}

/** 指数条取数的市场标记：与顶栏市场一致（A 股按段规则，外盘 HK/US）。 */
function marketTokenOf(m: Market): string {
  return m as string
}

function removeItem(i: number) {
  const it = list()[i]
  if (!it) return
  if (!confirm(`确定删除「${it.name}」？`)) return
  const arr = list().filter((_, idx) => idx !== i)
  arr.forEach((x, idx) => (x.sort = idx))
  cfg.value = { ...cfg.value, [active.value]: arr }
  saveIndexIndicators(cfg.value)
  message.value = `已删除 ${it.name}`
}

function toggleEnabled(i: number) {
  const it = list()[i]
  if (!it) return
  it.enabled = !it.enabled
  touch(`${it.name} 已${it.enabled ? '启用' : '停用'}`)
}

function move(i: number, dir: -1 | 1) {
  const arr = list()
  const j = i + dir
  if (j < 0 || j >= arr.length) return
  const tmp = arr[i]
  arr[i] = arr[j]
  arr[j] = tmp
  arr.forEach((x, idx) => (x.sort = idx))
  touch('顺序已保存')
}

function onReset() {
  if (!confirm('恢复各市场默认指数配置？自定义项会丢失。')) return
  cfg.value = resetIndexIndicators()
  message.value = '已恢复默认'
}

// 初始化默认值键（首次访问时补齐，避免 undefined 键）
for (const k of Object.keys(defaultIndexIndicators())) {
  if (!cfg.value[k]) cfg.value[k] = defaultIndexIndicators()[k]
}
</script>

<template>
  <div class="idx-view">
    <header class="page-header">
      <div>
        <h2>指数设置</h2>
        <p class="subtitle">
          配置各市场看板顶部的指数条与大盘日历的指数指标：新增 / 修改 / 删除 / 排序 / 启停，
          并可为每条指数叠加技术指标（MA/EMA/BOLL）。默认取各市场主流指数。
        </p>
      </div>
      <div class="header-actions">
        <button class="ghost" @click="onReset">恢复默认</button>
        <button class="primary" @click="openCreate">＋ 新增指数</button>
      </div>
    </header>

    <nav class="market-tabs">
      <button
        v-for="m in MARKETS"
        :key="m.value"
        :class="{ on: active === m.value }"
        @click="active = m.value"
      >
        {{ m.label }}<span class="cnt">{{ (cfg[m.value] ?? []).length }}</span>
      </button>
    </nav>

    <p v-if="message" class="message">{{ message }}</p>
    <p class="hint">
      当前 <b>{{ marketLabel(active) }}</b> 看板显示 {{ visibleCount }} 条（上限 6 条）。
      指数代码按各自市场协议取行情：美股 DJI/IXIC/SPX/NDX 为真指数，港股 HSI/HSCEI/HSTECH 同理。
    </p>

    <table class="idx-table">
      <thead>
        <tr>
          <th>顺序</th>
          <th>名称</th>
          <th>代码</th>
          <th>叠加指标</th>
          <th>状态</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="list().length === 0">
          <td colspan="6" class="empty">该市场暂无指数，点「＋ 新增指数」添加。</td>
        </tr>
        <tr v-for="(it, i) in list()" :key="`${it.market}${it.code}`" :class="{ off: !it.enabled }">
          <td class="ord">
            <button class="mini" title="上移" :disabled="i === 0" @click="move(i, -1)">↑</button>
            <button class="mini" title="下移" :disabled="i === list().length - 1" @click="move(i, 1)">↓</button>
          </td>
          <td class="name">{{ it.name }}</td>
          <td class="mono dim">{{ it.market }}{{ it.code }}</td>
          <td>
            <span v-if="it.overlays.length === 0" class="dim">—</span>
            <span v-for="k in it.overlays" :key="k" class="ov-tag">{{ k.toUpperCase() }}</span>
          </td>
          <td>
            <button class="status" :class="it.enabled ? 'on' : 'off'" @click="toggleEnabled(i)">
              {{ it.enabled ? '启用' : '停用' }}
            </button>
          </td>
          <td class="ops">
            <button class="ghost sm" @click="openEdit(i)">修改</button>
            <button class="danger sm" @click="removeItem(i)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 新增 / 修改弹窗 -->
    <div v-if="formOpen" class="modal-mask" @click.self="formOpen = false">
      <div class="modal" role="dialog" aria-modal="true" aria-label="指数编辑">
        <div class="modal-head">
          <h3>{{ editingIdx === null ? `新增${marketLabel(active)}指数` : '修改指数' }}</h3>
          <button class="close-btn" @click="formOpen = false">✕</button>
        </div>
        <label class="field">
          <span>代码 *</span>
          <input v-model="form.code" class="mono" placeholder="如 000001 / HSI / DJI" spellcheck="false" />
          <em v-if="form.code.trim() && codeHint(form.code)" class="hint-err">{{ codeHint(form.code) }}</em>
        </label>
        <label class="field">
          <span>显示名称（留空=用代码）</span>
          <input v-model="form.name" maxlength="24" placeholder="如 上证指数" />
        </label>
        <label class="field">
          <span>叠加技术指标（可多选，画在指数条迷你图上）</span>
          <div class="ov-list">
            <label v-for="o in INDEX_OVERLAY_OPTIONS" :key="o.value" class="ov-item">
              <input
                type="checkbox"
                :checked="form.overlays.includes(o.value)"
                @change="toggleOverlay(o.value)"
              />
              <span>{{ o.label }}</span>
              <em class="dim">{{ o.hint }}</em>
            </label>
          </div>
        </label>
        <label class="en-row">
          <input v-model="form.enabled" type="checkbox" />启用（关闭后不在指数条显示）
        </label>
        <div v-if="formError" class="form-err">{{ formError }}</div>
        <div class="modal-actions">
          <button class="ghost sm" @click="formOpen = false">取消</button>
          <button class="primary sm" @click="submitForm">
            {{ editingIdx === null ? '新增' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.idx-view {
  height: 100%;
  overflow-y: auto;
  padding: 16px 20px 32px;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
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
  gap: 8px;
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
.market-tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
}
.market-tabs button {
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  padding: 8px 14px;
  font-size: 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.market-tabs button.on {
  color: var(--text);
  border-bottom-color: var(--accent);
}
.cnt {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--border);
  color: var(--text-dim);
}
.hint {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.6;
  margin-bottom: 10px;
}
.message {
  font-size: 12px;
  color: var(--accent);
  margin-bottom: 8px;
}
.idx-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.idx-table th,
.idx-table td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.idx-table th {
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 600;
}
.idx-table tr.off {
  opacity: 0.55;
}
.idx-table .ord {
  white-space: nowrap;
}
.idx-table .ord .mini {
  margin-right: 4px;
}
.mini {
  padding: 1px 6px;
  font-size: 11px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  cursor: pointer;
}
.mini:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.name {
  font-weight: 600;
}
.ov-tag {
  display: inline-block;
  font-size: 11px;
  padding: 1px 7px;
  margin-right: 4px;
  border-radius: 9px;
  background: rgba(74, 158, 255, 0.15);
  color: var(--accent);
}
.status {
  padding: 2px 10px;
  font-size: 11px;
  border-radius: 10px;
  cursor: pointer;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-dim);
}
.status.on {
  border-color: var(--green, #4caf50);
  color: var(--green, #4caf50);
  background: rgba(76, 175, 80, 0.1);
}
.ops {
  white-space: nowrap;
}
.ops .ghost {
  margin-right: 6px;
}
.danger {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  border-radius: var(--radius);
  cursor: pointer;
}
.danger:hover {
  border-color: var(--up);
  color: var(--up);
}
.empty {
  text-align: center;
  color: var(--text-dim);
  padding: 24px 0;
}
.dim {
  color: var(--text-dim);
}
.mono {
  font-family: var(--font-mono);
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
  width: 420px;
  max-width: calc(100vw - 32px);
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
.field {
  display: block;
  font-size: 12px;
  margin-bottom: 10px;
}
.field span {
  display: block;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.field input {
  width: 100%;
  padding: 6px 8px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 12.5px;
}
.hint-err {
  color: var(--warn, #f0a020);
  font-size: 11px;
  font-style: normal;
  margin-top: 4px;
  display: block;
}
.ov-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ov-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text);
}
.ov-item input {
  width: auto;
}
.ov-item em {
  font-size: 11px;
  font-style: normal;
}
.en-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
}
.en-row input {
  width: auto;
}
.form-err {
  color: var(--up);
  font-size: 12px;
  margin-bottom: 8px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>