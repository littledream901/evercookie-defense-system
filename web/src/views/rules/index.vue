<template>
  <CommonPage title="风控规则" subtitle="配置规则、发布版本、版本回滚">
    <template #action>
      <n-select v-model:value="appId" :options="appOptions" placeholder="选择应用" style="width: 200px" @update:value="load" />
      <n-button :disabled="!appId" @click="onSyncCache">同步缓存</n-button>
      <n-button type="primary" :disabled="!appId" @click="openCreate">新建规则</n-button>
    </template>

    <n-data-table :columns="columns" :data="list" :loading="loading" :bordered="false" />

    <n-modal v-model:show="modalShow" preset="card" :title="modalTitle" style="width: 760px; max-height: 90vh; overflow-y: auto">
      <n-form ref="formRef" :model="form" :rules="rules" label-placement="top">
        <n-form-item label="规则名" path="name">
          <n-input v-model:value="form.name" />
        </n-form-item>
        <n-form-item label="快速套用模板">
          <n-select :options="templateOptions" clearable placeholder="选择内置模板" @update:value="applyTemplate" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="form.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
        </n-form-item>
        <n-grid :cols="3" x-gap="12">
          <n-gi>
            <n-form-item label="规则种类">
              <n-select v-model:value="form.kind" :options="kindOptions" />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="优先级">
              <n-select v-model:value="form.priority" :options="priorityOptions" />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="规则组">
              <n-input v-model:value="form.group" placeholder="留空表示不归组" clearable />
            </n-form-item>
          </n-gi>
        </n-grid>

        <n-form-item v-if="form.kind === 'scoring'" label="权重">
          <n-input-number v-model:value="form.weight" :min="-1000" :max="1000" style="width: 100%" />
          <template #feedback>
            打分规则不终止流水线，只贡献权重，最终由评分阈值决定处置
          </template>
        </n-form-item>

        <n-form-item v-else label="处置动作">
          <DispositionEditor v-model="form.disposition" style="width: 100%" />
        </n-form-item>

        <n-form-item>
          <template #label>
            <div class="flex items-center gap-8px">
              <span>触发条件</span>
              <n-tooltip>
                <template #trigger>
                  <n-tag size="small" type="info" style="cursor: help">全部满足 (AND)</n-tag>
                </template>
                多个条件之间为「与」关系：所有条件同时满足才会命中该规则
              </n-tooltip>
              <n-button text size="small" style="margin-left: auto" @click="toggleRawMode">
                {{ rawMode ? '可视化编辑' : '原始 JSON' }}
              </n-button>
            </div>
          </template>

          <template v-if="rawMode">
            <n-input
              v-model:value="form.conditionsText"
              type="textarea"
              :autosize="{ minRows: 6, maxRows: 14 }"
              placeholder='[{"field":"ua.crawler_category","op":"eq","value":"security"}]'
              style="font-family: monospace; font-size: 12px"
            />
          </template>
          <template v-else>
            <ConditionBuilder v-model="form.conditions" style="width: 100%" @update:model-value="syncConditionsText" />
          </template>
        </n-form-item>
      </n-form>

      <template #footer>
        <div class="flex justify-between items-center">
          <n-button size="small" :loading="testRunning" @click="onTestRun">试跑</n-button>
          <div class="flex gap-8px">
            <n-button @click="modalShow = false">取消</n-button>
            <n-button type="primary" :loading="saving" @click="onSave">保存</n-button>
          </div>
        </div>
        <n-collapse-transition :show="!!testResult">
          <div v-if="testResult" class="test-result-panel">
            <n-divider style="margin: 12px 0 8px" />
            <div class="flex items-center gap-8px mb-8px">
              <n-tag :type="testResult.matched ? 'error' : 'success'" size="small">
                {{ testResult.matched ? '规则命中' : '规则未命中' }}
              </n-tag>
              <n-tag type="default" size="small">{{ testResult.durationMs }}ms</n-tag>
              <template v-if="testResult.matched && testResult.verdict">
                <n-tag :type="VERDICT_TAGS[testResult.verdict]" size="small">
                  {{ testResult.verdict }}
                </n-tag>
                <n-tag :type="MECHANISM_TAGS[testResult.mechanism]" size="small">
                  {{ testResult.mechanism }}
                </n-tag>
                <n-tag type="default" size="small">HTTP {{ testResult.httpStatus }}</n-tag>
                <code v-if="testResult.targetUrl" class="trace-expected">
                  {{ testResult.targetUrl }}
                </code>
              </template>
            </div>
            <div class="text-12px text-gray-500 mb-8px">
              IP: {{ testCtx.ip }} | UA: {{ testCtx.ua.slice(0, 60) }}
            </div>

            <div class="flex gap-8px mb-8px">
              <n-input v-model:value="testCtx.ip" size="small" placeholder="测试 IP" style="width: 150px" />
              <n-input v-model:value="testCtx.ua" size="small" placeholder="测试 User-Agent" style="flex: 1" />
            </div>

            <div v-if="testResult.conditions?.length" class="mb-8px">
              <div class="ctx-block__title mb-4px">条件逐行结果</div>
              <div v-for="(trace, i) in testResult.conditions" :key="i" class="trace-row">
                <n-tag size="tiny" :type="trace.matched ? 'success' : 'error'" style="flex-shrink:0">
                  {{ trace.matched ? '✓' : '✗' }}
                </n-tag>
                <code class="trace-field">{{ trace.field }}</code>
                <span class="trace-op">{{ trace.op }}</span>
                <code class="trace-expected">{{ JSON.stringify(trace.expected) }}</code>
                <span class="trace-sep">→ 实际:</span>
                <n-tag size="tiny" :type="trace.matched ? 'success' : 'warning'">
                  {{ trace.actual === null || trace.actual === undefined ? '(null)' : String(trace.actual) }}
                </n-tag>
              </div>
            </div>

            <div v-if="testResult.context" class="mt-8px">
              <n-collapse>
                <n-collapse-item title="解析上下文（ip / ua）" name="ctx">
                  <n-grid :cols="2" x-gap="12">
                    <n-gi>
                      <div class="ctx-block">
                        <div class="ctx-block__title">IP 信息</div>
                        <div v-for="(v, k) in testResult.context.ip" :key="k" class="ctx-item">
                          <span class="ctx-key">ip.{{ k }}</span>
                          <n-tag size="tiny" :type="v === true ? 'error' : v === false ? 'default' : 'info'">
                            {{ v === null || v === undefined ? '—' : String(v) }}
                          </n-tag>
                        </div>
                      </div>
                    </n-gi>
                    <n-gi>
                      <div class="ctx-block">
                        <div class="ctx-block__title">UA 解析</div>
                        <div v-for="(v, k) in testResult.context.ua" :key="k" class="ctx-item">
                          <span class="ctx-key">ua.{{ k }}</span>
                          <n-tag size="tiny" :type="v === true ? 'error' : v === false ? 'default' : 'info'">
                            {{ v === null || v === undefined ? '—' : String(v) }}
                          </n-tag>
                        </div>
                      </div>
                    </n-gi>
                  </n-grid>
                </n-collapse-item>
              </n-collapse>
            </div>
          </div>
        </n-collapse-transition>
      </template>
    </n-modal>
  </CommonPage>
