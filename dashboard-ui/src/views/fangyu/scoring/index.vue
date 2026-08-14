<!-- 评分配置 -->
<template>
  <div class="art-full-height" style="overflow-y: auto; padding: 4px;">
    <div class="mb-3">
      <h2 class="text-lg font-medium text-g-900">评分配置</h2>
      <p class="mt-1 text-sm text-g-600">
        调整各维度权重和阈值。<strong>评分即裁决</strong>：分数决定风险等级（可信/可疑/敌对），然后根据等级执行对应的处置策略
      </p>
    </div>

    <ElTabs v-model="activeTab" @tab-change="onTabChange">
      <!-- 全局配置 -->
      <ElTabPane label="全局配置" name="global">
        <ElAlert type="info" show-icon :closable="false" class="mb-4">
          全局配置作用于所有未单独配置的站点。修改后将同步到网关节点并立即生效。
        </ElAlert>
        
        <div class="mb-3 flex items-center justify-between">
          <span v-if="!configReady && !configLoading" class="text-sm text-g-500">
            配置未成功加载，保存已禁用
          </span>
          <div v-else></div>
          <div class="flex items-center gap-2">
            <ElButton v-auth="'app.write'" :disabled="configLoading" @click="resetConfig">
              恢复默认
            </ElButton>
            <ElButton
              type="primary"
              v-auth="'app.write'"
              :loading="saving"
              :disabled="configLoading || !configReady"
              @click="saveConfig"
            >
              保存配置
            </ElButton>
          </div>
        </div>

        <ElAlert v-if="loadError" type="error" :closable="false" class="mb-3 shrink-0" :title="loadError">
          <template #default>
            <ElButton link type="primary" :loading="configLoading" @click="loadConfig()">重新加载</ElButton>
          </template>
        </ElAlert>

        <ElRow :gutter="16" class="shrink-0 items-stretch">
        <!-- 基础配置 -->
        <ElCol :span="12" class="flex flex-col">
          <ElCard shadow="never" header="基础配置" v-loading="configLoading" class="flex-1">
            <ElForm ref="configFormRef" :model="configForm" label-width="160px">
              <ElFormItem label="启用评分">
                <ElSwitch v-model="configForm.enabled" />
              </ElFormItem>
              <ElDivider content-position="left">阈值与裁决</ElDivider>
              <ElAlert type="info" :closable="false" class="mb-3" show-icon>
                <template #title>
                  <span class="text-xs">评分自动转为裁决：&lt; {{ configForm.threshold_suspect }}分 = <strong>可信</strong>，{{ configForm.threshold_suspect }}-{{ configForm.threshold_hostile-1 }}分 = <strong>可疑</strong>，≥ {{ configForm.threshold_hostile }}分 = <strong>敌对</strong></span>
                </template>
              </ElAlert>
              <ElFormItem label="可疑阈值">
                <ElInputNumber v-model="configForm.threshold_suspect" :min="0" :max="100" :step="5" />
                <span class="ml-2 text-sm text-g-500">分</span>
              </ElFormItem>
              <ElFormItem label="敌对阈值">
                <ElInputNumber v-model="configForm.threshold_hostile" :min="0" :max="100" :step="5" />
                <span class="ml-2 text-sm text-g-500">分</span>
              </ElFormItem>
              <ElDivider content-position="left">处置策略（按裁决级别）</ElDivider>
              <ElFormItem v-for="branch in dispositionBranches" :key="branch.key" :label="branch.label">
                <div class="flex flex-col gap-2 w-full">
                  <div class="flex items-center gap-2 flex-wrap">
                    <ElSwitch
                      :model-value="!!branch.form"
                      active-text="自定义"
                      inactive-text="沿用规则链"
                      @update:model-value="v => toggleDisposition(branch, !!v)"
                    />
                    <template v-if="branch.form">
                      <ElSelect
                        v-model="branch.form.mechanism"
                        size="small"
                        class="!w-40"
                        @change="() => onMechanismChange(branch.form!)"
                      >
                        <ElOption v-for="o in MECHANISM_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
                      </ElSelect>
                      <ElSelect
                        v-if="branch.form.mechanism === 'challenge'"
                        v-model="branch.form.challengeKind"
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
                      <ElSelect
                        v-if="targetKindOptionsFor(branch.form.mechanism).length > 1"
                        v-model="branch.form.target.kind"
                        size="small"
                        class="!w-44"
                        @change="() => onTargetKindChange(branch.form!)"
                      >
                        <ElOption
                          v-for="o in targetKindOptionsFor(branch.form.mechanism)"
                          :key="o.value"
                          :label="o.label"
                          :value="o.value"
                        />
                      </ElSelect>
                    </template>
                  </div>
                  <!-- serve_alt 的 target.url 存的是页面资源**名**，不是 URL -->
                  <ElSelect
                    v-if="branch.form && branch.form.target.kind === 'page_resource'"
                    v-model="branch.form.target.url"
                    size="small"
                    filterable
                    :loading="pageResourceLoading"
                    placeholder="选择要投放的页面资源"
                    @visible-change="(v: boolean) => v && loadPageResources()"
                  >
                    <ElOption v-for="r in pageResourceOptions" :key="r.value" :label="r.label" :value="r.value" />
                    <template #empty>
                      <div class="px-3 py-2 text-xs text-g-500">
                        暂无已启用的页面资源，请先到「页面资源」页新建或从模板载入
                      </div>
                    </template>
                  </ElSelect>
                  <ElInput
                    v-if="branch.form && (branch.form.target.kind === 'url' || (URL_REQUIRED_MECHANISMS.includes(branch.form.mechanism) && branch.form.target.kind !== 'url_pool'))"
                    v-model="branch.form.target.url"
                    size="small"
                    placeholder="跳转目标 URL，如 https://example.com/block"
                  />

                  <!-- 轮询地址池：多地址按策略分摊 -->
                  <RotationPoolEditor
                    v-if="branch.form && branch.form.target.kind === 'url_pool' && branch.form.target.rotation"
                    :rotation="branch.form.target.rotation"
                    @update:rotation="(r) => { if (branch.form) branch.form.target.rotation = r }"
                  />
                </div>
              </ElFormItem>
            </ElForm>
          </ElCard>
        </ElCol>

        <!-- 维度权重 -->
        <ElCol :span="12" class="flex flex-col">
          <ElCard shadow="never" v-loading="configLoading || dimensionsLoading" class="flex-1">
            <template #header>
              <div class="flex items-center gap-2">
                <span>维度权重</span>
                <ElTooltip placement="top">
                  <template #content>
                    每个维度先算出 0-100 的原始分，再乘以本维度权重后累加，总分截顶到 100。<br />
                    权重 10 表示 1.0 倍；设为 0 等于停用该维度。<br />
                    括号内为系统默认值，供调整时参照。
                  </template>
                  <ElIcon class="text-g-400"><QuestionFilled /></ElIcon>
                </ElTooltip>
              </div>
            </template>
            <ElScrollbar max-height="380px">
              <div v-for="dim in dimensions" :key="dim.key" class="mb-3 px-3">
                <div class="flex items-center justify-between mb-1">
                  <span class="text-sm font-medium text-g-700">{{ dim.label }}</span>
                  <div class="flex items-center gap-1.5">
                    <span v-if="dim.defaultWeight !== undefined" class="text-xs text-g-400">
                      默认 {{ dim.defaultWeight }}
                    </span>
                    <ElTag
                      size="small"
                      :type="(configForm.weights[dim.key] ?? 0) === 0 ? 'warning' : 'info'"
                    >
                      {{ ((configForm.weights[dim.key] ?? 0) / 10).toFixed(1) }} 倍
                    </ElTag>
                  </div>
                </div>
                <ElSlider
                  v-model="configForm.weights[dim.key]"
                  :min="0" :max="100" :step="1"
                  show-input :show-input-controls="false"
                  size="small"
                />
                <div class="text-xs text-g-400 mt-0.5">
                  {{ dim.description }}
                  <span v-if="(configForm.weights[dim.key] ?? 0) === 0" class="text-warning">
                    （当前为 0，该维度不参与评分）
                  </span>
                </div>
              </div>
            </ElScrollbar>
          </ElCard>
        </ElCol>
      </ElRow>
      </ElTabPane>

      <!-- 站点配置 -->
      <ElTabPane label="站点配置" name="site">
        <div class="mb-4 flex items-center gap-3">
          <span class="text-sm text-g-600">选择站点：</span>
          <ElSelect
            v-model="selectedSiteId"
            filterable
            placeholder="请选择站点"
            :loading="siteListLoading"
            @change="onSiteChange"
            style="width: 300px"
          >
            <ElOption
              v-for="site in siteList"
              :key="site.id"
              :label="`${site.name} (ID: ${site.id})`"
              :value="site.id"
            />
          </ElSelect>
        </div>

        <template v-if="selectedSiteId">
          <!-- 站点未配置：显示继承关系 -->
          <ElCard v-if="!hasSiteConfig" class="mb-4">
            <template #header>
              <div class="flex items-center justify-between">
                <span>🔗 当前站点继承全局配置</span>
                <ElButton link type="primary" @click="activeTab = 'global'">查看全局配置</ElButton>
              </div>
            </template>
            <div class="space-y-3">
              <div class="flex items-center gap-2">
                <span class="text-sm text-g-600 w-20">评分状态：</span>
                <ElTag :type="globalConfig.enabled ? 'success' : 'info'">
                  {{ globalConfig.enabled ? '开启' : '关闭' }}
                </ElTag>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-sm text-g-600 w-20">阈值配置：</span>
                <span class="text-sm">可疑 ≥ {{ globalConfig.threshold_suspect }} 分 / 敌对 ≥ {{ globalConfig.threshold_hostile }} 分</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-sm text-g-600 w-20">维度权重：</span>
                <div class="flex flex-wrap gap-2">
                  <ElTag v-for="(weight, key) in globalConfig.weights" :key="key" size="small">
                    {{ key }}: {{ weight }}
                  </ElTag>
                </div>
              </div>
              <ElDivider />
              <div class="flex items-center gap-2">
                <ElButton type="primary" @click="createSiteConfig">
                  为当前站点创建独立配置
                </ElButton>
                <span class="text-xs text-g-500">创建后将不再继承全局配置</span>
              </div>
            </div>
          </ElCard>

          <!-- 站点已配置：显示独立配置提示 -->
          <ElAlert v-else type="success" show-icon :closable="false" class="mb-4">
            <template #title>
              <div class="flex items-center justify-between">
                <span>当前站点使用独立配置，不受全局配置影响</span>
                <ElButton link @click="showGlobalComparison = !showGlobalComparison">
                  {{ showGlobalComparison ? '隐藏' : '对比' }}全局配置
                </ElButton>
              </div>
            </template>
          </ElAlert>

          <!-- 全局配置对比 -->
          <ElCard v-if="hasSiteConfig && showGlobalComparison" class="mb-4" shadow="never">
            <template #header>
              <span class="text-sm">全局配置（仅供参考）</span>
            </template>
            <div class="space-y-2 text-sm">
              <div class="flex items-center gap-2">
                <span class="text-g-600 w-20">评分状态：</span>
                <ElTag :type="globalConfig.enabled ? 'success' : 'info'" size="small">
                  {{ globalConfig.enabled ? '开启' : '关闭' }}
                </ElTag>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-g-600 w-20">阈值：</span>
                <span class="text-xs">可疑 {{ globalConfig.threshold_suspect }} / 敌对 {{ globalConfig.threshold_hostile }}</span>
              </div>
            </div>
          </ElCard>

          <div class="mb-3 flex items-center justify-between">
            <span v-if="!configReady && !configLoading" class="text-sm text-g-500">
              配置未成功加载，保存已禁用
            </span>
            <div v-else></div>
            <div class="flex items-center gap-2">
              <ElButton v-auth="'app.write'" :disabled="configLoading || !hasSiteConfig" @click="resetConfig">
                删除站点配置
              </ElButton>
              <ElButton
                type="primary"
                v-auth="'app.write'"
                :loading="saving"
                :disabled="configLoading || !configReady"
                @click="saveConfig"
              >
                保存配置
              </ElButton>
            </div>
          </div>

          <ElAlert v-if="loadError" type="error" :closable="false" class="mb-3 shrink-0" :title="loadError">
            <template #default>
              <ElButton link type="primary" :loading="configLoading" @click="loadConfig()">重新加载</ElButton>
            </template>
          </ElAlert>

          <!-- 决策流水线 -->
          <ElCard shadow="never" class="mb-4 shrink-0">
            <template #header>
              <div class="flex items-center gap-2">
                <span>决策流水线</span>
                <ElTooltip placement="top">
                  <template #content>
                    访客请求自上而下逐阶段流过，任一阶段命中即返回处置，后续阶段不再执行。<br />
                    「配置来源」标明该阶段受什么控制——只有风险评分能在本页调整。
                  </template>
                  <ElIcon class="text-g-400"><QuestionFilled /></ElIcon>
                </ElTooltip>
              </div>
            </template>
            <div class="flex flex-col gap-1.5">
              <div
                v-for="(stage, idx) in pipelineStages"
                :key="stage.key"
                class="flex items-start gap-3 rounded border px-3 py-2"
                :class="stage.dimmed ? 'border-g-200 bg-g-50' : 'border-g-200'"
              >
                <span
                  class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs"
                  :class="stage.dimmed ? 'bg-g-200 text-g-500' : 'bg-primary text-white'"
                >{{ idx + 1 }}</span>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium" :class="stage.dimmed ? 'text-g-400' : 'text-g-800'">
                      {{ stage.label }}
                    </span>
                    <ElTag size="small" :type="stage.tagType">{{ stage.source }}</ElTag>
                    <span v-if="stage.terminal" class="text-xs text-g-400">命中即返回</span>
                  </div>
                  <div class="mt-0.5 text-xs" :class="stage.dimmed ? 'text-g-400' : 'text-g-500'">
                    {{ stage.description }}
                  </div>
                </div>
              </div>
            </div>
          </ElCard>

          <ElRow :gutter="16" class="shrink-0 items-stretch">
             <!-- 基础配置 -->
             <ElCol :span="12" class="flex flex-col">
               <ElCard shadow="never" header="基础配置" v-loading="configLoading" class="flex-1">
                 <ElForm ref="configFormRef" :model="configForm" label-width="160px">
                   <ElFormItem label="启用评分">
                     <ElSwitch v-model="configForm.enabled" />
                   </ElFormItem>
                   <ElDivider content-position="left">阈值与裁决</ElDivider>
                   <ElAlert type="info" :closable="false" class="mb-3" show-icon>
                     <template #title>
                       <span class="text-xs">评分自动转为裁决：&lt; {{ configForm.threshold_suspect }}分 = <strong>可信</strong>，{{ configForm.threshold_suspect }}-{{ configForm.threshold_hostile-1 }}分 = <strong>可疑</strong>，≥ {{ configForm.threshold_hostile }}分 = <strong>敌对</strong></span>
                     </template>
                   </ElAlert>
                   <ElFormItem label="可疑阈值">
                     <ElInputNumber v-model="configForm.threshold_suspect" :min="0" :max="100" :step="5" />
                     <span class="ml-2 text-sm text-g-500">分</span>
                   </ElFormItem>
                   <ElFormItem label="敌对阈值">
                     <ElInputNumber v-model="configForm.threshold_hostile" :min="0" :max="100" :step="5" />
                     <span class="ml-2 text-sm text-g-500">分</span>
                   </ElFormItem>
                   <ElDivider content-position="left">处置策略（按裁决级别）</ElDivider>
                   <ElFormItem v-for="branch in dispositionBranches" :key="branch.key" :label="branch.label">
                     <div class="flex flex-col gap-2 w-full">
                       <div class="flex items-center gap-2 flex-wrap">
                         <ElSwitch
                           :model-value="!!branch.form"
                           active-text="自定义"
                           inactive-text="沿用规则链"
                           @update:model-value="v => toggleDisposition(branch, !!v)"
                         />
                         <template v-if="branch.form">
                           <ElSelect
                             v-model="branch.form.mechanism"
                             size="small"
                             class="!w-40"
                             @change="() => onMechanismChange(branch.form!)"
                           >
                             <ElOption v-for="o in MECHANISM_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
                           </ElSelect>
                           <ElSelect
                             v-if="branch.form.mechanism === 'challenge'"
                             v-model="branch.form.challengeKind"
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
                           <ElSelect
                             v-if="targetKindOptionsFor(branch.form.mechanism).length > 1"
                             v-model="branch.form.target.kind"
                             size="small"
                             class="!w-44"
                             @change="() => onTargetKindChange(branch.form!)"
                           >
                             <ElOption
                               v-for="o in targetKindOptionsFor(branch.form.mechanism)"
                               :key="o.value"
                               :label="o.label"
                               :value="o.value"
                             />
                           </ElSelect>
                         </template>
                       </div>
                       <!-- serve_alt 的 target.url 存的是页面资源**名**，不是 URL -->
                       <ElSelect
                         v-if="branch.form && branch.form.target.kind === 'page_resource'"
                         v-model="branch.form.target.url"
                         size="small"
                         filterable
                         :loading="pageResourceLoading"
                         placeholder="选择要投放的页面资源"
                         @visible-change="(v: boolean) => v && loadPageResources()"
                       >
                         <ElOption v-for="r in pageResourceOptions" :key="r.value" :label="r.label" :value="r.value" />
                         <template #empty>
                           <div class="px-3 py-2 text-xs text-g-500">
                             暂无已启用的页面资源，请先到「页面资源」页新建或从模板载入
                           </div>
                         </template>
                       </ElSelect>
                       <ElInput
                         v-if="branch.form && (branch.form.target.kind === 'url' || (URL_REQUIRED_MECHANISMS.includes(branch.form.mechanism) && branch.form.target.kind !== 'url_pool'))"
                         v-model="branch.form.target.url"
                         size="small"
                         placeholder="跳转目标 URL，如 https://example.com/block"
                       />

                       <!-- 轮询地址池：多地址按策略分摊 -->
                       <RotationPoolEditor
                         v-if="branch.form && branch.form.target.kind === 'url_pool' && branch.form.target.rotation"
                         :rotation="branch.form.target.rotation"
                       />
                     </div>
                   </ElFormItem>
                 </ElForm>
               </ElCard>
             </ElCol>

             <!-- 权重调整 -->
             <ElCol :span="12" class="flex flex-col">
               <ElCard shadow="never" class="flex-1" v-loading="configLoading">
                 <template #header>
                   <span>维度权重 <span class="text-xs text-g-500">(总计: {{ totalWeight }})</span></span>
                 </template>
                 <ElScrollbar max-height="600px">
                   <div class="flex flex-col gap-3">
                     <div v-for="dim in dimensions" :key="dim.key" class="flex flex-col gap-1">
                       <div class="flex items-center justify-between">
                         <div class="flex items-center gap-2">
                           <span class="text-sm font-medium text-g-800">{{ dim.label }}</span>
                           <ElTooltip v-if="dim.description" placement="top" :content="dim.description">
                             <ElIcon class="text-g-400"><QuestionFilled /></ElIcon>
                           </ElTooltip>
                         </div>
                         <span class="text-sm font-medium text-primary">
                           {{ configForm.weights[dim.key] ?? 0 }}
                         </span>
                       </div>
                       <ElSlider
                         v-model="configForm.weights[dim.key]"
                         :min="0"
                         :max="30"
                         :step="1"
                         :marks="{ 0: '0', 15: '15', 30: '30' }"
                       />
                     </div>
                   </div>
                 </ElScrollbar>
               </ElCard>
             </ElCol>
           </ElRow>
         </template>

         <ElEmpty v-else description="请先选择站点" />
       </ElTabPane>
     </ElTabs>
   </div>
 </template>
 <script setup lang="ts">
