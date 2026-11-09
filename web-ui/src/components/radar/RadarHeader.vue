<script setup lang="ts">
// 顶部导航条：品牌 + 观测池说明 + 区块锚点 + 右上角快照状态。
//
// 原站这里是 sticky 顶栏，本页面的区块靠锚点互跳，顶栏必须常驻，
// 否则点完锚点标题就被滚出视口了（各区块的 scroll-margin-top 已配合留位）。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { RADAR_NAV, type RadarMeta, type RadarRebuildState } from '../../data/usRadar'

/** 当前滚动到哪个区块：给导航项做高亮。用 IntersectionObserver 而不是 scroll 事件，
 *  因为一屏内会同时跨过多个区块边界，scroll 算出来的值会来回抖。 */
const active = ref('')
let io: IntersectionObserver | null = null

onMounted(() => {
  const targets = RADAR_NAV.map(([href]) => document.querySelector(href)).filter(
    (el): el is Element => el !== null,
  )
  io = new IntersectionObserver(
    (entries) => {
      // 取当前吸顶带内最靠上的那个区块作为「当前」
      const visible = entries
        .filter((e) => e.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (visible.length > 0) active.value = visible[0].target.id
    },
    // 上边界贴着顶栏下沿、下边界放到视口 1/3 处：区块标题进入这条带子即算「当前」
    { rootMargin: '-72px 0px -66% 0px', threshold: 0 },
  )
  for (const t of targets) io.observe(t)
})

onBeforeUnmount(() => {
  io?.disconnect()
  io = null
})

const props = defineProps<{
  meta: RadarMeta
  /** 唯一的「最新时间戳」：每次加载/重建完成时由页面刷新。 */
  updatedAt?: string
  /** 定时重建状态；null = 后端未提供（纯静态托管），不显示重建控件。 */
  rebuild?: RadarRebuildState | null
  rebuilding?: boolean
  rebuildingMsg?: string
}>()

const emit = defineEmits<{ rebuild: [] }>()

/** 缺源分区数与清单。旧静态快照没有 degraded 字段 → 计数 0，不显示角标。 */
const degradedCount = computed(() => Object.keys(props.meta.degraded ?? {}).length)
const degradedList = computed(() =>
  Object.entries(props.meta.degraded ?? {})
    .map(([k, v]) => `${k}：${v}`)
    .join('\n'),
)

/** 右上角只显示一个「最新时间戳」；状态/口径放进悬停 title，不占版面。 */
const snapTitle = computed(() => {
  const r = props.rebuild
  return [
    `数据基准日：${props.meta.asOf}`,
    `快照构建日：${props.meta.builtAt ?? '—'}`,
    `口径：${props.meta.delay ?? '—'}`,
    r ? `定时重建：${r.enabled ? '启用' : '未启用（EXE/纯静态托管态）'}` : '',
    r ? `重建间隔：${Math.round(r.interval_sec / 60)} 分钟 · 成功 ${r.builds} / 失败 ${r.failures}` : '',
    r?.last_error ? `上次错误：${r.last_error}` : '',
    '（该时间为本次加载/最近一次重建完成时刻；数据是收盘后日线，非盘中实时行情）',
  ]
    .filter(Boolean)
    .join('\n')
})
</script>

<template>
  <header class="rd-head">
    <div class="rd-head-inner">
      <svg class="rd-logo" width="34" height="34" viewBox="0 0 40 40" aria-hidden="true">
        <circle cx="20" cy="20" r="18" fill="none" stroke="var(--rd-cyan)" stroke-width="1.2" />
        <circle cx="20" cy="20" r="12" fill="none" stroke="var(--rd-cyan)" stroke-width="1" opacity=".55" />
        <circle cx="20" cy="20" r="6" fill="none" stroke="var(--rd-cyan)" stroke-width="1" opacity=".35" />
        <line x1="20" y1="20" x2="32" y2="20" stroke="var(--rd-cyan)" stroke-width="1.4" />
        <circle cx="27" cy="14" r="2.4" fill="var(--rd-cyan)" />
      </svg>

      <div class="rd-head-titles">
        <div class="rd-head-row">
          <h1 class="rd-head-title">美股观测雷达</h1>
          <span class="rd-head-en">US MARKET OBSERVATION RADAR</span>
        </div>
        <div class="rd-head-sub">{{ meta.universe }}</div>
      </div>

      <nav class="rd-nav">
        <a
          v-for="[href, label] in RADAR_NAV"
          :key="href"
          :href="href"
          class="rd-nav-item"
          :class="{ on: active === href.slice(1) }"
        >
          {{ label }}
        </a>
      </nav>

      <div class="rd-snap" :title="snapTitle">
        <span
          class="rd-snap-dot"
          :class="{ live: props.rebuild?.enabled, busy: props.rebuilding || props.rebuild?.running }"
        />
        <div class="rd-snap-text">
          <div class="rd-snap-key">{{ props.rebuilding || props.rebuild?.running ? '更新中 UPDATING' : '最新数据 LATEST' }}</div>
          <div class="rd-snap-val">{{ props.updatedAt || meta.asOf }}</div>
          <button
            v-if="props.rebuild?.enabled"
            class="rd-rebuild-btn"
            :disabled="props.rebuilding || props.rebuild.running"
            @click="emit('rebuild')"
          >
            {{ props.rebuilding || props.rebuild.running ? '重建中…' : '重新构建' }}
          </button>
          <span v-if="props.rebuildingMsg" class="rd-rebuild-msg">{{ props.rebuildingMsg }}</span>
        </div>
        <!--
          缺源分区计数：顶栏常驻，读者不必滚到每个区块才发现那里是空的。
          悬停给出完整清单（title 属性），省得为一个说明再开一层浮层。
        -->
        <span
          v-if="degradedCount > 0"
          class="rd-snap-deg"
          :title="degradedList"
        >{{ degradedCount }} 区缺源</span>
      </div>
    </div>
  </header>
</template>

<style scoped>
.rd-head {
  position: sticky;
  top: 0;
  z-index: 50;
  background: color-mix(in srgb, var(--bg) 88%, transparent);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border);
}
.rd-head-inner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 24px;
}
.rd-logo {
  flex-shrink: 0;
}
.rd-head-titles {
  min-width: 0;
}
.rd-head-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.rd-head-title {
  font-size: 17px;
  font-weight: 800;
  letter-spacing: 0.04em;
}
/* 英文全称在窄屏没有意义，藏起来给导航让位 */
.rd-head-en {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.22em;
  color: var(--text-dim);
}
.rd-head-sub {
  margin-top: 2px;
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rd-nav {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
  flex-wrap: wrap;
}
.rd-nav-item {
  padding: 4px 9px;
  border-radius: 3px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  text-decoration: none;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}
.rd-nav-item:hover {
  background: var(--rd-panel2);
  color: var(--rd-cyan);
}
/* 当前区块高亮：让 18 个区块里自己在哪一段一眼可见 */
.rd-nav-item.on {
  background: var(--rd-cyan-dim);
  color: var(--rd-cyan);
}
.rd-snap {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 16px;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: var(--rd-panel);
  flex-shrink: 0;
}
.rd-snap-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--rd-amber);
  animation: rd-pulse 1.6s ease-in-out infinite;
}
@keyframes rd-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.25;
  }
}
.rd-snap-text {
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1.25;
}
.rd-snap-key {
  color: var(--rd-amber);
  letter-spacing: 0.06em;
}
.rd-snap-val {
  color: var(--text-muted);
}
/* 启用定时重建时圆点转青色，与「静态快照」的琥珀色区分 */
.rd-snap-dot.live {
  background: var(--rd-cyan);
}
/* 正在重建：加快脉冲，提示「更新中」 */
.rd-snap-dot.busy {
  background: var(--rd-cyan);
  animation-duration: 0.7s;
}
.rd-rebuild-btn {
  margin-top: 3px;
  padding: 2px 7px;
  border: 1px solid var(--border);
  border-radius: 2px;
  background: var(--rd-panel2);
  color: var(--rd-cyan);
  font-size: 9px;
  cursor: pointer;
}
.rd-rebuild-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.rd-rebuild-msg {
  display: block;
  margin-top: 2px;
  color: var(--text-dim);
  font-size: 9px;
  max-width: 160px;
}
/* 缺源角标：用中性灰而非警示色——缺的是次要分区，不是数据错误 */
.rd-snap-deg {
  padding: 1px 5px;
  border-radius: 2px;
  background: var(--rd-panel2);
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.04em;
  color: var(--text-dim);
  cursor: help;
  white-space: nowrap;
}
@media (max-width: 1100px) {
  .rd-head-en,
  .rd-nav {
    display: none;
  }
}
@media (max-width: 720px) {
  .rd-head-sub,
  .rd-snap {
    display: none;
  }
}
</style>