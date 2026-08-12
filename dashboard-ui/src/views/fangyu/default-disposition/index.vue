<template>
  <div class="art-full-height" style="overflow-y: auto; padding: 4px;">
    <div class="mb-3">
      <h2 class="text-lg font-medium text-g-900">默认处置</h2>
      <p class="mt-1 text-sm text-g-600">
        当访客请求穿透所有前置阶段（无规则命中、未触发安全检查/威胁情报、评分未达阈值或评分关闭）时，
        用此处置兜底。站点有独立配置则覆盖全局，否则继承全局；全局也未配置则回退系统默认（放行）。
      </p>
    </div>

    <ElTabs v-model="activeTab" @tab-change="onTabChange">
      <ElTabPane label="全局配置" name="global">
        <ElAlert type="info" show-icon :closable="false" class="mb-4">
          全局默认处置作用于所有未单独配置的站点。修改后将同步到网关节点。
        </ElAlert>
      </ElTabPane>

      <ElTabPane label="当前站点" name="site">
        <div class="mb-4 flex items-center gap-3">
          <span class="text-sm text-g-600">选择站点：</span>
          <ElSelect
            v-model="selectedSiteId"
            filterable
            placeholder="请选择站点"
            :loading="siteListLoading"
            style="width: 300px"
            @change="onSiteChange"
          >
            <ElOption
              v-for="site in siteList"
              :key="site.id"
              :label="`${site.name} (ID: ${site.id})`"
              :value="site.id"
            />
          </ElSelect>
        </div>

        <ElAlert v-if="selectedSiteId && !hasSiteConfig" type="success" show-icon :closable="false" class="mb-4">
          <template #title>
            <div class="flex items-center justify-between">
              <span>当前站点继承全局配置</span>
              <ElButton link type="primary" @click="activeTab = 'global'">查看全局配置</ElButton>
            </div>
          </template>
          <div class="mt-2 text-xs text-g-600">
            继承的全局处置：
            <ElTag size="small" class="ml-1">{{ mechanismLabel(globalMechanism) }}</ElTag>
          </div>
        </ElAlert>

        <ElAlert v-else-if="selectedSiteId && hasSiteConfig" type="warning" show-icon :closable="false" class="mb-4">
          当前站点使用独立配置，不受全局配置影响。
        </ElAlert>

        <ElEmpty v-if="!selectedSiteId" description="请先选择站点" />
      </ElTabPane>
    </ElTabs>

    <!-- 处置编辑器（全局/站点共用） -->
    <ElCard shadow="never" class="mb-4">
      <template #header>
        <div class="flex items-center justify-between">
          <span>处置策略</span>
          <span class="text-xs text-g-500">
            该机制将判定为
            <ElTag size="small" :type="verdictTag">{{ verdictLabel }}</ElTag>
          </span>
        </div>
      </template>

      <div class="flex flex-col gap-3">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-sm text-g-600 w-20">机制</span>
          <ElSelect
            v-model="disposition.mechanism"
            size="small"
            class="!w-44"
            @change="onMechanismChange"
          >
            <ElOption v-for="o in MECHANISM_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </ElSelect>

          <ElSelect
            v-if="disposition.mechanism === 'challenge'"
            v-model="disposition.challengeKind"
            size="small"
            class="!w-36"
            placeholder="挑战类型"
          >
            <ElOption
              v-for="o in CHALLENGE_KIND_OPTIONS"
              :key="o.value"
              :label="o.label"
              :value="o.value"
            />
          </ElSelect>
        </div>

        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-sm text-g-600 w-20">目标</span>
          <ElSelect
            v-if="targetKindOptionsFor(disposition.mechanism).length > 1"
            v-model="disposition.target.kind"
            size="small"
            class="!w-44"
            @change="onTargetKindChange"
          >
            <ElOption
              v-for="o in targetKindOptionsFor(disposition.mechanism)"
              :key="o.value"
              :label="o.label"
              :value="o.value"
            />
          </ElSelect>

          <span v-else class="text-sm text-g-400">
            {{ targetKindOptionsFor(disposition.mechanism)[0]?.label ?? '原始目标' }}
          </span>
        </div>

        <ElSelect
          v-if="disposition.target.kind === 'page_resource'"
          v-model="disposition.target.url"
          size="small"
          filterable
          :loading="pageResourceLoading"
          placeholder="选择要投放的页面资源"
          class="!w-80"
          @visible-change="(v: boolean) => v && loadPageResources()"
        >
          <ElOption v-for="r in pageResourceOptions" :key="r.value" :label="r.label" :value="r.value" />
          <template #empty>
            <div class="px-3 py-2 text-xs text-g-500">
              暂无已启用的页面资源，请先到「页面资源」页新建
            </div>
          </template>
        </ElSelect>

        <ElInput
          v-else-if="disposition.target.kind === 'url' || (URL_REQUIRED_MECHANISMS.includes(disposition.mechanism) && disposition.target.kind !== 'url_pool')"
          v-model="disposition.target.url"
          size="small"
          placeholder="跳转目标 URL，如 https://example.com/block"
          class="!w-80"
        />

        <RotationPoolEditor
          v-if="disposition.target.kind === 'url_pool' && disposition.target.rotation"
          v-model:rotation="disposition.target.rotation"
        />
      </div>
    </ElCard>

    <!-- 操作 -->
    <div class="mb-4 flex items-center justify-between">
      <span v-if="loadError" class="text-sm text-danger">{{ loadError }}</span>
      <span v-else class="text-sm text-g-500">
        {{ activeTab === 'global' ? '全局配置' : `站点 ${selectedSiteId ?? '未选择'}` }}
      </span>
      <div class="flex items-center gap-2">
        <ElButton
          v-auth="'app.write'"
          :disabled="saving || !canOperate || (activeTab === 'site' && !hasSiteConfig)"
          @click="resetConfig"
        >
          {{ activeTab === 'global' ? '恢复默认' : '删除站点配置' }}
        </ElButton>
        <ElButton
          type="primary"
          v-auth="'app.write'"
          :loading="saving"
          :disabled="!canOperate || !!loadError"
          @click="saveConfig"
        >
          保存配置
        </ElButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  MECHANISM_OPTIONS, CHALLENGE_KIND_OPTIONS, URL_REQUIRED_MECHANISMS,
  createDecisionDisposition, targetKindOptionsFor, defaultTargetKindFor,
  validateDisposition, createRotation, VERDICT_OPTIONS, VERDICT_TAGS,
  verdictForMechanism
} from '@/constants/disposition'
import RotationPoolEditor from '@/components/RotationPoolEditor.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  fetchGetGlobalDefaultDisposition, fetchPutGlobalDefaultDisposition, fetchResetGlobalDefaultDisposition,
  fetchGetDefaultDisposition, fetchPutDefaultDisposition, fetchResetDefaultDisposition
} from '@/api/default-disposition'
import { fetchGetSiteList } from '@/api/apps'
import { fetchGetPageResourceList } from '@/api/page-resources'