import { QuestionFilled } from '@element-plus/icons-vue'
import { 
  fetchGetGlobalScoringConfig, fetchPutGlobalScoringConfig, fetchResetGlobalScoringConfig,
  fetchGetScoringConfig, fetchPutScoringConfig, fetchResetScoringConfig,
  fetchGetScoringDimensions 
} from '@/api/scoring'
import { fetchGetAllSites } from '@/api/apps'
import { fetchGetPageResourceList } from '@/api/page-resources'
import {
  MECHANISM_OPTIONS, CHALLENGE_KIND_OPTIONS,
  URL_REQUIRED_MECHANISMS, createDecisionDisposition,
  targetKindOptionsFor, defaultTargetKindFor, validateDisposition,
  createRotation
} from '@/constants/disposition'
import RotationPoolEditor from '@/components/RotationPoolEditor.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'

defineOptions({ name: 'FangyuScoring' })

// 标签页
const activeTab = ref<'global' | 'site'>('global')

// 站点列表
const siteList = ref<Array<{ id: number; name: string }>>([])
const siteListLoading = ref(false)
const selectedSiteId = ref<number | null>(null)

// 站点是否有独立配置
const hasSiteConfig = ref(false)

// 全局配置（用于站点继承展示）
const globalConfig = ref({
  enabled: true,
  threshold_suspect: 30,
  threshold_hostile: 75,
  weights: {} as Record<string, number>
})

