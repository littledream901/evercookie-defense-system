<!-- 接入诊断详情抽屉 -->
<template>
  <ElDrawer
    v-model="drawerVisible"
    :title="`接入诊断 · ${site?.name || '站点'}`"
    direction="rtl"
    size="680px"
    destroy-on-close
  >
    <!-- 加载中 -->
    <div v-if="loading" class="flex justify-center items-center py-20">
      <ElIcon class="is-loading mr-2"><Loading /></ElIcon>
      <span class="text-g-600">正在诊断...</span>
    </div>

    <!-- 加载失败 -->
    <ElAlert v-else-if="loadError" type="error" :closable="false" show-icon class="mb-4">
      <template #title>加载失败</template>
      <p class="text-sm">{{ loadError }}</p>
      <ElButton link type="primary" @click="loadDiagnostics">重新加载</ElButton>
    </ElAlert>

    <!-- 诊断结果 -->
    <template v-else-if="diagnostics">
      <!-- 概览卡片 -->
      <ElCard class="mb-4" shadow="never">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h3 class="text-lg font-medium text-g-900">{{ diagnostics.site_name }}</h3>
            <p class="text-sm text-g-600 mt-1">{{ diagnostics.domain }}</p>
          </div>
          <ElTag :type="statusTagType" size="large">
            {{ statusText }}
          </ElTag>
        </div>

        <ElDivider style="margin: 16px 0" />

        <ElDescriptions :column="2" border size="small">
          <ElDescriptionsItem label="配置接入方式">
            <ElTag size="small">{{ diagnostics.configured_access_mode }}</ElTag>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="实测接入方式">
            <template v-if="diagnostics.ingress_stats.length">
              <ElTag
                v-for="stat in diagnostics.ingress_stats"
                :key="stat.ingress"
                size="small"
                class="mr-1"
              >
                {{ stat.ingress }} ({{ stat.total }})
              </ElTag>
            </template>
            <span v-else class="text-g-400">无数据</span>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="近24h请求数">
            <span class="font-mono">{{ diagnostics.total_requests.toLocaleString() }}</span>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="最后活跃时间">
            <span v-if="diagnostics.last_seen_at">
              {{ formatTime(diagnostics.last_seen_at) }}
            </span>
            <span v-else class="text-g-400">无数据</span>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="站点状态">
            <ElTag :type="diagnostics.is_active ? 'success' : 'danger'" size="small">
              {{ diagnostics.is_active ? '已启用' : '已停用' }}
            </ElTag>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="网关地址">
            <span class="text-xs font-mono">
              {{ diagnostics.gateway_url || '使用默认网关' }}
            </span>
          </ElDescriptionsItem>
        </ElDescriptions>
      </ElCard>

      <!-- 诊断发现 -->
      <div class="space-y-3">
        <h3 class="text-sm font-medium text-g-900 mb-2">诊断结果</h3>
        <div v-for="finding in diagnostics.findings" :key="finding.code">
          <ElAlert
            :type="finding.level === 'ok' ? 'success' : finding.level"
            :title="finding.title"
            :closable="false"
            show-icon
          >
            <p class="text-sm mb-2 text-g-700">{{ finding.detail }}</p>
            <p class="text-sm font-medium text-g-900">
              <span class="text-g-600">建议：</span>{{ finding.suggestion }}
            </p>
          </ElAlert>
        </div>
      </div>

      <!-- 统计数据 -->
      <ElCard v-if="diagnostics.ingress_stats.length" class="mt-4" shadow="never">
        <template #header>
          <span class="text-sm font-medium">接入来源统计</span>
        </template>
        <ElTable :data="diagnostics.ingress_stats" size="small" border>
          <ElTableColumn prop="ingress" label="来源" width="80" />
          <ElTableColumn prop="total" label="总请求" width="90" align="right" />
          <ElTableColumn label="判定结果" min-width="180">
            <template #default="{ row }">
              <div class="text-xs space-y-1">
                <div v-if="row.clean_count">
                  <ElTag type="success" size="small">clean</ElTag>
                  <span class="ml-1">{{ row.clean_count }}</span>
                </div>
                <div v-if="row.suspicious_count">
                  <ElTag type="warning" size="small">suspicious</ElTag>
                  <span class="ml-1">{{ row.suspicious_count }}</span>
                </div>
                <div v-if="row.hostile_count">
                  <ElTag type="danger" size="small">hostile</ElTag>
                  <span class="ml-1">{{ row.hostile_count }}</span>
                </div>
                <div v-if="row.unknown_verdict_count">
                  <ElTag type="info" size="small">unknown</ElTag>
                  <span class="ml-1">{{ row.unknown_verdict_count }}</span>
                </div>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="unique_fingerprints" label="唯一指纹" width="90" align="right" />
          <ElTableColumn prop="unique_ips" label="唯一IP" width="80" align="right" />
          <ElTableColumn label="平均耗时" width="90" align="right">
            <template #default="{ row }">
              {{ row.avg_cost_ms.toFixed(1) }} ms
            </template>
          </ElTableColumn>
        </ElTable>
      </ElCard>
    </template>

    <!-- 操作按钮 -->
    <template #footer>
      <div class="flex justify-between">
        <ElButton @click="drawerVisible = false">关闭</ElButton>
        <ElSpace>
          <ElButton :loading="testing" @click="testConnection">
            <ElIcon class="mr-1"><Connection /></ElIcon>
            测试连通性
          </ElButton>
          <ElButton type="primary" @click="openIntegrationGuide">
            <ElIcon class="mr-1"><Document /></ElIcon>
            查看接入指引
          </ElButton>
        </ElSpace>
      </div>
    </template>
  </ElDrawer>
