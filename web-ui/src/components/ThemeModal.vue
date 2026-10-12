<script setup lang="ts">
// 主题切换弹窗：顶栏 🎨 图标唤起。点卡片即生效并持久化，弹窗不自动关——
// 留在原地才能横向比较四套配色，确认手再关。
//
// 每张卡片自带一块用「该主题自己的变量」画的色板预览（不是截图），
// 所以新增主题无需维护第二份预览图。
import { onBeforeUnmount, onMounted } from 'vue'

import { THEMES, applyTheme, currentTheme } from '../theme'

const emit = defineEmits<{ close: [] }>()

function pick(id: string) {
  applyTheme(id)
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="modal">
      <h3>🎨 主题</h3>
      <p class="modal-desc">
        选择后立即生效并记住（存 localStorage，下次打开沿用）。
        涨跌红绿是 A 股语义约定，各主题下保持一致，不随主题改变。
      </p>
      <div class="theme-list">
        <button
          v-for="t in THEMES"
          :key="t.id"
          class="theme-card"
          :class="{ active: t.id === currentTheme.id }"
          @click="pick(t.id)"
        >
          <span class="swatch">
            <i class="sw-bg" :style="{ background: t.swatch[0] }" />
            <i class="sw-panel" :style="{ background: t.swatch[1] }" />
            <i class="sw-accent" :style="{ background: t.swatch[2] }" />
            <i
              class="sw-up"
              :style="{ background: t.vars['--up'], borderColor: t.vars['--border'] }"
            />
            <i
              class="sw-down"
              :style="{ background: t.vars['--down'], borderColor: t.vars['--border'] }"
            />
          </span>
          <span class="meta">
            <span class="name">
              {{ t.label }}
              <em v-if="t.id === currentTheme.id" class="cur">当前</em>
            </span>
            <span class="desc">{{ t.desc }}</span>
          </span>
        </button>
      </div>
      <div class="modal-actions">
        <button class="ghost" @click="emit('close')">完成</button>
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
  width: 420px;
  max-width: 92vw;
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-shadow: 0 16px 48px var(--shadow);
}
.modal h3 {
  font-size: 15px;
  font-weight: 600;
}
.modal-desc {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.5;
}
.theme-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.theme-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  text-align: left;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.theme-card:hover {
  border-color: var(--accent);
}
.theme-card.active {
  border-color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent);
}
/* 色板预览：底 → 面板 → 强调 + 一对涨跌色，一眼看出这套主题的气质 */
.swatch {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: repeat(3, 10px);
  grid-template-rows: repeat(2, 10px);
  gap: 3px;
  padding: 4px;
  border-radius: 5px;
  border: 1px solid var(--border);
}
.swatch i {
  display: block;
  border-radius: 2px;
}
.sw-bg {
  grid-row: span 2;
}
.sw-panel {
  grid-column: 2;
}
.sw-accent {
  grid-column: 3;
}
.sw-up {
  grid-column: 2;
  border: 1px solid;
}
.sw-down {
  grid-column: 3;
  border: 1px solid;
}
.meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.name {
  font-size: 13.5px;
  color: var(--text);
  font-weight: 600;
}
.cur {
  margin-left: 6px;
  font-size: 10.5px;
  font-style: normal;
  font-weight: 500;
  color: var(--accent);
}
.desc {
  font-size: 11.5px;
  color: var(--text-dim);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
.modal-actions .ghost {
  font-size: 13px;
  padding: 7px 16px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
}
</style>
