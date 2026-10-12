<script setup lang="ts">
// 策略编辑器（新增 / 修改共用）：名称 + 策略类型 + 标的 + 参数 JSON + 备注。
//
// 新增模式：选策略类型 + 填标的（MARKET:CODE 或裸代码自动识别）+ 参数 JSON，
// 直接写入策略库（无需先跑回测）。
// 修改模式：回填现有值，可改名称/策略类型/标的/参数/备注/标签。
import { computed, ref, watch } from 'vue'

import { toSymbolAuto } from '../market'
import type { SavedStrategy } from '../types'
import { useBacktestStore } from '../stores/backtest'

const props = defineProps<{
  /** 修改模式传现有策略；新增模式不传。 */
  editing?: SavedStrategy | null
}>()
const emit = defineEmits<{ (e: 'save', v: StrategyForm): void; (e: 'close'): void }>()

export interface StrategyForm {
  name: string
  strategy: string
  symbol: string
  paramsText: string
  notes: string
  tagsText: string
}

const store = useBacktestStore()

const name = ref('')
const strategy = ref('ma_cross')
const symbolInput = ref('')
const paramsText = ref('{}')
const notes = ref('')
const tagsText = ref('')
const formError = ref('')

function fillFrom(s: SavedStrategy | null | undefined) {
  if (!s) {
    name.value = ''
    strategy.value = store.strategies[0]?.name ?? 'ma_cross'
    symbolInput.value = ''
    paramsText.value = '{}'
    notes.value = ''
    tagsText.value = ''
  } else {
    name.value = s.name
    strategy.value = s.strategy
    symbolInput.value = String((s.context?.symbol as string) ?? '')
    paramsText.value = JSON.stringify(s.params ?? {}, null, 2)
    notes.value = s.notes ?? ''
    tagsText.value = (s.tags ?? []).join(' ')
  }
  formError.value = ''
}

watch(() => props.editing, fillFrom, { immediate: true })

/** 标的归一化预览（MARKET:CODE），非法返回空。 */
const symbolPreview = computed(() => {
  const s = symbolInput.value.trim()
  if (!s) return ''
  try {
    return toSymbolAuto(s)
  } catch {
    return ''
  }
})

function onSave() {
  formError.value = ''
  if (!name.value.trim()) {
    formError.value = '请填写策略名称'
    return
  }
  if (!symbolPreview.value) {
    formError.value = '标的格式不对（A股6位/港股4-5位/美股字母，或 MARKET:CODE）'
    return
  }
  try {
    JSON.parse(paramsText.value || '{}')
  } catch {
    formError.value = '参数不是合法 JSON'
    return
  }
  emit('save', {
    name: name.value.trim(),
    strategy: strategy.value,
    symbol: symbolPreview.value,
    paramsText: paramsText.value || '{}',
    notes: notes.value.trim(),
    tagsText: tagsText.value.trim(),
  })
}
</script>

<template>
  <teleport to="body">
    <div class="ed-mask" @click.self="emit('close')">
      <div class="ed">
        <div class="ed-head">
          <span class="ed-title">{{ editing ? '修改策略' : '新增策略' }}</span>
          <button class="close-btn" @click="emit('close')">✕</button>
        </div>
        <div class="ed-body">
          <div class="ed-row">
            <label>名称</label>
            <input v-model="name" class="wide" maxlength="64" placeholder="如 双均线 · 贵州茅台" />
          </div>
          <div class="ed-row">
            <label>策略类型</label>
            <select v-model="strategy" class="wide">
              <option v-for="st in store.strategies" :key="st.name" :value="st.name">
                {{ st.label || st.name }}{{ st.custom ? '（自定义）' : '' }}
              </option>
            </select>
          </div>
          <div class="ed-row">
            <label>标的</label>
            <input
              v-model="symbolInput"
              class="wide mono"
              placeholder="600519 / 00700 / AAPL / HK:00700"
            />
          </div>
          <div v-if="symbolPreview" class="ed-hint">识别为：{{ symbolPreview }}</div>
          <div class="ed-row">
            <label>参数 JSON</label>
            <textarea v-model="paramsText" class="wide mono" rows="4" spellcheck="false" />
          </div>
          <div class="ed-row">
            <label>标签</label>
            <input v-model="tagsText" class="wide" maxlength="64" placeholder="空格分隔" />
          </div>
          <div class="ed-row">
            <label>备注</label>
            <input v-model="notes" class="wide" maxlength="256" />
          </div>
          <div v-if="formError" class="err">{{ formError }}</div>
          <div class="ed-foot">
            <button class="primary" @click="onSave">{{ editing ? '保存修改' : '新增' }}</button>
            <button class="ghost" @click="emit('close')">取消</button>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<style scoped>
.ed-mask {
  position: fixed;
  inset: 0;
  background: var(--overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.ed {
  width: min(560px, 92vw);
  max-height: 90vh;
  overflow: auto;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.ed-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.ed-title {
  font-size: 14px;
  font-weight: 700;
}
.close-btn {
  margin-left: auto;
  padding: 2px 8px;
  font-size: 12px;
}
.ed-body {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ed-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.ed-row > label {
  min-width: 64px;
  color: var(--text-muted);
  flex-shrink: 0;
}
.wide {
  flex: 1;
  min-width: 0;
}
textarea.wide {
  resize: vertical;
  font-size: 12px;
}
.ed-hint {
  font-size: 11px;
  color: var(--text-dim);
  margin: -6px 0 0 72px;
}
.err {
  color: var(--up);
  font-size: 12px;
}
.ed-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>