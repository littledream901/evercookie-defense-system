<!-- 访问日志页面 -->
<template>
  <div class="art-full-height access-logs-page">
    <div class="mb-3">
      <h2 class="text-lg font-medium text-g-900">访问日志</h2>
      <p class="mt-1 text-sm text-g-600">网站访问访客日志列表</p>
    </div>

    <!-- 顶部提示横幅 -->
    <ElAlert type="info" :closable="false" class="access-banner mb-3" show-icon>
      <template #title>
        <span>
          由于网站访问记录数据量巨大，默认列表数据会缓存 10 秒，并且只显示当前周（<span
            class="banner-date-range"
          >{{ weekRange }}</span>）最新的 5000 条记录，但不限搜索条件。查询前 30 天内的数据，可以通过搜索条件【记录日期】进行筛选。
        </span>
      </template>
    </ElAlert>

    <AccessLogSearch
      v-show="showSearchBar"
      v-model="searchForm"
      @search="handleSearch"
      @reset="handleReset"
    />

    <ElCard class="art-table-card" :style="{ 'margin-top': showSearchBar ? '12px' : '0' }">
      <ArtTableHeader
        v-model:columns="columnChecks"
        v-model:showSearchBar="showSearchBar"
        :loading="loading"
        @refresh="refreshData"
      >
        <template #left>
          <ElSpace wrap>
            <ElDivider direction="vertical" />
            <span class="text-xs text-g-500">实时刷新</span>
            <ElSwitch v-model="realtimeEnabled" size="small" />
            <ElSelect
              v-if="realtimeEnabled"
              v-model="realtimeInterval"
              size="small"
              style="width: 80px"
              @change="restartInterval"
            >
              <ElOption label="5s" :value="5000" />
              <ElOption label="10s" :value="10000" />
              <ElOption label="30s" :value="30000" />
            </ElSelect>
            <ElTag v-if="realtimeEnabled" type="success" size="small" effect="plain">刷新中</ElTag>
          </ElSpace>
        </template>
      </ArtTableHeader>

      <ArtTable
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      >
        <!-- 1. 访客编号：域名 / request_id / 时间 -->
        <template #request_id="{ row }">
          <div class="cell-stack">
            <span class="cell-line cell-domain">
              {{ row.host || extractDomain(row.referer) || '-' }}
            </span>
            <span class="cell-line text-code">{{ row.request_id || '-' }}</span>
            <span class="cell-line cell-time">{{ fmtTime(row.occurred_at) }}</span>
          </div>
        </template>

        <!-- 2. 访客访问网址：host + path 拼出可点击的完整地址 -->
        <template #path="{ row }">
          <a
            v-if="row.host"
            :href="`https://${row.host}${row.path || '/'}`"
            target="_blank"
            class="cell-link"
            :title="`https://${row.host}${row.path || '/'}`"
          >
            {{ row.path || '/' }}
          </a>
          <span v-else-if="row.path" class="cell-line text-secondary" :title="row.path">
            {{ row.path }}
          </span>
          <span v-else class="text-placeholder">-</span>
        </template>

        <!-- 3. 访问状态（居中） -->
        <template #verdict="{ row }">
          <div class="cell-center">
            <template v-if="row.verdict === 'hostile'">
              <span class="verdict-block">拦截</span>
              <div class="verdict-sub">
                <span v-if="row.decided_by" class="verdict-source">{{ DECIDED_BY_LABELS[row.decided_by] || row.decided_by }}</span>
                <span v-if="fmtReason(row.reason)" class="verdict-reason-text">{{ fmtReason(row.reason) }}</span>
              </div>
            </template>
            <template v-else-if="row.verdict === 'suspect'">
              <span class="verdict-warn">可疑</span>
              <div class="verdict-sub">
                <span v-if="row.decided_by" class="verdict-source">{{ DECIDED_BY_LABELS[row.decided_by] || row.decided_by }}</span>
                <span v-if="fmtReason(row.reason)" class="verdict-reason-text">{{ fmtReason(row.reason) }}</span>
              </div>
            </template>
            <template v-else>
              <span class="verdict-pass">放行</span>
            </template>
          </div>
        </template>

        <!-- 4. 处置机制（居中） -->
        <template #mechanism="{ row }">
          <div class="cell-center">
            <ElTag :type="MECHANISM_TAGS[row.mechanism] || 'info'" size="small" class="mechanism-tag">
              {{ MECHANISM_LABELS[row.mechanism] || row.mechanism || '-' }}
            </ElTag>
            <div class="mech-meta">
              <span :class="scoreClass(row.score)">评分: {{ row.score != null ? row.score : '-' }}</span>
              <span class="mech-cost">耗时: {{ row.decision_cost_ms != null ? `${row.decision_cost_ms}ms` : '-' }}</span>
            </div>
          </div>
        </template>

        <!-- 5. 访问来路 -->
        <template #referer="{ row }">
          <span v-if="row.referer" class="cell-line text-secondary">{{ row.referer }}</span>
          <span v-else class="text-placeholder">-</span>
        </template>

        <!-- 6. IP 地址 -->
        <template #ip="{ row }">
          <div class="cell-stack">
            <span class="cell-line text-code">{{ row.ip || '-' }}</span>
            <span class="cell-line text-secondary">
              {{ [row.country, row.ip_type].filter(Boolean).join(' / ') || '-' }}
            </span>
          </div>
        </template>

        <!-- 7. IP 详情 -->
        <template #asn="{ row }">
          <template v-if="row.asn || row.connection_type">
            <ElTooltip placement="top" :show-after="200">
              <template #content>
                <div class="tooltip-stack">
                  <div v-if="row.asn">ASN：AS{{ row.asn }}</div>
                  <div v-if="row.connection_type">网络类型：{{ row.connection_type }}</div>
                  <div v-if="row.ip_type">IP 类型：{{ row.ip_type }}</div>
                  <div v-if="row.is_vpn">VPN：是</div>
                  <div v-if="row.is_proxy">代理：是</div>
                </div>
              </template>
              <span class="cell-isp">{{ row.asn ? `AS${row.asn}` : row.connection_type }}</span>
            </ElTooltip>
          </template>
          <span v-else class="text-placeholder">-</span>
        </template>

        <!-- 8. 设备系统 -->
        <template #device_type="{ row }">
          <div class="cell-stack">
            <span class="cell-line">类型: {{ DEVICE_TYPE_LABELS[row.device_type] || row.device_type || '-' }}</span>
            <span class="cell-line">系统: {{ row.os || '-' }}</span>
            <span class="cell-line">
              设备:
              <ElTooltip v-if="row.device_id" placement="top" :show-after="300">
                <template #content>
                  <div style="word-break: break-all">{{ row.device_id }}</div>
                </template>
                <span class="text-code">{{ row.device_id.slice(0, 8) }}</span>
              </ElTooltip>
              <span v-else class="text-placeholder">-</span>
            </span>
          </div>
        </template>

        <!-- 9. 客户端信息 -->
        <template #browser="{ row }">
          <div class="cell-stack">
            <span class="cell-line">类型: 浏览器</span>
            <span class="cell-line">名称: {{ row.browser || '-' }}</span>
            <span class="cell-line">
              <ElTooltip v-if="row.user_agent" placement="top" :show-after="300">
                <template #content>
                  <div style="max-width: 400px; word-break: break-all">{{ row.user_agent }}</div>
                </template>
                <span class="cell-ua">UA</span>
              </ElTooltip>
              <span v-else class="text-placeholder">-</span>
            </span>
          </div>
        </template>

        <!-- 10. 客户端语言 -->
        <template #accept_language="{ row }">
          <template v-if="row.accept_language">
            <div class="lang-cell">
              <div class="lang-primary">
                <ElTag type="danger" size="small" effect="dark" class="lang-preferred-tag">首选</ElTag>
                <span class="lang-primary-text">{{ primaryLang(row.accept_language) }}</span>
              </div>
              <div class="lang-others">{{ otherLangs(row.accept_language) }}</div>
            </div>
          </template>
          <span v-else class="text-placeholder">-</span>
        </template>

        <!-- 操作 -->
        <template #_actions="{ row }">
          <ElButton size="small" type="primary" link @click="openDetail(row.request_id)">
            详情
          </ElButton>
        </template>
      </ArtTable>
    </ElCard>

    <LogDetailDrawer
      v-model:visible="detailVisible"
      :request-id="detailRequestId"
      :site-id="siteId"
    />
  </div>