// 是否显示全局配置对比
const showGlobalComparison = ref(false)

const configLoading = ref(false)
const dimensionsLoading = ref(false)
const saving = ref(false)
const configFormRef = ref<FormInstance>()

const dimensions = ref<
  Array<{ key: string; label: string; description: string; defaultWeight?: number }>
>([])

// 流水线阶段常量已移除，相关配置移至「默认处置」页面

const configForm = reactive<{
  enabled: boolean
  threshold_suspect: number
  threshold_hostile: number
  disposition_suspect: Api.Fangyu.DecisionDisposition | null
  disposition_hostile: Api.Fangyu.DecisionDisposition | null
  weights: Record<string, number>
}>({
  enabled: true,
  threshold_suspect: 40,
  threshold_hostile: 70,
  disposition_suspect: null,
  disposition_hostile: null,
  weights: {}
})

const pipelineStages = computed(() => {
  // 评分页不再展示流水线，该代码可以删除
  // 流水线配置已移至「默认处置」页面
  return []
})

type DispositionBranch = {
  key: 'disposition_suspect' | 'disposition_hostile'
  label: string
  form: Api.Fangyu.DecisionDisposition | null
}

const dispositionBranches = computed<DispositionBranch[]>(() => [
  { key: 'disposition_suspect', label: '可疑处置 (suspect)', form: configForm.disposition_suspect },
  { key: 'disposition_hostile', label: '敌对处置 (hostile)', form: configForm.disposition_hostile }
])

