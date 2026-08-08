<template>
  <ElDialog
    v-model="dialogVisible"
    :title="isEdit ? '编辑站点' : '新建站点'"
    width="640px"
    align-center
    :close-on-click-modal="false"
  >
    <ElForm ref="formRef" :model="form" :rules="rules" label-width="110px">
      <ElTabs v-model="activeTab" type="border-card">
        <ElTabPane label="基础配置" name="basic">
          <div class="tab-pane-body">
            <ElFormItem v-if="isEdit" label="Site Key">
              <span class="readonly-text">{{ appData?.site_key }}</span>
            </ElFormItem>

            <ElFormItem label="所属应用" prop="app_id">
              <ElSelect
                v-model="form.app_id"
                placeholder="请选择所属应用"
                :loading="appLoading"
                :disabled="isEdit"
                filterable
                class="w-full"
              >
                <ElOption
                  v-for="opt in appOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </ElSelect>
              <div v-if="isEdit" class="form-tip">所属应用创建后不可变更</div>
            </ElFormItem>

            <ElFormItem label="站点名称" prop="name">
              <ElInput v-model="form.name" placeholder="如：官方商城" />
            </ElFormItem>

            <ElFormItem label="主域名" prop="domain">
              <ElInput
                v-model="form.domain"
                placeholder="如：www.example.com"
                :disabled="isEdit"
              />
              <div v-if="isEdit" class="form-tip">主域名创建后不可修改</div>
            </ElFormItem>

            <ElFormItem label="备用域名">
              <div class="w-full">
                <ElTag
                  v-for="d in form.alt_domains"
                  :key="d"
                  class="mr-2 mb-2"
                  closable
                  :disable-transitions="false"
                  @close="removeAltDomain(d)"
                >{{ d }}</ElTag>
                <ElInput
                  v-if="altDomainInputVisible"
                  ref="altDomainInputRef"
                  v-model="altDomainInputValue"
                  class="!w-48 mb-2"
                  size="small"
                  placeholder="example.com"
                  @keyup.enter="confirmAltDomain"
                  @blur="confirmAltDomain"
                />
                <ElButton v-else class="mb-2" size="small" @click="showAltDomainInput">+ 新增备用域名</ElButton>
              </div>
            </ElFormItem>

            <ElFormItem label="接入模式" prop="access_mode">
              <ElRadioGroup v-model="form.access_mode">
                <ElRadioButton value="adapter">适配器</ElRadioButton>
                <ElRadioButton value="sdk">SDK 接入</ElRadioButton>
              </ElRadioGroup>
            </ElFormItem>

            <ElFormItem v-if="isEdit" label="启用状态">
              <ElSwitch v-model="form.is_active" />
            </ElFormItem>

            <ElFormItem label="备注">
              <ElInput
                v-model="form.remark"
                type="textarea"
                :rows="2"
                placeholder="备注信息（选填）"
              />
            </ElFormItem>
          </div>
        </ElTabPane>

        <ElTabPane label="风控规则" name="rules">
          <div class="tab-pane-body">
            <template v-if="isEdit">
              <ElFormItem label="绑定规则">
                <div class="w-full">
                  <div v-if="rulesLoading" class="py-4 text-center text-g-400 text-sm">加载中…</div>
                  <template v-else>
                    <div class="rule-select-tip text-sm text-g-500 mb-2">
                      从下方列表中选择要绑定到该站点的风控规则（可多选）。
                      已发布的规则保存后立即生效。
                    </div>
                    <ElCheckboxGroup v-model="selectedRuleIds" class="rule-checkbox-group">
                      <div
                        v-for="rule in allRules"
                        :key="rule.id"
                        class="rule-checkbox-item"
                      >
                        <ElCheckbox :value="rule.id">
                          <div class="rule-checkbox-label">
                            <span class="rule-item__name">{{ rule.name }}</span>
                            <ElTag size="small" :type="RULE_STATUS_TAGS[rule.status] || 'info'" class="ml-2">
                              {{ RULE_STATUS_LABELS[rule.status] || rule.status }}
                            </ElTag>
                            <span v-if="rule.description" class="rule-item__desc ml-2">{{ rule.description }}</span>
                          </div>
                        </ElCheckbox>
                      </div>
                    </ElCheckboxGroup>
                    <div v-if="!allRules.length" class="py-4 text-center text-g-400 text-sm">
                      暂无自定义风控规则，请先在「规则列表」中创建。
                    </div>
                  </template>
                </div>
              </ElFormItem>
            </template>
            <template v-else>
              <ElAlert type="info" :closable="false" class="mt-2">
                站点创建后，可在「规则列表」或此处「风控规则」标签页为该站点绑定具体的分控规则。
              </ElAlert>
            </template>
          </div>
        </ElTabPane>

        <ElTabPane label="高级设置" name="advanced">
          <div class="tab-pane-body">
            <ElFormItem label="时钟统计">
              <ElSwitch v-model="form.clock_stats_enabled" />
              <span class="form-tip ml-3">记录站点请求的 Clock 时序统计</span>
            </ElFormItem>

            <ElFormItem label="日志保留天数" prop="log_retention_days">
              <ElInputNumber
                v-model="form.log_retention_days"
                :min="1"
                :max="365"
                style="width: 160px"
              />
              <span class="form-tip ml-3">天</span>
            </ElFormItem>
          </div>
        </ElTabPane>
      </ElTabs>
    </ElForm>

    <template #footer>
      <ElButton @click="dialogVisible = false">取消</ElButton>
      <ElButton type="primary" :loading="saving" @click="handleSubmit" v-ripple>
        {{ isEdit ? '保存' : '创建站点' }}
      </ElButton>
    </template>
  </ElDialog>
