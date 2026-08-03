<!-- 地址池命中分布：验证轮询权重/策略是否按预期生效 -->
<template>
  <ElCard shadow="never" v-loading="loading">
    <template #header>
      <div class="flex-b items-center">
        <span class="font-medium">地址池命中分布</span>
        <ElSpace>
          <ElSelect
            v-model="siteId"
            placeholder="选择站点"
            size="small"
            style="width:160px"
            :loading="appLoading"
            @change="onSiteChange"
          >
            <ElOption v-for="o in appOptions" :key="o.value" :label="o.label" :value="o.value" />
          </ElSelect>
          <ElInput
            v-model.number="ruleId"
            placeholder="规则 ID（可选）"
            size="small"
            style="width:130px"
            clearable
            @change="load"
          />
          <ElButton size="small" @click="load">刷新</ElButton>
        </ElSpace>
      </div>
    </template>

    <ElEmpty
      v-if="!rows.length && !loading"
      :description="siteId ? '暂无数据：需要有规则使用轮询地址池才会产生记录' : '请先选择站点'"
      :image-size="60"
    />
    <template v-else>
      <ArtHBarChart
        height="240px"
        :data="hitCounts"
        :x-axis-data="urlLabels"
        :colors="['#409eff']"
        :show-legend="false"
      />
      <ElTable :data="rows" size="small" class="mt-3">
        <ElTableColumn prop="target_url" label="地址" min-width="240" show-overflow-tooltip />
        <ElTableColumn prop="hit_count" label="命中" width="90" align="right" />
        <ElTableColumn label="占比" width="90" align="right">
          <template #default="{ row }">{{ ratio(row.hit_count) }}</template>
        </ElTableColumn>
        <ElTableColumn label="错误" width="90" align="right">
          <template #default="{ row }">
            <span :class="row.error_count > 0 ? 'text-red-500' : ''">{{ row.error_count }}</span>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="last_hit_at" label="最近命中" width="170" />
      </ElTable>
      <div class="mt-2 text-xs text-g-500">
        近 24 小时，仅统计 target_kind=url_pool 的记录。占比可用于核对权重配置是否生效。
      </div>
    </template>
  </ElCard>
</template>

<script setup lang="ts">
  import { fetchGetPoolDistribution } from '@/api/logs'
  import { fetchGetAppList } from '@/api/apps'
  import { recentRange } from '@/constants/fangyu'

  defineOptions({ name: 'PoolDistributionChart' })

  const loading    = ref(false)
  const appLoading = ref(false)
  const rows       = ref<Api.Fangyu.PoolDistributionItem[]>([])
  const siteId     = ref<number>()
  const ruleId     = ref<number>()
  const appOptions = ref<{ label: string; value: number }[]>([])

  // ArtHBarChart 自下而上渲染，倒序让命中最多的落在顶部
  const ordered   = computed(() => rows.value.slice().reverse())
  const hitCounts = computed(() => ordered.value.map(r => r.hit_count))
  const urlLabels = computed(() => ordered.value.map(r => shortenUrl(r.target_url)))

  const total = computed(() => rows.value.reduce((sum, r) => sum + r.hit_count, 0))

  /** 只留 host + path：完整 URL 带查询串会把 Y 轴标签挤成一片 */
  function shortenUrl(url: string): string {
    try {
      const u = new URL(url)
      return u.host + (u.pathname === '/' ? '' : u.pathname)
    } catch {
      return url.slice(0, 40)
    }
  }

  function ratio(hit: number): string {
    return total.value ? `${((hit / total.value) * 100).toFixed(1)}%` : '-'
  }

  function onSiteChange() {
    ruleId.value = undefined
    load()
  }

  const load = async () => {
    if (!siteId.value) {
      rows.value = []
      return
    }
    loading.value = true
    try {
      const { start, end } = recentRange(24)
      const data = await fetchGetPoolDistribution({
        siteId: siteId.value,
        ruleId: ruleId.value || undefined,
        start,
        end
      })
      rows.value = (data as Api.Fangyu.PoolDistributionItem[]) ?? []
    } finally {
      loading.value = false
    }
  }

  const loadApps = async () => {
    appLoading.value = true
    try {
      const res = await fetchGetAppList({ page: 1, pageSize: 100 })
      appOptions.value = (res.items || []).map((i: any) => ({ label: i.name, value: i.id }))
      // 默认选中第一个站点，避免面板初始为空让人以为功能没生效
      if (!siteId.value && appOptions.value.length) {
        siteId.value = appOptions.value[0].value
        await load()
      }
    } finally {
      appLoading.value = false
    }
  }

  onMounted(loadApps)
</script>
