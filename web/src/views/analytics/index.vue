<template>
  <CommonPage title="分析看板" subtitle="按时间范围查询决策数据">
    <template #action>
      <n-select v-model:value="appId" :options="appOptions" placeholder="选择应用" style="width: 180px" />
      <n-date-picker v-model:value="range" type="datetimerange" clearable />
      <n-select v-model:value="granularity" :options="granularityOptions" style="width: 120px" />
      <n-button type="primary" @click="load">查询</n-button>
    </template>
    <div class="grid grid-cols-2 gap-16px">
      <n-card title="决策数量趋势" :bordered="false">
        <VChart :option="lineOption" style="height: 320px" autoresize />
      </n-card>
      <n-card title="处置分布" :bordered="false">
        <VChart :option="pieOption" style="height: 320px" autoresize />
      </n-card>
      <n-card title="Top 命中规则" :bordered="false" class="col-span-2">
        <n-data-table :columns="topColumns" :data="topEntities" :loading="loading" :bordered="false" />
      </n-card>
    </div>
  </CommonPage>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { use } from 'echarts/core'
import VChart from 'vue-echarts'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import CommonPage from '@/components/CommonPage.vue'
import { analyticsApi } from '@/api/analytics'
import { appsApi } from '@/api/apps'

use([CanvasRenderer, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent])

const message = useMessage()
const appId = ref(null)
const appOptions = ref([])
const range = ref([Date.now() - 24 * 3600 * 1000, Date.now()])
const granularity = ref('hour')
const granularityOptions = [
  { label: '分钟', value: 'minute' },
  { label: '小时', value: 'hour' },
  { label: '天', value: 'day' },
]

const loading = ref(false)
const timelineData = ref([])
const dispositionData = ref([])
const topEntities = ref([])

async function loadApps() {
  const resp = await appsApi.list({ page: 1, pageSize: 100 })
  appOptions.value = ((resp.data?.items) || []).map((a) => ({ label: a.name, value: a.id }))
  if (!appId.value && appOptions.value[0]) appId.value = appOptions.value[0].value
}

async function load() {
  if (!appId.value || !range.value) return
  loading.value = true
  const payload = {
    app_id: appId.value,
    start: new Date(range.value[0]).toISOString(),
    end: new Date(range.value[1]).toISOString(),
  }
  try {
    const [tl, dp, top] = await Promise.all([
      analyticsApi.timeline({ ...payload, granularity: granularity.value }),
      analyticsApi.disposition(payload),
      analyticsApi.topEntities({ ...payload, dimension: 'device', limit: 10 }),
    ])
    timelineData.value = tl.data || []
    dispositionData.value = dp.data || []
    topEntities.value = top.data || []
  } catch (e) {
    message.error(e.message || '查询失败')
  } finally {
    loading.value = false
  }
}

const lineOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: timelineData.value.map((b) => b.bucket) },
  yAxis: { type: 'value' },
  series: [{ type: 'line', smooth: true, data: timelineData.value.map((b) => b.count) }],
}))

const pieOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{ type: 'pie', radius: ['40%', '65%'], data: dispositionData.value.map((b) => ({ name: b.disposition, value: b.count })) }],
}))

const topColumns = [
  { title: '实体', key: 'entity' },
  { title: '命中次数', key: 'count' },
]

onMounted(async () => {
  await loadApps()
  await load()
})
</script>
