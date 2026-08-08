<!-- SDK 接入诊断：核对站点埋码是否真正生效，以及实测接入方式与配置是否一致 -->
<template>
  <div class="art-full-height" style="overflow-y: auto; padding: 4px">
    <div class="mb-3 flex shrink-0 flex-wrap items-center justify-between gap-2">
      <div>
        <h2 class="text-lg font-medium text-g-900">SDK 接入诊断</h2>
        <p class="mt-1 text-sm text-g-600">
          核对站点 SDK / 适配器埋码是否真正生效，实测接入方式与站点配置是否一致
        </p>
      </div>
      <div class="flex items-center gap-2">
        <ElSelect
          v-model="siteId"
          placeholder="选择站点"
          style="width: 180px"
          :loading="appLoading"
          @change="onSiteChange"
        >
          <ElOption v-for="o in appOptions" :key="o.value" :label="o.label" :value="o.value" />
        </ElSelect>
        <ElSelect v-model="hours" style="width: 120px" @change="load">
          <ElOption v-for="o in HOUR_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
        </ElSelect>
        <ElButton :loading="loading" :disabled="!siteId" @click="load">
          <ElIcon class="mr-1"><Refresh /></ElIcon>
          重新诊断
        </ElButton>
      </div>
    </div>

    <ElAlert v-if="loadError" type="error" :closable="false" class="mb-3" :title="loadError">
      <template #default>
        <ElButton link type="primary" :loading="loading" @click="load">重新加载</ElButton>
      </template>
    </ElAlert>

    <ElEmpty
      v-if="!siteId && !appLoading"
      description="请先选择站点"
      :image-size="60"
    />

    <template v-if="siteId && data">
      <!-- 诊断结论横幅 -->
      <ElAlert
        :type="STATUS_META[data.status].alert"
        :closable="false"
        show-icon
        class="mb-3"
      >
        <template #title>
          <span class="font-medium">{{ STATUS_META[data.status].title }}</span>
        </template>
        {{ STATUS_META[data.status].desc }}
      </ElAlert>

      <ElRow :gutter="16" class="mb-3">
        <!-- 概览 -->
        <ElCol :span="10">
          <ElCard shadow="never" header="站点概览" v-loading="loading">
            <ElDescriptions :column="1" size="small" border>
              <ElDescriptionsItem label="站点">
                {{ data.site_name }}
                <ElTag v-if="!data.is_active" type="danger" size="small" class="ml-1">已停用</ElTag>
              </ElDescriptionsItem>
              <ElDescriptionsItem label="域名">{{ data.domain }}</ElDescriptionsItem>
              <ElDescriptionsItem label="配置接入模式">
                <ElTag size="small" :type="data.configured_access_mode === 'sdk' ? 'primary' : 'success'">
                  {{ MODE_LABEL[data.configured_access_mode] ?? data.configured_access_mode }}
                </ElTag>
              </ElDescriptionsItem>
              <ElDescriptionsItem label="实测接入来源">
                <template v-if="data.ingress_stats.length">
                  <ElTag
                    v-for="s in data.ingress_stats"
                    :key="s.ingress"
                    size="small"
                    class="mr-1"
                    :type="s.ingress === data.configured_access_mode ? 'success' : 'warning'"
                  >
                    {{ MODE_LABEL[s.ingress] ?? s.ingress }}
                  </ElTag>
                </template>
                <span v-else class="text-g-500">无</span>
              </ElDescriptionsItem>
              <ElDescriptionsItem label="窗口内请求数">{{ data.total_requests }}</ElDescriptionsItem>
              <ElDescriptionsItem label="最后活跃">
                <span :class="lastSeenStale ? 'text-warning' : ''">{{ lastSeenText }}</span>
              </ElDescriptionsItem>
              <ElDescriptionsItem label="配置 SDK 版本">
                {{ data.configured_sdk_version || '未填写' }}
              </ElDescriptionsItem>
              <ElDescriptionsItem label="网关地址">
                {{ data.gateway_url || '使用部署级默认网关' }}
              </ElDescriptionsItem>
            </ElDescriptions>
          </ElCard>
        </ElCol>

        <!-- 诊断项 -->
        <ElCol :span="14">
          <ElCard shadow="never" v-loading="loading" class="h-full">
            <template #header>
              <div class="flex items-center gap-2">
                <span>诊断结论</span>
                <ElTooltip placement="top">
                  <template #content>
                    <div style="max-width: 320px">
                      诊断只读取历史遥测数据，不会向网关发送探测请求，因此不产生真实决策事件、不消耗
                      nonce。验签失败的请求在网关鉴权阶段即被拒绝、不会落库，故这里查不到具体失败原因。
                    </div>
                  </template>
                  <ElIcon class="text-g-400"><QuestionFilled /></ElIcon>
                </ElTooltip>
              </div>
            </template>
            <div v-for="f in data.findings" :key="f.code" class="finding">
              <div class="finding-head">
                <ElTag :type="LEVEL_TAG[f.level]" size="small" effect="dark">
                  {{ LEVEL_LABEL[f.level] }}
                </ElTag>
                <span class="finding-title">{{ f.title }}</span>
              </div>
              <p class="finding-detail">{{ f.detail }}</p>
              <p v-if="f.level !== 'ok'" class="finding-fix">
                <span class="finding-fix-label">处理建议</span>{{ f.suggestion }}
              </p>
            </div>
          </ElCard>
        </ElCol>
      </ElRow>

      <!-- 分接入来源明细 -->
      <ElCard shadow="never" v-loading="loading">
        <template #header>
          <div class="flex items-center gap-2">
            <span>分接入来源明细</span>
            <ElTooltip placement="top">
              <template #content>
                <div style="max-width: 320px">
                  SDK 与适配器两条路径的信号丰富度不同：SDK 有真指纹与行为时序，适配器只有服务端字段、
                  指纹由网关派生。因此必须分开看，否则派生指纹会污染「独立设备数」这类指标。
                </div>
              </template>
              <ElIcon class="text-g-400"><QuestionFilled /></ElIcon>
            </ElTooltip>
          </div>
        </template>
        <ElTable :data="data.ingress_stats" size="small" border>
          <ElTableColumn label="接入来源" min-width="110">
            <template #default="{ row }">
              <ElTag size="small" :type="row.ingress === 'sdk' ? 'primary' : 'success'">
                {{ MODE_LABEL[row.ingress] ?? row.ingress }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="host" label="接入网站" min-width="180" show-overflow-tooltip />
          <ElTableColumn prop="total" label="请求数" min-width="90" />
          <ElTableColumn label="派生指纹" min-width="130">
            <template #default="{ row }">
              <span :class="derivedClass(row)">
                {{ row.derived_count }}（{{ pct(row.derived_count, row.total) }}）
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="含行为事件" min-width="130">
            <template #default="{ row }">
              <span :class="row.ingress === 'sdk' && !row.behavior_count ? 'text-warning' : ''">
                {{ row.behavior_count }}（{{ pct(row.behavior_count, row.total) }}）
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="unique_fingerprints" label="独立指纹" min-width="100" />
          <ElTableColumn prop="unique_ips" label="独立 IP" min-width="90" />
          <ElTableColumn label="判定分布" min-width="200">
            <template #default="{ row }">
              <span class="text-danger">敌对 {{ row.hostile_count }}</span>
              <span class="mx-1 text-g-300">/</span>
              <span class="text-warning">可疑 {{ row.suspicious_count }}</span>
              <span class="mx-1 text-g-300">/</span>
              <span class="text-success">正常 {{ row.clean_count }}</span>
              <template v-if="row.unknown_verdict_count">
                <span class="mx-1 text-g-300">/</span>
                <span class="text-g-500">未判定 {{ row.unknown_verdict_count }}</span>
              </template>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="restore_count" label="自愈命中" min-width="100" />
          <ElTableColumn label="平均耗时" min-width="100">
            <template #default="{ row }">{{ row.avg_cost_ms }} ms</template>
          </ElTableColumn>
          <ElTableColumn label="最后活跃" min-width="160">
            <template #default="{ row }">{{ fmt(row.last_seen_at) }}</template>
          </ElTableColumn>
        </ElTable>
        <ElEmpty
          v-if="!data.ingress_stats.length && !loading"
          description="窗口内无决策记录：埋码可能未生效，也可能请求在网关鉴权阶段就被拒绝"
          :image-size="60"
        />
      </ElCard>
    </template>
  </div>
</template>

<script setup lang="ts">
  import { QuestionFilled, Refresh } from '@element-plus/icons-vue'
  import { fetchGetSiteList } from '@/api/apps'
  import { fetchGetIntegrationDiagnostics } from '@/api/diagnostics'

  defineOptions({ name: 'FangyuSdkDiagnostics' })

  const HOUR_OPTIONS = [
    { label: '近 1 小时', value: 1 },
    { label: '近 24 小时', value: 24 },
    { label: '近 7 天', value: 168 },
    { label: '近 30 天', value: 720 }
  ]

  const MODE_LABEL: Record<string, string> = {
    sdk: '浏览器 SDK',
    adapter: '服务端适配器',
    unknown: '未知'
  }

  const LEVEL_TAG: Record<string, 'success' | 'warning' | 'danger'> = {
    ok: 'success',
    warning: 'warning',
    error: 'danger'
  }

  const LEVEL_LABEL: Record<string, string> = {
    ok: '正常',
    warning: '注意',
    error: '异常'
  }

  const STATUS_META: Record<string, { alert: 'success' | 'warning' | 'error' | 'info'; title: string; desc: string }> = {
    ok: {
      alert: 'success',
      title: '接入正常',
      desc: '实测接入方式与站点配置一致，未发现异常信号。'
    },
    warning: {
      alert: 'warning',
      title: '接入基本可用，但有需要注意的问题',
      desc: '请求已到达网关，但部分信号不符合预期，可能导致判定能力下降。'
    },
    error: {
      alert: 'error',
      title: '接入存在问题',
      desc: '检测到会实质影响防护效果的问题，建议按下方建议尽快处理。'
    },
    no_data: {
      alert: 'error',
      title: '窗口内没有任何决策记录',
      desc: '无法确认埋码是否生效。验签失败的请求不会落库，因此「未接入」与「密钥/时钟错误」在此无法区分。'
    }
  }

  const siteId = ref<number>()
  const hours = ref(24)
  const appOptions = ref<{ label: string; value: number }[]>([])
  const appLoading = ref(false)
  const loading = ref(false)
  const loadError = ref('')
  const data = ref<Api.Fangyu.IntegrationDiagnostics | null>(null)

  const fmt = (v: string | null) => {
    if (!v) return '—'
    // ClickHouse 返回的 UTC 时间，强制补 Z 后缀让浏览器按 UTC 解析
    const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(v) ? v : `${v}Z`
    const d = new Date(iso)
    return Number.isNaN(d.getTime()) ? v : d.toLocaleString('zh-CN', { hour12: false })
  }

  const lastSeenText = computed(() => {
    const last = data.value?.last_seen_at
    if (!last) return '窗口内无记录'
    const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(last) ? last : `${last}Z`
    const diffMin = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
    const rel = diffMin < 1 ? '刚刚' : diffMin < 60 ? `${diffMin} 分钟前` : `${Math.floor(diffMin / 60)} 小时前`
    return `${fmt(last)}（${rel}）`
  })

  // 超过 1 小时没有流量就标黄提醒：正常有量的站点不会这么久没记录
  const lastSeenStale = computed(() => {
    const last = data.value?.last_seen_at
    if (!last) return false
    const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(last) ? last : `${last}Z`
    return Date.now() - new Date(iso).getTime() > 3600_000
  })

  const pct = (part: number, whole: number) =>
    whole ? `${((part / whole) * 100).toFixed(1)}%` : '0%'

  // 适配器的派生指纹是设计预期，不该标红；SDK 出现派生指纹才是问题
  const derivedClass = (row: Api.Fangyu.IngressStat) => {
    if (row.ingress !== 'sdk' || !row.total) return ''
    return row.derived_count / row.total > 0.5 ? 'text-danger' : ''
  }

  const load = async () => {
    if (!siteId.value) {
      data.value = null
      return
    }
    loading.value = true
    loadError.value = ''
    try {
      data.value = await fetchGetIntegrationDiagnostics(siteId.value, hours.value)
    } catch (err) {
      data.value = null
      loadError.value = '诊断数据加载失败，请稍后重试。'
      console.error('加载接入诊断失败:', err)
    } finally {
      loading.value = false
    }
  }

  const onSiteChange = () => load()

  const loadApps = async () => {
    appLoading.value = true
    try {
      const res = await fetchGetSiteList({ page: 1, pageSize: 100 })
      appOptions.value = (res.items || []).map((i) => ({ label: i.name, value: i.id }))
      // 默认选中第一个站点，避免页面初始为空让人以为功能没生效
      if (!siteId.value && appOptions.value.length) {
        siteId.value = appOptions.value[0].value
        await load()
      }
    } catch (err) {
      loadError.value = '站点列表加载失败，请稍后重试。'
      console.error('加载站点列表失败:', err)
    } finally {
      appLoading.value = false
    }
  }

  onMounted(loadApps)
</script>

<style scoped>
  .finding {
    padding: 10px 0;
    border-bottom: 1px solid var(--el-border-color-lighter);
  }
  .finding:last-child {
    border-bottom: none;
  }
  .finding-head {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .finding-title {
    font-size: 14px;
    font-weight: 500;
    color: var(--el-text-color-primary);
  }
  .finding-detail {
    margin: 6px 0 0;
    font-size: 13px;
    line-height: 1.6;
    color: var(--el-text-color-regular);
  }
  .finding-fix {
    margin: 6px 0 0;
    font-size: 13px;
    line-height: 1.6;
    color: var(--el-text-color-secondary);
  }
  .finding-fix-label {
    display: inline-block;
    margin-right: 6px;
    padding: 0 6px;
    font-size: 12px;
    color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    border-radius: 3px;
  }
  .text-danger {
    color: var(--el-color-danger);
  }
  .text-warning {
    color: var(--el-color-warning);
  }
  .text-success {
    color: var(--el-color-success);
  }
</style>
