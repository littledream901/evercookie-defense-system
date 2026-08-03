<template>
  <ArtSearchBar
    ref="searchBarRef"
    v-model="formData"
    :items="formItems"
    @reset="handleReset"
    @search="handleSearch"
  >
  </ArtSearchBar>
</template>

<script setup lang="ts">
  import { USER_STATUS_OPTIONS } from '@/constants/fangyu'

  type SearchParams = Api.Fangyu.UserListParams

  interface Props {
    modelValue: SearchParams
  }

  interface Emits {
    (e: 'update:modelValue', value: SearchParams): void
    (e: 'search', params: SearchParams): void
    (e: 'reset'): void
  }

  const props = defineProps<Props>()
  const emit = defineEmits<Emits>()

  const searchBarRef = ref()

  const formData = computed({
    get: () => props.modelValue,
    set: (val) => emit('update:modelValue', val)
  })

  const formItems = computed(() => [
    {
      label: '关键词',
      key: 'keyword',
      type: 'input',
      props: { placeholder: '用户名 / 邮箱', clearable: true }
    },
    {
      label: '状态',
      key: 'status',
      type: 'select',
      props: {
        placeholder: '请选择状态',
        clearable: true,
        options: USER_STATUS_OPTIONS
      }
    }
  ])

  function handleReset() {
    emit('reset')
  }

  function handleSearch(params: SearchParams) {
    emit('search', params)
  }
</script>
