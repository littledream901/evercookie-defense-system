<template>
  <div class="flex-center h-56px border-b border-gray-200 dark:border-gray-700 select-none">
    <div class="i-ion-shield-checkmark text-primary text-24px" />
    <span v-if="!collapsed" class="ml-8px font-semibold text-16px">防御系统</span>
  </div>
</template>

<script setup>
defineProps({ collapsed: Boolean })
</script>
