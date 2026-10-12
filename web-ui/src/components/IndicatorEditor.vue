<script setup lang="ts">
// 指标编辑器：调 StockKline 全部指标参数（主图选择 + 各指标周期）。
//
// 修改即时生效（@change 回父组件，父组件把 params 传给 StockKline 重绘），
// 落 localStorage 全局共用——个股弹窗、看板 K 线面板、回测 K 线看到同一套。
import { ref, watch } from 'vue'

import {
  DEFAULT_INDICATOR_PARAMS,
  resetIndicatorParams,
  sanitizeIndicatorParams,
  saveIndicatorParams,
  type IndicatorParams,
} from '../indicatorParams'
import type { Overlay, SubPane } from './StockKline.vue'

const props = defineProps<{ modelValue: IndicatorParams }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: IndicatorParams): void; (e: 'close'): void }>()

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

// 主图叠加可多选（MA+EMA+BOLL 同时显示）；勾满即等价「主图无」。
const overlayOpts: Array<{ value: Overlay; label: string }> = [
  { value: 'ma', label: 'MA 均线' },
  { value: 'ema', label: 'EMA 指数平均' },
  { value: 'boll', label: 'BOLL 布林带' },
]

function toggleOverlay(v: Overlay) {
  const cur = draft.value.overlays
  draft.value.overlays = cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]
  draft.value.overlay = draft.value.overlays[0] ?? 'ma'
  commit()
}

function clearOverlays() {
  draft.value.overlays = []
  commit()
}
const subOpts: Array<{ value: SubPane; label: string }> = [
  { value: 'macd', label: 'MACD' },
  { value: 'kdj', label: 'KDJ' },
  { value: 'rsi', label: 'RSI' },
  { value: 'none', label: '副图无' },
]

function setMa(text: string) {
  draft.value.maPeriods = text
    .split(/[,，\s]+/)
    .map((s) => Math.round(Number(s)))
    .filter((n) => Number.isFinite(n) && n >= 2 && n <= 250)
    .slice(0, 4)
  commit()
}

function setRsi(text: string) {
  draft.value.rsiPeriods = text
    .split(/[,，\s]+/)
    .map((s) => Math.round(Number(s)))
    .filter((n) => Number.isFinite(n) && n >= 2 && n <= 250)
    .slice(0, 4)
  commit()
}
</script>

<template>
  <teleport to="body">
    <div class="ed-mask" @click.self="emit('close')">
      <div class="ed">
        <div class="ed-head">
          <span class="ed-title">指标编辑</span>
          <span class="ed-hint">修改即时生效 · 全局共用</span>
          <button class="close-btn" @click="emit('close')">✕</button>
        </div>
        <div class="ed-body">
          <div class="ed-row">
            <label>主图叠加</label>
            <span class="seg">
              <button
                v-for="o in overlayOpts"
                :key="o.value"
                class="chip"
                :class="{ on: draft.overlays.includes(o.value) }"
                @click="toggleOverlay(o.value)"
              >
                {{ o.label }}
              </button>
              <button class="chip" :class="{ on: draft.overlays.length === 0 }" @click="clearOverlays">
                主图无
              </button>
            </span>
            <span class="tip">可多选叠加（如 MA+EMA+BOLL 同时显示）</span>
          </div>
          <div class="ed-row">
            <label>副图</label>
            <span class="seg">
              <button
                v-for="o in subOpts"
                :key="o.value"
                class="chip"
                :class="{ on: draft.subPane === o.value }"
                @click="draft.subPane = o.value; commit()"
              >
                {{ o.label }}
              </button>
            </span>
          </div>

          <div v-if="draft.overlays.includes('ma')" class="ed-row">
            <label>MA 周期</label>
            <input
              class="num-text"
              :value="draft.maPeriods.join(',')"
              placeholder="5,10,20,60"
              @change="(e) => setMa((e.target as HTMLInputElement).value)"
            />
            <span class="tip">逗号分隔，最多 4 个（默认 {{ DEFAULT_INDICATOR_PARAMS.maPeriods.join(',') }}）</span>
          </div>
          <template v-if="draft.overlays.includes('ema')">
            <div class="ed-row">
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
          </template>
          <template v-if="draft.overlays.includes('boll')">
            <div class="ed-row">
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
          </template>

          <template v-if="draft.subPane === 'macd'">
            <div class="ed-row">
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
          </template>
          <div v-if="draft.subPane === 'kdj'" class="ed-row">
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
          <div v-if="draft.subPane === 'rsi'" class="ed-row">
            <label>RSI 周期</label>
            <input
              class="num-text"
              :value="draft.rsiPeriods.join(',')"
              placeholder="6,12,24"
              @change="(e) => setRsi((e.target as HTMLInputElement).value)"
            />
            <span class="tip">逗号分隔，最多 4 个</span>
          </div>

          <div class="ed-foot">
            <button class="ghost" @click="onReset">恢复默认</button>
            <button class="primary" @click="emit('close')">完成</button>
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
  z-index: 200;
}
.ed {
  width: min(560px, 92vw);
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
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
.ed-hint {
  font-size: 11px;
  color: var(--text-dim);
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
  gap: 12px;
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
}
.ed-row > label.ml {
  min-width: 0;
  margin-left: 8px;
}
.seg {
  display: inline-flex;
  gap: 4px;
  flex-wrap: wrap;
}
.chip {
  padding: 3px 10px;
  font-size: 12px;
}
.chip.on {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(74, 158, 255, 0.12);
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
.ed-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>