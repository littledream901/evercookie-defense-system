<!-- 爬虫分析视图 -->
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Icon } from '@iconify/vue'
import { getAccessLogCrawlerOverview, getAccessLogCrawlerVendorDistribution, getAccessLogCrawlerCategoryDistribution, getAccessLogCrawlerTopList, getAccessLogCrawlerTimeline } from '@/api/fangyu/access-logs'
import { getCrawlerDetail, getSubcategoryLabel } from '@/constants/crawlerDetails'
import * as echarts from 'echarts'

// 站点 ID（TODO: 从路由参数或全局状态获取）
const siteId = ref<number>()

// ========== 筛选条件 ==========
const dateRange = ref<[string, string]>([
  new Date(Date.now() - 24 * 3600 * 1000).toISOString().slice(0, 19),
  new Date().toISOString().slice(0, 19)
])
const granularity = ref<'hour' | 'day'>('hour')

// 日期快捷选项
const dateShortcuts = [
  { text: '最近1小时', value: () => [new Date(Date.now() - 3600 * 1000), new Date()] },
  { text: '最近6小时', value: () => [new Date(Date.now() - 6 * 3600 * 1000), new Date()] },
  { text: '最近24小时', value: () => [new Date(Date.now() - 24 * 3600 * 1000), new Date()] },
  { text: '最近7天', value: () => [new Date(Date.now() - 7 * 24 * 3600 * 1000), new Date()] }
]

// ========== 加载状态 ==========
const overviewLoading = ref(false)
const timelineLoading = ref(false)
const vendorLoading = ref(false)
const categoryLoading = ref(false)
const topLoading = ref(false)

// ========== 数据状态 ==========
const overviewData = ref<any>({})
const timelineData = ref<any[]>([])
const vendorData = ref<any[]>([])
const categoryData = ref<any[]>([])
const topListData = ref<any[]>([])

// ========== 图表引用 ==========
const timelineChartRef = ref<HTMLDivElement>()
const vendorChartRef = ref<HTMLDivElement>()
const categoryChartRef = ref<HTMLDivElement>()
let timelineChart: echarts.ECharts | null = null
let vendorChart: echarts.ECharts | null = null
let categoryChart: echarts.ECharts | null = null

// ========== 计算属性 ==========
const crawlerPercentage = computed(() => {
  if (!overviewData.value.total_requests) return 0
  return ((overviewData.value.crawler_requests / overviewData.value.total_requests) * 100).toFixed(2)
})

// ========== 加载数据 ==========
async function loadOverview() {
  if (!dateRange.value) return
  overviewLoading.value = true
  try {
    const resp = await getAccessLogCrawlerOverview({
      siteId: siteId.value,
      start: dateRange.value[0],
      end: dateRange.value[1]
    })
    overviewData.value = resp.data || {}
  } catch (err: any) {
    ElMessage.error(err.message || '加载概览数据失败')
  } finally {
    overviewLoading.value = false
  }
}

async function loadTimeline() {
  if (!dateRange.value) return
  timelineLoading.value = true
  try {
    const resp = await getAccessLogCrawlerTimeline({
      siteId: siteId.value,
      start: dateRange.value[0],
      end: dateRange.value[1],
      granularity: granularity.value
    })
    timelineData.value = resp.data || []
    renderTimeline()
  } catch (err: any) {
    ElMessage.error(err.message || '加载趋势数据失败')
  } finally {
    timelineLoading.value = false
  }
}

async function loadVendorDistribution() {
  if (!dateRange.value) return
  vendorLoading.value = true
  try {
    const resp = await getAccessLogCrawlerVendorDistribution({
      siteId: siteId.value,
      start: dateRange.value[0],
      end: dateRange.value[1]
    })
    vendorData.value = resp.data || []
    renderVendorChart()
  } catch (err: any) {
    ElMessage.error(err.message || '加载厂商分布失败')
  } finally {
    vendorLoading.value = false
  }
}

async function loadCategoryDistribution() {
  if (!dateRange.value) return
  categoryLoading.value = true
  try {
    const resp = await getAccessLogCrawlerCategoryDistribution({
      siteId: siteId.value,
      start: dateRange.value[0],
      end: dateRange.value[1]
    })
    categoryData.value = resp.data || []
    renderCategoryChart()
  } catch (err: any) {
    ElMessage.error(err.message || '加载分类分布失败')
  } finally {
    categoryLoading.value = false
  }
}

async function loadTopList() {
  if (!dateRange.value) return
  topLoading.value = true
  try {
    const resp = await getAccessLogCrawlerTopList({
      siteId: siteId.value,
      start: dateRange.value[0],
      end: dateRange.value[1],
      limit: 20
    })
    topListData.value = resp.data || []
  } catch (err: any) {
    ElMessage.error(err.message || '加载Top列表失败')
  } finally {
    topLoading.value = false
  }
}

