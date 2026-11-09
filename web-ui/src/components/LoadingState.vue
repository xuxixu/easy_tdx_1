<script setup lang="ts">
// 通用加载态：骨架屏微光 + 可选真实进度条 + 淡入过渡。
//
// 全站原先散落的「加载中… / 构建中…」纯文字占位统一换成本组件：
// - 有真实进度（后端 building 返回的 progress，形如 0~1 小数或 "120/800"）
//   时显示百分比进度条，让读者知道还要等多久；
// - 无进度时用骨架屏微光暗示「在动、没卡死」；
// - 容器整块淡入，替换数据时由父级的 v-if 切换自然衔接。
//
// 不改父级的显示/隐藏逻辑，只替换占位内容，因此不改变任何取数行为。
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 加载说明文案。 */
    label?: string
    /** 真实进度：0~1 小数，或 "120/800" 字符串；null/0 = 不确定进度（仅骨架屏）。 */
    progress?: number | string | null
    /** 进度条下方的补充提示（如「首次约 20~70 秒」）。 */
    hint?: string
    /** 骨架条数量。 */
    lines?: number
    /** 紧凑模式：用于卡片内的小块占位（更矮、条更少）。 */
    compact?: boolean
  }>(),
  { label: '加载中…', progress: null, hint: '', lines: 3, compact: false },
)

/** 把 progress 归一成 0~100 百分比；无法解析返回 null（走不确定态）。 */
const pct = computed<number | null>(() => {
  const p = props.progress
  if (p === null || p === undefined || p === '') return null
  if (typeof p === 'number') {
    if (!Number.isFinite(p) || p <= 0) return null
    return Math.min(100, Math.round(p <= 1 ? p * 100 : p))
  }
  // "120/800" → 15；"45%" → 45；纯数字字符串按小数或百分数处理
  const frac = /^(\d+)\s*\/\s*(\d+)$/.exec(p.trim())
  if (frac) {
    const total = Number(frac[2])
    return total > 0 ? Math.min(100, Math.round((Number(frac[1]) / total) * 100)) : null
  }
  const num = Number(p.replace('%', '').trim())
  if (!Number.isFinite(num) || num <= 0) return null
  return Math.min(100, Math.round(num <= 1 ? num * 100 : num))
})

const hasBar = computed(() => pct.value !== null)
</script>

<template>
  <div class="ld" :class="{ 'ld-compact': compact }" role="status" aria-live="polite">
    <!-- 骨架屏：微光横条，暗示内容正在填充 -->
    <div class="ld-skeleton" aria-hidden="true">
      <span
        v-for="i in (compact ? Math.min(lines, 2) : lines)"
        :key="i"
        class="ld-bar"
        :style="{ width: `${92 - (i % 3) * 18}%`, animationDelay: `${(i - 1) * 0.12}s` }"
      />
    </div>

    <!-- 有真实进度时显示百分比进度条 -->
    <div v-if="hasBar" class="ld-progress">
      <div class="ld-track"><div class="ld-fill" :style="{ width: `${pct}%` }" /></div>
      <span class="ld-pct mono">{{ pct }}%</span>
    </div>

    <div v-if="label" class="ld-label">{{ label }}</div>
    <div v-if="hint" class="ld-hint">{{ hint }}</div>
  </div>
</template>

<style scoped>
.ld {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 24px 16px;
  min-height: 120px;
  animation: ld-fade-in 0.28s ease both;
}
.ld-compact {
  min-height: 72px;
  padding: 14px 12px;
  gap: 7px;
}
.ld-skeleton {
  width: 100%;
  max-width: 260px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ld-bar {
  height: 10px;
  border-radius: 3px;
  background: linear-gradient(
    90deg,
    var(--bg-elevated) 25%,
    color-mix(in srgb, var(--text-dim) 22%, var(--bg-elevated)) 50%,
    var(--bg-elevated) 75%
  );
  background-size: 200% 100%;
  animation: ld-shimmer 1.4s ease-in-out infinite;
}
.ld-compact .ld-bar {
  height: 7px;
}
@keyframes ld-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
@keyframes ld-fade-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.ld-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  max-width: 260px;
}
.ld-track {
  flex: 1;
  height: 5px;
  border-radius: 3px;
  background: var(--bg-elevated);
  overflow: hidden;
}
.ld-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--accent);
  transition: width 0.4s ease;
}
.ld-pct {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--accent);
  min-width: 34px;
  text-align: right;
}
.ld-label {
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
}
.ld-hint {
  font-size: 10.5px;
  color: var(--text-dim);
  text-align: center;
}
/* 尊重系统「减少动态效果」偏好 */
@media (prefers-reduced-motion: reduce) {
  .ld,
  .ld-bar {
    animation: none;
  }
  .ld-fill {
    transition: none;
  }
}
</style>