</template>

<script setup lang="ts">
import { fetchCreateSite, fetchUpdateSite, fetchGetApplicationList } from '@/api/apps'
import { fetchGetAllRules, fetchBindRulesToSite } from '@/api/rules'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules, InputInstance } from 'element-plus'
import type { DialogType } from '@/types'
import { RULE_STATUS_TAGS, RULE_STATUS_LABELS } from '@/constants/fangyu'

interface Props {
  visible: boolean
  type: DialogType
  appData?: Partial<Api.Fangyu.Site>
}

interface Emits {
  (e: 'update:visible', value: boolean): void
  (e: 'submit'): void
  (e: 'created', site: Api.Fangyu.SiteDetail): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value)
})

const isEdit = computed(() => props.type === 'edit')
const activeTab = ref('basic')
const formRef = ref<FormInstance>()
const saving = ref(false)

/** 所有规则（全局列表，多选用） */
const allRules = ref<Api.Fangyu.Rule[]>([])
const rulesLoading = ref(false)
/** 当前站点已绑定的规则 id 列表 */
const selectedRuleIds = ref<number[]>([])
/** 规则绑定是否被修改（避免每次保存都调用 bind API） */
const rulesChanged = ref(false)

/** 应用选项（下拉用） */
const appOptions = ref<Array<{ label: string; value: number }>>([])
const appLoading = ref(false)

const loadApplications = async () => {
  appLoading.value = true
  try {
    const res = await fetchGetApplicationList({ page: 1, pageSize: 100 })
    appOptions.value = (res.items || []).map((app) => ({ label: app.name, value: app.id }))
  } finally {
    appLoading.value = false
  }
}

const loadAllRules = async () => {
  if (allRules.value.length) return
  rulesLoading.value = true
  try {
    const res = await fetchGetAllRules({ page: 1, pageSize: 200 })
    allRules.value = res.items ?? []
  } finally {
    rulesLoading.value = false
  }
}

const loadSiteRules = async (siteId: number) => {
  try {
    const res = await fetchGetAllRules({ siteId, page: 1, pageSize: 200 })
    selectedRuleIds.value = (res.items ?? []).map((r) => r.id)
  } catch (err) {
    console.error('加载站点规则失败:', err)
  }
}

watch(selectedRuleIds, () => {
  rulesChanged.value = true
}, { deep: true })

watch(activeTab, (tab) => {
  if (tab === 'rules') {
    loadAllRules()
    if (isEdit.value && props.appData?.id) {
      loadSiteRules(props.appData.id)
    }
  }
})

const defaultForm = () => ({
  app_id: undefined as number | undefined,
  name: '',
  domain: '',
  alt_domains: [] as string[],
  access_mode: 'adapter' as 'adapter' | 'sdk',
  sdk_version: null as string | null,
  gateway_url: null as string | null,
  is_active: true,
  clock_stats_enabled: false,
  log_retention_days: 30,
  remark: null as string | null
})

const form = reactive(defaultForm())

