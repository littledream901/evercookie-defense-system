<!-- 数据概览 -->
<template>
  <div class="art-full-height" style="gap: 16px; overflow-y: auto; padding: 4px;">

    <!-- KPI 卡片行 -->
    <ElRow :gutter="16">
      <ElCol :span="4" v-for="card in kpiCards" :key="card.label">
        <ArtStatsCard
          :icon="card.icon"
          :icon-style="card.iconStyle"
          :count="card.count"
          :description="card.label"
        />
      </ElCol>
    </ElRow>

    <!-- 图表主行 -->
    <ElRow :gutter="16" style="flex: 0 0 auto;">
      <!-- 决策趋势折线图 -->
      <ElCol :span="16">
        <ElCard shadow="never" v-loading="chartsLoading">
          <template #header>
            <div class="flex-b items-center">
              <span class="font-medium">决策趋势（近 24 小时）</span>
              <ElSelect v-model="trendSeries" size="small" style="width:120px" @change="renderTimeline">
                <ElOption label="按裁决分色" value="verdict" />
                <ElOption label="汇总折线" value="total" />
              </ElSelect>
            </div>
          </template>
          <div ref="timelineRef" style="height: 220px"></div>
        </ElCard>
      </ElCol>

      <!-- 处置来源分布（decidedBy） -->
      <ElCol :span="8">
        <ElCard shadow="never" header="决策来源分布" v-loading="chartsLoading">
          <ArtRingChart
            height="220px"
            :data="decidedByData"
            :show-legend="true"
            legend-position="bottom"
            center-text=""
          />
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 底部行：Top IP + 机制分布 -->
    <ElRow :gutter="16" style="flex: 0 0 auto;">
      <ElCol :span="14">
        <ElCard shadow="never" header="Top 10 威胁 IP（近 24h）" v-loading="chartsLoading">
          <ArtHBarChart
            height="180px"
            :data="topIpCounts"
            :x-axis-data="topIpLabels"
            :colors="['#f56c6c']"
            :show-legend="false"
          />
        </ElCard>
      </ElCol>
      <ElCol :span="10">
        <ElCard shadow="never" header="处置机制分布" v-loading="chartsLoading">
          <ArtRingChart
            height="180px"
            :data="mechanismData"
            :show-legend="true"
            legend-position="right"
          />
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 处置动作逻辑合规性占位面板 -->
    <ElRow :gutter="16" style="flex: 0 0 auto;">
      <ElCol :span="24">
        <DispositionAuditPanel />
      </ElCol>
    </ElRow>

  </div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { useResizeObserver, useIntervalFn } from '@vueuse/core'
import { fetchGetTimeline, fetchGetDispositionBreakdown, fetchGetTopEntities } from '@/api/analytics'
import { recentRange } from '@/constants/fangyu'
import { DECIDED_BY_LABELS } from '@/constants/disposition'
import DispositionAuditPanel from './components/DispositionAuditPanel.vue'

defineOptions({ name: 'FangyuDashboard' })

const chartsLoading = ref(false)
const trendSeries   = ref<'verdict' | 'total'>('verdict')
const timelineRef   = ref<HTMLElement>()
let   timelineChart: echarts.ECharts | null = null

// ── KPI ──────────────────────────────────────────────────────────────────────
const kpiCards = ref([
  { label: '近24h 决策量',  count: 0, icon: 'ri:cursor-line',         iconStyle: 'bg-blue-500'   },
  { label: '威胁拦截',       count: 0, icon: 'ri:shield-keyhole-line', iconStyle: 'bg-red-500'    },
  { label: '可疑访客',       count: 0, icon: 'ri:alert-line',          iconStyle: 'bg-orange-500' },
  { label: '规则命中',       count: 0, icon: 'ri:git-branch-line',     iconStyle: 'bg-purple-500' },
  { label: '混合层拦截',     count: 0, icon: 'ri:stack-line',          iconStyle: 'bg-teal-500'   },
  { label: '放行',           count: 0, icon: 'ri:check-double-line',   iconStyle: 'bg-green-500'  },
])

// ── 图表数据 ──────────────────────────────────────────────────────────────────
// timeline 原始（按 verdict 分组）
let timelineRaw: Api.Fangyu.TimelineBucket[] = []

// Ring chart data
const decidedByData = ref<{ name: string; value: number }[]>([])
const mechanismData = ref<{ name: string; value: number }[]>([])

