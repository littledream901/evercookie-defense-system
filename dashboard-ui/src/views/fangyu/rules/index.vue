<!-- 风控规则 -->
<template>
  <div class="art-full-height">
    <div class="mb-3">
      <h2 class="text-lg font-medium text-g-900">风控规则</h2>
      <p class="mt-1 text-sm text-g-600">应用风控决策规则，支持发布、停用、归档、回滚</p>
    </div>

    <ElCard class="art-table-card">
      <ArtTableHeader :loading="loading" v-model:columns="columnChecks" @refresh="refreshData">
        <template #left>
          <ElSpace wrap>
            <ElButton v-auth="'rule.write'" @click="showDialog('add')">新建规则</ElButton>
            <template v-if="selectedRules.length > 0">
              <ElDivider direction="vertical" />
              <span class="text-sm text-g-500">已选 {{ selectedRules.length }} 条</span>
              <ElButton :loading="batchActing" size="small" type="success" plain @click="batchPublish">批量发布</ElButton>
              <ElButton :loading="batchActing" size="small" type="warning" plain @click="batchDisable">批量停用</ElButton>
              <ElButton :loading="batchActing" size="small" type="danger"  plain @click="batchArchive">批量归档</ElButton>
            </template>
          </ElSpace>
        </template>
      </ArtTableHeader>
      <ArtTable
        :loading="loading" :data="data" :columns="columns" :pagination="pagination"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
        @selection-change="handleSelectionChange"
      />
    </ElCard>

    <!-- 规则编辑弹窗 -->
    <ElDialog
      v-model="dialogVisible"
      :title="dialogType === 'add' ? '新建规则' : `编辑规则：${ruleForm.name}`"
      width="760px"
      destroy-on-close
    >
      <ElScrollbar max-height="82vh">
        <ElForm ref="ruleFormRef" :model="ruleForm" :rules="ruleRules" label-width="90px" class="rule-editor-form">

          <!-- ── 基础信息 ── -->
          <ElDivider content-position="left"><span class="section-label">基础信息</span></ElDivider>
          <ElFormItem label="名称" prop="name">
            <ElInput v-model="ruleForm.name" placeholder="如：海外 VPN 拦截" />
          </ElFormItem>
          <ElRow :gutter="12">
            <ElCol :span="12">
              <ElFormItem prop="priority">
                <template #label>
                  <span>优先级</span>
                  <ElTooltip placement="top" :show-after="200">
                    <template #content>
                      <div style="max-width:280px;font-size:12px;line-height:1.8">
                        规则链按优先级从高到低求值：<b>critical → high → normal → low</b><br>
                        同级规则按 ID 升序排列。<br>
                        <b>critical</b>：安全兜底（IP 黑名单、已知攻击），最先匹配<br>
                        <b>high</b>：强信号规则（VPN/DC/Tor + 高风险行为）<br>
                        <b>normal</b>：常规业务规则（地区、频次、设备）<br>
                        <b>low</b>：宽松规则或观察规则，放最后
                      </div>
                    </template>
                    <ElIcon class="ml-1 cursor-help text-g-400" style="vertical-align:-2px"><QuestionFilled /></ElIcon>
                  </ElTooltip>
                </template>
                <ElSelect v-model="ruleForm.priority" class="w-full">
                  <ElOption v-for="o in RULE_PRIORITY_OPTIONS" :key="o.value" v-bind="o" />
                </ElSelect>
              </ElFormItem>
            </ElCol>
            <ElCol :span="12">
              <ElFormItem label="分组">
                <ElInput v-model="ruleForm.group" placeholder="default / payment / login" />
              </ElFormItem>
            </ElCol>
          </ElRow>
          <ElFormItem label="描述">
            <ElInput v-model="ruleForm.description" type="textarea" :rows="2" placeholder="规则用途说明" />
          </ElFormItem>

          <!-- ── 匹配条件 ── -->
          <ElDivider content-position="left">
            <span class="section-label">匹配条件</span>
            <ElRadioGroup v-model="ruleForm.matchAll" size="small" style="margin-left:12px">
              <ElRadioButton :value="true">全部满足 (AND)</ElRadioButton>
              <ElRadioButton :value="false">任一满足 (OR)</ElRadioButton>
            </ElRadioGroup>
          </ElDivider>
          <div v-if="ruleForm.conditions.length === 0" class="no-conditions mb-2">
            <span class="text-g-400 text-sm">
              至少需要一个匹配条件。无条件的规则不会命中任何请求（风控侧 fail-closed，不会误伤全站流量）。
            </span>
          </div>
          <div v-for="(cond, idx) in ruleForm.conditions" :key="idx" class="condition-row mb-2">
            <ElRow :gutter="8" align="middle">
              <ElCol :span="7">
                <ElSelect
                  v-model="cond.field"
                  placeholder="字段"
                  class="w-full"
                  filterable
                  @change="() => { cond.operator = getDefaultOperator(cond.field); cond.value = defaultValueFor(FIELD_MAP[cond.field]?.type, getDefaultOperator(cond.field)) as string | string[] }"
                >
                  <ElOptionGroup v-for="grp in FIELD_GROUPS" :key="grp.label" :label="grp.label">
                    <ElOption v-for="f in grp.fields" :key="f.value" :label="f.label" :value="f.value" />
                  </ElOptionGroup>
                </ElSelect>
              </ElCol>
              <ElCol :span="5">
                <ElSelect
                  v-model="cond.operator"
                  class="w-full"
                  @change="() => { cond.value = LIST_OPS.has(cond.operator) ? [] : '' }"
                >
                  <ElOption v-for="op in getOperatorOptions(cond.field)" :key="op.value" :label="op.label" :value="op.value" />
                </ElSelect>
              </ElCol>
              <ElCol :span="10">
                <!-- bool 字段 -->
                <ElSelect v-if="FIELD_MAP[cond.field]?.type === 'bool'" v-model="cond.value" class="w-full">
                  <ElOption label="是 (true)" :value="true" />
                  <ElOption label="否 (false)" :value="false" />
                </ElSelect>
                <!-- enum 字段：有预定义选项 -->
                <ElSelect
                  v-else-if="FIELD_MAP[cond.field]?.options?.length"
                  v-model="cond.value"
                  class="w-full"
                  :multiple="LIST_OPS.has(cond.operator)"
                  collapse-tags
                >
                  <!--
                    可空字段配 eq/neq 时提供「空」，用于写「字段不等于空」排除数据缺失。
                    ElOption 的 value prop 不接受 null，用哨兵值承载，提交时还原为 null。
                  -->
                  <ElOption
                    v-if="FIELD_MAP[cond.field]?.nullable && !LIST_OPS.has(cond.operator)"
                    label="空（无数据）"
                    :value="NULL_SENTINEL"
                  />
                  <ElOption
                    v-for="opt in FIELD_MAP[cond.field]!.options"
                    :key="opt"
                    :label="optionLabel(cond.field, opt)"
                    :value="opt"
                  />
                </ElSelect>
                <!-- text/number 字段：列表操作符 → 多值 tag 输入 -->
                <ElSelect
                  v-else-if="LIST_OPS.has(cond.operator)"
                  v-model="cond.value"
                  class="w-full"
                  multiple
                  allow-create
                  filterable
                  default-first-option
                  :reserve-keyword="false"
                  placeholder="输入后按 Enter 确认"
                />
                <!-- 普通文本/数字输入 -->
                <ElInput
                  v-else
                  v-model="cond.value"
                  :placeholder="FIELD_MAP[cond.field]?.hint || '值'"
                />
              </ElCol>
              <ElCol :span="2" style="display:flex;justify-content:center">
                <ElButton type="danger" :icon="Delete" circle @click="removeCondition(idx)" />
              </ElCol>
            </ElRow>
            <!-- 落空/误杀风险提示：脏字段永不命中，可空字段配否定操作符会误杀 -->
            <div v-if="conditionRiskHint(cond.field, cond.operator)" class="condition-risk">
              <ElIcon><WarningFilled /></ElIcon>
              <span>{{ conditionRiskHint(cond.field, cond.operator) }}</span>
            </div>
          </div>
          <div style="margin-top:4px;margin-bottom:4px">
            <ElSpace>
              <ElButton size="small" :icon="Plus" @click="addCondition">添加条件</ElButton>
              <ElButton size="small" :icon="Files" @click="openTemplates">从模板套用</ElButton>
            </ElSpace>
          </div>

          <!-- ── 处置动作 ── -->
          <ElDivider content-position="left"><span class="section-label">处置动作</span></ElDivider>

          <div class="disposition-grid">
            <div v-for="branch in dispositionBranches" :key="branch.key" class="disposition-branch">
              <div class="disposition-branch__header">
                <span class="disposition-branch__label">{{ branch.label }}</span>
                <ElTooltip :content="branch.tip" placement="top" :show-after="200">
                  <ElIcon class="cursor-help text-g-400 ml-1"><QuestionFilled /></ElIcon>
                </ElTooltip>
              </div>
              <ElRow :gutter="12">
                <ElCol :span="10">
                  <ElFormItem label="机制" label-width="40px">
                    <ElSelect
                      v-model="branch.form.mechanism"
                      class="w-full"
                      @change="() => onMechanismChange(branch)"
                    >
                      <ElOption v-for="o in MECHANISM_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
                    </ElSelect>
                  </ElFormItem>
                </ElCol>
                <ElCol :span="8">
                  <ElFormItem label="TTL" label-width="36px">
                    <ElInputNumber v-model="branch.form.ttlSeconds" :min="0" :step="60" style="width:100%" />
                  </ElFormItem>
                </ElCol>
              </ElRow>
              <ElRow v-if="branch.form.mechanism === 'challenge'" :gutter="12">
                <ElCol :span="10">
                  <ElFormItem label="挑战" label-width="40px">
                    <ElSelect v-model="branch.form.challengeKind" class="w-full">
                      <ElOption v-for="o in CHALLENGE_KIND_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
                    </ElSelect>
                  </ElFormItem>
                </ElCol>
              </ElRow>
              <ElFormItem
                v-if="targetKindOptionsFor(branch.form.mechanism).length > 1"
                label="目标"
                label-width="70px"
              >
                <ElSelect v-model="branch.form.target.kind" class="w-full" @change="() => onTargetKindChange(branch)">
                  <ElOption
                    v-for="o in targetKindOptionsFor(branch.form.mechanism)"
                    :key="o.value"
                    :label="o.label"
                    :value="o.value"
                  />
                </ElSelect>
              </ElFormItem>

              <!-- serve_alt 的 target.url 存的是页面资源**名**，不是 URL -->
              <ElFormItem
                v-if="branch.form.target.kind === 'page_resource'"
                label="页面资源"
                label-width="70px"
              >
                <ElSelect
                  v-model="branch.form.target.url"
                  class="w-full"
                  filterable
                  :loading="pageResourceLoading"
                  placeholder="选择要投放的页面资源"
                  @visible-change="(v: boolean) => v && loadPageResources()"
                >
                  <ElOption
                    v-for="r in pageResourceOptions"
                    :key="r.value"
                    :label="r.label"
                    :value="r.value"
                  />
                  <template #empty>
                    <div class="px-3 py-2 text-xs text-g-500">
                      暂无已启用的页面资源，请先到「页面资源」页新建或从模板载入
                    </div>
                  </template>
                </ElSelect>
              </ElFormItem>

              <ElFormItem
                v-if="branch.form.target.kind === 'url' || (URL_REQUIRED_MECHANISMS.includes(branch.form.mechanism) && branch.form.target.kind !== 'url_pool')"
                label="目标URL"
                label-width="70px"
              >
                <ElInput
                  v-model="branch.form.target.url"
                  placeholder="https://example.com 支持 {ip} {fingerprint} {score} 等变量"
                >
                  <template #append>
                    <ElTooltip placement="top-end">
                      <template #content>
                        <div style="max-width:300px;font-size:12px;line-height:1.8">
                          {ip} {ip_enc} {fingerprint} {country} {score} {score_int} {verdict}<br>
                          {connection_type} {is_vpn} {is_proxy} {ua_enc} {referer_enc}<br>
                          {url} {url_enc} {scheme} {host} {path} {query} {app_id} {request_id}
                        </div>
                      </template>
                      <span class="text-xs cursor-help" style="color:#409eff">变量</span>
                    </ElTooltip>
                  </template>
                </ElInput>
              </ElFormItem>

              <!-- 轮询地址池：多地址按策略分摊 -->
              <RotationPoolEditor
                v-if="branch.form.target.kind === 'url_pool' && branch.form.target.rotation"
                :rotation="branch.form.target.rotation"
                @update:rotation="(r) => (branch.form.target.rotation = r)"
              />
            </div>
          </div>

        </ElForm>
      </ElScrollbar>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="saving" @click="submitRule">保存</ElButton>
      </template>
    </ElDialog>

    <!-- 规则模板选择弹窗 -->
    <ElDialog v-model="templateDialogVisible" title="从模板套用条件" width="720px" destroy-on-close>
      <p class="text-sm text-g-500 mb-3">
        套用后会覆盖当前的匹配条件与处置动作，名称和分组保持不变。可在套用后继续调整。
      </p>
      <ElScrollbar max-height="60vh">
        <div v-loading="templateLoading">
          <div v-for="t in templates" :key="t.id" class="template-item" @click="applyTemplate(t)">
            <div class="template-item__head">
              <span class="template-item__name">{{ t.name }}</span>
              <ElTag size="small" :type="t.priority === 'critical' ? 'danger' : t.priority === 'high' ? 'warning' : 'info'">
                {{ t.priority }}
              </ElTag>
              <ElTag v-if="t.kind === 'scoring'" size="small" type="info">打分规则</ElTag>
            </div>
            <div class="template-item__desc">{{ t.description }}</div>
            <div class="template-item__conds">
              <ElTag v-for="(c, i) in t.conditions || []" :key="i" size="small" effect="plain">
                {{ FIELD_MAP[c.field]?.label || c.field }}
                {{ OPERATOR_LABELS[c.op] || c.op }}
                {{ formatTemplateValue(c.field, c.value) }}
              </ElTag>
            </div>
          </div>
        </div>
      </ElScrollbar>
      <template #footer>
        <ElButton @click="templateDialogVisible = false">取消</ElButton>
      </template>
    </ElDialog>

    <!-- 分配站点弹窗（many-to-many 多选） -->
    <ElDialog v-model="assignDialogVisible" title="分配站点" width="420px" destroy-on-close>
      <p class="text-sm text-g-500 mb-4">为规则「{{ assigningRule?.name }}」选择绑定的站点（可多选，保存后全量覆盖）。</p>
      <ElSelect v-model="assignSelectedIds" multiple placeholder="选择站点" class="w-full"
        :loading="appLoading" clearable collapse-tags collapse-tags-tooltip>
        <ElOption v-for="o in appOptions" :key="o.value" :label="o.label" :value="o.value" />
      </ElSelect>
      <template #footer>
        <ElButton @click="assignDialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="assignSaving" @click="confirmAssign">确认</ElButton>
      </template>
    </ElDialog>
  </div>