const rules: FormRules = {
  app_id: [{ required: true, message: '请选择所属应用', trigger: 'change' }],
  name: [{ required: true, message: '请输入站点名称', trigger: 'blur' }],
  domain: [
    { required: true, message: '请输入主域名', trigger: 'blur' },
    {
      pattern: /^(https?:\/\/)?([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(\/.*)?$/,
      message: '请输入有效的域名格式',
      trigger: 'blur'
    }
  ],
  access_mode: [{ required: true, message: '请选择接入模式', trigger: 'change' }]
}

const altDomainInputVisible = ref(false)
const altDomainInputValue = ref('')
const altDomainInputRef = ref<InputInstance>()

const showAltDomainInput = () => {
  altDomainInputVisible.value = true
  nextTick(() => altDomainInputRef.value?.focus())
}

const confirmAltDomain = () => {
  const val = altDomainInputValue.value.trim()
  if (val && !form.alt_domains.includes(val)) {
    form.alt_domains.push(val)
  }
  altDomainInputVisible.value = false
  altDomainInputValue.value = ''
}

const removeAltDomain = (domain: string) => {
  form.alt_domains = form.alt_domains.filter((d) => d !== domain)
}

const initForm = () => {
  const d = defaultForm()
  if (isEdit.value && props.appData) {
    const s = props.appData
    Object.assign(form, {
      ...d,
      app_id: s.app_id,
      name: s.name || '',
      domain: s.domain || '',
      alt_domains: Array.isArray(s.alt_domains) ? [...s.alt_domains] : [],
      access_mode: (s.access_mode as 'adapter' | 'sdk') || 'adapter',
      sdk_version: s.sdk_version ?? null,
      gateway_url: s.gateway_url ?? null,
      is_active: s.is_active !== undefined ? s.is_active : true,
      clock_stats_enabled: s.clock_stats_enabled || false,
      log_retention_days: s.log_retention_days ?? 30,
      remark: s.remark ?? null
    })
  } else {
    Object.assign(form, d)
  }
  altDomainInputVisible.value = false
  altDomainInputValue.value = ''
  activeTab.value = 'basic'
  selectedRuleIds.value = []
  rulesChanged.value = false
}

watch(
  () => [props.visible, props.type, props.appData],
  ([visible]) => {
    if (visible) {
      initForm()
      nextTick(() => formRef.value?.clearValidate())
      // 应用列表用于「所属应用」下拉
      loadApplications()
      // 预加载所有规则列表（避免切换 tab 时延迟）
      loadAllRules()
      // 如果是编辑模式，预加载当前站点的规则绑定
      if (isEdit.value && props.appData?.id) {
        loadSiteRules(props.appData.id)
      }
    }
  },
  { immediate: true }
)

const buildCreatePayload = (): Api.Fangyu.SiteCreatePayload => ({
  app_id: form.app_id!,
  name: form.name,
  domain: form.domain,
  alt_domains: form.alt_domains,
  access_mode: form.access_mode,
  sdk_version: form.access_mode === 'sdk' ? form.sdk_version : null,
  gateway_url: form.gateway_url || null,
  clock_stats_enabled: form.clock_stats_enabled,
  log_retention_days: form.log_retention_days,
  remark: form.remark || null
})

const buildUpdatePayload = (): Api.Fangyu.SiteUpdatePayload => ({
  name: form.name,
  alt_domains: form.alt_domains,
  access_mode: form.access_mode,
  sdk_version: form.access_mode === 'sdk' ? form.sdk_version : null,
  gateway_url: form.gateway_url || null,
  is_active: form.is_active,
  clock_stats_enabled: form.clock_stats_enabled,
  log_retention_days: form.log_retention_days,
  remark: form.remark || null
})

const handleSubmit = async () => {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    if (isEdit.value && props.appData?.id) {
      await fetchUpdateSite(props.appData.id, buildUpdatePayload())
      // 规则绑定有变更时，提交绑定关系
      if (rulesChanged.value && props.appData.id) {
        const res = await fetchBindRulesToSite(props.appData.id, selectedRuleIds.value)
        
        // 检查冲突
        if (res.conflicts?.has_conflicts) {
          const highCount = res.conflicts.high_severity_count
          if (highCount > 0) {
            ElMessageBox.alert(
              `检测到 ${highCount} 个高危冲突，这些规则可能无法正常工作。请在规则列表中查看详情并修复。`,
              '规则冲突警告',
              { type: 'warning', confirmButtonText: '我知道了' }
            )
          } else {
            ElMessage.warning({
              message: `检测到 ${res.conflicts.conflicts.length} 个潜在冲突，建议检查规则配置`,
              duration: 5000
            })
          }
        }
      }
      ElMessage.success('站点更新成功')
      dialogVisible.value = false
      emit('submit')
    } else {
      const res = await fetchCreateSite(buildCreatePayload())
      dialogVisible.value = false
      emit('created', res)
      emit('submit')
    }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.tab-pane-body {
  padding: 16px 4px 4px;
}

.readonly-text {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.form-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.rule-checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 280px;
  overflow-y: auto;
}

.rule-checkbox-item {
  padding: 6px 10px;
  border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter);
  transition: background 0.15s;
}

.rule-checkbox-item:hover {
  background: var(--el-fill-color-light);
}

.rule-checkbox-label {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.rule-item__name {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.rule-item__desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
