<!-- 分析报表 -->
<template>
  <div class="art-full-height overflow-y-auto">
    <div class="flex flex-col gap-4 pb-4">

    <!-- 筛选栏 -->
    <ElCard shadow="never">
      <ElSpace wrap>
        <ElDatePicker v-model="dateRange" type="datetimerange"
          start-placeholder="开始时间" end-placeholder="结束时间"
          value-format="YYYY-MM-DDTHH:mm:ss" :shortcuts="dateShortcuts"
          @change="loadAll" />
        <ElSelect v-model="granularity" class="w-28" @change="loadAll">
          <ElOption label="按小时" value="hour" />
          <ElOption label="按天" value="day" />
        </ElSelect>
        <ElButton type="primary" @click="loadAll">刷新</ElButton>
      </ElSpace>
    </ElCard>

    <!-- 趋势图（按 verdict 分色堆叠） -->
    <ElCard shadow="never" v-loading="timelineLoading">
      <template #header>
        <div class="flex-b items-center">
          <span class="font-medium">决策趋势</span>
          <ElRadioGroup v-model="trendMode" size="small" @change="renderTimeline">
            <ElRadioButton label="verdict">按裁决</ElRadioButton>
            <ElRadioButton label="total">汇总</ElRadioButton>
          </ElRadioGroup>
        </div>
      </template>
      <div ref="timelineRef" style="height: 260px"></div>
    </ElCard>

    <!-- 处置 & 来源 -->
    <ElRow :gutter="16">
      <!-- 裁决分布 -->
      <ElCol :span="8">
        <ElCard shadow="never" header="裁决分布（verdict）" v-loading="breakdownLoading">
          <ArtRingChart
            height="220px"
            :data="verdictData"
            :show-legend="true"
            legend-position="bottom"
            center-text=""
          />
        </ElCard>
      </ElCol>
      <!-- decidedBy -->
      <ElCol :span="8">
        <ElCard shadow="never" header="决策来源（decidedBy）" v-loading="decidedByLoading">
          <ArtRingChart
            height="220px"
            :data="decidedByData"
            :show-legend="true"
            legend-position="bottom"
            center-text=""
          />
        </ElCard>
      </ElCol>
      <!-- 处置机制 -->
      <ElCol :span="8">
        <ElCard shadow="never" header="处置机制（mechanism）" v-loading="breakdownLoading">
          <ArtRingChart
            height="220px"
            :data="mechanismData"
            :show-legend="true"
            legend-position="bottom"
            center-text=""
          />
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- Top 实体 -->
    <ElRow :gutter="16">
      <ElCol :span="14">
        <ElCard shadow="never" v-loading="topLoading">
          <template #header>
            <div class="flex-b items-center">
              <span class="font-medium">Top 实体</span>
              <ElSelect v-model="topDimension" size="small" style="width:130px" @change="loadTop">
                <ElOption label="IP 地址" value="ip" />
                <ElOption label="设备指纹" value="device" />
                <ElOption label="国家" value="country" />
              </ElSelect>
            </div>
          </template>
          <ArtHBarChart
            height="200px"
            :data="topCounts"
            :x-axis-data="topLabels"
            :colors="['#f56c6c']"
            :show-legend="false"
          />
        </ElCard>
      </ElCol>
      <ElCol :span="10">
        <ElCard shadow="never" header="混合层命中趋势（hybrid_layer）" v-loading="hybridLoading">
          <div ref="hybridRef" style="height: 200px"></div>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 地址池命中分布 -->
    <PoolDistributionChart />

    </div>
  </div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { useResizeObserver, useIntervalFn } from '@vueuse/core'
import { fetchGetTimeline, fetchGetDispositionBreakdown, fetchGetTopEntities } from '@/api/analytics'
import { recentRange, recentLocalRange } from '@/constants/fangyu'
import { DECIDED_BY_LABELS } from '@/constants/disposition'
import PoolDistributionChart from './components/PoolDistributionChart.vue'

defineOptions({ name: 'FangyuAnalytics' })

