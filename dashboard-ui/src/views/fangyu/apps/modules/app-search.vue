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
  import { fetchGetApplicationList } from '@/api/apps'

  type AppSearchFormParams = {
    keyword?: string
    appId?: number
    is_active?: boolean
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

  /** 应用下拉选项 */
  const appOptions = ref<Array<{ label: string; value: number }>>([])
  const appLoading = ref(false)

  onMounted(async () => {
    appLoading.value = true
    try {
      const res = await fetchGetApplicationList({ page: 1, pageSize: 100 })
      appOptions.value = (res.items || []).map((app) => ({ label: app.name, value: app.id }))
    } finally {
      appLoading.value = false
    }
  })

  /**
   * 搜索表单配置项
   */
  const formItems = computed(() => [
    {
      label: '站点名 / 域名',
      key: 'keyword',
      type: 'input',
      placeholder: '请输入站点名或域名关键词',
      clearable: true
    },
    {
      label: '所属应用',
      key: 'appId',
      type: 'select',
      props: {
        placeholder: '请选择应用',
        options: appOptions.value,
        loading: appLoading.value,
        filterable: true,
        clearable: true
      }
    },
    {
      label: '启用状态',
      key: 'is_active',
      type: 'select',
      props: {
        placeholder: '请选择启用状态',
        options: [
          { label: '已启用', value: true },
          { label: '已停用', value: false }
        ],
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
