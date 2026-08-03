<template>
  <div class="flex flex-col h-full min-h-0">
    <ElCard size="small" class="mb-3">
      <div class="flex flex-wrap items-center gap-2">
        <ElInput
          v-if="searchable"
          v-model="keyword"
          :placeholder="searchPlaceholder"
          clearable
          style="width: 200px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />

        <template v-for="f in filterFields" :key="f.key">
          <ElSelect
            v-if="f.type === 'select'"
            v-model="filterValues[f.key]"
            :placeholder="f.placeholder"
            clearable
            style="width: 140px"
            @change="handleSearch"
          >
            <ElOption
              v-for="opt in f.options"
              :key="String(opt.value)"
              :label="opt.label"
              :value="opt.value"
            />
          </ElSelect>
        </template>

        <ElButton v-auth="'threat_intel.write'" type="primary" @click="$emit('add')">新增</ElButton>
        <ElButton v-auth="'threat_intel.write'" @click="triggerImport">批量导入</ElButton>
        <ElButton v-if="exportable" @click="handleExport">导出全部</ElButton>
      </div>
    </ElCard>

    <ElAlert v-if="loadError" type="error" :closable="false" class="mb-3" :title="loadError">
      <template #default>
        <ElButton link type="primary" @click="fetchData()">重试</ElButton>
      </template>
    </ElAlert>

    <div class="table-wrap flex-1 min-h-0">
      <ArtTable
        :loading="loading"
        :data="list"
        :columns="columns"
        :pagination="pagination"
        :show-table-header="false"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </div>

    <input ref="fileInputRef" type="file" accept=".csv" style="display:none" @change="onFileChange" />

    <!-- 数据来源卡片插槽，固定在 Tab 底部 -->
    <slot name="footer" />
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import {
  fetchGetIntelList,
  fetchImportIntelCsv,
  fetchExportIntel,
  type IntelListParams
} from '@/api/threat-intel'
import type { ColumnOption } from '@/types/component'

export interface FilterField {
  key: string
  type: 'select'
  placeholder: string
  options: { label: string; value: string | number | boolean }[]
}

interface Props {
  intelType: string
  columns: ColumnOption<any>[]
  filterFields?: FilterField[]
  searchable?: boolean
  searchPlaceholder?: string
  exportable?: boolean
  extraParams?: Record<string, unknown>
}

interface Emits {
  (e: 'add'): void
  (e: 'imported'): void
  /** 列表加载完成，父级可据此拉取附加信息（如 MMDB 覆盖对比） */
  (e: 'loaded', rows: any[]): void
}

const props = withDefaults(defineProps<Props>(), {
  filterFields: () => [],
  searchable: true,
  searchPlaceholder: '搜索关键词',
  exportable: false,
  extraParams: () => ({})
})

const emit = defineEmits<Emits>()

const loading = ref(false)
const list = ref<any[]>([])
const keyword = ref('')
const filterValues = reactive<Record<string, string | number | boolean | undefined>>({})
const fileInputRef = ref<HTMLInputElement>()

// 字段名需与 ArtTable 的 PaginationConfig 契约一致（current / size / total）
const pagination = reactive({
  current: 1,
  size: 20,
  total: 0,
  pageSizes: [20, 50, 100]
})

const loadError = ref('')

async function fetchData() {
  loading.value = true
  loadError.value = ''
  try {
    const params: IntelListParams = {
      page: pagination.current,
      page_size: pagination.size,
      ...props.extraParams
    }
    if (keyword.value) params.keyword = keyword.value
    for (const [k, v] of Object.entries(filterValues)) {
      if (v !== '' && v !== null && v !== undefined) params[k] = v
    }
    const res = await fetchGetIntelList(props.intelType, params)
    list.value = res?.items ?? []
    pagination.total = res?.total ?? 0
    emit('loaded', list.value)
  } catch (err) {
    list.value = []
    pagination.total = 0
    loadError.value = '情报数据加载失败，请稍后重试'
    console.error('加载情报列表失败:', err)
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.current = 1
  fetchData()
}

function handleSizeChange(size: number) {
  pagination.size = size
  pagination.current = 1
  fetchData()
}

function handleCurrentChange(page: number) {
  pagination.current = page
  fetchData()
}

function triggerImport() {
  fileInputRef.value?.click()
}

async function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const res = await fetchImportIntelCsv(props.intelType, file)
    ElMessage.success(`导入成功：${res.imported} 条`)
    emit('imported')
    fetchData()
  } catch {
    ElMessage.error('导入失败，请检查文件格式')
  } finally {
    if (fileInputRef.value) fileInputRef.value.value = ''
  }
}

async function handleExport() {
  try {
    const blob = await fetchExportIntel(props.intelType)
    const url = URL.createObjectURL(blob as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `intel-${props.intelType}-${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('导出失败')
  }
}

defineExpose({ fetchData, handleSearch })

onMounted(fetchData)
</script>

<style scoped>
/* ArtTable 的 .el-table 自带 10px 上边距用于隔开 ArtTableHeader；
   这里没有 header（show-table-header=false），该边距不计入高度换算，会顶掉分页器 */
.table-wrap :deep(.el-table) {
  margin-top: 0;
}
</style>