</template>

<script setup lang="ts">
  import { ElButton, ElTag, ElTooltip, ElDivider, ElMessage } from 'element-plus'
  import { useIntervalFn } from '@vueuse/core'
  import { useTable } from '@/hooks/core/useTable'
  import { fetchGetAccessLogList } from '@/api/logs'
  import AccessLogSearch from './modules/access-log-search.vue'
  import LogDetailDrawer from './modules/log-detail-drawer.vue'
  import { DEVICE_TYPE_OPTIONS, pruneParams, recentLocalRange } from '@/constants/fangyu'
  import { MECHANISM_TAGS, DECIDED_BY_LABELS } from '@/constants/disposition'

  defineOptions({ name: 'AccessLogs' })

  const MECHANISM_LABELS: Record<string, string> = {
    pass: '放行', serve_alt: '替代内容', redirect: '跳转',
    challenge: '人机挑战', deny: '拒绝', not_found: '假装404'
  }

  function fmtTime(raw?: string | null): string {
    if (!raw) return '-'
    return raw.replace('T', ' ').replace(/\.\d+.*$/, '').replace('Z', '') || '-'
  }

  function fmtReason(reason?: string | null): string {
    if (!reason) return ''
    const parts = reason.split(':')
    for (let i = parts.length - 1; i >= 0; i--) {
      const p = parts[i].trim()
      if (p && !/^[a-z_]+$/.test(p)) return p
    }
    return parts[parts.length - 1] || reason
  }

  /** Accept-Language 首选语言（第一个） */
  function primaryLang(raw?: string | null): string {
    if (!raw) return '-'
    const first = raw.split(',')[0]
    return first.split(';')[0].trim()
  }

  /** 其余语言列表 */
  function otherLangs(raw?: string | null): string {
    if (!raw) return ''
    const parts = raw.split(',').map((s) => s.split(';')[0].trim())
    return parts.slice(1).join('、')
  }

  type AccessLogSearchFormParams = {
    requestId?: string; ip?: string; verdict?: string; mechanism?: string
    decidedBy?: string; deviceType?: string; isBot?: boolean; daterange?: string[]
  }

  const DEVICE_TYPE_LABELS: Record<string, string> = {}
  DEVICE_TYPE_OPTIONS.forEach((o) => { DEVICE_TYPE_LABELS[o.value] = o.label })

  const weekRange = computed(() => {
    const now = new Date()
    const day = now.getDay()
    const monday = new Date(now)
    monday.setDate(now.getDate() - (day === 0 ? 6 : day - 1))
    const sunday = new Date(monday)
    sunday.setDate(monday.getDate() + 6)
    const fmt = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    return `${fmt(monday)} ~ ${fmt(sunday)}`
  })

  const realtimeEnabled  = ref(false)
  const realtimeInterval = ref(10000)
  const { pause: pauseInterval, resume: resumeInterval } = useIntervalFn(
    () => { refreshData() }, realtimeInterval, { immediate: false }
  )
  function restartInterval() { pauseInterval(); if (realtimeEnabled.value) resumeInterval() }
  watch(realtimeEnabled, (v) => { v ? resumeInterval() : pauseInterval() })
  onDeactivated(pauseInterval)
  onActivated(() => { if (realtimeEnabled.value) resumeInterval() })

  const showSearchBar   = ref(false)
  const detailVisible   = ref(false)
  const detailRequestId = ref('')
  const siteId          = ref<number>()

  function openDetail(requestId: string) {
    detailRequestId.value = requestId
    detailVisible.value   = true
  }

  const searchForm = ref<AccessLogSearchFormParams>({
    requestId: undefined, ip: undefined, verdict: undefined, mechanism: undefined,
    decidedBy: undefined, deviceType: undefined, isBot: undefined, daterange: recentLocalRange(24)
  })

  const {
    columns, columnChecks, data, loading, pagination,
    getData, replaceSearchParams, handleSizeChange, handleCurrentChange, refreshData
  } = useTable({
    core: {
      apiFn: fetchGetAccessLogList,
      apiParams: { page: 1, pageSize: 20 },
      immediate: false,
      columnsFactory: () => [
        { prop: 'request_id',      label: '访客编号',     minWidth: 200, useSlot: true },
        { prop: 'path',            label: '访客访问网址', minWidth: 220, useSlot: true },
        { prop: 'verdict',         label: '访问状态',     width: 160,    useSlot: true, align: 'center' },
        { prop: 'mechanism',       label: '处置机制',     width: 130,    useSlot: true, align: 'center' },
        { prop: 'referer',         label: '访问来路',     minWidth: 150, useSlot: true },
        { prop: 'ip',              label: 'IP 地址',      minWidth: 175, useSlot: true },
        { prop: 'asn',             label: 'IP 详情',      width: 120,    useSlot: true },
        { prop: 'device_type',     label: '设备系统',     width: 145,    useSlot: true },
        { prop: 'browser',         label: '客户端信息',   width: 155,    useSlot: true },
        { prop: 'accept_language', label: '客户端语言',   minWidth: 155, useSlot: true },
        { prop: '_actions',        label: '操作',         width: 70,     fixed: 'right', useSlot: true }
      ]
    }
  })

  function extractDomain(raw?: string | null): string {
    if (!raw) return ''
    try {
      const u = new URL(raw.startsWith('http') ? raw : `https://${raw}`)
      return u.hostname
    } catch { return '' }
  }

  function scoreClass(score?: number | null): string {
    if (score == null) return 'score-na'
    if (score >= 70) return 'score-high'
    if (score >= 30) return 'score-mid'
    return 'score-low'
  }

  const buildParams = (form: AccessLogSearchFormParams) => {
    const { daterange, ...rest } = form
    return pruneParams({
      ...rest, siteId: siteId.value,
      start: daterange?.[0], end: daterange?.[1]
    }) as Partial<Api.Fangyu.AccessLogListParams>
  }

  const handleSearch = (form: AccessLogSearchFormParams) => {
    replaceSearchParams(buildParams(form))
    getData()
  }

  const handleReset = () => {
    searchForm.value = {
      requestId: undefined, ip: undefined, verdict: undefined,
      mechanism: undefined, decidedBy: undefined, deviceType: undefined,
      isBot: undefined, daterange: recentLocalRange(24)
    }
    handleSearch(searchForm.value)
    ElMessage.success('已重置筛选条件，默认展示近 24 小时日志')
  }

  onMounted(() => { handleSearch(searchForm.value) })
