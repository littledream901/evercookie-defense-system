<template>
  <CommonPage title="威胁情报" subtitle="维护恶意 IP 库并同步至网关">
    <template #action>
      <n-button @click="syncRedis">同步 Redis</n-button>
      <n-button type="primary" @click="openCreate">新增情报</n-button>
    </template>

    <div class="filters">
      <n-select
        v-model:value="filters.category"
        :options="categoryOptions"
        placeholder="分类"
        clearable
        style="width: 150px"
      />
      <n-select
        v-model:value="filters.source"
        :options="sourceOptions"
        placeholder="来源"
        clearable
        style="width: 150px"
      />
      <n-button @click="load">查询</n-button>
    </div>

    <n-data-table
      :columns="columns"
      :data="list"
      :loading="loading"
      :bordered="false"
      :scroll-x="1200"
      size="small"
    />

    <n-pagination
      v-model:page="page"
      :page-count="pageCount"
      :page-size="pageSize"
      class="pager"
      @update:page="load"
    />

    <n-modal v-model:show="showCreate" preset="card" title="新增威胁情报" style="width: 520px">
      <n-form :model="form" label-placement="left" label-width="80">
        <n-form-item label="IP" required>
          <n-input v-model:value="form.ip" placeholder="支持单个 IP 或 CIDR" />
        </n-form-item>
        <n-form-item label="分类">
          <n-select v-model:value="form.category" :options="categoryOptions" />
        </n-form-item>
        <n-form-item label="严重度">
          <n-select v-model:value="form.severity" :options="severityOptions" />
        </n-form-item>
        <n-form-item label="置信度">
          <n-slider v-model:value="form.confidence" :min="0" :max="100" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="form.description" type="textarea" :rows="2" />
        </n-form-item>
        <n-form-item label="过期时间">
          <n-date-picker v-model:value="form.expiresAt" type="datetime" clearable style="width: 100%" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="showCreate = false">取消</n-button>
          <n-button type="primary" :loading="submitting" @click="submit">提交</n-button>
        </div>
      </template>
    </n-modal>
  </CommonPage>
</template>

<script setup>
import { computed, h, onMounted, reactive, ref } from 'vue'
import { NButton, NTag, useDialog, useMessage } from 'naive-ui'
import CommonPage from '@/components/CommonPage.vue'
import { threatIntelApi } from '@/api/threat-intel'

const message = useMessage()
const dialog = useDialog()
const list = ref([])
const loading = ref(false)
const submitting = ref(false)
const showCreate = ref(false)
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)

const filters = reactive({ category: null, source: null })

const categoryOptions = ['malicious', 'proxy', 'tor', 'vpn', 'scanner', 'botnet'].map((v) => ({
  label: v,
  value: v,
}))
const severityOptions = ['low', 'medium', 'high', 'critical'].map((v) => ({ label: v, value: v }))
const sourceOptions = ['manual', 'feed', 'auto'].map((v) => ({ label: v, value: v }))

const SEVERITY_TAGS = { low: 'default', medium: 'info', high: 'warning', critical: 'error' }

const form = reactive({
  ip: '',
  category: 'malicious',
  severity: 'medium',
  confidence: 80,
  description: '',
  expiresAt: null,
})

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

const columns = [
  { title: 'IP', key: 'ip', width: 160, ellipsis: { tooltip: true } },
  {
    title: '分类',
    key: 'category',
    width: 110,
    render: (row) => h(NTag, { size: 'small' }, { default: () => row.category || '-' }),
  },
  {
    title: '严重度',
    key: 'severity',
    width: 100,
    render: (row) =>
      h(
        NTag,
        { type: SEVERITY_TAGS[row.severity] || 'default', size: 'small' },
        { default: () => row.severity || '-' },
      ),
  },
  { title: '来源', key: 'source', width: 100, render: (row) => row.source || '-' },
  {
    title: '置信度',
    key: 'confidence',
    width: 90,
    render: (row) => `${row.confidence ?? 0}%`,
  },
  { title: '描述', key: 'description', ellipsis: { tooltip: true }, render: (row) => row.description || '-' },
  {
    title: '过期时间',
    key: 'expires_at',
    width: 170,
    render: (row) => row.expires_at || '永久',
  },
  {
    title: '操作',
    key: 'actions',
    width: 90,
    render: (row) =>
      h(
        NButton,
        { size: 'tiny', type: 'error', quaternary: true, onClick: () => confirmRemove(row) },
        { default: () => '停用' },
      ),
  },
]

function openCreate() {
  Object.assign(form, {
    ip: '',
    category: 'malicious',
    severity: 'medium',
    confidence: 80,
    description: '',
    expiresAt: null,
  })
  showCreate.value = true
}

async function submit() {
  if (!form.ip.trim()) {
    message.warning('请填写 IP')
    return
  }
  submitting.value = true
  try {
    // 后端读 snake_case 的 expires_at，且要 ISO 8601 字符串
    await threatIntelApi.add({
      ip: form.ip.trim(),
      category: form.category,
      severity: form.severity,
      confidence: form.confidence,
      description: form.description,
      expires_at: form.expiresAt ? new Date(form.expiresAt).toISOString() : null,
    })
    message.success('已新增')
    showCreate.value = false
    await load()
  } catch (e) {
    message.error(e.message || '新增失败')
  } finally {
    submitting.value = false
  }
}

function confirmRemove(row) {
  dialog.warning({
    title: '确认停用',
    content: `停用后网关将不再拦截 ${row.ip}，确定继续？`,
    positiveText: '停用',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await threatIntelApi.remove(row.ip)
        message.success('已停用')
        await load()
      } catch (e) {
        message.error(e.message || '停用失败')
      }
    },
  })
}

async function syncRedis() {
  try {
    const resp = await threatIntelApi.syncRedis()
    message.success(`同步完成，共 ${resp.total ?? resp.data?.total ?? 0} 条`)
  } catch (e) {
    message.error(e.message || '同步失败')
  }
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (filters.category) params.category = filters.category
    if (filters.source) params.source = filters.source
    const resp = await threatIntelApi.list(params)
    // 该路由直返 dict，未包 SuccessResponse，因此兼容两种形状
    const payload = resp.data ?? resp
    list.value = payload.items || []
    total.value = payload.total || 0
  } catch (e) {
    message.error(e.message || '加载威胁情报失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
