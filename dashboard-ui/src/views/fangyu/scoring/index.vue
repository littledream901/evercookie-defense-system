<!-- 评分配置 -->
<template>
  <div class="art-full-height" style="overflow-y: auto; padding: 4px;">
    <div class="mb-3 flex shrink-0 items-center justify-between">
      <div>
        <h2 class="text-lg font-medium text-g-900">评分配置</h2>
        <p class="mt-1 text-sm text-g-600">调整各维度权重及可疑/敌对阈值，决定最终处置策略</p>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="!configReady && !configLoading" class="text-sm text-g-500">
          配置未成功加载，保存已禁用
        </span>
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
            <ElForm ref="configFormRef" :model="configForm" label-width="120px">
              <ElFormItem label="启用评分">
                <ElSwitch v-model="configForm.enabled" />
              </ElFormItem>
              <ElDivider content-position="left">阈值</ElDivider>
              <ElFormItem label="可疑阈值">
                <ElInputNumber v-model="configForm.threshold_suspect" :min="0" :max="100" :step="5" />
                <span class="ml-2 text-sm text-g-500">分（≥ 此值 = 可疑）</span>
              </ElFormItem>
              <ElFormItem label="敌对阈值">
                <ElInputNumber v-model="configForm.threshold_hostile" :min="0" :max="100" :step="5" />
                <span class="ml-2 text-sm text-g-500">分（≥ 此值 = 敌对）</span>
              </ElFormItem>
              <ElDivider content-position="left">处置策略</ElDivider>
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
  </div>
</template>
<script setup lang="ts">
import { QuestionFilled } from '@element-plus/icons-vue'
import { fetchGetGlobalScoringConfig, fetchPutGlobalScoringConfig, fetchResetGlobalScoringConfig, fetchGetScoringDimensions } from '@/api/scoring'
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

const configLoading = ref(false)
const dimensionsLoading = ref(false)
const saving = ref(false)
const configFormRef = ref<FormInstance>()

const dimensions = ref<
  Array<{ key: string; label: string; description: string; defaultWeight?: number }>
>([])

/**
 * 决策流水线阶段，顺序与网关 DecisionService.decide() 的实际执行顺序一致。
 *
 * source 标明配置来源，避免误以为都能在本页调整：
 * - 网关环境变量：改动需重启网关进程
 * - 代码固定：当前无开关
 * - 本页配置：仅风险评分一项
 */
const PIPELINE_STAGES = [
  {
    key: 'ingress',
    label: '接入层解析',
    description: 'SDK 取 socket peer IP / Adapter 由调用方传入；解析指纹、UA、访问路径。未解析出 IP 会直接抛错，不进流水线',
    source: '代码固定',
    terminal: false
  },
  {
    key: 'whitelist',
    label: '白名单',
    description: '按 IP / 指纹查站点白名单。放在最前是误封兜底——被频控封禁的访客到不了后面的阶段。代价是白名单流量不参与频控计数',
    source: '网关环境变量',
    terminal: true
  },
  {
    key: 'challenge_pass',
    label: '挑战通行',
    description: '查访客是否持有已通过挑战的凭据，持有则放行，不必重复验证',
    source: '代码固定',
    terminal: true
  },
  {
    key: 'clock',
    label: '频控',
    description: '按 IP / 指纹多窗口计数并落行为时序，超限升级为封禁。必须前置于缓存，否则缓存命中的请求不计数会漏掉突发流量。拦截返回 404 而非 403，不暴露频控存在',
    source: '网关环境变量',
    terminal: true
  },
  {
    key: 'hybrid_lookup',
    label: 'Hybrid 查询',
    description: '仅 SDK 请求。用 serverToken 查第一层（Adapter）预判：规则命中过则直接短路；纯评分产生的可疑只作为信号注入，交由本层用真实指纹重判。token 消费后即删，防重放',
    source: '代码固定',
    terminal: true
  },
  {
    key: 'cache',
    label: '决策缓存',
    description: '按 (站点, 指纹, IP) 查已有结论，命中则跳过后续全部阶段。频控结论不写入此缓存——它与时间强相关，缓存后窗口滑过仍会被拒',
    source: '代码固定',
    terminal: true
  },
  {
    key: 'profile',
    label: '画像构建',
    description: '读设备与 IP 画像缓存，叠加 MMDB 归属地、ASN、UA 解析与六类维度情报，产出后续阶段的求值上下文。不产出处置',
    source: '代码固定',
    terminal: false
  },
  {
    key: 'decision_rule',
    label: '决策规则',
    description: '按优先级匹配已发布的决策规则，首次命中即终止。含 allowlist 规则组兜底与「未命中处置」短路；影子规则只记录不生效',
    source: '规则页配置',
    terminal: true
  },
  {
    key: 'threat_intel',
    label: '威胁情报',
    description: '查 IP 是否在威胁情报库中，命中则拒绝',
    source: '代码固定',
    terminal: true
  },
  {
    key: 'security',
    label: '基础安全检查',
    description: 'IP 黑名单、地理围栏、Tor 出口节点。前两项默认为空列表，未配置时实际只有 Tor 判定在起作用',
    source: '网关环境变量',
    terminal: true
  },
  {
    key: 'risk_scoring',
    label: '风险评分',
    description: '六个维度加权累加后截顶到 100 分，越过阈值施加对应处置。关闭后本阶段整体跳过，直接落到默认处置',
    source: '本页配置',
    terminal: true
  },
  {
    key: 'default',
    label: '默认处置',
    description: '前面全部未命中时的兜底：站点级默认处置 → 系统默认放行',
    source: '代码固定',
    terminal: false
  }
] as const

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

