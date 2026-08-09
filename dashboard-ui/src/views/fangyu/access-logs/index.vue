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

    <!-- 快速筛选按钮组 -->
    <div class="quick-filters mb-3">
      <ElCheckTag
        v-for="filter in quickFilters"
        :key="filter.label"
        :checked="isFilterActive(filter)"
        @change="toggleQuickFilter(filter)"
        class="quick-filter-tag"
      >
        {{ filter.label }}
      </ElCheckTag>
    </div>


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
            <ElTooltip v-if="row.host" placement="top" :content="row.host" :show-after="300">
              <span class="cell-line cell-domain">
                {{ row.host }}
              </span>
            </ElTooltip>
            <ElTooltip
              v-else-if="extractDomain(row.referer)"
              placement="top"
              :content="extractDomain(row.referer)"
              :show-after="300"
            >
              <span class="cell-line cell-domain">
                {{ extractDomain(row.referer) }}
              </span>
            </ElTooltip>
            <span v-else class="cell-line text-placeholder">-</span>
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

        <!-- 3. 访问状态：裁决（为什么）+ 处置来源 + 原因 -->
        <template #verdict="{ row }">
          <div class="cell-center">
            <ElTag :type="VERDICT_TAGS[row.verdict] || 'info'" size="small">
              {{ VERDICT_LABELS[row.verdict] || row.verdict || '-' }}
            </ElTag>
            <div class="verdict-sub">
              <span v-if="row.decided_by" class="verdict-source">{{ DECIDED_BY_LABELS[row.decided_by] || row.decided_by }}</span>
              <ElTooltip
                v-if="fmtReason(row.reason)"
                placement="top"
                :content="fmtReason(row.reason)"
                :show-after="300"
              >
                <span class="verdict-reason-text">{{ fmtReason(row.reason) }}</span>
              </ElTooltip>
            </div>
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

        <!-- 5. 爬虫识别（简化显示 + Tooltip） -->
        <template #crawler_info="{ row }">
          <div v-if="row.crawler_name || row.crawler_category" class="crawler-detail">
            <!-- 爬虫详细信息 -->
            <template v-if="getCrawlerDetailInfo(row.crawler_name)">
              <ElTooltip placement="top" :show-after="200">
                <template #content>
                  <div class="crawler-tooltip">
                    <div class="tooltip-row">
                      <span class="tooltip-label">厂商：</span>
                      <span>{{ getCrawlerDetailInfo(row.crawler_name)?.vendorName }}</span>
                    </div>
                    <div class="tooltip-row">
                      <span class="tooltip-label">产品：</span>
                      <span>{{ getCrawlerDetailInfo(row.crawler_name)?.product }}</span>
                    </div>
                    <div class="tooltip-row">
                      <span class="tooltip-label">用途：</span>
                      <span>{{ getCrawlerDetailInfo(row.crawler_name)?.purpose }}</span>
                    </div>
                  </div>
                </template>
                <div class="crawler-main">
                  <Icon
                    :icon="getVendorIcon(getCrawlerDetailInfo(row.crawler_name)?.vendor)"
                    class="crawler-vendor-icon"
                  />
                  <div class="crawler-text">
                    <div class="crawler-name">{{ getCrawlerDetailInfo(row.crawler_name)?.displayName }}</div>
                    <ElTag 
                      :type="getCrawlerCategoryType(getCrawlerDetailInfo(row.crawler_name)?.subcategory || '') as any" 
                      size="small"
                      class="crawler-subcategory-tag"
                    >
                      {{ getSubcategoryLabel(getCrawlerDetailInfo(row.crawler_name)?.subcategory || '') }}
                    </ElTag>
                  </div>
                </div>
              </ElTooltip>
            </template>
            
            <!-- 降级显示：只有基础信息 -->
            <template v-else>
              <ElTooltip v-if="row.crawler_name" placement="top" :show-after="200">
                <template #content>
                  <div class="crawler-tooltip">
                    <div class="tooltip-row" v-if="row.crawler_name">
                      <span class="tooltip-label">名称：</span>
                      <span>{{ row.crawler_name }}</span>
                    </div>
                    <div class="tooltip-row" v-if="row.crawler_category">
                      <span class="tooltip-label">类别：</span>
                      <span>{{ getCrawlerCategoryLabel(row.crawler_category) }}</span>
                    </div>
                    <div class="tooltip-row" v-if="row.crawler_vendor">
                      <span class="tooltip-label">厂商：</span>
                      <span>{{ row.crawler_vendor }}</span>
                    </div>
                  </div>
                </template>
                <div class="crawler-basic">
                  <div class="crawler-basic-header">
                    <Icon
                      :icon="getVendorIcon(row.crawler_vendor)"
                      class="crawler-vendor-icon"
                    />
                    <div class="crawler-basic-info">
                      <span class="crawler-name-basic">{{ row.crawler_name }}</span>
                      <div class="crawler-tags">
                        <ElTag :type="getCrawlerCategoryColor(row.crawler_category) as any" size="small" effect="plain">
                          {{ getCrawlerCategoryLabel(row.crawler_category) }}
                        </ElTag>
                      </div>
                    </div>
                  </div>
                </div>
              </ElTooltip>
              <div v-else class="crawler-basic">
                <ElTag :type="getCrawlerCategoryColor(row.crawler_category) as any" size="small" effect="plain">
                  {{ getCrawlerCategoryLabel(row.crawler_category) }}
                </ElTag>
              </div>
            </template>
          </div>
          <span v-else class="text-placeholder">-</span>
        </template>

        <!-- 6. 访问来路：两行显示 + tooltip -->
        <template #referer="{ row }">
          <ElTooltip v-if="row.referer" placement="top" :content="row.referer" :show-after="300">
            <div class="cell-referer">
              {{ row.referer }}
            </div>
          </ElTooltip>
          <span v-else class="text-placeholder">-</span>
        </template>

        <!-- 7. IP 地址（三行堆叠：IP / 国家 / 时间） -->
        <template #ip="{ row }">
          <div class="cell-stack">
            <ElTooltip v-if="row.ip" placement="top" :content="row.ip" :show-after="300">
              <span class="cell-line text-code">{{ row.ip }}</span>
            </ElTooltip>
            <span v-else class="cell-line text-placeholder">-</span>
            <span class="cell-line text-secondary">
              {{ countryName(row.country) || '-' }}
            </span>
            <span class="cell-line cell-time">{{ fmtTime(row.occurred_at) }}</span>
          </div>
        </template>

        <!-- 8. IP 详情（两行：运营商名称 / 归属类型） -->
        <template #asn="{ row }">
          <template v-if="row.asn_org || row.asn || row.connection_type">
            <ElTooltip placement="top" :show-after="200">
              <template #content>
                <div class="tooltip-stack">
                  <div v-if="row.asn_org">名称：{{ row.asn_org }}</div>
                  <div v-if="row.asn">ASN：AS{{ row.asn }}</div>
                  <div v-if="row.connection_type">网络类型：{{ connTypeName(row.connection_type) }}</div>
                  <div v-if="row.ip_type">IP 类型：{{ row.ip_type }}</div>
                  <div v-if="row.is_vpn">VPN：是</div>
                  <div v-if="row.is_proxy">代理：是</div>
                </div>
              </template>
              <div class="cell-stack">
                <span class="cell-line cell-isp">
                  {{ row.asn_org || (row.asn ? `AS${row.asn}` : '-') }}
                </span>
                <span class="cell-line text-secondary">
                  {{ connTypeName(row.connection_type) || '-' }}
                </span>
              </div>
            </ElTooltip>
          </template>
          <span v-else class="text-placeholder">-</span>
        </template>

        <!-- 9. 设备系统 -->
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

        <!-- 10. 客户端信息（三行：类型 / 名称 / 版本） -->
        <template #browser="{ row }">
          <ElTooltip v-if="row.user_agent" placement="top" :show-after="200">
            <template #content>
              <div style="max-width: 400px; word-break: break-all">{{ row.user_agent }}</div>
            </template>
            <div class="cell-stack">
              <span class="cell-line">类型：浏览器</span>
              <span class="cell-line">名称：{{ browserDisplayName(row.browser_name) }}</span>
              <span class="cell-line">版本：{{ browserVersion(row.user_agent) }}</span>
            </div>
          </ElTooltip>
          <span v-else class="text-placeholder">-</span>
        </template>

        <!-- 11. 客户端语言（两行：首选标签 / 全部偏好） -->
        <template #accept_language="{ row }">
          <ElTooltip v-if="row.accept_language" placement="top" :show-after="200">
            <template #content>
              <div class="tooltip-stack">
                <div>原始值：{{ row.accept_language }}</div>
                <div>偏好顺序：{{ allLangNames(row.accept_language) }}</div>
              </div>
            </template>
            <div class="lang-cell">
              <div class="lang-primary">
                <ElTag type="danger" size="small" effect="dark" class="lang-preferred-tag">首选</ElTag>
                <span class="lang-primary-text">{{ langName(primaryLang(row.accept_language)) }}</span>
              </div>
              <div class="lang-others">{{ otherLangNames(row.accept_language) || '-' }}</div>
            </div>
          </ElTooltip>
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
  import { MECHANISM_TAGS, DECIDED_BY_LABELS, VERDICT_TAGS } from '@/constants/disposition'
  import { MECHANISM_LABELS, VERDICT_LABELS } from '@/constants/accessLogDetail'
  import { getCrawlerDetail, getSubcategoryLabel, getVendorIcon, type CrawlerDetail } from '@/constants/crawlerDetails'
  import { Icon } from '@iconify/vue'

  defineOptions({ name: 'AccessLogs' })

  function fmtTime(raw?: string | null): string {
    if (!raw) return '-'
    // ClickHouse 存的是 UTC，aiochclient 返回不带时区的 naive datetime，
    // FastAPI 序列化后无 Z 后缀。若直接交给 new Date 会被当本地时区，
    // 导致东八区多加 8 小时。这里强制补 Z 让浏览器按 UTC 解析。
    const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(raw) ? raw : `${raw}Z`
    const d = new Date(iso)
    if (isNaN(d.getTime())) return raw
    // 转换为本地时区，格式：2024/1/1 16:00:00
    return d.toLocaleString('zh-CN', { hour12: false })
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

  /** 拆出全部语言标签，按 Accept-Language 原有顺序（即 q 值降序） */
  function langTags(raw?: string | null): string[] {
    if (!raw) return []
    return raw
      .split(',')
      .map((s) => s.split(';')[0].trim())
      .filter(Boolean)
  }

  // Intl.DisplayNames 覆盖全部 BCP-47 标签，比手写映射表准确且免维护
  const langDisplay = new Intl.DisplayNames(['zh-CN'], { type: 'language' })
  const regionDisplay = new Intl.DisplayNames(['zh-CN'], { type: 'region' })

  /** 语言标签转中文名：zh-CN → 简体中文（中国） */
  function langName(tag?: string | null): string {
    if (!tag || tag === '-') return '-'
    if (tag === '*') return '任意语言'
    try {
      return langDisplay.of(tag) || tag
    } catch {
      return tag
    }
  }

  /** 除首选之外的语言中文名，逗号分隔 */
  function otherLangNames(raw?: string | null): string {
    return langTags(raw).slice(1).map(langName).join('、')
  }

  /** 全部语言中文名，用于 tooltip */
  function allLangNames(raw?: string | null): string {
    return langTags(raw).map(langName).join('、')
  }

  /** 国家代码转中文名：HK → 中国香港 */
  function countryName(code?: string | null): string {
    if (!code) return ''
    try {
      return regionDisplay.of(code.toUpperCase()) || code
    } catch {
      return code
    }
  }

  const CONN_TYPE_LABELS: Record<string, string> = {
    datacenter: '机房',
    hosting: '机房',
    business: '企业专线',
    cellular: '移动网络',
    mobile: '移动网络',
    residential: '家庭宽带',
    dialup: '拨号',
    cable: '有线宽带',
    unknown: '未知'
  }

  /** 连接类型转中文 */
  function connTypeName(raw?: string | null): string {
    if (!raw) return ''
    return CONN_TYPE_LABELS[raw.toLowerCase()] || raw
  }

  const BROWSER_LABELS: Record<string, string> = {
    edge: 'Microsoft Edge',
    chrome: 'Chrome',
    safari: 'Safari',
    firefox: 'Firefox',
    opera: 'Opera',
    samsung: 'Samsung Internet',
    ie: 'Internet Explorer',
    wechat: '微信内置浏览器',
    micromessenger: '微信内置浏览器'
  }

  /** 后端存的是小写标识（chrome/edge），转成展示名 */
  function browserDisplayName(raw?: string | null): string {
    if (!raw) return '-'
    return BROWSER_LABELS[raw.toLowerCase()] || raw
  }

  // 顺序敏感：Edge 的 UA 同时含 Chrome/Safari，Chrome 的 UA 也含 Safari，
  // 必须让更具体的品牌先匹配，否则版本号会取错。
  const UA_VERSION_RULES: Array<[RegExp, string]> = [
    [/Edg(?:e|A|iOS)?\/([\d.]+)/, 'edge'],
    [/OPR\/([\d.]+)/, 'opera'],
    [/SamsungBrowser\/([\d.]+)/, 'samsung'],
    [/MicroMessenger\/([\d.]+)/, 'wechat'],
    [/Firefox\/([\d.]+)/, 'firefox'],
    [/Chrome\/([\d.]+)/, 'chrome'],
    [/Version\/([\d.]+).*Safari/, 'safari'],
    [/MSIE ([\d.]+)/, 'ie']
  ]

  /** 从 UA 提取浏览器版本号 */
  function browserVersion(ua?: string | null): string {
    if (!ua) return '-'
    for (const [re] of UA_VERSION_RULES) {
      const m = ua.match(re)
      if (m?.[1]) return m[1]
    }
    return '-'
  }

  type AccessLogSearchFormParams = {
    requestId?: string; ip?: string; verdict?: string; mechanism?: string
    decidedBy?: string; deviceType?: string; isBot?: boolean; isCrawler?: boolean
    crawlerCategory?: string; crawlerVendor?: string; daterange?: string[]
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

  /** 快速筛选项：点击即切换搜索表单对应字段，无需展开完整搜索栏 */
  interface QuickFilter {
    label: string
    key: keyof AccessLogSearchFormParams
    value: AccessLogSearchFormParams[keyof AccessLogSearchFormParams]
  }
  const quickFilters: QuickFilter[] = [
    { label: '仅爬虫', key: 'isBot', value: true },
    { label: '仅真人', key: 'isBot', value: false },
    { label: '可信', key: 'verdict', value: 'trusted' },
    { label: '可疑', key: 'verdict', value: 'suspect' },
    { label: '恶意', key: 'verdict', value: 'hostile' }
  ]

  function isFilterActive(filter: QuickFilter): boolean {
    return searchForm.value[filter.key] === filter.value
  }

  /** 再次点击同一快筛项即取消，否则覆盖同字段的旧值 */
  function toggleQuickFilter(filter: QuickFilter) {
    searchForm.value = {
      ...searchForm.value,
      [filter.key]: isFilterActive(filter) ? undefined : filter.value
    }
    handleSearch(searchForm.value)
  }

  function openDetail(requestId: string) {
    detailRequestId.value = requestId
    detailVisible.value   = true
  }

  const searchForm = ref<AccessLogSearchFormParams>({
    requestId: undefined, ip: undefined, verdict: undefined, mechanism: undefined,
    decidedBy: undefined, deviceType: undefined, isBot: undefined, isCrawler: undefined,
    crawlerCategory: undefined, crawlerVendor: undefined, daterange: recentLocalRange(24)
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
        { prop: 'request_id',      label: '访客编号',     minWidth: 200, useSlot: true, align: 'center'  },
        { prop: 'path',            label: '访客访问网址', minWidth: 160, useSlot: true, align: 'center'  },
        { prop: 'verdict',         label: '访问状态',     width: 160,    useSlot: true, align: 'center' },
        { prop: 'mechanism',       label: '处置机制',     width: 130,    useSlot: true, align: 'center' },
        { prop: 'crawler_info',    label: '爬虫识别',     width: 180, useSlot: true, align: 'center'  },
        { prop: 'referer',         label: '访问来路',     minWidth: 150, useSlot: true  , align: 'center'  },
        { prop: 'ip',              label: 'IP 地址',      minWidth: 130, useSlot: true , align: 'center' },
        { prop: 'asn',             label: 'IP 详情',      width: 130,    useSlot: true, align: 'center'  },
        { prop: 'device_type',     label: '设备系统',     width: 130,    useSlot: true, align: 'center'  },
        { prop: 'browser',         label: '客户端信息',   width: 130,    useSlot: true, align: 'center'  },
        { prop: 'accept_language', label: '客户端语言',   minWidth: 130, useSlot: true, align: 'center'  },
        { prop: '_actions',        label: '操作',         width: 70,     fixed: 'right', useSlot: true, align: 'center'  }
      ]
    }
  })

  function extractDomain(raw?: string | null): string {
    if (!raw) return ''
    // 相对路径（/products/xxx）补上协议头后会被解析成 https:///products/xxx，
    // 首个路径段会被误当作 hostname，需先排除
    const trimmed = raw.trim()
    if (!trimmed || trimmed.startsWith('/')) return ''
    try {
      const u = new URL(trimmed.startsWith('http') ? trimmed : `https://${trimmed}`)
      // 合法域名至少含一个点号，可排除 products、localhost 段等误判
      return u.hostname.includes('.') ? u.hostname : ''
    } catch { return '' }
  }

  function scoreClass(score?: number | null): string {
    if (score == null) return 'score-na'
    if (score >= 70) return 'score-high'
    if (score >= 30) return 'score-mid'
    return 'score-low'
  }

  /* ── 爬虫详细信息处理 ── */

  function getCrawlerDetailInfo(crawlerName: string | null | undefined): CrawlerDetail | null {
    return getCrawlerDetail(crawlerName)
  }

  /**
   * 根据子分类返回标签类型
   */
  function getCrawlerCategoryType(subcategory: string): string {
    const typeMap: Record<string, string> = {
      web_search: 'primary',
      image_search: 'primary',
      video_search: 'primary',
      news_search: 'primary',
      mobile_search: 'primary',
      
      ad_quality: 'warning',
      ad_quality_mobile: 'warning',
      ad_indexing: 'warning',
      contextual_ads: 'warning',
      
      ai_training: 'danger',
      browsing: 'warning',
      search_indexing: 'warning',
      
      link_preview: 'success',
      
      seo_analysis: 'info',
      backlink_analysis: 'info',
      seo_tool: 'info',
      
      web_archiving: '',
      uptime_monitoring: 'info'
    }
    return typeMap[subcategory] || 'info'
  }

  function getCrawlerCategoryColor(category?: string): 'success' | 'info' | 'warning' | 'danger' {
    if (!category) return 'info'
    const colors: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
      search_engine: 'success',
      social: 'success',
      ai_crawler: 'warning',
      seo: 'info',
      monitoring: 'info',
      security: 'danger',
      library: 'warning',
      feed: 'info',
      archive: 'info',
      other: 'info'
    }
    return colors[category] || 'info'
  }

  function getCrawlerCategoryLabel(category?: string): string {
    if (!category) return '未知类型'
    const labels: Record<string, string> = {
      search_engine: '搜索引擎',
      ai_crawler: 'AI爬虫',
      social_media: '社交媒体',
      monitoring: '监控工具',
      seo_tool: 'SEO工具',
      feed_reader: 'Feed订阅',
      security_scanner: '安全扫描',
      e_commerce: '电商平台',
      advertising: '广告系统',
      archiving: '存档服务',
      accessibility: '辅助功能'
    }
    return labels[category] || category
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
      isBot: undefined, isCrawler: undefined, crawlerCategory: undefined,
      crawlerVendor: undefined,
      daterange: recentLocalRange(24)
    }
    handleSearch(searchForm.value)
    ElMessage.success('已重置筛选条件，默认展示近 24 小时日志')
  }

  onMounted(() => { handleSearch(searchForm.value) })