</script>

<style scoped>
.access-logs-page { padding: 0; }

/* ── 顶部提示横幅 ── */
.access-banner :deep(.el-alert__title) { font-size: 13px; line-height: 1.7; }
.banner-date-range { color: #e6a23c; font-weight: 500; }

/* ── 通用单元格 ── */
.cell-stack {
  display: flex;
  flex-direction: column;
  gap: 3px;
  line-height: 1.5;
  padding: 2px 0;
}
.cell-line {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  font-size: 12px;
}
.cell-domain  { font-weight: 600; color: #1d2129; font-size: 12px; }
.cell-time    { font-size: 12px; color: #86909c; }
.text-code {
  font-family: 'SF Mono', 'Cascadia Code', Consolas, monospace;
  font-size: 11px;
  color: #409eff;
}
.text-secondary  { color: #606266; font-size: 12px; }
.text-placeholder { color: #c9cdd4; font-size: 12px; }

/* ── 居中列包裹器 ── */
.cell-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 4px;
  padding: 2px 0;
}

/* ── 访问状态 ── */
.verdict-block { color: #f53f3f; font-weight: 700; font-size: 14px; }
.verdict-warn  { color: #ff7d00; font-weight: 700; font-size: 14px; }
.verdict-pass  { color: #00b42a; font-weight: 700; font-size: 14px; }
.verdict-sub {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  line-height: 1.4;
}
.verdict-source      { font-size: 11px; color: #86909c; }
.verdict-reason-text { font-size: 11px; color: #4e5969; }

/* ── 处置机制 ── */
.mechanism-tag { align-self: center; }
.mech-meta {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  font-size: 11px;
  line-height: 1.5;
}
.mech-cost { color: #4e5969; }
.score-high { color: #f53f3f; font-weight: 600; }
.score-mid  { color: #ff7d00; font-weight: 600; }
.score-low  { color: #00b42a; }
.score-na   { color: #86909c; }

/* ── 链接 ── */
.cell-link {
  color: #409eff;
  font-size: 12px;
  word-break: break-all;
  text-decoration: none;
}
.cell-link:hover { text-decoration: underline; }

/* ── IP 详情 hover ── */
.cell-isp {
  color: #606266;
  font-size: 12px;
  cursor: default;
  border-bottom: 1px dashed #c9cdd4;
}
.tooltip-stack { display: flex; flex-direction: column; gap: 3px; font-size: 12px; }

/* ── UA hover ── */
.cell-ua { color: #409eff; font-size: 11px; cursor: pointer; text-decoration: underline dotted; }

/* ── 客户端语言 ── */
.lang-cell { display: flex; flex-direction: column; gap: 4px; padding: 2px 0; }
.lang-primary { display: flex; align-items: center; gap: 5px; }
.lang-preferred-tag { flex-shrink: 0; }
.lang-primary-text  { font-size: 12px; color: #1d2129; font-weight: 500; }
.lang-others { font-size: 11px; color: #86909c; word-break: break-word; }
</style>
