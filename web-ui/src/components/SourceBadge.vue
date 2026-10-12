<script setup lang="ts">
// 数据源徽标：tdx=实时，ak=日级（收盘后），sina=延时15分钟，qq=快照。
//
// 取数优先级是 服务器 → 免费接口 → 报错；免费接口的数据天然有延时，
// 必须明确标出来，否则用户会把延时价当实时价用。
import { computed } from 'vue'

const props = defineProps<{ source?: string }>()

const meta = computed(() => {
  switch (props.source) {
    case 'tdx':
      return { label: '实时', cls: 'live', title: '通达信服务器实时行情' }
    case 'ak':
      return { label: '日级', cls: 'eod', title: 'AkShare 日级历史（收盘后更新）' }
    case 'sina':
      return { label: '延时15′', cls: 'delayed', title: '新浪免费接口，约延时15分钟' }
    case 'qq':
      return { label: '快照', cls: 'snapshot', title: '腾讯快照（仅最新值）' }
    default:
      return null
  }
})
</script>

<template>
  <span v-if="meta" class="src-badge" :class="meta.cls" :title="meta.title">{{ meta.label }}</span>
</template>

<style scoped>
.src-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  border: 1px solid var(--border);
  color: var(--text-dim);
  white-space: nowrap;
}
.src-badge.live {
  color: var(--up);
  border-color: var(--up);
}
.src-badge.delayed {
  color: var(--warn);
  border-color: var(--warn);
}
.src-badge.eod,
.src-badge.snapshot {
  color: var(--text-dim);
}
</style>