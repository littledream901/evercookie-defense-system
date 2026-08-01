<template>
  <CommonPage title="权限管理" subtitle="维护 resource.action 权限元数据">
    <template #action>
      <n-button type="primary" @click="openCreate">新增权限</n-button>
    </template>
    <n-data-table :columns="columns" :data="list" :loading="loading" :bordered="false" />
    <n-modal v-model:show="modalShow" preset="card" title="权限" style="width: 480px">
      <n-form ref="formRef" :model="form" :rules="rules" label-placement="top">
        <n-form-item label="权限码" path="code">
          <n-input v-model:value="form.code" placeholder="示例：user.read" />
        </n-form-item>
        <n-form-item label="描述" path="description">
          <n-input v-model:value="form.description" />
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
import { ref, reactive, onMounted } from 'vue'
import CommonPage from '@/components/CommonPage.vue'
import { permissionsApi } from '@/api/permissions'

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const list = ref([])
const modalShow = ref(false)
const formRef = ref(null)
const form = reactive({ code: '', description: '' })
const rules = { code: { required: true, message: '请输入权限码' } }

async function load() {
  loading.value = true
  try {
    const resp = await permissionsApi.list()
    list.value = resp.items || []
  } catch (e) {
    message.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { code: '', description: '' })
  modalShow.value = true
}

async function onSave() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    await permissionsApi.upsert(form)
    message.success('保存成功')
    modalShow.value = false
    await load()
  } catch (e) {
    message.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const columns = [
  { title: '权限码', key: 'code' },
  { title: '描述', key: 'description' },
  { title: '创建时间', key: 'created_at' },
]

onMounted(load)
</script>
