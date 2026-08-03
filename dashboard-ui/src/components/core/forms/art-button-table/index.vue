<!-- 表格按钮 -->
<template>
  <button
    type="button"
    :class="[
      'inline-flex items-center justify-center min-w-8 h-8 px-2.5 mr-2.5 text-sm c-p rounded-md align-middle',
      'disabled:opacity-50 disabled:!cursor-not-allowed',
      buttonClass
    ]"
    :style="{ backgroundColor: buttonBgColor, color: iconColor }"
    :disabled="disabled"
    :title="accessibleName"
    :aria-label="accessibleName"
    @click="handleClick"
  >
    <ArtSvgIcon :icon="iconContent" />
  </button>
</template>

<script setup lang="ts">
  defineOptions({ name: 'ArtButtonTable' })

  interface Props {
    /** 按钮类型 */
    type?: 'add' | 'edit' | 'delete' | 'more' | 'view'
    /** 按钮图标 */
    icon?: string
    /** 按钮样式类 */
    iconClass?: string
    /** icon 颜色 */
    iconColor?: string
    /** 按钮背景色 */
    buttonBgColor?: string
    /** 无障碍名称：图标按钮必须提供，否则读屏用户只能听到 "button" */
    title?: string
    /** 禁用态：真正阻止点击，而非仅靠样式伪装 */
    disabled?: boolean
  }

  const props = withDefaults(defineProps<Props>(), {
    disabled: false
  })

  const emit = defineEmits<{
    (e: 'click'): void
  }>()

  // 默认按钮配置
  const defaultButtons = {
    add: { icon: 'ri:add-fill', class: 'bg-theme/12 text-theme', label: '新增' },
    edit: { icon: 'ri:pencil-line', class: 'bg-secondary/12 text-secondary', label: '编辑' },
    delete: { icon: 'ri:delete-bin-5-line', class: 'bg-error/12 text-error', label: '删除' },
    view: { icon: 'ri:eye-line', class: 'bg-info/12 text-info', label: '查看' },
    more: { icon: 'ri:more-2-fill', class: '', label: '更多操作' }
  } as const

  // 无障碍名称：优先用调用方传入的 title，否则按类型回退到默认中文标签
  const accessibleName = computed(() => {
    return props.title || (props.type ? defaultButtons[props.type]?.label : '') || '操作'
  })

  // 获取图标内容
  const iconContent = computed(() => {
    return props.icon || (props.type ? defaultButtons[props.type]?.icon : '') || ''
  })

  // 获取按钮样式类
  const buttonClass = computed(() => {
    return props.iconClass || (props.type ? defaultButtons[props.type]?.class : '') || ''
  })

  const handleClick = () => {
    emit('click')
  }
</script>
