<script setup lang="ts">
// 全局异常弹窗：顶栏 🐛 图标唤起。展示 errors.ts 捕获到的全部异常，
// 支持按来源筛选、单条/全部复制、清空。
//
// 交互取的是「开发工具」的路子而不是「弹窗表单」的路子：默认逐条折叠，
// 只显示时间 + 来源 + 首行消息，展开才出堆栈——异常一多时列表仍然可读。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import {
  KIND_LABEL_TEXT,
  clearErrors,
  errorUnread,
  errors,
  formatAll,
  formatOne,
  markErrorsSeen,
} from '../errors'
import type { CapturedError, ErrorKind } from '../errors'

const emit = defineEmits<{ close: [] }>()

/** 筛选项：全部 + 四种来源。 */
const FILTERS: Array<{ key: ErrorKind | 'all'; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'js', label: 'JS' },
  { key: 'promise', label: 'Promise' },
  { key: 'console', label: 'Console' },
  { key: 'vue', label: 'Vue' },
]
const filter = ref<ErrorKind | 'all'>('all')

/** 展开堆栈的条目 id 集合（用 Set 存，复制成新数组给 Vue 比较）。 */
const expanded = ref<number[]>([])

const shown = computed(() =>
  filter.value === 'all' ? errors.value : errors.value.filter((x) => x.kind === filter.value),
)

const hint = ref('')

function kindLabel(k: ErrorKind) {
  return KIND_LABEL_TEXT[k]
}

