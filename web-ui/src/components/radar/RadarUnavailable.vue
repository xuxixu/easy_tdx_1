<script setup lang="ts">
// 分区无数据源时的占位块。
//
// 为什么要有它，而不是让页面留空或崩掉：实算构建会把拿不到数据的分区写成
// null（期权链、基本面、国会持仓、新闻…），此时最诚实的做法是**说明为什么空**
// ——「留空」会被读成「今天没信号」，「沿用旧值」会被读成「这些数字是真的」，
// 两者都是误导。
//
// 块内直接给出 meta.degraded 里登记的原因，读者不必去翻构建日志。
defineProps<{
  /** 分区名，需与 meta.degraded 的键一致 */
  section: string
  /** 该分区的中文名，用于标题 */
  title: string
  /** meta.degraded 里登记的原因 */
  reason?: string
}>()
</script>

<template>
  <div class="na">
    <div class="na-head">
      <span class="na-title">{{ title }}</span>
      <span class="na-badge">数据源不可用</span>
    </div>
    <p class="na-reason">{{ reason ?? '本分区依赖的数据源当前不可达，已留空而非沿用旧值。' }}</p>
  </div>
</template>

<style scoped>
.na {
  padding: 14px;
  background: var(--rd-panel);
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
}
.na-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.na-title {
  font-size: 13px;
  font-weight: 600;
}
.na-badge {
  padding: 1px 6px;
  border-radius: 2px;
  background: var(--rd-amber-dim);
  font-family: var(--font-mono);
  font-size: 9.5px;
  color: var(--rd-amber);
}
.na-reason {
  margin-top: 6px;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--text-dim);
}
</style>