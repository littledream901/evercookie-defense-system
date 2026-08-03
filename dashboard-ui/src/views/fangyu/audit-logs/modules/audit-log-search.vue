<template>
  <ArtSearchBar
    ref="searchBarRef"
    v-model="formData"
    :items="formItems"
    :rules="rules"
    @reset="handleReset"
    @search="handleSearch"
  >
  </ArtSearchBar>
</template>

<script setup lang="ts">
  type AuditLogSearchFormParams = {
    keyword?: string
    resource?: string
    action?: string
    daterange?: string[]
  }

  interface Props {
    modelValue: AuditLogSearchFormParams
  }

  interface Emits {
    (e: 'update:modelValue', value: AuditLogSearchFormParams): void
    (e: 'search', params: AuditLogSearchFormParams): void
    (e: 'reset'): void
  }

  const props = defineProps<Props>()
  const emit = defineEmits<Emits>()

  const searchBarRef = ref()

  /**
   * 表单数据双向绑定
   */
  const formData = computed({
    get: () => props.modelValue,
    set: (val) => emit('update:modelValue', val)
  })

  /**
   * 表单校验规则
   */
  const rules = {}

  /**
   * 搜索表单配置项
   */
  const formItems = computed(() => [
    {
      label: '关键词',
      key: 'keyword',
      type: 'input',
      props: { placeholder: '路径 / 用户名', clearable: true }
    },
    {
      label: '资源',
      key: 'resource',
      type: 'input',
      props: { placeholder: '请输入资源', clearable: true }
    },
    {
      label: '动作',
      key: 'action',
      type: 'input',
      props: { placeholder: '请输入动作', clearable: true }
    },
    {
      label: '时间范围',
      key: 'daterange',
      type: 'datetime',
      props: {
        type: 'datetimerange',
        valueFormat: 'YYYY-MM-DDTHH:mm:ss',
        rangeSeparator: '至',
        startPlaceholder: '开始',
        endPlaceholder: '结束',
        style: { width: '100%' }
      }
    }
  ])

  /**
   * 处理重置事件
   */
  const handleReset = () => {
    emit('reset')
  }

  /**
   * 处理搜索事件
   */
  const handleSearch = async (params: AuditLogSearchFormParams) => {
    await searchBarRef.value.validate()
    emit('search', params)
  }
</script>