async function loadAll() {
  await Promise.all([
    loadOverview(),
    loadTimeline(),
    loadVendorDistribution(),
    loadCategoryDistribution(),
    loadTopList()
  ])
}

// ========== 渲染图表 ==========
function renderTimeline() {
  if (!timelineChartRef.value || !timelineData.value.length) return
  
  if (!timelineChart) {
    timelineChart = echarts.init(timelineChartRef.value)
  }
  
  const times = timelineData.value.map(item => item.time_bucket)
  const crawlerCounts = timelineData.value.map(item => item.crawler_count)
  const nonCrawlerCounts = timelineData.value.map(item => item.non_crawler_count)
  
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: {
      data: ['爬虫流量', '真实用户流量'],
      bottom: 0
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '12%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: times
    },
    yAxis: {
      type: 'value',
      name: '请求数'
    },
    series: [
      {
        name: '爬虫流量',
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.3 },
        data: crawlerCounts,
        itemStyle: { color: '#f56c6c' }
      },
      {
        name: '真实用户流量',
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.3 },
        data: nonCrawlerCounts,
        itemStyle: { color: '#67c23a' }
      }
    ]
  }
  
  timelineChart.setOption(option)
}

function renderVendorChart() {
  if (!vendorChartRef.value || !vendorData.value.length) return
  
  if (!vendorChart) {
    vendorChart = echarts.init(vendorChartRef.value)
  }
  
  const data = vendorData.value.map((item: any) => ({
    name: item.crawler_vendor || '未知',
    value: item.request_count
  }))
  
  const option = {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'horizontal',
      bottom: 0,
      type: 'scroll'
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: false,
        label: {
          show: false
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: 'bold'
          }
        },
        data
      }
    ]
  }
  
  vendorChart.setOption(option)
}

function renderCategoryChart() {
  if (!categoryChartRef.value || !categoryData.value.length) return
  
  if (!categoryChart) {
    categoryChart = echarts.init(categoryChartRef.value)
  }
  
  const categoryLabels: Record<string, string> = {
    search_engine: '搜索引擎',
    ai_crawler: 'AI爬虫',
    advertising: '广告',
    social_media: '社交媒体',
    seo_tool: 'SEO工具',
    e_commerce: '电商',
    monitoring: '监控',
    archiving: '存档',
    accessibility: '无障碍',
    other: '其他'
  }
  
  const data = categoryData.value.map((item: any) => ({
    name: categoryLabels[item.crawler_category] || item.crawler_category || '未知',
    value: item.request_count
  }))
  
  const option = {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'horizontal',
      bottom: 0,
      type: 'scroll'
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: false,
        label: {
          show: false
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: 'bold'
          }
        },
        data
      }
    ]
  }
  
  categoryChart.setOption(option)
}

// ========== 生命周期 ==========
onMounted(() => {
  loadAll()
  
  // 监听窗口大小变化
  window.addEventListener('resize', () => {
    timelineChart?.resize()
    vendorChart?.resize()
    categoryChart?.resize()
  })
})
</script>

