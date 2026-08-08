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
                  @change="handleFieldChange(idx)"
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
                  @change="handleOperatorChange(idx)"
                >
                  <ElOption 
                    v-for="op in getSupportedOperators(cond.field)" 
                    :key="op.value" 
                    :label="op.label" 
                    :value="op.value" 
                  />
                </ElSelect>
              </ElCol>
              <ElCol :span="10">
                <SmartValueInput
                  v-model="cond.value"
                  :field-key="cond.field"
                  :operator="cond.operator"
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
                          {url} {url_enc} {scheme} {host} {path} {handle} {query} {app_id} {request_id}
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
    <RuleTemplateDialog v-model="templateDialogVisible" @select="applyTemplate" />

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
  import { ref, reactive, computed, h, onMounted } from 'vue'
  import { useTable } from '@/hooks/core/useTable'
  import { Delete, Plus, QuestionFilled, Edit, Upload, VideoPause, Box, RefreshLeft, Files, View, WarningFilled } from '@element-plus/icons-vue'
  import type { FormInstance, FormRules } from 'element-plus'
  import { ElButton, ElIcon, ElSpace, ElTag, ElTooltip, ElMessage, ElMessageBox } from 'element-plus'
  import { fetchArchiveRule, fetchCreateGlobalRule, fetchDeleteRule, fetchDisableRule, fetchPublishRule, fetchShadowRule, fetchUnarchiveRule, fetchUpdateRule, fetchSetRuleSites, fetchGetAllRules } from '@/api/rules'
  import SmartValueInput from '@/components/SmartValueInput.vue'
  import { getFieldType } from '@/constants/fieldMetadata'
  import { fetchGetAppList } from '@/api/apps'
  import { RULE_PRIORITY_OPTIONS, RULE_STATUS_TAGS, RULE_STATUS_LABELS, pruneParams } from '@/constants/fangyu'
  import {
    MECHANISM_OPTIONS, CHALLENGE_KIND_OPTIONS,
    URL_REQUIRED_MECHANISMS, createDecisionDisposition,
    targetKindOptionsFor, defaultTargetKindFor, validateDisposition,
    createRotation
  } from '@/constants/disposition'
  import RotationPoolEditor from '@/components/RotationPoolEditor.vue'
  import RuleTemplateDialog from '@/components/RuleTemplateDialog.vue'
  import { fetchGetPageResourceList } from '@/api/page-resources'
  import {
    FIELD_GROUPS, FIELD_MAP, getOperatorOptions, defaultValueFor, LIST_OPS,
    conditionRiskHint, OPERATOR_LABELS
  } from '@/constants/ruleFields'
  import type { RuleTemplate } from '@/constants/ruleTemplates'

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

  // ========== 工具函数 ==========
  // 获取字段支持的操作符
  // 缓存操作符选项，避免重复计算
  const operatorCache = new Map<string, Array<{ label: string; value: string }>>()
  const getSupportedOperators = (field: string) => {
    if (!operatorCache.has(field)) {
      operatorCache.set(field, getOperatorOptions(field))
    }
    return operatorCache.get(field)!
  }

  // 获取操作符标签
  const getOperatorLabel = (op: string) => {
    return OPERATOR_LABELS[op] || op
  }

  function addCondition()             { ruleForm.conditions.push({ field: 'ip.ip', operator: 'eq', value: '' }) }
  function removeCondition(i: number) { ruleForm.conditions.splice(i, 1) }

  /* ── 智能组件处理函数 ── */
  function handleFieldChange(idx: number) {
    const cond = ruleForm.conditions[idx]
    // 字段改变时，重置操作符为该字段的默认操作符
    const supportedOps = getSupportedOperators(cond.field)
    cond.operator = supportedOps.length > 0 ? supportedOps[0].value : 'eq'
    // 重置值
    const fieldType = getFieldType(cond.field)
    if (fieldType === 'bool') {
      cond.value = true
    } else if (['in', 'in_ci', 'not_in', 'not_in_ci'].includes(cond.operator)) {
      cond.value = []
    } else {
      cond.value = ''
    }
  }

  function handleOperatorChange(idx: number) {
    const cond = ruleForm.conditions[idx]
    // 操作符改变时，调整值的类型
    const isListOp = ['in', 'in_ci', 'not_in', 'not_in_ci'].includes(cond.operator)
    if (isListOp && !Array.isArray(cond.value)) {
      cond.value = cond.value ? [cond.value] : []
    } else if (!isListOp && Array.isArray(cond.value)) {
      cond.value = cond.value.length > 0 ? cond.value[0] : ''
    }
  }

  /* ── 规则模板 ── */
  const templateDialogVisible = ref(false)

  function openTemplates() {
    templateDialogVisible.value = true
  }

  /**
   * 套用模板到当前表单
   * 
   * 新模板系统使用 onMatch/onMiss 替代旧的 disposition
   */
  function applyTemplate(t: RuleTemplate) {
    // 填充条件（注意新模板使用 operator 而非 op）
    ruleForm.conditions = (t.conditions ?? []).map((c) => ({
      field: c.field,
      operator: c.operator,
      value: c.value === null ? NULL_SENTINEL : (c.value as any)
    }))
    
    // 设置匹配模式和基础信息
    ruleForm.matchAll = t.matchAll ?? true
    if (t.priority) ruleForm.priority = t.priority
    if (!ruleForm.description) ruleForm.description = t.description ?? ''
    
    // 填充处置动作（onMatch）
    if (t.onMatch) {
      const mech = t.onMatch.mechanism
      ruleForm.disposition_match = {
        mechanism: mech,
        challengeKind: t.onMatch.challengeKind ?? null,
        ttlSeconds: t.onMatch.ttlSeconds ?? 300,
        target: {
        kind: t.onMatch.target?.kind ?? defaultTargetKindFor(mech),
        url: t.onMatch.target?.url ?? null,
        urls: (t.onMatch.target as any)?.urls ?? null,
        rotation: (t.onMatch.target as any)?.rotation ?? null,
        httpStatus: t.onMatch.target?.statusCode ?? null
      } as Api.Fangyu.DispositionTarget
      }
    }
    
    // 填充未命中处置动作（onMiss，通常为 allow）
    if (t.onMiss) {
      const mech = t.onMiss.mechanism
      ruleForm.disposition_miss = {
        mechanism: mech,
        challengeKind: t.onMiss.challengeKind ?? null,
        ttlSeconds: t.onMiss.ttlSeconds ?? 0,
        target: {
        kind: t.onMiss.target?.kind ?? defaultTargetKindFor(mech),
        url: t.onMiss.target?.url ?? null,
        urls: (t.onMiss.target as any)?.urls ?? null,
        rotation: (t.onMiss.target as any)?.rotation ?? null,
        httpStatus: t.onMiss.target?.statusCode ?? null
      } as Api.Fangyu.DispositionTarget
      }
    }
    
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
        { type: 'selection', width: 55 },
        { prop: 'id',       label: 'ID',     width: 80 },
        { prop: 'name',     label: '名称',   minWidth: 180, showOverflowTooltip: true },
        { prop: 'status',   label: '状态',   width: 90,
          formatter: (r: Rule) => h(ElTag, { size: 'small', type: RULE_STATUS_TAGS[r.status] ?? 'info' }, () => RULE_STATUS_LABELS[r.status] ?? r.status) },
        { prop: 'priority', label: '优先级', width: 90 },
        { prop: 'version',  label: '版本',   width: 80 },
        { prop: 'group',    label: '分组',   width: 120, showOverflowTooltip: true, formatter: (r: Rule) => r.group ?? '-' },
        { prop: 'siteIds', label: '绑定站点', width: 120,
          formatter: (r: Rule) => r.siteIds?.length
            ? h(ElTag, { size: 'small', type: 'primary' }, () => `${r.siteIds.length} 个站点`)
            : h(ElTag, { size: 'small', type: 'info' }, () => '未分配') },
        { prop: 'operation', label: '操作', width: 360, fixed: 'right',
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
              btns.push(btn('primary', View, '影子', () => shadowRule(r)))
              btns.push(btn('warning', Box, '归档', () => archiveRule(r)))
              btns.push(btn('danger',  Delete, '删除', () => deleteRule(r)))
            } else if (s === 'shadow') {
              // 影子只有三条出路，与状态机 _TRANSITIONS[SHADOW] 一一对应：
              // 观察合格→发布、有问题→退回草稿、直接放弃→归档。没有「停用」，
              // 因为 shadow→disabled 被状态机禁止（两者都不参与真实处置）。
              btns.push(btn('success', Upload, '发布', () => publishRule(r)))
              btns.push(btn('primary', RefreshLeft, '退回草稿', () => unarchiveRule(r)))
              btns.push(btn('warning', Box, '归档', () => archiveRule(r)))
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
    
    if (type === 'add') {
      // 新建规则：使用初始表单
      Object.assign(ruleForm, INITIAL_FORM())
    } else if (type === 'edit' && row) {
      // 编辑规则：使用浅拷贝优化性能
      const getDisp = (d: any): DecisionDisposition => d
        ? { ...d, rotation: d.rotation ? { ...d.rotation } : undefined }
        : createDecisionDisposition()

      // 直接赋值，避免深拷贝
      ruleForm.name = row.name ?? ''
      ruleForm.priority = row.priority ?? 'normal'
      ruleForm.group = row.group ?? 'default'
      ruleForm.description = row.description ?? ''
      ruleForm.matchAll = (row as any).matchAll ?? (row as any).match_all ?? true
      
      // 条件数组：只在必要时转换
      if (Array.isArray(row.conditions)) {
        ruleForm.conditions = row.conditions.map((c: any) => ({
          field:    c.field,
          operator: c.op ?? c.operator,
          value:    c.value === null ? NULL_SENTINEL : (c.value ?? ''),
        }))
      } else {
        ruleForm.conditions = []
      }
      
      ruleForm.disposition_match = getDisp((row as any).disposition_match ?? row.disposition)
      ruleForm.disposition_miss = getDisp((row as any).disposition_miss)
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
  function shadowRule(r: Rule) {
    ElMessageBox.confirm(
      `将规则「${r.name}」置为灰度影子？规则会下发到线上求值并记录命中影响面，但不会真的拦截流量。`,
      '灰度影子', { confirmButtonText: '进入影子', cancelButtonText: '取消', type: 'info' }
    ).then(async () => { await fetchShadowRule(r.id); ElMessage.success('已进入灰度影子'); await fetchData() })
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
