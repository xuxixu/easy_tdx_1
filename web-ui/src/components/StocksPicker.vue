<script setup lang="ts">
// 多标的输入（组合回测用）。支持三种写法：
//   - A 股 6 位数字（如 600519，市场自动识别沪/深/北）
//   - 港股 4-5 位数字（如 00700，识别为 HK）
//   - 美股字母（如 AAPL，识别为 US）
// 也支持 "MARKET:CODE" 完整写法直输（如 HK:00700）。

import { computed, ref } from 'vue'

import { detectAShareMarket, marketLabel, parseSymbol, type Market } from '../market'

const props = defineProps<{
  modelValue: string[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()

const code = ref('')

/** 输入解析预览：返回识别到的 "MARKET:CODE"，非法返回空。 */
const preview = computed(() => parseInput(code.value))

function parseInput(raw: string): string {
  const s = raw.trim().toUpperCase()
  if (!s) return ''
  // 完整写法直输
  if (s.includes(':')) {
    const [m, c] = parseSymbol(s)
    if (m && c) return `${m}:${c}`
    return ''
  }
  // A 股 6 位
  if (/^\d{6}$/.test(s)) {
    const m: Market = detectAShareMarket(s)
    return `${m}:${s}`
  }
  // 港股 4-5 位
  if (/^\d{4,5}$/.test(s)) return `HK:${s}`
  // 美股字母（排除纯数字）
  if (/^[A-Z][A-Z0-9.\-]{0,11}$/.test(s) && !/^\d+$/.test(s)) return `US:${s}`
  return ''
}

const detectedMarket = computed(() => {
  const p = preview.value
  if (!p) return ''
  return marketLabel(p.split(':')[0] as Market)
})

function add() {
  const sym = parseInput(code.value)
  if (!sym) return
  if (!props.modelValue.includes(sym)) {
    emit('update:modelValue', [...props.modelValue, sym])
  }
  code.value = ''
}

function remove(sym: string) {
  emit('update:modelValue', props.modelValue.filter((s) => s !== sym))
}
</script>

<template>
  <div class="stocks-picker">
    <div class="row add-row">
      <input
        v-model="code"
        maxlength="18"
        placeholder="代码（A股6位/港股4-5位/美股字母，或 MARKET:CODE）"
        @keyup.enter="add"
      />
      <button @click="add">添加</button>
    </div>
    <p v-if="detectedMarket" class="market-hint">将识别为：{{ detectedMarket }} · {{ preview }}</p>

    <div v-if="modelValue.length" class="stock-list">
      <span v-for="s in modelValue" :key="s" class="stock-tag">
        {{ s }}
        <button class="remove" @click="remove(s)">×</button>
      </span>
    </div>
    <p v-else class="hint">至少添加 1 只标的</p>
  </div>
</template>

<style scoped>
.add-row {
  display: flex;
  gap: 6px;
}
.add-row input {
  flex: 1;
}
.market-hint {
  color: var(--text-dim);
  font-size: 11px;
  margin-top: 4px;
}
.stock-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.stock-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-family: var(--font-mono);
}
.remove {
  border: none;
  background: none;
  color: var(--text-dim);
  padding: 0 2px;
  font-size: 14px;
  line-height: 1;
}
.remove:hover {
  color: var(--up);
}
.hint {
  color: var(--text-dim);
  font-size: 11px;
  margin-top: 8px;
}
</style>