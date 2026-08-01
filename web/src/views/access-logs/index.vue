<template>
  <CommonPage title="访问日志" subtitle="查询决策事件与命中记录">
    <template #action>
      <n-select v-model:value="appId" :options="appOptions" placeholder="选择应用" style="width: 180px" />
      <n-button type="primary" @click="load">查询</n-button>
    </template>

    <div class="log-filters">
      <n-input v-model:value="filters.requestId" placeholder="请求 ID" clearable style="width: 180px" />
      <n-input v-model:value="filters.ip" placeholder="IP" clearable style="width: 140px" />
      <n-select
        v-model:value="filters.verdict"
        :options="verdictFilterOptions"
        placeholder="裁决"
        clearable
        style="width: 130px"
      />
      <n-select
        v-model:value="filters.mechanism"
        :options="mechanismFilterOptions"
        placeholder="机制"
        clearable
        style="width: 150px"
      />
      <n-select
        v-model:value="filters.decidedBy"
        :options="decidedByFilterOptions"
        placeholder="处置来源"
        clearable
        style="width: 150px"
      />
      <n-select
        v-model:value="filters.deviceType"
        :options="deviceTypeOptions"
        placeholder="设备类型"
        clearable
        style="width: 130px"
      />
      <n-select
        v-model:value="filters.isBot"
        :options="botOptions"
        placeholder="是否爬虫"
        clearable
        style="width: 120px"
      />
    </div>

    <n-data-table
      :columns="columns"
      :data="list"
      :loading="loading"
      :bordered="false"
      :scroll-x="1800"
      size="small"
    />
  </CommonPage>
</template>

<script setup>
import { h, onMounted, reactive, ref } from 'vue'
import { NTag, NTooltip, useMessage } from 'naive-ui'
import CommonPage from '@/components/CommonPage.vue'
import {
  DECIDED_BY_LABELS,
  MECHANISM_OPTIONS,
  MECHANISM_TAGS,
  VERDICT_OPTIONS,
  VERDICT_TAGS,
} from '../rules/utils/dispositionDefs'
import { appsApi } from '@/api/apps'
import { accessLogsApi } from '@/api/access-logs'

const message = useMessage()
const appId = ref(null)
const appOptions = ref([])
const list = ref([])
const loading = ref(false)

const filters = reactive({
  requestId: null,
  ip: null,
  verdict: null,
  mechanism: null,
  decidedBy: null,
  deviceType: null,
  isBot: null,
})

const verdictFilterOptions = VERDICT_OPTIONS.map((o) => ({ label: o.label, value: o.value }))
const mechanismFilterOptions = MECHANISM_OPTIONS.map((o) => ({ label: o.label, value: o.value }))
const decidedByFilterOptions = Object.entries(DECIDED_BY_LABELS).map(([value, label]) => ({
  label,
  value,
}))
const deviceTypeOptions = ['desktop', 'mobile', 'tablet', 'bot', 'unknown'].map((v) => ({
  label: v,
  value: v,
}))
const botOptions = [
  { label: '仅爬虫', value: true },
  { label: '仅真人', value: false },
]

function tag(type, text) {
  return h(NTag, { type: type || 'default', size: 'small' }, { default: () => text })
}

const columns = [
  {
    title: '请求ID',
    key: 'request_id',
    width: 130,
    ellipsis: { tooltip: true },
    render: (row) => h('code', { style: 'font-size:11px' }, row.request_id || '-'),
  },
  { title: 'IP', key: 'ip', width: 130, ellipsis: { tooltip: true } },
  {
    title: '地区',
    key: 'country',
    width: 70,
    render: (row) => row.country || '-',
  },
  {
    title: 'ASN',
    key: 'asn',
    width: 80,
    render: (row) => (row.asn ? `AS${row.asn}` : '-'),
  },
  {
    title: '网络类型',
    key: 'connection_type',
    width: 100,
    render: (row) => {
      const map = { datacenter: 'warning', mobile: 'info', residential: 'success' }
      return row.connection_type ? tag(map[row.connection_type], row.connection_type) : '-'
    },
  },
  {
    title: '设备',
    key: 'device_type',
    width: 150,
    render: (row) => {
      if (!row.device_type && !row.os_name) return '-'
      const label = [row.device_type, row.os_name, row.browser_name].filter(Boolean).join(' / ')
      return h(NTooltip, null, {
        trigger: () => h('span', { style: 'font-size:12px' }, label),
        default: () => row.user_agent || label,
      })
    },
  },
  {
    title: '爬虫',
    key: 'is_bot',
    width: 130,
    render: (row) => {
      if (!row.is_bot) return h('span', { style: 'color:#ccc' }, '-')
      const text = row.crawler_vendor || row.crawler_category || 'bot'
      return tag('warning', text)
    },
  },
  {
    title: '裁决',
    key: 'verdict',
    width: 90,
    render: (row) => tag(VERDICT_TAGS[row.verdict], row.verdict || '-'),
  },
  {
    title: '机制',
    key: 'mechanism',
    width: 110,
    render: (row) => tag(MECHANISM_TAGS[row.mechanism], row.mechanism || '-'),
  },
  {
    title: 'HTTP',
    key: 'http_status',
    width: 70,
    render: (row) => row.http_status || '-',
  },
  {
    title: '处置来源',
    key: 'decided_by',
    width: 120,
    render: (row) => {
      const label = DECIDED_BY_LABELS[row.decided_by] || row.decided_by || '-'
      return h(NTooltip, null, {
        trigger: () => h('span', { style: 'font-size:12px' }, label),
        default: () =>
          `阶段: ${row.decided_stage || '-'}｜规则: ${row.decided_rule_id || '-'}｜${row.reason || ''}`,
      })
    },
  },
  { title: '分数', key: 'score', width: 70 },
  {
    title: '自愈',
    key: 'evercookie_restore',
    width: 70,
    render: (row) => (row.evercookie_restore ? tag('error', '是') : h('span', { style: 'color:#ccc' }, '-')),
  },
  {
    title: '影子',
    key: 'shadow_rule_ids',
    width: 80,
    render: (row) => {
      const ids = row.shadow_rule_ids || []
      return ids.length ? tag('info', `${ids.length} 条`) : h('span', { style: 'color:#ccc' }, '-')
    },
  },
  {
    title: '耗时',
    key: 'decision_cost_ms',
    width: 80,
    render: (row) => `${row.decision_cost_ms ?? 0}ms`,
  },
  { title: '路径', key: 'path', ellipsis: { tooltip: true } },
  { title: '时间', key: 'occurred_at', width: 170 },
]

async function loadApps() {
  const resp = await appsApi.list({ page: 1, pageSize: 100 })
  appOptions.value = (resp.data?.items || []).map((a) => ({ label: a.name, value: a.id }))
  if (!appId.value && appOptions.value[0]) appId.value = appOptions.value[0].value
}

async function load() {
  if (!appId.value) return
  loading.value = true
  try {
    // 只传有值的过滤项，避免空串被后端当作有效条件
    const params = { appId: appId.value, page: 1, pageSize: 100 }
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== null && value !== '') params[key] = value
    })
    const resp = await accessLogsApi.list(params)
    list.value = resp.data?.items || []
  } catch (e) {
    message.error(e.message || '加载访问日志失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadApps()
  await load()
})
</script>

<style scoped>
.log-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
</style>