</script>

<style scoped>
.access-logs-page { padding: 0; }

/* ── 快速筛选按钮组 ── */
.quick-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 16px;
  background: #f7f8fa;
  border-radius: 4px;
}

.quick-filter-tag {
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}

.quick-filter-tag:hover {
  transform: translateY(-1px);
}

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

/* ── 爬虫识别列单元格约束（ElTable 自动生成的 .cell） ── */
:deep(.el-table__body .cell) {
  overflow: hidden;
  max-width: 100%;
}

/* ── 爬虫识别增强样式 ── */
.crawler-detail {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: 6px;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  height: 66px;
  min-height: 66px;
  max-height: 66px;
  overflow: hidden;
  box-sizing: border-box;
  cursor: default;
}

/* Tooltip 内容样式 */
.crawler-tooltip {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 320px;
  font-size: 12px;
  line-height: 1.5;
}
.tooltip-row {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}
.tooltip-label {
  color: #c9cdd4;
  flex-shrink: 0;
  min-width: 42px;
}

.crawler-main {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  min-width: 0;
  max-width: 100%;
  width: 100%;
  height: 100%;
}

.crawler-icon {
  font-size: 20px;
  line-height: 20px;
  height: 20px;
  flex-shrink: 0;
}

/* 厂商 logo 图标（iconify） */
.crawler-vendor-icon {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  display: block;
}