<template>
  <div class="art-full-height overflow-y-auto">
    <div class="flex flex-col gap-4 pb-4">
      
      <!-- 筛选栏 -->
      <ElCard shadow="never">
        <ElSpace wrap>
          <ElDatePicker 
            v-model="dateRange" 
            type="datetimerange"
            start-placeholder="开始时间" 
            end-placeholder="结束时间"
            value-format="YYYY-MM-DDTHH:mm:ss" 
            :shortcuts="dateShortcuts"
          />
          <ElSelect v-model="granularity" class="w-28">
            <ElOption label="按小时" value="hour" />
            <ElOption label="按天" value="day" />
          </ElSelect>
          <ElButton type="primary" @click="loadAll">刷新</ElButton>
        </ElSpace>
      </ElCard>

      <!-- 概览卡片 -->
      <ElRow :gutter="16">
        <ElCol :span="6">
          <ElCard shadow="never" v-loading="overviewLoading">
            <div class="stat-card">
              <div class="stat-icon" style="background: #fef0f0">
                <Icon icon="icon-park-outline:trend" width="32" height="32" style="color: #f56c6c"/>
              </div>
              <div class="stat-content">
                <div class="stat-label">总请求数</div>
                <div class="stat-value">{{ overviewData.total_requests?.toLocaleString() || 0 }}</div>
              </div>
            </div>
          </ElCard>
        </ElCol>
        <ElCol :span="6">
          <ElCard shadow="never" v-loading="overviewLoading">
            <div class="stat-card">
              <div class="stat-icon" style="background: #fef5e7">
                <Icon icon="icon-park-outline:histogram" width="32" height="32" style="color: #e6a23c"/>
              </div>
              <div class="stat-content">
                <div class="stat-label">爬虫请求数</div>
                <div class="stat-value">{{ overviewData.crawler_requests?.toLocaleString() || 0 }}</div>
                <div class="stat-extra">占比 {{ crawlerPercentage }}%</div>
              </div>
            </div>
          </ElCard>
        </ElCol>
        <ElCol :span="6">
          <ElCard shadow="never" v-loading="overviewLoading">
            <div class="stat-card">
              <div class="stat-icon" style="background: #e8f4ff">
                <Icon icon="icon-park-outline:trend" width="32" height="32" style="color: #409eff"/>
              </div>
              <div class="stat-content">
                <div class="stat-label">唯一爬虫数</div>
                <div class="stat-value">{{ overviewData.unique_crawlers || 0 }}</div>
              </div>
            </div>
          </ElCard>
        </ElCol>
        <ElCol :span="6">
          <ElCard shadow="never" v-loading="overviewLoading">
            <div class="stat-card">
              <div class="stat-icon" style="background: #fef0f0">
                <Icon icon="icon-park-outline:trend" width="32" height="32" style="color: #f56c6c"/>
              </div>
              <div class="stat-content">
                <div class="stat-label">恶意爬虫请求</div>
                <div class="stat-value">{{ overviewData.hostile_crawler_requests?.toLocaleString() || 0 }}</div>
              </div>
            </div>
          </ElCard>
        </ElCol>
      </ElRow>

      <!-- 流量趋势图 -->
      <ElCard shadow="never" v-loading="timelineLoading">
        <template #header>
          <span class="font-medium">爬虫流量趋势（爬虫 vs 真实用户）</span>
        </template>
        <div ref="timelineChartRef" style="height: 300px"></div>
      </ElCard>

      <!-- 厂商分布 & 分类分布 -->
      <ElRow :gutter="16">
        <ElCol :span="12">
          <ElCard shadow="never" v-loading="vendorLoading">
            <template #header>
              <span class="font-medium">爬虫厂商分布</span>
            </template>
            <div ref="vendorChartRef" style="height: 280px;"></div>
          </ElCard>
        </ElCol>
        <ElCol :span="12">
          <ElCard shadow="never" v-loading="categoryLoading">
            <template #header>
              <span class="font-medium">爬虫分类分布</span>
            </template>
            <div ref="categoryChartRef" style="height: 280px;"></div>
          </ElCard>
        </ElCol>
      </ElRow>

      <!-- Top 爬虫列表 -->
      <ElCard shadow="never" v-loading="topLoading">
        <template #header>
          <span class="font-medium">访问频率 Top 20 爬虫</span>
        </template>
        <ElTable :data="topListData" stripe>
          <ElTableColumn label="爬虫名称" min-width="180">
            <template #default="{ row }">
              <div class="crawler-name-cell">
                <span class="crawler-icon-sm">{{ getCrawlerDetail(row.crawler_name)?.icon || '🤖' }}</span>
                <span class="crawler-name-text">{{ getCrawlerDetail(row.crawler_name)?.displayName || row.crawler_name }}</span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="crawler_vendor" label="厂商" width="120">
            <template #default="{ row }">
              {{ getCrawlerDetail(row.crawler_name)?.vendorName || row.crawler_vendor || '-' }}
            </template>
          </ElTableColumn>
          <ElTableColumn label="分类" width="120">
            <template #default="{ row }">
              <ElTag size="small" :type="row.crawler_category === 'ai_crawler' ? 'danger' : 'info'">
                {{ getCrawlerDetail(row.crawler_name)?.subcategory ? getSubcategoryLabel(getCrawlerDetail(row.crawler_name)!.subcategory) : (row.crawler_category || '-') }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="request_count" label="请求数" width="120" sortable>
            <template #default="{ row }">
              {{ row.request_count?.toLocaleString() }}
            </template>
          </ElTableColumn>
          <ElTableColumn prop="unique_ips" label="唯一IP" width="100" sortable />
          <ElTableColumn prop="blocked_count" label="被拦截" width="100" sortable>
            <template #default="{ row }">
              <span :class="row.blocked_count > 0 ? 'text-red-500' : ''">
                {{ row.blocked_count }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="first_seen_at" label="首次访问" width="160" />
          <ElTableColumn prop="last_seen_at" label="最后访问" width="160" />
        </ElTable>
      </ElCard>

    </div>
  </div>
</template>

<style scoped lang="scss">
.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  
  .stat-icon {
    width: 64px;
    height: 64px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  
  .stat-content {
    flex: 1;
    
    .stat-label {
      font-size: 14px;
      color: #909399;
      margin-bottom: 4px;
    }
    
    .stat-value {
      font-size: 24px;
      font-weight: 600;
      color: #303133;
      line-height: 1.2;
    }
    
    .stat-extra {
      font-size: 12px;
      color: #909399;
      margin-top: 4px;
    }
  }
}

.crawler-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  
  .crawler-icon-sm {
    font-size: 18px;
    flex-shrink: 0;
  }
  
  .crawler-name-text {
    font-weight: 500;
  }
}
</style>