defineOptions({ name: 'FangyuDefaultDisposition' })

const activeTab = ref<'global' | 'site'>('global')

const siteList = ref<Array<{ id: number; name: string }>>([])
const siteListLoading = ref(false)
const selectedSiteId = ref<number | null>(null)
const hasSiteConfig = ref(false)

const disposition = reactive<Api.Fangyu.DecisionDisposition>(createDecisionDisposition())
const saving = ref(false)
const loadError = ref('')

// 全局配置（用于站点继承展示）
const globalMechanism = ref('pass')

const canOperate = computed(() => activeTab.value === 'global' || !!selectedSiteId.value)

const verdictLabel = computed(() => {
  const v = verdictForMechanism(disposition.mechanism)
  return VERDICT_OPTIONS.find(o => o.value === v)?.label ?? v
})
const verdictTag = computed(() => VERDICT_TAGS[verdictForMechanism(disposition.mechanism)] ?? 'info')

function mechanismLabel(mech: string): string {
  return MECHANISM_OPTIONS.find(o => o.value === mech)?.label ?? mech
}

/* ── 机制 / 目标切换时同步纠正 ── */
function onMechanismChange() {
  const mech = disposition.mechanism
  disposition.challengeKind = mech === 'challenge' ? (disposition.challengeKind ?? 'captcha') : null

  const allowed = targetKindOptionsFor(mech).map(o => o.value)
  if (!allowed.includes(disposition.target.kind)) {
    disposition.target.kind = defaultTargetKindFor(mech)
  }
  if (!URL_REQUIRED_MECHANISMS.includes(mech) && disposition.target.kind !== 'page_resource') {
    disposition.target.url = null
  }
  if (disposition.target.kind !== 'url_pool') {
    disposition.target.rotation = null
  }
}

function onTargetKindChange() {
  disposition.target.url = null
  if (disposition.target.kind === 'url_pool') {
    if (!disposition.target.rotation) {
      disposition.target.rotation = createRotation()
    }
  } else {
    disposition.target.rotation = null
  }
}

/* ── 页面资源选项 ── */
const pageResourceOptions = ref<{ label: string; value: string }[]>([])
const pageResourceLoading = ref(false)
let pageResourceLoaded = false

async function loadPageResources() {
  if (pageResourceLoaded) return
  pageResourceLoading.value = true
  try {
    const res = await fetchGetPageResourceList({ enabled: true, page: 1, pageSize: 100 })
    pageResourceOptions.value = (res?.items ?? []).map((r: any) => ({
      label: `${r.name}（${r.kind === 'safe' ? '正常分支' : '阻断/质疑'}）`,
      value: r.name
    }))
    pageResourceLoaded = true
  } finally {
    pageResourceLoading.value = false
  }
}