// 计算当前有效维度的总权重
const totalWeight = computed(() => {
  return dimensions.value.reduce((sum, dim) => sum + (configForm.weights[dim.key] || 0), 0)
})

function toggleDisposition(branch: DispositionBranch, enabled: boolean) {
  configForm[branch.key] = enabled ? createDecisionDisposition() : null
}

/** 机制切换时同步纠正下游字段，逻辑与规则页 `onMechanismChange` 一致 */
function onMechanismChange(form: Api.Fangyu.DecisionDisposition) {
  const mech = form.mechanism
  form.challengeKind = mech === 'challenge' ? (form.challengeKind ?? 'captcha') : null

  const allowed = targetKindOptionsFor(mech).map((o) => o.value)
  if (!allowed.includes(form.target.kind)) {
    form.target.kind = defaultTargetKindFor(mech)
  }
  if (!URL_REQUIRED_MECHANISMS.includes(mech) && form.target.kind !== 'page_resource') {
    form.target.url = null
  }
  // 目标类型可能已回落到非 url_pool，rotation 随之失效
  if (form.target.kind !== 'url_pool') {
    form.target.rotation = null
  }
}

function onTargetKindChange(form: Api.Fangyu.DecisionDisposition) {
  form.target.url = null
  
  // 切换到 url_pool 时初始化 rotation；切换离开时清空
  if (form.target.kind === 'url_pool') {
    if (!form.target.rotation) {
      form.target.rotation = createRotation()
    }
  } else {
    form.target.rotation = null
  }
}

