<template>
  <CommonPage title="审计日志" subtitle="追踪管理端的操作记录">
    <template #action>
      <n-button type="primary" @click="load">查询</n-button>
    </template>

    <div class="log-filters">
      <n-input v-model:value="filters.keyword" placeholder="关键词（路径/用户名）" clearable style="width: 200px" />
      <n-input v-model:value="filters.resource" placeholder="资源" clearable style="width: 140px" />
      <n-input v-model:value="filters.action" placeholder="动作" clearable style="width: 120px" />
      <n-date-picker v-model:value="range" type="datetimerange" clearable style="width: 380px" />
    </div>

    <n-data-table
      :columns="columns"
      :data="list"
      :loading="loading"
      :bordered="false"
      :scroll-x="1500"
      size="small"
    />

    <n-pagination
      v-model:page="page"
      :page-count="pageCount"
      :page-size="pageSize"
      class="pager"
      @update:page="load"
    />
  </CommonPage>
</template>

<script setup>
import { computed, h, onMounted, reactive, ref } from 'vue'
import { NTag, NTooltip, useMessage } from 'naive-ui'
import CommonPage from '@/components/CommonPage.vue'
import { auditLogsApi } from '@/api/audit-logs'

const message = useMessage()
const list = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const range = ref(null)

const filters = reactive({
  keyword: null,
  resource: null,
  action: null,
})

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

function statusTag(code) {
  if (!code) return h('span', { style: 'color:#ccc' }, '-')
  const type = code < 300 ? 'success' : code < 400 ? 'info' : code < 500 ? 'warning' : 'error'
  return h(NTag, { type, size: 'small' }, { default: () => String(code) })
}

const columns = [
  { title: '时间', key: 'occurredAt', width: 170 },
  {
    title: '操作人',
    key: 'username',
    width: 120,
    render: (row) => row.username || (row.userId ? `#${row.userId}` : '-'),
  },
  {
    title: '方法',
    key: 'method',
    width: 80,
    render: (row) => (row.method ? h(NTag, { size: 'small' }, { default: () => row.method }) : '-'),
  },
  { title: '资源', key: 'resource', width: 120, render: (row) => row.resource || '-' },
  { title: '动作', key: 'action', width: 100, render: (row) => row.action || '-' },
  {
    title: '对象 ID',
    key: 'resourceId',
    width: 110,
    ellipsis: { tooltip: true },
    render: (row) => row.resourceId || '-',
  },
  { title: '状态', key: 'statusCode', width: 80, render: (row) => statusTag(row.statusCode) },
  { title: 'IP', key: 'ip', width: 130, ellipsis: { tooltip: true }, render: (row) => row.ip || '-' },
  {
    title: '路径',
    key: 'path',
    ellipsis: { tooltip: true },
    render: (row) =>
      h(NTooltip, null, {
        trigger: () => h('code', { style: 'font-size:11px' }, row.path || '-'),
        default: () => `请求 ID: ${row.requestId || '-'}｜UA: ${row.userAgent || '-'}`,
      }),
  },
]

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, pageSize: pageSize.value }
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== null && value !== '') params[key] = value
    })
    // n-date-picker 给的是毫秒时间戳，后端要 ISO 8601
    if (range.value?.length === 2) {
      params.startAt = new Date(range.value[0]).toISOString()
      params.endAt = new Date(range.value[1]).toISOString()
    }
    const resp = await auditLogsApi.list(params)
    list.value = resp.data?.items || []
    total.value = resp.data?.total || 0
  } catch (e) {
    message.error(e.message || '加载审计日志失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.log-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
