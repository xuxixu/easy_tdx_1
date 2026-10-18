<script setup lang="ts">
// 页面骨架：统一的「标题 + 描述 + 右侧操作 + 可选工具条 + 内容区」。
//
// 为什么要有这一层：22 个页面此前各写各的顶部结构——有的 `<h2>` 跟一排按钮挤在
// 一行（.toolbar），有的是「左标题 + 副标题 / 右操作」（.page-header），padding
// 也从 14/16 到 16/20/32 各不相同。同一套产品里翻页时标题位置会跳。
//
// 这里只统一「骨架」，不碰页面内部布局：内容区由调用方自由组织。
// 三个插槽：
//   #actions —— 标题右侧的主操作（新建 / 刷新 / 导出）
//   #toolbar —— 标题下方的一排筛选/切换（tab、下拉、搜索）
//   默认插槽 —— 内容
defineProps<{
  /** 页面标题（h2，全站 17px 统一） */
  title: string
  /** 一行说明，通常由页面已有的统计文案传入 */
  desc?: string
  /** 内容区是否自身滚动；需要整页不滚（内部各自滚）的页面传 false */
  bodyScroll?: boolean
}>()
</script>

<template>
  <div class="page-shell">
    <header class="ps-head">
      <div class="ps-titles">
        <h2>{{ title }}</h2>
        <p v-if="desc" class="ps-desc">{{ desc }}</p>
      </div>
      <div v-if="$slots.actions" class="ps-actions">
        <slot name="actions" />
      </div>
    </header>

    <div v-if="$slots.toolbar" class="ps-toolbar">
      <slot name="toolbar" />
    </div>

    <div class="ps-body" :class="{ 'ps-body-scroll': bodyScroll !== false }">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.page-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: var(--sp-4);
  gap: var(--sp-3);
}
.ps-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-4);
  flex-shrink: 0;
}
.ps-titles {
  min-width: 0;
}
.ps-desc {
  margin-top: 3px;
  font-size: var(--fs-sm);
  line-height: 1.5;
  color: var(--text-dim);
}
.ps-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-shrink: 0;
}
.ps-toolbar {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex-wrap: wrap;
  flex-shrink: 0;
}
.ps-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  /* 内容区常见「多个卡片竖排」，统一间距，免得各页自己写 margin-bottom */
  gap: var(--sp-3);
}
.ps-body.ps-body-scroll {
  overflow-y: auto;
}
</style>