</template>

<script setup>
import { ref, reactive, h, onMounted, computed } from 'vue'
import { NButton, NInput, NSpace, NTag, useDialog, useMessage } from 'naive-ui'
import CommonPage from '@/components/CommonPage.vue'
import ConditionBuilder from './components/ConditionBuilder.vue'
import DispositionEditor from './components/DispositionEditor.vue'
import {
  MECHANISM_TAGS,
  VERDICT_TAGS,
  createDisposition,
  validateDisposition,
} from './utils/dispositionDefs'
import { rulesApi } from '@/api/rules'
import { appsApi } from '@/api/apps'
import { ruleTemplatesApi } from '@/api/rule-templates'

const message = useMessage()
const dialog = useDialog()

const appId = ref(null)
const appOptions = ref([])
const loading = ref(false)
const saving = ref(false)
const testRunning = ref(false)
const list = ref([])
const modalShow = ref(false)
const modalTitle = ref('新建规则')
const testResult = ref(null)
const templates = ref([])
const formRef = ref(null)
const rawMode = ref(false)

const testCtx = reactive({
  ip: '8.8.8.8',
  ua: 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
})

const form = reactive({
  id: null,
  name: '',
  description: '',
  kind: 'decision',
  priority: 'normal',
  group: null,
  weight: 10,
  disposition: createDisposition(),
  conditions: [],
  conditionsText: '[]',
})

const rules = { name: { required: true, message: '请输入规则名' } }

const kindOptions = [
  { label: '决策规则（命中即终止）', value: 'decision' },
  { label: '打分规则（仅贡献权重）', value: 'scoring' },
]

const priorityOptions = [
  { label: '低 (low)', value: 'low' },
  { label: '普通 (normal)', value: 'normal' },
  { label: '高 (high)', value: 'high' },
  { label: '关键 (critical)', value: 'critical' },
]