const granularity  = ref<'hour' | 'day'>('hour')
const trendMode    = ref<'verdict' | 'total'>('verdict')
const topDimension = ref<'ip' | 'device' | 'country'>('ip')
const dateRange    = ref<[string, string]>(recentLocalRange(24))

const dateShortcuts = [
  { text: '近1小时',  value: () => { const r = recentRange(1);   return [r.start, r.end] } },
  { text: '近24小时', value: () => { const r = recentRange(24);  return [r.start, r.end] } },
  { text: '近7天',    value: () => { const r = recentRange(168); return [r.start, r.end] } },
]

const getRange = () =>
  dateRange.value?.length === 2
    ? { start: dateRange.value[0], end: dateRange.value[1] }
    : recentRange(24)

// ── Loading states ────────────────────────────────────────────────────────────
const timelineLoading  = ref(false)
const breakdownLoading = ref(false)
const decidedByLoading = ref(false)
const topLoading       = ref(false)
const hybridLoading    = ref(false)

// ── Ring chart data ───────────────────────────────────────────────────────────
const VERDICT_COLORS: Record<string, string> = {
  trusted: '#67c23a', suspect: '#e6a23c', hostile: '#f56c6c',
}

const verdictData   = ref<{ name: string; value: number }[]>([])
const decidedByData = ref<{ name: string; value: number }[]>([])
const mechanismData = ref<{ name: string; value: number }[]>([])

// ── HBarChart data ────────────────────────────────────────────────────────────
const topLabels = ref<string[]>([])
const topCounts = ref<number[]>([])

// ── ECharts refs ──────────────────────────────────────────────────────────────
const timelineRef = ref<HTMLElement>()
const hybridRef   = ref<HTMLElement>()
let timelineChart: echarts.ECharts | null = null
let hybridChart:   echarts.ECharts | null = null

// timeline raw
let timelineRaw: Api.Fangyu.TimelineBucket[] = []
let hybridRaw:   Api.Fangyu.TimelineBucket[] = []

// ── Render trend ─────────────────────────────────────────────────────────────
function renderTimeline() {
  if (!timelineRef.value) return
  if (!timelineChart) timelineChart = echarts.init(timelineRef.value)

  const buckets = timelineRaw
  if (!buckets.length) { timelineChart.setOption({ series: [] }); return }

  const bucketMap = new Map<string, Record<string, number>>()
  for (const b of buckets) {
    const key = granularity.value === 'hour'
      ? String(b.bucket).slice(11, 16)
      : String(b.bucket).slice(0, 10)
    if (!bucketMap.has(key)) bucketMap.set(key, {})
    const entry = bucketMap.get(key)!
    const v = String(b.verdict || 'unknown')
    entry[v] = (entry[v] || 0) + Number(b.count)
  }
  const xData = [...bucketMap.keys()]

  let series: echarts.SeriesOption[]
  if (trendMode.value === 'verdict') {
    const verdicts = ['trusted', 'suspect', 'hostile']
    series = verdicts.map(v => ({
      name: v,
      type: 'line' as const,
      smooth: true,
      stack: 'total',
      areaStyle: { opacity: 0.2 },
      data: xData.map(k => bucketMap.get(k)?.[v] ?? 0),
      itemStyle: { color: VERDICT_COLORS[v] || '#909399' },
    }))
  } else {
    series = [{
      name: '总量',
      type: 'line' as const,
      smooth: true,
      areaStyle: { opacity: 0.15 },
      data: xData.map(k => Object.values(bucketMap.get(k)!).reduce((a, b) => a + b, 0)),
      itemStyle: { color: '#409eff' },
    }]
  }

  timelineChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: trendMode.value === 'verdict' ? { bottom: 0, textStyle: { fontSize: 11 } } : { show: false },
    xAxis: { type: 'category', data: xData, axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 1 },
    series,
    grid: { left: 44, right: 16, top: 12, bottom: trendMode.value === 'verdict' ? 40 : 36 },
  }, true)
}

