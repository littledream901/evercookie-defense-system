<template>
  <div class="art-full-height">
    <div class="mb-3">
      <h2 class="text-lg font-medium text-g-900">IP 白名单</h2>
      <p class="mt-1 text-sm text-g-600">白名单条目跳过全部决策管道，删除后立即生效</p>
    </div>

    <ElCard class="art-table-card">
      <ArtTableHeader :loading="loading" v-model:columns="columnChecks" @refresh="loadData">
        <template #left>
          <ElSpace wrap>
            <ElButton v-auth="'app.write'" @click="showAddDialog = true">新增</ElButton>
            <ElButton v-auth="'app.write'" type="danger" plain @click="handleDeleteAll">清空</ElButton>
          </ElSpace>
        </template>
      </ArtTableHeader>
      <ArtTable :loading="loading" :data="list" :columns="columns" />
    </ElCard>

    <ElDialog v-model="showAddDialog" title="新增白名单条目" width="440px" destroy-on-close>
      <ElForm ref="addFormRef" :model="addForm" :rules="addRules" label-width="90px">
        <ElFormItem label="维度" prop="dimension">
          <ElSelect v-model="addForm.dimension" class="w-full">
            <ElOption label="IP（明文）" value="ip" />
            <ElOption label="设备指纹" value="fingerprint" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="值" prop="value">
          <ElInput v-model="addForm.value" :placeholder="addForm.dimension === 'ip' ? '例：1.2.3.4' : '设备指纹值'" />
        </ElFormItem>
        <ElFormItem label="备注">
          <ElInput v-model="addForm.note" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="showAddDialog = false">取消</ElButton>
        <ElButton type="primary" :loading="addSaving" @click="submitAdd">确认</ElButton>
      </template>
    </ElDialog>
  </div>
</template>
<script setup lang="ts">
import ArtButtonTable from '@/components/core/forms/art-button-table/index.vue'
import { fetchGetWhitelistList, fetchAddWhitelistEntry, fetchDeleteWhitelistEntry, fetchDeleteAllWhitelist } from '@/api/whitelist'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import type { ColumnOption } from '@/types'

defineOptions({ name: 'FangyuWhitelist' })

type WhitelistEntry = Api.Fangyu.WhitelistEntry

const loading = ref(false)
const list = ref<WhitelistEntry[]>([])
const showAddDialog = ref(false)
const addSaving = ref(false)
const addFormRef = ref<FormInstance>()
const addForm = reactive({
  dimension: 'ip' as Api.Fangyu.WhitelistDimension,
  value: '',
  note: ''
})

const addRules: FormRules = {
  dimension: [{ required: true }],
  value: [{ required: true, message: '请输入值', trigger: 'blur' }]
}

const columnChecks = ref<any[]>([])
const columns = computed<ColumnOption<WhitelistEntry>[]>(() => [
  { prop: 'dimension', label: '维度', width: 110,
    formatter: (r: WhitelistEntry) => r.dimension === 'ip' ? 'IP' : '设备指纹' },
  { prop: 'value', label: '值', showOverflowTooltip: true },
  { prop: 'note', label: '备注', showOverflowTooltip: true },
  { prop: 'created_by', label: '创建人', width: 100,
    formatter: (r: WhitelistEntry) => r.created_by ?? '-' },
  { prop: 'created_at', label: '创建时间', width: 170 },
  { prop: 'operation', label: '操作', width: 80, fixed: 'right',
    formatter: (r: WhitelistEntry) =>
      h(ArtButtonTable, { type: 'delete', onClick: () => deleteEntry(r) })
  }
])

const loadData = async () => {
  loading.value = true
  try {
    list.value = await fetchGetWhitelistList()
  } finally { loading.value = false }
}

async function submitAdd() {
  const valid = await addFormRef.value?.validate().catch(() => false)
  if (!valid) return
  addSaving.value = true
  try {
    await fetchAddWhitelistEntry({ ...addForm })
    ElMessage.success('添加成功')
    showAddDialog.value = false
    addFormRef.value?.resetFields()
    Object.assign(addForm, { dimension: 'ip', value: '', note: '' })
    await loadData()
  } finally { addSaving.value = false }
}

function deleteEntry(row: WhitelistEntry) {
  const label = `${row.dimension === 'ip' ? 'IP' : '指纹'} ${row.value}`
  ElMessageBox.confirm(`确定移除「${label}」的白名单条目吗？`, '移除白名单', { type: 'warning' })
    .then(async () => {
      await fetchDeleteWhitelistEntry({ dimension: row.dimension, value: row.value })
      ElMessage.success('已移除')
      await loadData()
    })
}

function handleDeleteAll() {
  ElMessageBox.confirm('确定清空全部白名单条目吗？此操作不可恢复。', '清空白名单', {
    confirmButtonText: '确认清空', cancelButtonText: '取消', type: 'error'
  }).then(async () => {
    await fetchDeleteAllWhitelist()
    ElMessage.success('已清空')
    await loadData()
  })
}

onMounted(loadData)
</script>
