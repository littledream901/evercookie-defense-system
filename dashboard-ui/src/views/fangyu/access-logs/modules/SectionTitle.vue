<template>
  <div class="section-title">
    <span v-if="icon" class="icon">{{ icon }}</span>
    <span class="text"><slot /></span>
  </div>
</template>

<script setup lang="ts">
  interface Props {
    icon?: string
  }

  defineProps<Props>()
</script>

<style scoped lang="scss">
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: linear-gradient(135deg, #f5f7fa 0%, #f0f2f5 100%);
  border-left: 4px solid #409eff;
  border-radius: 4px;
  
  .icon {
    font-size: 18px;
    line-height: 1;
  }
  
  .text {
    flex: 1;
  }
}
</style>