/* ── 页面资源选项（serve_alt 的投放目标）── */
const pageResourceOptions = ref<{ label: string; value: string }[]>([])
const pageResourceLoading = ref(false)
let pageResourceLoaded = false

async function loadPageResources() {
  if (pageResourceLoaded) return
  pageResourceLoading.value = true
  try {
    const res = await fetchGetPageResourceList({ enabled: true, page: 1, pageSize: 100 })
    pageResourceOptions.value = (res?.items ?? []).map((r) => ({
      label: `${r.name}（${r.kind === 'safe' ? '正常分支' : '阻断/质疑'}）`,
      value: r.name
    }))
    pageResourceLoaded = true
  } finally {
    pageResourceLoading.value = false
  }
}

/** 配置加载失败原因；非空时禁止保存，避免用默认值覆盖线上配置 */
const loadError = ref('')
/** 配置已就绪（读到线上配置或确认尚未创建），才允许保存 */
const configReady = ref(false)

/**
 * 为存量配置里缺失的维度补上系统默认权重。
 *
 * 缺省值取 defaultWeight 而非 0：0 的语义是「停用该维度」，若用 0 补齐，
 * 早期配置（维度 key 与当前 scorer 不一致）一保存就会把全部维度静默停用。
 */
function fillMissingWeights() {
  dimensions.value.forEach(d => {
    if (!(d.key in configForm.weights)) configForm.weights[d.key] = d.defaultWeight ?? 0
  })
}

