<!-- 按钮组件 -->
<template>
  <button
    type="button"
    class="size-8.5 inline-flex flex-cc c-p text-g-600 dark:text-g-800 text-xl rounded tad-300 hover:bg-hover-color"
    :class="{ 'rounded-full': circle }"
    :title="title"
    :aria-label="title"
  >
    <ArtSvgIcon :icon="icon"></ArtSvgIcon>
    <slot></slot>
  </button>
</template>

<script lang="ts" setup>
  defineOptions({ name: 'ArtIconButton' })

  interface Props {
    /** 图标名称 */
    icon: string
    /** 圆角按钮 */
    circle?: boolean
    /** 无障碍名称：纯图标按钮必须提供，否则读屏用户只能听到 "button" */
    title?: string
  }

  withDefaults(defineProps<Props>(), {
    title: '操作'
  })
</script>
