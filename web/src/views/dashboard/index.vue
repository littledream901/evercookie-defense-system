<template>
  <CommonPage title="数据概览" subtitle="最近 24 小时决策趋势与处置分布">
    <template #action>
      <n-select v-model:value="appId" :options="appOptions" placeholder="选择应用" clearable style="width: 200px" />
      <n-button type="primary" @click="load">刷新</n-button>
    </template>
    <n-grid :cols="4" x-gap="16" y-gap="16" responsive="screen">
      <n-gi v-for="item in stats" :key="item.label">
        <n-card :bordered="false" size="small">
          <div class="text-12px text-gray-500">{{ item.label }}</div>
          <div class="text-24px font-semibold mt-8px" :style="{ color: item.color }">{{ item.value }}</div>
        </n-card>
      </n-gi>
    </n-grid>
    <div class="mt-16px grid grid-cols-2 gap-16px">
      <n-card title="决策处置分布" :bordered="false">
        <VChart :option="pieOption" style="height: 300px" autoresize />
      </n-card>
      <n-card title="决策趋势（每小时）" :bordered="false">
        <VChart :option="lineOption" style="height: 300px" autoresize />
      </n-card>
    </div>
  </CommonPage>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
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
const timelineData = ref([])
const dispositionData = ref([])

async function loadApps() {
  try {
    const resp = await appsApi.list({ page: 1, size: 100 })
    appOptions.value = (resp.items || []).map((a) => ({ label: a.name, value: a.id }))
    if (!appId.value && appOptions.value[0]) appId.value = appOptions.value[0].value
  } catch (e) {
    message.error(e.message || '加载应用列表失败')
  }
}

async function load() {
  if (!appId.value) return
  const now = new Date()
  const start = new Date(now.getTime() - 24 * 3600 * 1000)
  const payload = {
    app_id: appId.value,
    start_time: start.toISOString(),
    end_time: now.toISOString(),
  }
  try {
    const [tl, dp] = await Promise.all([
      analyticsApi.timeline({ ...payload, granularity: '1h' }),
      analyticsApi.disposition(payload),
    ])
    timelineData.value = tl.buckets || []
    dispositionData.value = dp.buckets || []
  } catch (e) {
    message.error(e.message || '加载分析数据失败')
  }
}

const stats = computed(() => {
  const total = timelineData.value.reduce((sum, b) => sum + (b.count || 0), 0)
  // 后端已按 verdict + mechanism 两维聚合，这里按机制归并展示
  const sumByMechanism = (...mechanisms) =>
    dispositionData.value
      .filter((b) => mechanisms.includes(b.mechanism))
      .reduce((sum, b) => sum + (b.count || 0), 0)
  return [
    { label: '总决策数', value: total, color: '#2080f0' },
    { label: '放行', value: sumByMechanism('pass'), color: '#18a058' },
    { label: '挑战', value: sumByMechanism('challenge'), color: '#f0a020' },
    { label: '阻断', value: sumByMechanism('deny', 'not_found'), color: '#d03050' },
  ]
})

const pieOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [
    {
      type: 'pie',
      radius: ['40%', '65%'],
      data: dispositionData.value.map((b) => ({ name: b.disposition, value: b.count })),
    },
  ],
}))

const lineOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: timelineData.value.map((b) => b.bucket) },
  yAxis: { type: 'value' },
  series: [
    {
      type: 'line',
      smooth: true,
      areaStyle: { opacity: 0.2 },
      data: timelineData.value.map((b) => b.count),
    },
  ],
}))

onMounted(async () => {
  await loadApps()
  await load()
})
</script>