const loadConfig = async () => {
  configLoading.value = true
  loadError.value = ''
  hasSiteConfig.value = false
  
  try {
    // 根据当前标签页加载对应配置
    if (activeTab.value === 'global') {
      const cfg = await fetchGetGlobalScoringConfig()
      if (cfg) {
        Object.assign(configForm, {
          enabled: cfg.enabled,
          threshold_suspect: cfg.threshold_suspect,
          threshold_hostile: cfg.threshold_hostile,
          disposition_suspect: cfg.disposition_suspect ?? null,
          disposition_hostile: cfg.disposition_hostile ?? null,
          weights: { ...cfg.weights }
        })
        // 同步保存全局配置用于站点继承展示
        Object.assign(globalConfig.value, {
          enabled: cfg.enabled,
          threshold_suspect: cfg.threshold_suspect,
          threshold_hostile: cfg.threshold_hostile,
          weights: { ...cfg.weights }
        })
      }
    } else {
      // 站点配置
      if (!selectedSiteId.value) {
        ElMessage.warning('请先选择站点')
        configReady.value = false
        return
      }
      
      const cfg = await fetchGetScoringConfig(selectedSiteId.value)
      if (cfg) {
        hasSiteConfig.value = true
        Object.assign(configForm, {
          enabled: cfg.enabled,
          threshold_suspect: cfg.threshold_suspect,
          threshold_hostile: cfg.threshold_hostile,
          disposition_suspect: cfg.disposition_suspect ?? null,
          disposition_hostile: cfg.disposition_hostile ?? null,
          weights: { ...cfg.weights }
        })
      }
    }
    
    fillMissingWeights()
    configReady.value = true
  } catch (err: any) {
    const code = err?.code ?? err?.response?.status
    if (code === 404 || code === 'NOT_FOUND') {
      hasSiteConfig.value = false
      dimensions.value.forEach(d => { configForm.weights[d.key] = d.defaultWeight ?? 0 })
      configReady.value = true
      const scopeText = activeTab.value === 'global' ? '全局' : '站点'
      ElMessage.info(`尚无${scopeText}评分配置，已加载默认值，保存后生效`)
    } else {
      configReady.value = false
      loadError.value = '评分配置加载失败，当前表单显示的是默认值而非线上配置。为避免覆盖生产配置，保存已被禁用。'
      console.error('加载评分配置失败:', err)
    }
  } finally { 
    configLoading.value = false 
  }
}

