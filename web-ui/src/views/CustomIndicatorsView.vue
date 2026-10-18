<script setup lang="ts">
// 自定义指标页（系统分组）：用户公式的新增 / 编辑 / 删除。
// 条目与预置同走后端公式引擎；保存后自动出现在各 K 线图标题栏的
// 选择 chips（虚线边框）里。
import PageShell from '../components/PageShell.vue'
import CustomList from '../components/CustomList.vue'
</script>

<template>
  <PageShell
    title="自定义指标"
    desc="在此编写通达信公式并保存为指标（与预置同走后端公式引擎）。保存后到各 K 线图标题栏点选叠加/切换；删除后其在各图的选择态自动清理。桌面大智慧指标转换包（52 个，见 docs/dzh-indicators.md）可用下方「从文件恢复」批量导入。"
  >
    <section class="card custom-card">
      <CustomList />
    </section>
  </PageShell>
</template>

<style scoped>
.card {
  padding: 16px;
}
.custom-card h2 {
  margin: 0 0 8px;
  font-size: 15px;
}
</style>
