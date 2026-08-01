<template>
  <CommonPage title="应用管理" subtitle="接入方应用配置、API Key、域名白名单">
    <template #action>
      <n-input v-model:value="query.keyword" placeholder="应用名" clearable style="width: 200px" />
      <n-button @click="load">搜索</n-button>
      <n-button type="primary" @click="openCreate">新建应用</n-button>
    </template>
    <n-data-table :columns="columns" :data="list" :loading="loading" :bordered="false" :pagination="pagination" remote @update:page="onPage" />
    <n-modal v-model:show="modalShow" preset="card" :title="modalTitle" style="width: 520px">
      <n-form ref="formRef" :model="form" :rules="rules" label-placement="top">
        <n-form-item label="名称" path="name"><n-input v-model:value="form.name" /></n-form-item>
        <n-form-item label="描述" path="description"><n-input v-model:value="form.description" type="textarea" /></n-form-item>
        <n-form-item label="域名白名单" path="domains">
          <n-dynamic-tags v-model:value="form.domains" />
        </n-form-item>
        <n-form-item label="状态" path="status">
          <n-select v-model:value="form.status" :options="statusOptions" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="flex justify-end gap-8px">
          <n-button @click="modalShow = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="onSave">保存</n-button>
        </div>
      </template>
    </n-modal>
  </CommonPage>
</template>

<script setup>
import { ref, reactive, h, onMounted } from 'vue'
import { NButton, NSpace, NTag } from 'naive-ui'
import CommonPage from '@/components/CommonPage.vue'
import { appsApi } from '@/api/apps'

const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const saving = ref(false)
const list = ref([])
const query = reactive({ keyword: '' })
const pagination = reactive({ page: 1, pageSize: 10, itemCount: 0 })
const modalShow = ref(false)
const modalTitle = ref('新建应用')
const formRef = ref(null)
const form = reactive({ id: null, name: '', description: '', domains: [], status: 'active' })
const rules = { name: { required: true, message: '请输入应用名' } }
const statusOptions = [
  { label: '正常', value: 'active' },
  { label: '禁用', value: 'disabled' },
]

async function load() {
  loading.value = true
  try {
    const resp = await appsApi.list({ page: pagination.page, size: pagination.pageSize, keyword: query.keyword || undefined })
    list.value = resp.items || []
    pagination.itemCount = resp.total || 0
  } catch (e) {
    message.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function onPage(p) {
  pagination.page = p
  load()
}

function openCreate() {
  Object.assign(form, { id: null, name: '', description: '', domains: [], status: 'active' })
  modalTitle.value = '新建应用'
  modalShow.value = true
}

function openEdit(row) {
  Object.assign(form, { id: row.id, name: row.name, description: row.description, domains: row.domains || [], status: row.status })
  modalTitle.value = '编辑应用'
  modalShow.value = true
}

async function onSave() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    if (form.id) {
      await appsApi.update(form.id, { name: form.name, description: form.description, domains: form.domains, status: form.status })
    } else {
      await appsApi.create({ name: form.name, description: form.description, domains: form.domains })
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

function onRotate(row) {
  dialog.warning({
    title: '轮换 API Key',
    content: `轮换后旧 Key 立即失效，${row.name} 的所有接入方需要更换。`,
    positiveText: '轮换',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const resp = await appsApi.rotateKey(row.id)
        message.success(`新 Key：${resp.api_key}`, { duration: 15000 })
        await load()
      } catch (e) {
        message.error(e.message || '轮换失败')
      }
    },
  })
}

function onDelete(row) {
  dialog.warning({
    title: '删除应用',
    content: `确定删除 ${row.name}？关联规则将失效。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await appsApi.remove(row.id)
        message.success('已删除')
        await load()
      } catch (e) {
        message.error(e.message || '删除失败')
      }
    },
  })
}

const columns = [
  { title: 'ID', key: 'id', width: 80 },
  { title: '名称', key: 'name' },
  { title: 'API Key', key: 'api_key', ellipsis: { tooltip: true } },
  {
    title: '状态',
    key: 'status',
    render: (row) => h(NTag, { type: row.status === 'active' ? 'success' : 'default' }, { default: () => row.status }),
  },
  { title: '域名数', key: 'domains', render: (row) => row.domains?.length ?? 0 },
  { title: '创建时间', key: 'created_at' },
  {
    title: '操作',
    key: 'actions',
    width: 240,
    render: (row) =>
      h(NSpace, null, {
        default: () => [
          h(NButton, { size: 'tiny', onClick: () => openEdit(row) }, { default: () => '编辑' }),
          h(NButton, { size: 'tiny', onClick: () => onRotate(row) }, { default: () => '轮换 Key' }),
          h(NButton, { size: 'tiny', type: 'error', onClick: () => onDelete(row) }, { default: () => '删除' }),
        ],
      }),
  },
]

onMounted(load)
</script>
