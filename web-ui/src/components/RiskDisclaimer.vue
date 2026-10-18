<script setup lang="ts">
// 风险提示组件：prominent=true 用于语义重点页（AI 解读历史等），
// 默认紧凑样式。文案可通过默认插槽整体替换。
withDefaults(defineProps<{ prominent?: boolean }>(), { prominent: false })
</script>

<template>
  <div v-if="prominent" class="risk prominent">
    <slot>
      <strong>⚠ 风险提示</strong>
      <p>
        本工具提供的全部行情数据、指标计算、回测与扫描结果仅供量化研究与学习，
        不构成任何投资建议、个股推荐或收益承诺。历史表现不代表未来，数据可能存在
        缺失或错误。股市有风险，入市需谨慎，据此操作风险自负。
      </p>
    </slot>
  </div>
  <div v-else class="risk">
    <slot>
      仅供研究学习，不构成投资建议；股市有风险，据此操作风险自负。
    </slot>
  </div>
</template>

<style scoped>
.risk {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.6;
  border-top: 1px solid var(--border);
  padding-top: 6px;
  margin-top: 10px;
}
.risk.prominent {
  background: color-mix(in srgb, var(--warn) 7%, transparent);
  border: 1px solid color-mix(in srgb, var(--warn) 35%, transparent);
  border-radius: var(--radius);
  padding: 10px 12px;
  margin-top: 0;
}
.risk.prominent strong {
  color: var(--warn, var(--warn));
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
}
.risk.prominent p {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.8;
}
</style>