const templateOptions = computed(() =>
  templates.value.map((item) => ({ label: item.name, value: item.id }))
)

function toggleRawMode() {
  if (rawMode.value) {
    try {
      form.conditions = JSON.parse(form.conditionsText || '[]')
    } catch {
      message.error('JSON 格式错误，无法切换到可视化模式')
      return
    }
  } else {
    form.conditionsText = JSON.stringify(form.conditions, null, 2)
  }
  rawMode.value = !rawMode.value
  testResult.value = null
}

function syncConditionsText(conditions) {
  form.conditionsText = JSON.stringify(conditions, null, 2)
}

async function loadApps() {
  try {
    const resp = await appsApi.list({ page: 1, pageSize: 100 })
    appOptions.value = ((resp.data?.items) || []).map((a) => ({ label: a.name, value: a.id }))
    if (!appId.value && appOptions.value[0]) appId.value = appOptions.value[0].value
  } catch (e) {
    message.error(e.message || '加载应用失败')
  }
}

async function loadTemplates() {
  try {
    const resp = await ruleTemplatesApi.list()
    templates.value = resp.data || []
  } catch (e) {
    message.error(e.message || '加载规则模板失败')
  }
}

function applyTemplate(templateId) {
  const template = templates.value.find((item) => item.id === templateId)
  if (!template) return
  Object.assign(form, {
    name: template.name,
    description: template.description,
    kind: template.kind || 'decision',
    priority: template.priority,
    group: null,
    weight: template.weight ?? 10,
    disposition: template.disposition
      ? JSON.parse(JSON.stringify(template.disposition))
      : createDisposition(),
    conditions: template.conditions || [],
    conditionsText: JSON.stringify(template.conditions || [], null, 2),
  })
  testResult.value = null
  message.success(`已套用模板：${template.name}`)
}

async function load() {
  if (!appId.value) return
  loading.value = true
  try {
    const resp = await rulesApi.list(appId.value, { page: 1, pageSize: 100 })
    list.value = resp.data?.items || []
  } catch (e) {
    message.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, {
    id: null, name: '', description: '', kind: 'decision', priority: 'normal',
    group: null, weight: 10, disposition: createDisposition(),
    conditions: [], conditionsText: '[]',
  })
  testResult.value = null
  rawMode.value = false
}

function openCreate() {
  resetForm()
  modalTitle.value = '新建规则'
  modalShow.value = true
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    description: row.description,
    kind: row.kind || 'decision',
    priority: row.priority,
    group: row.group ?? null,
    weight: row.weight ?? 10,
    disposition: row.disposition
      ? JSON.parse(JSON.stringify(row.disposition))
      : createDisposition(),
    conditions: row.conditions || [],
    conditionsText: JSON.stringify(row.conditions || [], null, 2),
  })
  testResult.value = null
  rawMode.value = false
  modalTitle.value = '编辑规则'
  modalShow.value = true
}