</template>

<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { ElMessage } from 'element-plus'
  import { Loading, Connection, Document } from '@element-plus/icons-vue'
  import { fetchGetIntegrationDiagnostics, testSiteConnection } from '@/api/diagnostics'
  import { formatTime } from '@/utils/format'

  interface SiteInfo {
    id: number
    name: string
    domain: string
  }

  interface Props {
    visible: boolean
    site: SiteInfo | null
  }

  const props = withDefaults(defineProps<Props>(), { visible: false })
  const emit = defineEmits<{ 
    'update:visible': [value: boolean]
    'open-integration-guide': []
  }>()

  const drawerVisible = computed({
    get: () => props.visible,
    set: (val) => emit('update:visible', val)
  })

  const loading = ref(false)
  const loadError = ref('')
  const testing = ref(false)
  const diagnostics = ref<Api.Fangyu.IntegrationDiagnostics | null>(null)

  const statusTagType = computed(() => {
    const map: Record<string, any> = {
      ok: 'success',
      warning: 'warning',
      error: 'danger',
      no_data: 'info'
    }
    return map[diagnostics.value?.status || 'no_data'] || 'info'
  })

  const statusText = computed(() => {
    const map: Record<string, string> = {
      ok: '✓ 接入正常',
      warning: '⚠ 存在警告',
      error: '✗ 接入异常',
      no_data: '无流量数据'
    }
    return map[diagnostics.value?.status || 'no_data'] || '未知状态'
  })

  // 监听站点变化，自动加载诊断
  watch(
    () => [props.visible, props.site?.id],
    async ([visible, siteId]) => {
      if (visible && siteId) {
        await loadDiagnostics()
      }
    },
    { immediate: true }
  )

  const loadDiagnostics = async () => {
    if (!props.site?.id) return

    loading.value = true
    loadError.value = ''

    try {
      diagnostics.value = await fetchGetIntegrationDiagnostics(props.site.id, 24)
    } catch (error: any) {
      loadError.value = error.message || '加载失败'
    } finally {
      loading.value = false
    }
  }

  const testConnection = async () => {
    if (!props.site?.id) return

    testing.value = true
    try {
      const result = await testSiteConnection(props.site.id)
      if (result.ok) {
        ElMessage.success(result.message || '连通性测试通过')
      } else {
        ElMessage.error(result.error || '测试失败')
      }
    } catch (error: any) {
      ElMessage.error(error.message || '测试失败')
    } finally {
      testing.value = false
    }
  }

  const openIntegrationGuide = () => {
    // 关闭当前抽屉，打开接入指引抽屉
    drawerVisible.value = false
    // 触发父组件打开接入指引
    emit('open-integration-guide')
  }
</script>

<style scoped lang="scss">
.space-y-3 > * + * {
  margin-top: 12px;
}
</style>
