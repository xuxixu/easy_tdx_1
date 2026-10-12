<script setup lang="ts">
// 指标选择 chips（各 K 线图标题栏共用）：主图叠加多选 + 副图单选。
// 选项 = 预置（MA/EMA/BOLL/MACD/KDJ/RSI）+ 管理清单里的自定义指标，
// 选择态由父组件传入（全局配置），点选经事件回父组件写回。
import { onUnmounted, ref } from 'vue'

import { loadCustoms, subscribeIndicatorParams, type CustomIndicator } from '../indicatorParams'
import { PRESETS } from '../presetFormulas'

const props = defineProps<{ overlays: string[]; sub: string }>()
const emit = defineEmits<{
  (e: 'toggle-overlay', id: string): void
  (e: 'select-sub', id: string): void
}>()

const customs = ref<CustomIndicator[]>(loadCustoms())
const unsubscribe = subscribeIndicatorParams(() => {
  customs.value = loadCustoms()
})
onUnmounted(unsubscribe)

const overlayPresets = PRESETS.filter((p) => p.kind === 'overlay')
const subPresets = PRESETS.filter((p) => p.kind === 'sub')

function customOverlays(): CustomIndicator[] {
  return customs.value.filter((c) => c.kind === 'overlay')
}

function customSubs(): CustomIndicator[] {
  return customs.value.filter((c) => c.kind === 'sub')
}

function isOn(id: string): boolean {
  return (props.overlays ?? []).includes(id)
}
</script>

<template>
  <span class="ind-group">
    <button
      v-for="o in overlayPresets"
      :key="o.id"
      class="chip"
      :class="{ on: isOn(o.id) }"
      :title="isOn(o.id) ? '点击取消叠加' : '点击叠加'"
      @click="emit('toggle-overlay', o.id)"
    >
      {{ o.short }}
    </button>
    <button
      v-for="c in customOverlays()"
      :key="c.id"
      class="chip chip-custom"
      :class="{ on: isOn(c.id) }"
      :title="`自定义：${c.name}`"
      @click="emit('toggle-overlay', c.id)"
    >
      {{ c.name }}
    </button>
  </span>
  <span class="ind-group">
    <button
      v-for="o in subPresets"
      :key="o.id"
      class="chip"
      :class="{ on: props.sub === o.id }"
      @click="emit('select-sub', o.id)"
    >
      {{ o.short }}
    </button>
    <button
      v-for="c in customSubs()"
      :key="c.id"
      class="chip chip-custom"
      :class="{ on: props.sub === c.id }"
      :title="`自定义：${c.name}`"
      @click="emit('select-sub', c.id)"
    >
      {{ c.name }}
    </button>
    <button class="chip" :class="{ on: props.sub === 'none' }" @click="emit('select-sub', 'none')">
      副图无
    </button>
  </span>
</template>

<style scoped>
.ind-group {
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
.chip-custom {
  border-style: dashed;
}
</style>
