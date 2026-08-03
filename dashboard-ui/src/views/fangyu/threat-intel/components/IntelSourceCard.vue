<template>
  <ElCard class="source-card mt-3 shrink-0" shadow="never" :body-style="{ padding: '12px 16px' }">
    <div class="flex items-center justify-between mb-2">
      <div class="flex items-center gap-2">
        <span class="text-sm font-medium">{{ title }}</span>
        <ElTooltip :content="hint" placement="top">
          <ElIcon class="text-g-400 cursor-help"><QuestionFilled /></ElIcon>
        </ElTooltip>
      </div>
      <ElButton
        v-if="mode === 'external'"
        v-auth="'threat_intel.write'"
        type="primary"
        size="small"
        :loading="syncing"
        @click="handleSyncAll"
      >
        立即同步
      </ElButton>
    </div>

    <div v-loading="loading" class="source-rows">
      <div
        v-for="s in rows"
        :key="s.key"
        class="flex items-center gap-3 py-2 border-b last:border-0"
      >
        <ElTag :type="s.tagType" size="small" class="shrink-0">{{ s.tagText }}</ElTag>
        <div class="min-w-0 flex-1">
          <div class="text-sm truncate">{{ s.name }}</div>
          <div class="text-xs text-g-500 truncate">{{ s.description }}</div>
        </div>
        <div class="text-right shrink-0 w-20">
          <div class="text-base font-semibold leading-none">{{ s.count }}</div>
          <div class="text-xs text-g-400 mt-1">{{ countLabel }}</div>
        </div>
        <ElButton
          v-if="mode === 'preset'"
          v-auth="'threat_intel.write'"
          size="small"
          :loading="loadingPreset === s.key"
          @click="handleLoadPreset(s.key)"
        >
          载入
        </ElButton>
      </div>

      <ElEmpty v-if="!loading && !rows.length" description="暂无可用数据源" :image-size="48" />
    </div>

    <div v-if="lastResult" class="text-xs text-g-500 mt-2">
      上次同步：写入 {{ lastResult.imported }} 条<template v-if="lastResult.skipped != null">
        ，跳过重复 {{ lastResult.skipped }} 条</template>
    </div>
  </ElCard>
</template>

<style scoped>
.source-card :deep(.el-card__body) {
  padding: 12px 16px;
}
</style>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import {
  fetchGetExternalSources,
  fetchSyncExternalIntel,
  fetchGetIntelExternalSources,
  fetchSyncIntelExternal,
  fetchGetIntelPresets,
  fetchLoadIntelPreset
} from '@/api/threat-intel'

interface Props {
  /** external = 真外部 HTTP 源；preset = 内置预设常量（ASN / 爬虫） */
  mode: 'external' | 'preset'
  /**
   * mode=preset 时必填，用于拼 /intelligence/{type}/presets。
   * mode=external 时可选：传了走 /intelligence/{type}/external-sources，
   * 不传则走 IP 威胁库专用的 /threat-intel/external-sources。
   */
  intelType?: string
}

const props = defineProps<Props>()

/** 载入/同步成功后通知父级刷新列表 */
const emit = defineEmits<{ (e: 'synced'): void }>()

interface SourceRow {
  key: string
  name: string
  description: string
  count: number | string
  tagText: string
  tagType: 'success' | 'warning' | 'info'
}

const loading = ref(false)
const syncing = ref(false)
const loadingPreset = ref<string | null>(null)
const rows = ref<SourceRow[]>([])
const lastResult = ref<{ imported: number; skipped?: number } | null>(null)

const title = computed(() =>
  props.mode === 'external' ? '外部情报源' : '内置预设数据源'
)

const countLabel = computed(() => (props.mode === 'external' ? '已入库' : '可载入'))

const hint = computed(() => {
  if (props.mode !== 'external') {
    return '预设数据来自系统内置常量，与决策链路的既有认定一致。重复条目会自动跳过。'
  }
  return props.intelType
    ? '拉取各云厂商官方公布的网段清单，标记为数据中心。已存在的网段会跳过，不会覆盖人工修正。'
    : '定时任务每 6 小时自动拉取一次。AbuseIPDB 需在服务器配置环境变量 ABUSEIPDB_API_KEY。'
})

async function loadExternal() {
  const res = props.intelType
    ? await fetchGetIntelExternalSources(props.intelType)
    : await fetchGetExternalSources()
  rows.value = (res?.sources ?? []).map((s) => {
    const unconfigured = s.requiresApiKey && !s.configured
    return {
      key: s.id,
      name: s.name,
      description: s.description,
      count: s.entry_count ?? 0,
      tagText: s.enabled ? (unconfigured ? '未配置 Key' : '已启用') : '已禁用',
      tagType: s.enabled ? (unconfigured ? 'warning' : 'success') : 'info'
    }
  })
}

async function loadPresets() {
  const res = await fetchGetIntelPresets(props.intelType!)
  rows.value = (res?.sources ?? []).map((s) => ({
    key: s.name,
    name: s.label,
    description: s.description,
    count: s.entry_count,
    tagText: '内置',
    tagType: 'info' as const
  }))
}

async function loadSources() {
  loading.value = true
  try {
    await (props.mode === 'external' ? loadExternal() : loadPresets())
  } catch {
    rows.value = []
  } finally {
    loading.value = false
  }
}

async function handleSyncAll() {
  syncing.value = true
  try {
    const res = props.intelType
      ? await fetchSyncIntelExternal(props.intelType)
      : await fetchSyncExternalIntel()
    lastResult.value = res
    ElMessage.success(`同步完成，写入 ${res.imported} 条`)
    await loadSources()
    emit('synced')
  } catch {
    ElMessage.error('外部情报源同步失败')
  } finally {
    syncing.value = false
  }
}

async function handleLoadPreset(name: string) {
  loadingPreset.value = name
  try {
    const res = await fetchLoadIntelPreset(props.intelType!, name)
    lastResult.value = res
    ElMessage.success(`预设载入成功：${res.imported} 条`)
    emit('synced')
  } catch {
    ElMessage.error('载入失败')
  } finally {
    loadingPreset.value = null
  }
}

defineExpose({ loadSources })

onMounted(loadSources)
</script>
