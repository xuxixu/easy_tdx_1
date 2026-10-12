<script setup lang="ts">
// 预置指标管理列表：六组预置（MA/EMA/BOLL/MACD/KDJ/RSI）
// = 锁定的通达信公式（公式文本由参数生成，只读展示），
// 每组可调周期/倍数（修改即时生效，全局共用）。
import { ref, watch } from 'vue'

import {
  DEFAULT_INDICATOR_PARAMS,
  resetIndicatorParams,
  sanitizeIndicatorParams,
  saveIndicatorParams,
  type IndicatorParams,
} from '../indicatorParams'
import { PRESETS } from '../presetFormulas'

const props = defineProps<{ modelValue: IndicatorParams }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: IndicatorParams): void }>()

const draft = ref<IndicatorParams>({ ...props.modelValue })
watch(
  () => props.modelValue,
  (v) => {
    draft.value = { ...v }
  },
)

function commit() {
  const clean = sanitizeIndicatorParams(draft.value)
  draft.value = clean
  saveIndicatorParams(clean)
  emit('update:modelValue', clean)
}

function onReset() {
  draft.value = resetIndicatorParams()
  emit('update:modelValue', { ...draft.value })
}

function setPeriods(field: 'maPeriods' | 'rsiPeriods', text: string) {
  draft.value[field] = text
    .split(/[,，\s]+/)
    .map((s) => Math.round(Number(s)))
    .filter((n) => Number.isFinite(n) && n >= 2 && n <= 250)
    .slice(0, 4)
  commit()
}
</script>

<template>
  <div class="preset-list">
    <div v-for="p in PRESETS" :key="p.id" class="preset-card">
      <div class="p-head">
        <span class="p-name">{{ p.name }}</span>
        <span class="p-kind">{{ p.kind === 'overlay' ? '主图' : '副图' }}</span>
        <span class="p-lock" title="预置公式锁定，只可调参数">🔒 锁定</span>
      </div>

      <div v-if="p.id === 'ma'" class="f-row">
        <label>MA 周期</label>
        <input
          class="num-text"
          :value="draft.maPeriods.join(',')"
          placeholder="5,10,20,60"
          @change="(e) => setPeriods('maPeriods', (e.target as HTMLInputElement).value)"
        />
        <span class="tip">逗号分隔，最多 4 个（默认 {{ DEFAULT_INDICATOR_PARAMS.maPeriods.join(',') }}）</span>
      </div>
      <div v-if="p.id === 'ema'" class="f-row">
        <label>EMA 快线</label>
        <input
          v-model.number="draft.emaFast"
          class="num"
          type="number"
          min="2"
          max="250"
          @change="commit"
        />
        <label class="ml">慢线</label>
        <input
          v-model.number="draft.emaSlow"
          class="num"
          type="number"
          min="2"
          max="250"
          @change="commit"
        />
      </div>
      <div v-if="p.id === 'boll'" class="f-row">
        <label>BOLL 周期</label>
        <input
          v-model.number="draft.bollN"
          class="num"
          type="number"
          min="2"
          max="250"
          @change="commit"
        />
        <label class="ml">倍数</label>
        <input
          v-model.number="draft.bollP"
          class="num"
          type="number"
          min="0.5"
          max="5"
          step="0.1"
          @change="commit"
        />
      </div>
      <div v-if="p.id === 'macd'" class="f-row">
        <label>MACD 快</label>
        <input
          v-model.number="draft.macdFast"
          class="num"
          type="number"
          min="2"
          max="250"
          @change="commit"
        />
        <label class="ml">慢</label>
        <input
          v-model.number="draft.macdSlow"
          class="num"
          type="number"
          min="2"
          max="250"
          @change="commit"
        />
        <label class="ml">信号</label>
        <input
          v-model.number="draft.macdSignal"
          class="num"
          type="number"
          min="2"
          max="250"
          @change="commit"
        />
      </div>
      <div v-if="p.id === 'kdj'" class="f-row">
        <label>KDJ 周期</label>
        <input
          v-model.number="draft.kdjN"
          class="num"
          type="number"
          min="2"
          max="250"
          @change="commit"
        />
        <span class="tip">K/D 平滑固定 3/1（国内口径）</span>
      </div>
      <div v-if="p.id === 'rsi'" class="f-row">
        <label>RSI 周期</label>
        <input
          class="num-text"
          :value="draft.rsiPeriods.join(',')"
          placeholder="6,12,24"
          @change="(e) => setPeriods('rsiPeriods', (e.target as HTMLInputElement).value)"
        />
        <span class="tip">逗号分隔，最多 4 个</span>
      </div>

      <pre class="p-formula">{{ p.buildFormula(draft) }}</pre>
    </div>

    <div class="f-foot">
      <button class="ghost" @click="onReset">恢复默认</button>
    </div>
  </div>
</template>

<style scoped>
.preset-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.preset-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.p-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.p-name {
  font-weight: 700;
}
.p-kind {
  font-size: 11px;
  padding: 1px 8px;
  border: 1px solid var(--accent);
  border-radius: 10px;
  color: var(--accent);
}
.p-lock {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-dim);
}
.f-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.f-row > label {
  min-width: 64px;
  color: var(--text-muted);
}
.f-row > label.ml {
  min-width: 0;
  margin-left: 8px;
}
.num {
  width: 64px;
}
.num-text {
  width: 130px;
}
.tip {
  font-size: 11px;
  color: var(--text-dim);
}
.p-formula {
  margin: 0;
  padding: 8px 10px;
  font-size: 11.5px;
  line-height: 1.7;
  font-family: var(--font-mono);
  background: var(--bg-elevated);
  border-radius: var(--radius);
  overflow-x: auto;
  color: var(--text-muted);
  white-space: pre-wrap;
}
.f-foot {
  display: flex;
  justify-content: flex-end;
  margin-top: 2px;
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
</style>