const onTabChange = async () => {
  await loadConfig()
}

const onSiteChange = async () => {
  if (selectedSiteId.value) {
    await loadConfig()
  }
}

const loadDimensions = async () => {
  dimensionsLoading.value = true
  try {
    dimensions.value = await fetchGetScoringDimensions()
    fillMissingWeights()
  } catch (err) {
    dimensions.value = []
    console.error('加载评分维度失败:', err)
  } finally { dimensionsLoading.value = false }
}

const saveConfig = async () => {
  if (configForm.threshold_hostile <= configForm.threshold_suspect) {
    ElMessage.warning('敌对阈值必须大于可疑阈值，否则可疑区间为空')
    return
  }
  // 只提交当前维度的 key：早期版本的维度名已与 scorer 对不上，
  // 原样回传会让废弃 key 长期滞留在库里，还会虚增下面的合计值。
  const weights = Object.fromEntries(
    dimensions.value.map(d => [d.key, configForm.weights[d.key] ?? 0])
  )
  const totalWeight = Object.values(weights).reduce((sum, w) => sum + (w || 0), 0)
  // 评分已关闭时跳过权重校验——网关侧会整段跳过评分阶段，权重不参与运算
  if (configForm.enabled) {
    if (totalWeight === 0) {
      ElMessage.warning('所有维度权重均为 0，评分将恒为 0 分，请至少设置一个维度权重')
      return
    }
    // 检查是否所有权重都为负值（会导致分数异常偏低）
    const allNegative = Object.values(weights).every(w => w <= 0)
    if (allNegative && totalWeight < 0) {
      ElMessage.warning('所有维度权重均为负值，评分结果将异常偏低，建议至少保留一个正权重维度')
      return
    }
    // 检查阈值配置是否合理
    if (configForm.threshold_suspect >= configForm.threshold_hostile) {
      ElMessage.warning('可疑阈值必须小于敌对阈值，否则可疑区间为空')
      return
    }
  }

  // 关闭评分时不应配置处置策略（评分阶段被跳过，处置策略不会生效）
  if (!configForm.enabled) {
    if (configForm.disposition_suspect) {
      ElMessage.warning('关闭评分时不应配置「可疑处置」策略，请清空后再保存')
      return
    }
    if (configForm.disposition_hostile) {
      ElMessage.warning('关闭评分时不应配置「敌对处置」策略，请清空后再保存')
      return
    }
  }

  for (const branch of dispositionBranches.value) {
    if (!branch.form) continue
    const err = validateDisposition(branch.form)
    if (err) {
      ElMessage.warning(`${branch.label}：${err}`)
      return
    }
  }

  const confirmMessage = configForm.enabled
    ? `保存后新的权重与阈值将同步到网关节点并立即用于线上请求判定（可疑 ≥ ${configForm.threshold_suspect} 分，敌对 ≥ ${configForm.threshold_hostile} 分）。确认保存？`
    : '评分已关闭：保存后网关将跳过风险评分阶段，所有未被前置阶段命中的请求直接落到默认处置（通常为放行）。确认保存？'

  const confirmed = await ElMessageBox.confirm(
    confirmMessage,
    `保存${activeTab.value === 'global' ? '全局' : '站点'}评分配置`,
    { confirmButtonText: '保存', cancelButtonText: '取消', type: 'warning' }
  ).catch(() => false)
  if (!confirmed) return

  saving.value = true
  try {
    if (activeTab.value === 'global') {
      await fetchPutGlobalScoringConfig({
        enabled: configForm.enabled,
        threshold_suspect: configForm.threshold_suspect,
        threshold_hostile: configForm.threshold_hostile,
        weights,
        disposition_suspect: configForm.disposition_suspect,
        disposition_hostile: configForm.disposition_hostile
      })
      // 更新全局配置缓存
      Object.assign(globalConfig.value, {
        enabled: configForm.enabled,
        threshold_suspect: configForm.threshold_suspect,
        threshold_hostile: configForm.threshold_hostile,
        weights: { ...weights }
      })
    } else {
      if (!selectedSiteId.value) {
        ElMessage.warning('请先选择站点')
        return
      }
      await fetchPutScoringConfig(selectedSiteId.value, {
        enabled: configForm.enabled,
        threshold_suspect: configForm.threshold_suspect,
        threshold_hostile: configForm.threshold_hostile,
        weights,
        disposition_suspect: configForm.disposition_suspect,
        disposition_hostile: configForm.disposition_hostile
      })
      hasSiteConfig.value = true
    }
    ElMessage.success('评分配置已保存并同步到网关节点')
  } catch {
    ElMessage.error('保存失败，线上配置未变更，请稍后重试')
  } finally { saving.value = false }
}

