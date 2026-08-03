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
  import { APP_STATUS_OPTIONS } from '@/constants/fangyu'

  type AppSearchFormParams = {
    keyword?: string
    status?: string
    access_mode?: string
  }

  interface Props {
    modelValue: AppSearchFormParams
  }

  interface Emits {
    (e: 'update:modelValue', value: AppSearchFormParams): void
    (e: 'search', params: AppSearchFormParams): void
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
      label: '应用名',
      key: 'keyword',
      type: 'input',
      placeholder: '请输入应用名关键词',
      clearable: true
    },
    {
      label: '状态',
      key: 'status',
      type: 'select',
      props: {
        placeholder: '请选择状态',
        options: APP_STATUS_OPTIONS,
        clearable: true
      }
    },
    {
      label: '接入模式',
      key: 'access_mode',
      type: 'select',
      props: {
        placeholder: '请选择接入模式',
        options: [
          { label: '适配器', value: 'adapter' },
          { label: 'SDK 接入', value: 'sdk' }
        ],
        clearable: true
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
  const handleSearch = async (params: AppSearchFormParams) => {
    await searchBarRef.value.validate()
    emit('search', params)
  }
</script>