// ── Render hybrid trend ───────────────────────────────────────────────────────
function renderHybrid() {
  if (!hybridRef.value) return
  if (!hybridChart) hybridChart = echarts.init(hybridRef.value)

  const buckets = hybridRaw
  if (!buckets.length) {
    hybridChart.setOption({
      graphic: [{ type: 'text', left: 'center', top: 'middle',
        style: { text: '暂无混合层数据', fill: '#909399', fontSize: 12 } }],
      series: [],
    })
    return
  }

  const xData = buckets.map(b =>
    granularity.value === 'hour' ? String(b.bucket).slice(11, 16) : String(b.bucket).slice(0, 10)
  )

  hybridChart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: xData, axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      name: 'hybrid_layer',
      type: 'bar',
      data: buckets.map(b => b.count),
      itemStyle: { color: '#20c997' },
    }],
    grid: { left: 40, right: 16, top: 12, bottom: 40 },
  }, true)
}

// ── Load functions ────────────────────────────────────────────────────────────
const loadTimeline = async () => {
  timelineLoading.value = true
  try {
    const data = await fetchGetTimeline({ ...getRange(), granularity: granularity.value })
    timelineRaw = data as Api.Fangyu.TimelineBucket[]
    renderTimeline()
  } finally { timelineLoading.value = false }
}

const loadBreakdown = async () => {
  breakdownLoading.value = true
  try {
    const data = await fetchGetDispositionBreakdown({ ...getRange() })
    const buckets = data as Api.Fangyu.DispositionBucket[]

    // verdict 环图
    const vMap = new Map<string, number>()
    for (const b of buckets) {
      const k = b.verdict ?? 'unknown'
      vMap.set(k, (vMap.get(k) || 0) + b.count)
    }
    verdictData.value = [...vMap.entries()].map(([name, value]) => ({ name, value }))

    // mechanism 环图
    const mMap = new Map<string, number>()
    for (const b of buckets) {
      const k = b.mechanism ?? b.disposition ?? 'unknown'
      mMap.set(k, (mMap.get(k) || 0) + b.count)
    }
    mechanismData.value = [...mMap.entries()].map(([name, value]) => ({ name, value }))
  } finally { breakdownLoading.value = false }
}

const loadDecidedBy = async () => {
  decidedByLoading.value = true
  try {
    const data = await fetchGetTopEntities({ ...getRange(), dimension: 'decided_by', limit: 20 })
    decidedByData.value = (data as Api.Fangyu.TopEntity[]).map(e => ({
      name: DECIDED_BY_LABELS[e.entity] || e.entity,
      value: e.count,
    }))
  } finally { decidedByLoading.value = false }
}

const loadTop = async () => {
  topLoading.value = true
  try {
    const data = await fetchGetTopEntities({ ...getRange(), dimension: topDimension.value, limit: 10 })
    const entities = (data as Api.Fangyu.TopEntity[]).slice().reverse()
    topLabels.value = entities.map(e => e.entity)
    topCounts.value = entities.map(e => e.count)
  } finally { topLoading.value = false }
}

const loadHybrid = async () => {
  hybridLoading.value = true
  try {
    const data = await fetchGetTimeline({ ...getRange(), granularity: granularity.value, filters: { decided_by: 'hybrid_layer' } })
    hybridRaw = data as Api.Fangyu.TimelineBucket[]
    renderHybrid()
  } finally { hybridLoading.value = false }
}

const loadAll = () => {
  loadTimeline()
  loadBreakdown()
  loadDecidedBy()
  loadTop()
  loadHybrid()
}

// ── Resize ────────────────────────────────────────────────────────────────────
useResizeObserver(timelineRef, () => {
  timelineChart?.resize()
  // 容器从 0 宽度恢复时重新渲染数据
  if (timelineRaw.length) renderTimeline()
})
useResizeObserver(hybridRef, () => {
  hybridChart?.resize()
  if (hybridRaw.length) renderHybrid()
})

const { pause, resume } = useIntervalFn(() => loadAll(), 60_000, { immediate: false })

onMounted(() => { setTimeout(() => { loadAll(); resume() }, 150) })
onActivated(() => { setTimeout(() => { loadAll(); resume() }, 150) })
onDeactivated(() => pause())
onUnmounted(() => { pause(); timelineChart?.dispose(); hybridChart?.dispose() })
</script>