/* ── 站点列表 ── */
async function loadSiteList() {
  siteListLoading.value = true
  try {
    const res = await fetchGetSiteList({ page: 1, pageSize: 1000 })
    siteList.value = res.items.map(site => ({ id: site.id, name: site.name }))
  } catch (err) {
    console.error('加载站点列表失败:', err)
    ElMessage.error('站点列表加载失败')
  } finally {
    siteListLoading.value = false
  }
}

/* ── 加载 ── */
function applyDisposition(d: Api.Fangyu.Disposition) {
  disposition.mechanism = d.mechanism
  disposition.challengeKind = d.challengeKind
  disposition.ttlSeconds = d.ttlSeconds
  disposition.target = {
    kind: d.target.kind,
    url: d.target.url ?? null,
    urls: d.target.urls ?? null,
    rotation: d.target.rotation ?? null,
    httpStatus: d.target.httpStatus ?? null
  }
}

async function loadConfig() {
  loadError.value = ''
  hasSiteConfig.value = false

  if (activeTab.value === 'global') {
    const cfg = await fetchGetGlobalDefaultDisposition()
    if (cfg) {
      applyDisposition(cfg.disposition)
      globalMechanism.value = cfg.disposition.mechanism
    } else {
      Object.assign(disposition, createDecisionDisposition())
      globalMechanism.value = 'pass'
    }
  } else {
    if (!selectedSiteId.value) return
    try {
      const cfg = await fetchGetDefaultDisposition(selectedSiteId.value)
      if (cfg) {
        hasSiteConfig.value = true
        applyDisposition(cfg.disposition)
      } else {
        // 继承全局
        const globalCfg = await fetchGetGlobalDefaultDisposition()
        if (globalCfg) {
          applyDisposition(globalCfg.disposition)
          globalMechanism.value = globalCfg.disposition.mechanism
        } else {
          Object.assign(disposition, createDecisionDisposition())
          globalMechanism.value = 'pass'
        }
      }
    } catch (err: any) {
      loadError.value = '默认处置加载失败，保存已被禁用'
      console.error('加载默认处置失败:', err)
    }
  }
}

async function onTabChange() {
  await loadConfig()
}

async function onSiteChange() {
  if (selectedSiteId.value) await loadConfig()
}

/* ── 保存 / 重置 ── */
async function saveConfig() {
  const err = validateDisposition(disposition)
  if (err) {
    ElMessage.warning(err)
    return
  }

  const scopeText = activeTab.value === 'global' ? '全局' : `站点 ${selectedSiteId.value}`
  const confirmed = await ElMessageBox.confirm(
    `保存后 ${scopeText} 的默认处置将同步到网关节点，穿透前置阶段的请求将按此兜底。确认保存？`,
    '保存默认处置',
    { confirmButtonText: '保存', cancelButtonText: '取消', type: 'warning' }
  ).catch(() => false)
  if (!confirmed) return

  saving.value = true
  try {
    if (activeTab.value === 'global') {
      await fetchPutGlobalDefaultDisposition({ disposition })
      globalMechanism.value = disposition.mechanism
    } else {
      if (!selectedSiteId.value) return
      await fetchPutDefaultDisposition(selectedSiteId.value, { disposition })
      hasSiteConfig.value = true
    }
    ElMessage.success('默认处置已保存')
  } catch (e: any) {
    ElMessage.error('保存失败：' + (e?.message || '未知错误'))
  } finally {
    saving.value = false
  }
}

async function resetConfig() {
  const scopeText = activeTab.value === 'global' ? '全局' : `站点 ${selectedSiteId.value}`
  const message = activeTab.value === 'global'
    ? '将删除全局默认处置，回退到系统默认（放行）。'
    : '将删除当前站点的默认处置，站点回退使用全局配置。'

  const confirmed = await ElMessageBox.confirm(
    message,
    `重置${scopeText}默认处置`,
    { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }
  ).catch(() => false)
  if (!confirmed) return

  saving.value = true
  try {
    if (activeTab.value === 'global') {
      await fetchResetGlobalDefaultDisposition()
      globalMechanism.value = 'pass'
    } else {
      if (!selectedSiteId.value) return
      await fetchResetDefaultDisposition(selectedSiteId.value)
      hasSiteConfig.value = false
    }
    ElMessage.success('已重置默认处置')
    await loadConfig()
  } catch (e: any) {
    ElMessage.error('重置失败：' + (e?.message || '未知错误'))
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await loadSiteList()
  await loadConfig()
})
</script>