function hhmm(ts: number) {
  const d = new Date(ts)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** 堆栈首行（"TypeError: xxx"）已经含在 message 里，这里只取第一帧定位行。 */
function firstFrame(x: CapturedError) {
  return x.stack
    .split('\n')
    .map((l) => l.trim())
    .find((l) => l.startsWith('at '))
}

function toggle(id: number) {
  expanded.value = expanded.value.includes(id)
    ? expanded.value.filter((x) => x !== id)
    : [...expanded.value, id]
}

/** 剪贴板兜底：非安全上下文（http 局域网访问）下 navigator.clipboard 不可用。 */
async function copy(text: string, okMsg: string) {
  try {
    await navigator.clipboard.writeText(text)
    hint.value = okMsg
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    hint.value = document.execCommand('copy') ? okMsg : '复制失败，请手动选中文本复制'
    document.body.removeChild(ta)
  }
}

function copyOne(x: CapturedError) {
  void copy(formatOne(x), `✓ 已复制这条异常（${kindLabel(x.kind)}）`)
}

function copyAll() {
  if (shown.value.length === 0) return
  void copy(formatAll(shown.value), `✓ 已复制全部 ${shown.value.length} 条异常`)
}

function onClear() {
  const n = errors.value.length
  if (n === 0) return
  if (!window.confirm(`确定清空全部 ${n} 条异常记录？（清空后无法恢复）`)) return
  clearErrors()
  expanded.value = []
  hint.value = `✓ 已清空 ${n} 条`
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

// 打开即视为已读：未读角标在弹窗展示的瞬间清零
markErrorsSeen()
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="modal">
      <h3>
        🐛 全局异常
        <span class="count">共 {{ errors.length }} 条<span v-if="errorUnread"> · 未读 {{ errorUnread }}</span></span>
      </h3>
      <p class="modal-desc">
        捕获页面上的未捕获异常、Promise 拒绝、被 catch 后仅打印的 console 错误与 Vue 渲染/路由错误；
        相同错误会合并计数。记录仅保存在本机浏览器，不上传任何服务器。
      </p>

      <div class="toolbar">
        <div class="filters">
          <button
            v-for="f in FILTERS"
            :key="f.key"
            class="chip"
            :class="{ active: filter === f.key }"
            @click="filter = f.key"
          >
            {{ f.label }}
          </button>
        </div>
        <div class="ops">
          <button class="ghost" :disabled="!shown.length" @click="copyAll">复制全部</button>
          <button class="ghost danger" :disabled="!errors.length" @click="onClear">清空</button>
        </div>
      </div>

      <div class="list">
        <p v-if="!errors.length" class="empty">✅ 暂无异常记录</p>
        <p v-else-if="!shown.length" class="empty">该来源下没有记录</p>

        <div
          v-for="x in shown"
          :key="x.id"
          class="item"
          :class="[`k-${x.kind}`, { open: expanded.includes(x.id) }]"
        >
          <div class="row1" @click="toggle(x.id)">
            <span class="time mono">{{ hhmm(x.lastTs) }}</span>
            <span class="badge">{{ kindLabel(x.kind) }}</span>
            <span v-if="x.count > 1" class="times">×{{ x.count }}</span>
            <span class="msg" :title="x.message">{{ x.message }}</span>
            <button class="mini" title="复制这条异常" @click.stop="copyOne(x)">复制</button>
          </div>
          <div v-if="expanded.includes(x.id)" class="detail">
            <div v-if="firstFrame(x)" class="frame mono">{{ firstFrame(x) }}</div>
            <div v-if="x.source" class="frame mono">来源: {{ x.source }}</div>
            <pre class="stack mono">{{ x.stack || '（无堆栈信息）' }}</pre>
          </div>
        </div>
      </div>

      <span v-if="hint" class="hint">{{ hint }}</span>
      <div class="modal-actions">
        <button class="ghost" @click="emit('close')">关闭</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1150;
}
.modal {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  width: 720px;
  max-width: 94vw;
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-shadow: 0 16px 48px var(--shadow);
}
.modal h3 {
  font-size: 15px;
  font-weight: 600;
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.count {
  font-size: 11.5px;
  font-weight: 400;
  color: var(--text-dim);
}
.modal-desc {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.5;
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.filters {
  display: flex;
  gap: 4px;
}
.chip {
  padding: 3px 10px;
  font-size: 11.5px;
  border-radius: 20px;
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-muted);
}
.chip:hover {
  border-color: var(--accent);
}
.chip.active {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--bg-elevated);
}
.ops {
  display: flex;
  gap: 6px;
}
.ghost {
  font-size: 12px;
  padding: 4px 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
}
.ghost.danger:hover:not(:disabled) {
  border-color: var(--up);
  color: var(--up);
}
.list {
  max-height: 52vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-right: 2px;
}
.empty {
  padding: 22px 0;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-dim);
}
.item {
  border: 1px solid var(--border);
  border-left-width: 3px;
  border-radius: var(--radius);
  background: var(--bg-elevated);
  overflow: hidden;
}
.k-js {
  border-left-color: var(--up);
}
.k-promise {
  border-left-color: var(--warn);
}
.k-console {
  border-left-color: var(--accent);
}
.k-vue {
  border-left-color: var(--good);
}
.row1 {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  cursor: pointer;
}
.row1:hover {
  background: var(--bg-panel);
}
.time {
  font-size: 11.5px;
  color: var(--text-dim);
  flex-shrink: 0;
}
.badge {
  flex-shrink: 0;
  padding: 1px 6px;
  font-size: 10.5px;
  border-radius: 3px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  color: var(--text-muted);
}
.times {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--warn);
  font-variant-numeric: tabular-nums;
}
.msg {
  flex: 1;
  min-width: 0;
  font-size: 12.5px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mini {
  flex-shrink: 0;
  padding: 2px 8px;
  font-size: 11px;
  border-radius: 4px;
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-muted);
}
.detail {
  padding: 4px 10px 10px;
  border-top: 1px solid var(--border);
}
.frame {
  font-size: 11.5px;
  color: var(--text-dim);
  word-break: break-all;
}
.stack {
  margin-top: 6px;
  max-height: 22vh;
  overflow: auto;
  padding: 8px 10px;
  font-size: 11px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
}
.hint {
  font-size: 12px;
  color: var(--good);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 4px;
}
</style>