const resetConfig = async () => {
  const scopeText = activeTab.value === 'global' ? '全局' : '站点'
  const message = activeTab.value === 'global'
    ? '将恢复全局默认评分配置，当前的权重、阈值与处置策略会立即被覆盖并同步到网关节点，操作不可撤销。'
    : '将删除当前站点的评分配置，站点将回退使用全局配置，操作不可撤销。'
  
  const confirmed = await ElMessageBox.confirm(
    message,
    `恢复${scopeText}默认`,
    { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }
  ).catch(() => false)
  if (!confirmed) return

  try {
    if (activeTab.value === 'global') {
      await fetchResetGlobalScoringConfig()
    } else {
      if (!selectedSiteId.value) {
        ElMessage.warning('请先选择站点')
        return
      }
      await fetchResetScoringConfig(selectedSiteId.value)
      hasSiteConfig.value = false
    }
    ElMessage.success(`已恢复${scopeText}默认评分配置`)
    await loadConfig()
  } catch {
    ElMessage.error('恢复失败，请稍后重试')
  }
}

const createSiteConfig = () => {
  hasSiteConfig.value = true
  ElMessage.info('现在可以为当前站点配置独立的评分规则，修改后记得保存')
}

// 加载站点列表
const loadSiteList = async () => {
  siteListLoading.value = true
  try {
    const sites = await fetchGetAllSites()
    siteList.value = sites.map(site => ({
      id: site.id,
      name: site.name
    }))
  } catch (err) {
    console.error('加载站点列表失败:', err)
    ElMessage.error('站点列表加载失败')
  } finally {
    siteListLoading.value = false
  }
}

onMounted(async () => {
  await loadDimensions()
  await loadSiteList()
  await loadConfig()
})
</script>
