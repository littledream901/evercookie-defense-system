<template>
  <CommonPage title="用户管理" subtitle="管理后台账号、角色分配与密码重置">
    <template #action>
      <n-input v-model:value="query.keyword" placeholder="用户名/邮箱" clearable style="width: 200px" />
      <n-button @click="load">搜索</n-button>
      <n-button type="primary" @click="openCreate">新建用户</n-button>
    </template>
    <n-data-table
      :columns="columns"
      :data="list"
      :loading="loading"
      :bordered="false"
      :pagination="pagination"
      remote
      @update:page="onPage"
    />
    <n-modal v-model:show="modalShow" preset="card" :title="modalTitle" style="width: 480px">
      <n-form ref="formRef" :model="form" :rules="rules" label-placement="top">
        <n-form-item label="用户名" path="username">
          <n-input v-model:value="form.username" :disabled="!!form.id" />
        </n-form-item>
        <n-form-item label="邮箱" path="email">
          <n-input v-model:value="form.email" />
        </n-form-item>
        <n-form-item label="显示名" path="display_name">
          <n-input v-model:value="form.display_name" />
        </n-form-item>
        <n-form-item v-if="!form.id" label="密码" path="password">
          <n-input v-model:value="form.password" type="password" show-password-on="click" />
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
    <n-modal v-model:show="rolesShow" preset="card" title="分配角色" style="width: 480px">
      <n-checkbox-group v-model:value="selectedRoleIds">
        <n-space vertical>
          <n-checkbox v-for="r in allRoles" :key="r.id" :value="r.id" :label="r.name" />
        </n-space>
      </n-checkbox-group>
      <template #footer>
        <div class="flex justify-end gap-8px">
          <n-button @click="rolesShow = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="onAssignRoles">保存</n-button>
        </div>
      </template>
    </n-modal>
  </CommonPage>
</template>

<script setup>
import { ref, reactive, h, onMounted } from 'vue'
import { NButton, NTag, NSpace } from 'naive-ui'
import CommonPage from '@/components/CommonPage.vue'
import { usersApi } from '@/api/users'
import { rolesApi } from '@/api/roles'

const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const saving = ref(false)
const list = ref([])
const query = reactive({ keyword: '', status: null })
const pagination = reactive({ page: 1, pageSize: 10, itemCount: 0, showSizePicker: false })
const modalShow = ref(false)
const rolesShow = ref(false)
const modalTitle = ref('新建用户')
const formRef = ref(null)
const form = reactive({ id: null, username: '', email: '', display_name: '', password: '', status: 'active' })
const rules = {
  username: { required: true, message: '请输入用户名' },
  email: { required: true, message: '请输入邮箱' },
  password: { required: true, message: '请输入密码' },
}
const statusOptions = [
  { label: '正常', value: 'active' },
  { label: '禁用', value: 'disabled' },
]
const allRoles = ref([])
const selectedRoleIds = ref([])
const currentUser = ref(null)

async function load() {
  loading.value = true
  try {
    const resp = await usersApi.list({ page: pagination.page, size: pagination.pageSize, keyword: query.keyword || undefined })
    list.value = resp.items || []
    pagination.itemCount = resp.total || 0
  } catch (e) {
    message.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function onPage(page) {
  pagination.page = page
  load()
}

function openCreate() {
  Object.assign(form, { id: null, username: '', email: '', display_name: '', password: '', status: 'active' })
  modalTitle.value = '新建用户'
  modalShow.value = true
}

function openEdit(row) {
  Object.assign(form, { id: row.id, username: row.username, email: row.email, display_name: row.display_name, password: '', status: row.status })
  modalTitle.value = '编辑用户'
  modalShow.value = true
}

async function onSave() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    if (form.id) {
      await usersApi.update(form.id, { email: form.email, display_name: form.display_name, status: form.status })
    } else {
      await usersApi.create({ username: form.username, email: form.email, display_name: form.display_name, password: form.password })
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

async function openAssignRoles(row) {
  currentUser.value = row
  try {
    const [roles, detail] = await Promise.all([rolesApi.list({ page: 1, size: 100 }), usersApi.get(row.id)])
    allRoles.value = roles.items || []
    selectedRoleIds.value = (detail.roles || []).map((r) => r.id)
    rolesShow.value = true
  } catch (e) {
    message.error(e.message || '加载失败')
  }
}

async function onAssignRoles() {
  saving.value = true
  try {
    await usersApi.assignRoles(currentUser.value.id, { role_ids: selectedRoleIds.value })
    message.success('保存成功')
    rolesShow.value = false
  } catch (e) {
    message.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function onResetPassword(row) {
  dialog.warning({
    title: '重置密码',
    content: `确定重置 ${row.username} 的密码？系统将生成新密码。`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const resp = await usersApi.resetPassword(row.id, { password: 'Reset@' + Math.random().toString(36).slice(2, 10) })
        message.success(`新密码：${resp.password || '已重置'}`, { duration: 10000 })
      } catch (e) {
        message.error(e.message || '重置失败')
      }
    },
  })
}

function onDelete(row) {
  dialog.warning({
    title: '删除用户',
    content: `确定删除 ${row.username}？该操作不可恢复。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await usersApi.remove(row.id)
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
  { title: '用户名', key: 'username' },
  { title: '邮箱', key: 'email' },
  { title: '显示名', key: 'display_name' },
  {
    title: '状态',
    key: 'status',
    render: (row) => h(NTag, { type: row.status === 'active' ? 'success' : 'default' }, { default: () => row.status }),
  },
  { title: '创建时间', key: 'created_at' },
  {
    title: '操作',
    key: 'actions',
    width: 240,
    render: (row) =>
      h(NSpace, null, {
        default: () => [
          h(NButton, { size: 'tiny', onClick: () => openEdit(row) }, { default: () => '编辑' }),
          h(NButton, { size: 'tiny', onClick: () => openAssignRoles(row) }, { default: () => '角色' }),
          h(NButton, { size: 'tiny', onClick: () => onResetPassword(row) }, { default: () => '重置密码' }),
          h(NButton, { size: 'tiny', type: 'error', onClick: () => onDelete(row) }, { default: () => '删除' }),
        ],
      }),
  },
]

onMounted(load)
</script>
