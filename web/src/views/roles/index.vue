<template>
  <CommonPage title="角色管理" subtitle="维护角色及其权限清单">
    <template #action>
      <n-button type="primary" @click="openCreate">新建角色</n-button>
    </template>
    <n-data-table :columns="columns" :data="list" :loading="loading" :bordered="false" />
    <n-modal v-model:show="modalShow" preset="card" :title="modalTitle" style="width: 560px">
      <n-form ref="formRef" :model="form" :rules="rules" label-placement="top">
        <n-form-item label="角色名" path="name">
          <n-input v-model:value="form.name" :disabled="form.is_system" />
        </n-form-item>
        <n-form-item label="描述" path="description">
          <n-input v-model:value="form.description" />
        </n-form-item>
        <n-form-item label="权限清单">
          <n-select v-model:value="form.permissions" multiple filterable :options="permissionOptions" placeholder="选择权限" />
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
import { rolesApi } from '@/api/roles'
import { permissionsApi } from '@/api/permissions'

const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const saving = ref(false)
const list = ref([])
const permissionOptions = ref([])
const modalShow = ref(false)
const modalTitle = ref('新建角色')
const formRef = ref(null)
const form = reactive({ id: null, name: '', description: '', permissions: [], is_system: false })
const rules = { name: { required: true, message: '请输入角色名' } }

async function load() {
  loading.value = true
  try {
    const resp = await rolesApi.list({ page: 1, size: 100 })
    list.value = resp.items || []
  } catch (e) {
    message.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadPermissions() {
  try {
    const resp = await permissionsApi.list()
    permissionOptions.value = (resp.items || []).map((p) => ({ label: `${p.code} - ${p.description}`, value: p.code }))
  } catch (e) {
    message.error(e.message || '加载权限失败')
  }
}

function openCreate() {
  Object.assign(form, { id: null, name: '', description: '', permissions: [], is_system: false })
  modalTitle.value = '新建角色'
  modalShow.value = true
}

function openEdit(row) {
  Object.assign(form, { id: row.id, name: row.name, description: row.description, permissions: row.permissions || [], is_system: row.is_system })
  modalTitle.value = '编辑角色'
  modalShow.value = true
}

async function onSave() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    if (form.id) {
      await rolesApi.update(form.id, { description: form.description, permissions: form.permissions })
    } else {
      await rolesApi.create({ name: form.name, description: form.description, permissions: form.permissions })
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

function onDelete(row) {
  if (row.is_system) return message.warning('系统角色不可删除')
  dialog.warning({
    title: '删除角色',
    content: `确定删除 ${row.name}？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await rolesApi.remove(row.id)
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
  { title: '角色名', key: 'name' },
  { title: '描述', key: 'description' },
  {
    title: '类型',
    key: 'is_system',
    render: (row) => h(NTag, { type: row.is_system ? 'warning' : 'default' }, { default: () => (row.is_system ? '系统' : '自定义') }),
  },
  {
    title: '权限数',
    key: 'permissions',
    render: (row) => (row.permissions?.length ?? 0),
  },
  {
    title: '操作',
    key: 'actions',
    width: 180,
    render: (row) =>
      h(NSpace, null, {
        default: () => [
          h(NButton, { size: 'tiny', onClick: () => openEdit(row) }, { default: () => '编辑' }),
          h(NButton, { size: 'tiny', type: 'error', disabled: row.is_system, onClick: () => onDelete(row) }, { default: () => '删除' }),
        ],
      }),
  },
]

onMounted(async () => {
  await Promise.all([load(), loadPermissions()])
})
</script>