// HBarChart: top IP
const topIpLabels = ref<string[]>([])
const topIpCounts = ref<number[]>([])

// ── 渲染趋势图 ────────────────────────────────────────────────────────────────
const VERDICT_COLORS: Record<string, string> = {
  trusted: '#67c23a',
  suspect: '#e6a23c',
  hostile: '#f56c6c',
}

function renderTimeline() {
  if (!timelineRef.value) return
  if (!timelineChart) timelineChart = echarts.init(timelineRef.value)

  const buckets = timelineRaw
  if (!buckets.length) { timelineChart.setOption({ series: [] }); return }

  const bucketMap = new Map<string, Record<string, number>>()
  for (const b of buckets) {
    const key = String(b.bucket).slice(11, 16)  // HH:mm
    if (!bucketMap.has(key)) bucketMap.set(key, {})
    const entry = bucketMap.get(key)!
    const v = String(b.verdict || 'unknown')
    entry[v] = (entry[v] || 0) + Number(b.count)
  }
  const xData = [...bucketMap.keys()]

  let series: echarts.SeriesOption[]
  if (trendSeries.value === 'verdict') {
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
    legend: trendSeries.value === 'verdict' ? { bottom: 0, textStyle: { fontSize: 11 } } : { show: false },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 1 },
    series,
    grid: { left: 40, right: 16, top: 12, bottom: trendSeries.value === 'verdict' ? 36 : 24 },
  }, true)
}

// ── 加载数据 ──────────────────────────────────────────────────────────────────
const loadData = async () => {
  chartsLoading.value = true
  try {
    const range = recentRange(24)
    const [timeline, breakdown, decidedByRaw, topIps] = await Promise.all([
      fetchGetTimeline({ start: range.start, end: range.end, granularity: 'hour' }),
      fetchGetDispositionBreakdown({ start: range.start, end: range.end }),
      fetchGetTopEntities({ start: range.start, end: range.end, dimension: 'decided_by', limit: 20 }),
      fetchGetTopEntities({ start: range.start, end: range.end, dimension: 'ip', limit: 10 }),
    ])

    // ── KPI 计算 ──
    const tl = timeline as Api.Fangyu.TimelineBucket[]
    timelineRaw = tl

    const total   = tl.reduce((s, b) => s + Number(b.count), 0)
    const hostile = tl.filter(b => b.verdict === 'hostile').reduce((s, b) => s + Number(b.count), 0)
    const suspect = tl.filter(b => b.verdict === 'suspect').reduce((s, b) => s + Number(b.count), 0)
    const trusted = tl.filter(b => b.verdict === 'trusted').reduce((s, b) => s + Number(b.count), 0)

    const dbRaw = decidedByRaw as Api.Fangyu.TopEntity[]
    const ruleHits   = dbRaw.find(e => e.entity === 'decision_rule')?.count ?? 0
    const hybridHits = dbRaw.find(e => e.entity === 'hybrid_layer')?.count ?? 0

    kpiCards.value[0].count = total
    kpiCards.value[1].count = hostile
    kpiCards.value[2].count = suspect
    kpiCards.value[3].count = ruleHits
    kpiCards.value[4].count = hybridHits
    kpiCards.value[5].count = trusted

    // ── decidedBy 环图 ──
    decidedByData.value = dbRaw.map(e => ({
      name: DECIDED_BY_LABELS[e.entity] || e.entity,
      value: e.count,
    }))

    // ── mechanism 环图 ──
    const mechRaw = breakdown as Api.Fangyu.DispositionBucket[]
    const mechMap = new Map<string, number>()
    for (const b of mechRaw) {
      const k = b.mechanism || b.disposition
      mechMap.set(k, (mechMap.get(k) || 0) + b.count)
    }
    mechanismData.value = [...mechMap.entries()].map(([name, value]) => ({ name, value }))

    // ── Top IP HBar ──
    const ipData = (topIps as Api.Fangyu.TopEntity[]).slice().reverse()
    topIpLabels.value = ipData.map(e => e.entity)
    topIpCounts.value = ipData.map(e => e.count)

    renderTimeline()
  } finally {
    chartsLoading.value = false
  }
}

useResizeObserver(timelineRef, () => timelineChart?.resize())

const { pause, resume } = useIntervalFn(() => loadData(), 30_000, { immediate: false })

onMounted(() => { loadData(); resume() })
onActivated(() => { loadData(); resume() })
onDeactivated(() => pause())
onUnmounted(() => { pause(); timelineChart?.dispose() })
</script>