</template>
<script setup lang="ts">
  import { Delete, Plus, QuestionFilled, Edit, Upload, VideoPause, Box, RefreshLeft, Files } from '@element-plus/icons-vue'
  import { useTable } from '@/hooks/core/useTable'
  import { fetchArchiveRule, fetchCreateGlobalRule, fetchDeleteRule, fetchDisableRule, fetchPublishRule, fetchUnarchiveRule, fetchUpdateRule, fetchSetRuleSites, fetchGetAllRules, fetchGetRuleTemplates } from '@/api/rules'
  import { fetchGetAppList } from '@/api/apps'
  import { RULE_PRIORITY_OPTIONS, RULE_STATUS_TAGS, RULE_STATUS_LABELS, pruneParams } from '@/constants/fangyu'
  import {
    MECHANISM_OPTIONS, CHALLENGE_KIND_OPTIONS,
    URL_REQUIRED_MECHANISMS, createDecisionDisposition,
    targetKindOptionsFor, defaultTargetKindFor, validateDisposition,
    createRotation
  } from '@/constants/disposition'
  import RotationPoolEditor from '@/components/RotationPoolEditor.vue'
  import { fetchGetPageResourceList } from '@/api/page-resources'
  import {
    FIELD_GROUPS, FIELD_MAP, getOperatorOptions, defaultValueFor, LIST_OPS,
    conditionRiskHint, OPERATOR_LABELS, optionLabel
  } from '@/constants/ruleFields'
  import { ElButton, ElIcon, ElSpace, ElTag, ElTooltip, ElMessage, ElMessageBox } from 'element-plus'
  import type { FormInstance, FormRules } from 'element-plus'

  defineOptions({ name: 'FangyuRules' })

  type Rule = Api.Fangyu.Rule
  type DecisionDisposition = Api.Fangyu.DecisionDisposition
  type RuleDialogType = 'add' | 'edit'

  function getDefaultOperator(field: string) {
    return getOperatorOptions(field)[0]?.value || 'eq'
  }

  const siteId      = ref<number>()
  const appOptions = ref<{ label: string; value: number }[]>([])
  const appLoading = ref(false)

  const dialogVisible    = ref(false)
  const dialogType    = ref<RuleDialogType>('add')
  const saving        = ref(false)
  const ruleFormRef   = ref<FormInstance>()
  const currentRule   = ref<Partial<Rule>>({})
  const selectedRules = ref<Rule[]>([])
  const batchActing   = ref(false)

  type ConditionRow = { field: string; operator: string; value: any }

  /**
   * 「空值」在下拉里的哨兵表示
   *
   * 后端用 null 表示「字段无数据」，可空字段配 neq null 即可排除数据缺失场景
   * （否定类操作符在取值为空时会命中，不排除会导致 MMDB 未加载时拦下全站）。
   * 但 ElOption 的 value prop 不接受 null，故在表单层用哨兵字符串承载，
   * 载入时转入、提交时还原。
   */
  const NULL_SENTINEL = '__null__'

  const INITIAL_FORM = () => ({
    name:        '',
    priority:    'normal' as string,
    group:       'default',
    description: '',
    matchAll:    true,
    conditions:  [] as ConditionRow[],
    disposition_match: createDecisionDisposition(),
    disposition_miss:  createDecisionDisposition()
  })

  const ruleForm = reactive(INITIAL_FORM())

  const ruleRules: FormRules = {
    name:     [{ required: true, message: '请输入规则名称', trigger: 'blur'   }],
    priority: [{ required: true, message: '请选择优先级',  trigger: 'change' }]
  }

  type DispositionBranch = {
    key: 'disposition_match' | 'disposition_miss'
    label: string
    tip: string
    form: DecisionDisposition
  }

  const dispositionBranches = computed<DispositionBranch[]>(() => [
    {
      key: 'disposition_match',
      label: '命中时',
      tip: '条件匹配成功时执行的处置动作，pass 表示立即放行并终止后续规则求值',
      form: ruleForm.disposition_match
    },
    {
      key: 'disposition_miss',
      label: '未命中时',
      tip: '条件未匹配时执行的处置动作，pass 表示放行并继续执行后续规则',
      form: ruleForm.disposition_miss
    }
  ])

  /**
   * 机制切换时同步纠正下游字段。
   *
   * 双向处理而非单向清理：切入 challenge 时补默认挑战类型，否则运维不点选就会
   * 提交出后端必然拒绝的处置（审计项 FY-DISP-010）。
   */
  function onMechanismChange(branch: DispositionBranch) {
    const mech = branch.form.mechanism
    branch.form.challengeKind = mech === 'challenge' ? (branch.form.challengeKind ?? 'captcha') : null

    // 机制变了，原目标类型可能已不合法，回落到该机制的默认值
    const allowed = targetKindOptionsFor(mech).map((o) => o.value)
    if (!allowed.includes(branch.form.target.kind)) {
      branch.form.target.kind = defaultTargetKindFor(mech)
    }
    // url 字段在 redirect 下是地址、serve_alt 下是资源名，语义不同，切换时一律清空
    if (!URL_REQUIRED_MECHANISMS.includes(mech) && branch.form.target.kind !== 'page_resource') {
      branch.form.target.url = null
    }
    // 目标类型可能已回落到非 url_pool，rotation 随之失效
    if (branch.form.target.kind !== 'url_pool') {
      branch.form.target.rotation = null
    }
  }

  function onTargetKindChange(branch: DispositionBranch) {
    // origin / status_only 不需要 url；page_resource 与 url 的取值语义又互不通用
    branch.form.target.url = null
    
    // 切换到 url_pool 时初始化 rotation；切换离开时清空
    if (branch.form.target.kind === 'url_pool') {
      if (!branch.form.target.rotation) {
        branch.form.target.rotation = createRotation()
      }
    } else {
      branch.form.target.rotation = null
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

  function addCondition()             { ruleForm.conditions.push({ field: 'ip.ip', operator: 'eq', value: '' }) }
  function removeCondition(i: number) { ruleForm.conditions.splice(i, 1) }

  /* ── 规则模板 ── */
  const templateDialogVisible = ref(false)
  const templateLoading = ref(false)
  const templates = ref<Api.Fangyu.RuleTemplate[]>([])

  async function openTemplates() {
    templateDialogVisible.value = true
    if (templates.value.length) return
    templateLoading.value = true
    try {
      templates.value = (await fetchGetRuleTemplates()) ?? []
    } finally {
      templateLoading.value = false
    }
  }

  /** 模板条件取值的展示文案，枚举值走中文映射，与条件编辑器保持一致 */
  function formatTemplateValue(field: string, v: unknown) {
    if (v === null) return '空'
    if (typeof v === 'boolean') return v ? '是' : '否'
    const hasOptions = Boolean(FIELD_MAP[field]?.options?.length)
    const render = (x: unknown) =>
      hasOptions && typeof x === 'string' ? optionLabel(field, x) : String(x)
    if (Array.isArray(v)) return v.map(render).join(' / ')
    return render(v)
  }

  /**
   * 套用模板到当前表单
   *
   * 打分模板没有 disposition，套用时只覆盖条件，保留表单已有的处置动作，
   * 由运营自行决定——否则会把处置清成默认值而运营不易察觉。
   */
  function applyTemplate(t: Api.Fangyu.RuleTemplate) {
    ruleForm.conditions = (t.conditions ?? []).map((c) => ({
      field: c.field,
      operator: c.op,
      value: c.value === null ? NULL_SENTINEL : (c.value as any)
    }))
    ruleForm.matchAll = true
    if (t.priority) ruleForm.priority = t.priority
    if (!ruleForm.description) ruleForm.description = t.description ?? ''
    if (t.disposition) {
      const mech = t.disposition.mechanism
      // 必须带上 target.kind：漏掉会让后端收到 kind=undefined，
      // page_resource / url 这类必须有 kind 才成立的目标类型直接失配。
      ruleForm.disposition_match = {
        mechanism: mech,
        challengeKind: t.disposition.challengeKind ?? null,
        ttlSeconds: t.disposition.ttlSeconds ?? 300,
        target: {
          kind: t.disposition.target?.kind ?? defaultTargetKindFor(mech),
          url: t.disposition.target?.url ?? null,
          urls: t.disposition.target?.urls ?? null,
          rotation: t.disposition.target?.rotation ?? null,
          httpStatus: t.disposition.target?.httpStatus ?? null
        }
      }
    }
    templateDialogVisible.value = false
    ElMessage.success(`已套用模板「${t.name}」`)
  }

  const {
    columns, columnChecks, data, loading, pagination, getData, fetchData,
    replaceSearchParams, handleSizeChange, handleCurrentChange, refreshData,
  } = useTable({
    core: {
      apiFn: (params: any) => fetchGetAllRules(pruneParams(params)),
      apiParams: { page: 1, pageSize: 20 },
      immediate: true,
      columnsFactory: () => [
        { type: 'selection', width: 50 },
        { prop: 'id',       label: 'ID',     width: 60 },
        { prop: 'name',     label: '名称',   width: 200, showOverflowTooltip: true },
        { prop: 'status',   label: '状态',   width: 100,
          formatter: (r: Rule) => h(ElTag, { size: 'small', type: RULE_STATUS_TAGS[r.status] ?? 'info' }, () => RULE_STATUS_LABELS[r.status] ?? r.status) },
        { prop: 'priority', label: '优先级', width: 100 },
        { prop: 'version',  label: '版本',   width: 100 },
        { prop: 'group',    label: '分组',   width: 100, formatter: (r: Rule) => r.group ?? '-' },
        { prop: 'siteIds', label: '绑定站点', width: 100,
          formatter: (r: Rule) => r.siteIds?.length
            ? h(ElTag, { size: 'small', type: 'primary' }, () => `${r.siteIds.length} 个站点`)
            : h(ElTag, { size: 'small', type: 'info' }, () => '未分配') },
        { prop: 'operation', label: '操作', width: 320, fixed: 'right',
          formatter: (r: any) => {
            const btns: ReturnType<typeof h>[] = []
            const s = r.status
            const btn = (type: 'primary' | 'success' | 'warning' | 'danger', icon: any, text: string, onClick: () => void) =>
              h(ElButton, { link: true, type, size: 'small', onClick },
                { default: () => [h(ElIcon, { class: 'mr-0.5' }, () => h(icon)), text] })
            if (s !== 'archived') {
              btns.push(btn('primary', Edit, '编辑', () => showDialog('edit', r)))
              btns.push(btn('primary', Upload, '分配站点', () => openAssignDialog(r)))
            }
            if (s === 'draft') {
              btns.push(btn('success', Upload, '发布', () => publishRule(r)))
              btns.push(btn('warning', Box, '归档', () => archiveRule(r)))
              btns.push(btn('danger',  Delete, '删除', () => deleteRule(r)))
            } else if (s === 'published') {
              btns.push(btn('warning', VideoPause, '停用', () => disableRule(r)))
              btns.push(btn('warning', Box, '归档', () => archiveRule(r)))
            } else if (s === 'disabled') {
              btns.push(btn('success', Upload, '发布', () => publishRule(r)))
              btns.push(btn('warning', Box, '归档', () => archiveRule(r)))
            } else if (s === 'archived') {
              btns.push(btn('primary', RefreshLeft, '恢复', () => unarchiveRule(r)))
              btns.push(btn('danger',  Delete, '删除', () => deleteRule(r)))
            }
            return h(ElSpace, { size: 4 }, () => btns)
          }
        },
      ],
    },
  })

  // ── 分配站点弹窗 ────────────────────────────────────────────────────────────
  const assignDialogVisible = ref(false)
  const assigningRule       = ref<Rule | null>(null)
  const assignSiteId        = ref<number | null>(null)
  const assignSaving        = ref(false)

  const loadApps = async () => {
    appLoading.value = true
    try {
      const res = await fetchGetAppList({ page: 1, pageSize: 100 })
      appOptions.value = (res.items || []).map((i: any) => ({ label: i.name, value: i.id }))
    } finally { appLoading.value = false }
  }

  /** 分配站点弹窗改为多选（many-to-many） */
  const assignSelectedIds = ref<number[]>([])

  function openAssignDialog(r: Rule) {
    assigningRule.value      = r
    assignSelectedIds.value  = [...(r.siteIds ?? [])]
    assignDialogVisible.value = true
    if (!appOptions.value.length) loadApps()
  }

  async function confirmAssign() {
    if (!assigningRule.value) return
    assignSaving.value = true
    try {
      await fetchSetRuleSites(assigningRule.value.id, assignSelectedIds.value)
      ElMessage.success(`已更新绑定站点（共 ${assignSelectedIds.value.length} 个）`)
      assignDialogVisible.value = false
      await fetchData()
    } finally { assignSaving.value = false }
  }

  function showDialog(type: RuleDialogType, row?: Rule) {
    dialogType.value  = type
    currentRule.value = row ?? {}
    Object.assign(ruleForm, INITIAL_FORM())
    if (type === 'edit' && row) {
      const getDisp = (d: any): DecisionDisposition => d
        ? JSON.parse(JSON.stringify(d))
        : createDecisionDisposition()

      Object.assign(ruleForm, {
        name:        row.name        ?? '',
        priority:    row.priority    ?? 'normal',
        group:       row.group       ?? 'default',
        description: row.description ?? '',
        matchAll:    (row as any).matchAll ?? (row as any).match_all ?? true,
        conditions:  Array.isArray(row.conditions)
          ? row.conditions.map((c: any) => ({
              field:    c.field,
              operator: c.op ?? c.operator,
              // 不能用 ?? '' 兜底：null 是有意义的取值（「字段不等于空」用来
              // 排除数据缺失），转成空串会静默改变规则语义。
              value:    c.value === null ? NULL_SENTINEL : (c.value ?? ''),
            }))
          : [],
        disposition_match: getDisp((row as any).disposition_match ?? row.disposition),
        disposition_miss:  getDisp((row as any).disposition_miss)
      })
    }
    dialogVisible.value = true
  }

  async function submitRule() {
    const valid = await ruleFormRef.value?.validate().catch(() => false)
    if (!valid) return
    if (ruleForm.conditions.length === 0) {
      ElMessage.warning('至少需要添加一个匹配条件')
      return
    }
    // 处置校验与后端语义一致，前置在此是为了给出带分支名的具体提示，
    // 而不是让运维对着后端的通用 ValueError 猜哪条分支配错了
    for (const branch of dispositionBranches.value) {
      const err = validateDisposition(branch.form)
      if (err) {
        ElMessage.warning(`${branch.label}处置：${err}`)
        return
      }
    }
    saving.value = true
    try {
      const conditions = ruleForm.conditions.map((c) => ({
        field: c.field,
        op:    c.operator,
        // 哨兵值还原为 null，后端据此判断「字段无数据」
        value: c.value === NULL_SENTINEL ? null : c.value,
      }))
      const payload: Api.Fangyu.RulePayload = {
        name:              ruleForm.name,
        priority:          ruleForm.priority,
        group:             ruleForm.group || undefined,
        description:       ruleForm.description || undefined,
        conditions,
        matchAll:          ruleForm.matchAll,
        disposition_match: ruleForm.disposition_match,
        disposition_miss:  ruleForm.disposition_miss
      }
      if (dialogType.value === 'add') {
        await fetchCreateGlobalRule(payload)
        ElMessage.success('规则创建成功')
      } else {
        await fetchUpdateRule(0, (currentRule.value as Rule).id, payload)
        ElMessage.success('规则已保存')
      }
      dialogVisible.value = false
      await fetchData()
    } finally { saving.value = false }
  }

  function publishRule(r: Rule) {
    ElMessageBox.confirm(`发布规则「${r.name}」？发布后立即对线上流量生效。`, '发布规则',
      { confirmButtonText: '发布', cancelButtonText: '取消', type: 'success' }
    ).then(async () => { await fetchPublishRule(r.id); ElMessage.success('已发布'); await fetchData() })
  }
  function disableRule(r: Rule) {
    ElMessageBox.confirm(`停用规则「${r.name}」？`, '停用规则', { confirmButtonText: '停用', type: 'warning' })
      .then(async () => { await fetchDisableRule(r.id); ElMessage.success('已停用'); await fetchData() })
  }
  function archiveRule(r: Rule) {
    ElMessageBox.confirm(`归档规则「${r.name}」？归档后可恢复为草稿。`, '归档规则', { confirmButtonText: '归档', type: 'error' })
      .then(async () => { await fetchArchiveRule(r.id); ElMessage.success('已归档'); await fetchData() })
  }
  function unarchiveRule(r: Rule) {
    ElMessageBox.confirm(`恢复规则「${r.name}」为草稿？`, '恢复规则', { confirmButtonText: '恢复', type: 'info' })
      .then(async () => { await fetchUnarchiveRule(r.id); ElMessage.success('已恢复为草稿'); await fetchData() })
  }
  function deleteRule(r: Rule) {
    ElMessageBox.confirm(`永久删除规则「${r.name}」？此操作不可撤销。`, '删除规则', { confirmButtonText: '删除', type: 'error' })
      .then(async () => { await fetchDeleteRule(r.id); ElMessage.success('已删除'); await fetchData() })
  }

  function handleSelectionChange(rows: Rule[]) {
    selectedRules.value = rows
  }

  async function batchPublish() {
    if (!selectedRules.value.length) return
    try { await ElMessageBox.confirm(`批量发布选中的 ${selectedRules.value.length} 条规则？`, '批量发布', { type: 'success' }) } catch { return }
    batchActing.value = true
    const results = await Promise.allSettled(selectedRules.value.map(r => fetchPublishRule(r.id)))
    batchActing.value = false
    const ok = results.filter(r => r.status === 'fulfilled').length
    const fail = results.length - ok
    ElMessage[fail ? 'warning' : 'success'](fail ? `已发布 ${ok} 条，失败 ${fail} 条` : `已批量发布 ${ok} 条`)
    await fetchData()
  }

  async function batchDisable() {
    if (!selectedRules.value.length) return
    try { await ElMessageBox.confirm(`批量停用选中的 ${selectedRules.value.length} 条规则？`, '批量停用', { type: 'warning' }) } catch { return }
    batchActing.value = true
    const results = await Promise.allSettled(selectedRules.value.map(r => fetchDisableRule(r.id)))
    batchActing.value = false
    const ok = results.filter(r => r.status === 'fulfilled').length
    const fail = results.length - ok
    ElMessage[fail ? 'warning' : 'success'](fail ? `已停用 ${ok} 条，失败 ${fail} 条` : `已批量停用 ${ok} 条`)
    await fetchData()
  }

  async function batchArchive() {
    if (!selectedRules.value.length) return
    try { await ElMessageBox.confirm(`批量归档选中的 ${selectedRules.value.length} 条规则？`, '批量归档', { type: 'error' }) } catch { return }
    batchActing.value = true
    const results = await Promise.allSettled(selectedRules.value.map(r => fetchArchiveRule(r.id)))
    batchActing.value = false
    const ok = results.filter(r => r.status === 'fulfilled').length
    const fail = results.length - ok
    ElMessage[fail ? 'warning' : 'success'](fail ? `已归档 ${ok} 条，失败 ${fail} 条` : `已批量归档 ${ok} 条`)
    await fetchData()
  }

  onMounted(() => { fetchData() })
</script>

<style scoped>
.section-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.disposition-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 8px;
}

.disposition-branch {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 12px 16px 4px;
  background: var(--el-fill-color-lighter);
}

.disposition-branch__header {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.disposition-branch__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.condition-risk {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  margin: 4px 0 0 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-color-warning);
}

.template-item {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.template-item:hover {
  border-color: var(--el-color-primary);
  background: var(--el-fill-color-lighter);
}

.template-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.template-item__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.template-item__desc {
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}

.template-item__conds {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