async function onSave() {
  try { await formRef.value?.validate() } catch { return }
  if (rawMode.value) {
    try {
      form.conditions = JSON.parse(form.conditionsText || '[]')
    } catch {
      return message.error('条件 JSON 格式错误')
    }
  }
  if (!form.conditions.length) {
    return message.error('至少需要一个触发条件')
  }
  if (form.kind === 'decision') {
    const dispErr = validateDisposition(form.disposition)
    if (dispErr) return message.error(dispErr)
  }
  saving.value = true
  try {
    // weight / disposition 按种类互斥，后端会拒绝多余字段
    const payload = {
      name: form.name,
      description: form.description,
      kind: form.kind,
      priority: form.priority,
      group: form.group || null,
      conditions: form.conditions,
      matchAll: true,
      ...(form.kind === 'scoring'
        ? { weight: form.weight }
        : { disposition: form.disposition }),
    }
    if (form.id) {
      await rulesApi.update(appId.value, form.id, payload)
    } else {
      await rulesApi.create(appId.value, payload)
    }
    message.success('保存成功')
    modalShow.value = false
    await load()
  } catch (e) {
    message.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onTestRun() {
  if (rawMode.value) {
    try {
      form.conditions = JSON.parse(form.conditionsText || '[]')
    } catch {
      return message.error('条件 JSON 格式错误')
    }
  }
  testRunning.value = true
  testResult.value = null
  try {
    // 试跑接口只接受决策规则，打分规则用等价放行处置占位
    const resp = await rulesApi.test({
      rule: {
        appId: appId.value,
        name: form.name || '预览',
        conditions: form.conditions,
        matchAll: true,
        disposition:
          form.kind === 'decision' ? form.disposition : createDisposition(),
      },
      ip: testCtx.ip,
      userAgent: testCtx.ua,
    })
    testResult.value = resp.data
  } catch (e) {
    message.error(e.message || '试跑失败')
  } finally {
    testRunning.value = false
  }
}

async function onPublish(row) {
  try {
    await rulesApi.publish(appId.value, row.id, { change_summary: '发布' })
    message.success('已发布')
    await load()
  } catch (e) {
    message.error(e.message || '发布失败')
  }
}

async function onDisable(row) {
  try {
    await rulesApi.disable(appId.value, row.id)
    message.success('已禁用')
    await load()
  } catch (e) {
    message.error(e.message || '操作失败')
  }
}

function onDelete(row) {
  dialog.warning({
    title: '删除规则',
    content: `确定删除规则「${row.name}」？此操作不可恢复。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await rulesApi.remove(appId.value, row.id)
        message.success('已删除')
        await load()
      } catch (e) {
        message.error(e.message || '删除失败')
      }
    },
  })
}

async function onSyncCache() {
  try {
    await rulesApi.syncCache(appId.value)
    message.success('已同步到 Redis 缓存')
  } catch (e) {
    message.error(e.message || '同步失败')
  }
}

const columns = [
  { title: 'ID', key: 'id', width: 64 },
  { title: '规则名', key: 'name', ellipsis: { tooltip: true } },
  {
    title: '状态', key: 'status', width: 80,
    render: (row) => {
      const map = {
        draft: 'default', shadow: 'info', published: 'success',
        disabled: 'warning', archived: 'error',
      }
      return h(NTag, { type: map[row.status] || 'default', size: 'small' }, { default: () => row.status })
    },
  },
  {
    title: '种类', key: 'kind', width: 80,
    render: (row) => h(
      NTag,
      { type: row.kind === 'scoring' ? 'info' : 'default', size: 'small' },
      { default: () => (row.kind === 'scoring' ? '打分' : '决策') },
    ),
  },
  { title: '优先级', key: 'priority', width: 72 },
  {
    title: '处置 / 权重', key: 'disposition', width: 180,
    render: (row) => {
      if (row.kind === 'scoring') {
        return h('span', { style: 'color:#888;font-size:13px' }, `权重 ${row.weight ?? 0}`)
      }
      const d = row.disposition
      if (!d) return h('span', { style: 'color:#ccc' }, '-')
      return h(NSpace, { size: 4, wrap: false }, {
        default: () => [
          h(NTag, { type: VERDICT_TAGS[d.verdict] || 'default', size: 'small' }, { default: () => d.verdict }),
          h(NTag, { type: MECHANISM_TAGS[d.mechanism] || 'default', size: 'small' }, { default: () => d.mechanism }),
        ],
      })
    },
  },
  {
    title: '条件数', key: 'conditions', width: 72,
    render: (row) => h('span', { style: 'color:#888;font-size:13px' }, (row.conditions?.length ?? 0) + ' 条'),
  },
  { title: '版本', key: 'version', width: 56 },
  {
    title: '操作', key: 'actions', width: 280,
    render: (row) =>
      h(NSpace, null, {
        default: () => [
          h(NButton, { size: 'tiny', onClick: () => openEdit(row) }, { default: () => '编辑' }),
          h(NButton, {
            size: 'tiny', type: 'primary',
            disabled: row.status === 'published',
            onClick: () => onPublish(row),
          }, { default: () => '发布' }),
          h(NButton, {
            size: 'tiny',
            disabled: row.status !== 'published',
            onClick: () => onDisable(row),
          }, { default: () => '禁用' }),
          h(NButton, { size: 'tiny', type: 'error', onClick: () => onDelete(row) }, { default: () => '删除' }),
        ],
      }),
  },
]

onMounted(async () => {
  await Promise.all([loadTemplates(), loadApps()])
  await load()
})
</script>

<style scoped>
.test-result-panel { padding: 0 2px; }
.ctx-block { font-size: 12px; }
.ctx-block__title { font-weight: 600; color: #666; margin-bottom: 6px; font-size: 12px; }
.ctx-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 2px 0; border-bottom: 1px solid #f0f0f0;
}
.ctx-key { font-family: monospace; color: #444; }
.trace-row {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 0; border-bottom: 1px solid #f5f5f5; font-size: 12px;
}
.trace-field { font-family: monospace; color: #1d4e89; }
.trace-op { color: #666; font-size: 11px; }
.trace-expected { font-family: monospace; color: #555; }
.trace-sep { color: #aaa; font-size: 11px; }
</style>
