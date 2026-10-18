<script setup lang="ts">
// 区块骨架：序号 + 中文标题 + 英文小标 + 一句话用途说明 + 内容。
//
// 说明为什么把这一层抽出来：整页 18 个区块的标题区长得完全一样（序号用等宽
// 小字、中文标题粗体、英文小标弱化、说明靠右），逐个区块各写一遍的话，
// 以后改标题样式要动 18 个文件。
defineProps<{
  /** 锚点 id，与顶栏 RADAR_NAV 的 href 对应 */
  id: string
  /** 两位序号，如 "01" */
  index: string
  title: string
  /** 英文小标 */
  en: string
  /** 一句话说明这个区块用来回答什么问题 */
  note?: string
}>()
</script>

<template>
  <section :id="id" class="rd-sec">
    <header class="rd-sec-head">
      <span class="rd-sec-index">{{ index }}</span>
      <h2 class="rd-sec-title">{{ title }}</h2>
      <span class="rd-sec-en">{{ en }}</span>
      <span v-if="note" class="rd-sec-note">{{ note }}</span>
    </header>
    <slot />
  </section>
</template>

<style scoped>
.rd-sec {
  /* 顶栏是 sticky 的，锚点跳转要留出让位高度，否则标题会钻到顶栏底下 */
  scroll-margin-top: 72px;
}
.rd-sec-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 12px;
  margin-bottom: 10px;
  padding-bottom: 7px;
  border-bottom: 1px solid var(--border);
}
.rd-sec-index {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.2em;
  color: var(--rd-cyan);
}
.rd-sec-title {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.rd-sec-en {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.18em;
  color: var(--text-dim);
}
/* 说明靠右并允许换行到下一行，宽屏时与标题同行、窄屏时独占一行 */
.rd-sec-note {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
}
</style>