const pipelineStages = computed(() =>
  PIPELINE_STAGES.map((s) => {
    // 评分关闭时该阶段不执行，置灰以反映真实链路
    const dimmed = s.key === 'risk_scoring' && !configForm.enabled
    const tagType: 'primary' | 'info' | 'warning' =
      s.source === '本页配置' ? 'primary' : s.source === '代码固定' ? 'info' : 'warning'
    return {
      ...s,
      dimmed,
      tagType: dimmed ? 'info' : tagType,
      description: dimmed ? `${s.description}（当前已关闭，本阶段跳过）` : s.description
    }
  })
)

type DispositionBranch = {
  key: 'disposition_suspect' | 'disposition_hostile'
  label: string
  form: Api.Fangyu.DecisionDisposition | null
}

const dispositionBranches = computed<DispositionBranch[]>(() => [
  { key: 'disposition_suspect', label: '可疑处置', form: configForm.disposition_suspect },
  { key: 'disposition_hostile', label: '敌对处置', form: configForm.disposition_hostile }
])

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
  try {
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
    }
    fillMissingWeights()
    configReady.value = true
  } catch (err: any) {
    const code = err?.code ?? err?.response?.status
    if (code === 404 || code === 'NOT_FOUND') {
      dimensions.value.forEach(d => { configForm.weights[d.key] = d.defaultWeight ?? 0 })
      configReady.value = true
      ElMessage.info('尚无全局评分配置，已加载默认值，保存后生效')
    } else {
      // 未知错误：表单里是默认值而非线上值，保存会静默覆盖生产配置
      configReady.value = false
      loadError.value = '评分配置加载失败，当前表单显示的是默认值而非线上配置。为避免覆盖生产配置，保存已被禁用。'
      console.error('加载评分配置失败:', err)
    }
  } finally { configLoading.value = false }
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
  if (totalWeight === 0) {
    ElMessage.warning('所有维度权重均为 0，评分将恒为 0 分，请至少设置一个维度权重')
    return
  }
  for (const branch of dispositionBranches.value) {
    if (!branch.form) continue
    const err = validateDisposition(branch.form)
    if (err) {
      ElMessage.warning(`${branch.label}：${err}`)
      return
    }
  }

  const confirmed = await ElMessageBox.confirm(
    `保存后新的权重与阈值将同步到网关节点并立即用于线上请求判定（可疑 ≥ ${configForm.threshold_suspect} 分，敌对 ≥ ${configForm.threshold_hostile} 分）。确认保存？`,
    '保存评分配置',
    { confirmButtonText: '保存', cancelButtonText: '取消', type: 'warning' }
  ).catch(() => false)
  if (!confirmed) return

  saving.value = true
  try {
    await fetchPutGlobalScoringConfig({
      enabled: configForm.enabled,
      threshold_suspect: configForm.threshold_suspect,
      threshold_hostile: configForm.threshold_hostile,
      weights,
      disposition_suspect: configForm.disposition_suspect,
      disposition_hostile: configForm.disposition_hostile
    })
    ElMessage.success('评分配置已保存并同步到网关节点')
  } catch {
    ElMessage.error('保存失败，线上配置未变更，请稍后重试')
  } finally { saving.value = false }
}

const resetConfig = async () => {
  const confirmed = await ElMessageBox.confirm(
    '将恢复全局默认评分配置，当前的权重、阈值与处置策略会立即被覆盖并同步到网关节点，操作不可撤销。',
    '恢复默认',
    { confirmButtonText: '恢复默认', cancelButtonText: '取消', type: 'warning' }
  ).catch(() => false)
  if (!confirmed) return

  try {
    await fetchResetGlobalScoringConfig()
    ElMessage.success('已恢复默认评分配置')
    await loadConfig()
  } catch {
    ElMessage.error('恢复失败，请稍后重试')
  }
}

onMounted(async () => {
  await loadDimensions()
  await loadConfig()
})
</script>
