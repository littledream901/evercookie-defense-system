<template>
  <div class="common-page bg-white dark:bg-gray-800 rounded-8px shadow-sm">
    <div v-if="showHeader" class="flex-between px-24px py-16px border-b border-gray-100 dark:border-gray-700">
      <div>
        <div class="text-18px font-semibold">{{ title }}</div>
        <div v-if="subtitle" class="text-13px text-gray-500 mt-4px">{{ subtitle }}</div>
      </div>
      <div class="flex items-center gap-8px">
        <slot name="action" />
      </div>
    </div>
    <div class="p-24px">
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  showHeader: { type: Boolean, default: true },
})
</script>