.crawler-text {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.crawler-name {
  font-size: 12px;
  font-weight: 600;
  color: #1d2129;
  line-height: 18px;
  height: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  text-align: center;
}

.crawler-subcategory-tag {
  align-self: center;
  flex-shrink: 0;
  font-size: 11px;
  width: fit-content;
  padding: 0 8px;
  height: 18px;
  line-height: 16px;
}

/* 降级显示样式 */
.crawler-basic {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  padding: 0;
  box-sizing: border-box;
  cursor: default;
}

.crawler-basic-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  width: 100%;
  height: 100%;
  max-width: 100%;
}

.crawler-icon-fallback {
  font-size: 20px;
  line-height: 20px;
  height: 20px;
  flex-shrink: 0;
  opacity: 0.7;
}

.crawler-basic-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.crawler-name-basic {
  display: inline-block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: #1d2129;
  font-weight: 600;
  max-width: 100%;
  line-height: 18px;
  height: 18px;
  text-align: center;
}

.crawler-tags {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  flex-wrap: nowrap;
  width: 100%;
  height: 18px;
}

/* 让降级视图中的 Tag 宽度贴合内容 */
.crawler-tags :deep(.el-tag) {
  padding: 0 8px;
  height: 18px;
  line-height: 16px;
  width: fit-content;
  max-width: 100%;
}

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
.verdict-source {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: #86909c;
}
.verdict-reason-text {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: #4e5969;
}

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

/* ── 访问来路：最多两行，超出省略 ── */
.cell-referer {
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
  word-break: break-all;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  cursor: default;
}

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
