<!-- API Key 管理组件 -->
<template>
  <div class="api-key-management">
    <div class="mb-4 flex justify-between items-center">
      <div>
        <h3 class="text-base font-medium text-g-900">API Keys</h3>
        <p class="mt-1 text-sm text-g-600">用于调用项目 API，请妥善保管</p>
      </div>
      <ElButton type="primary" @click="showCreateDialog = true">
        <ElIcon class="mr-1"><Plus /></ElIcon>
        创建 API Key
      </ElButton>
    </div>

    <!-- API Key 列表 -->
    <ElTable :data="apiKeys" border stripe v-loading="loading">
      <ElTableColumn prop="name" label="名称" width="250" />
      <ElTableColumn prop="key_prefix" label="Key 前缀" min-width="350">
        <template #default="{ row }">
          <code class="px-2 py-1 bg-g-100 rounded text-xs">{{ row.key_prefix }}...</code>
        </template>
      </ElTableColumn>
      <ElTableColumn prop="created_at" label="创建时间" width="180">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </ElTableColumn>
      <ElTableColumn prop="last_used_at" label="最后使用" width="180">
        <template #default="{ row }">
          {{ row.last_used_at ? formatTime(row.last_used_at) : '从未使用' }}
        </template>
      </ElTableColumn>
      <ElTableColumn prop="status" label="状态" width="100">
        <template #default="{ row }">
          <ElTag :type="row.status === 'active' ? 'success' : 'info'" size="small">
            {{ row.status === 'active' ? '正常' : row.status }}
          </ElTag>
        </template>
      </ElTableColumn>
      <ElTableColumn label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <ElButton link type="danger" size="small" @click="handleDelete(row)">删除</ElButton>
        </template>
      </ElTableColumn>
    </ElTable>

    <!-- 创建 API Key 对话框 -->
    <ElDialog
      v-model="showCreateDialog"
      title="创建 API Key"
      width="500px"
      :close-on-click-modal="false"
    >
      <ElForm ref="formRef" :model="form" :rules="rules" label-width="80px">
        <ElFormItem label="名称" prop="name">
          <ElInput
            v-model="form.name"
            placeholder="例如：生产环境 API"
            maxlength="128"
            show-word-limit
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="showCreateDialog = false">取消</ElButton>
        <ElButton type="primary" :loading="creating" @click="handleCreate">创建</ElButton>
      </template>
    </ElDialog>

    <!-- 显示新创建的 API Key -->
    <ElDialog
      v-model="showKeyDialog"
      title="API Key 创建成功"
      width="600px"
      :close-on-click-modal="false"
    >
      <ElAlert type="warning" :closable="false" class="mb-4">
        <template #title>
          <span class="font-medium">请立即复制保存，关闭后将无法再次查看完整 Key</span>
        </template>
      </ElAlert>
      <div class="api-key-display">
        <div class="flex items-center gap-2">
          <ElInput v-model="newApiKey" readonly>
            <template #append>
              <ElButton @click="copyApiKey">
                <ElIcon><CopyDocument /></ElIcon>
                复制
              </ElButton>
            </template>
          </ElInput>
        </div>
      </div>
      <template #footer>
        <ElButton type="primary" @click="closeKeyDialog">我已保存</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { Plus, CopyDocument } from '@element-plus/icons-vue'
  import type { FormInstance, FormRules } from 'element-plus'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { fetchCreateApiKey, fetchGetApiKeys, fetchDeleteApiKey, type ApiKey } from '@/api/api-keys'
  import { formatTime } from '@/utils/format'
  import { useClipboard } from '@vueuse/core'

  defineOptions({ name: 'ApiKeyManagement' })

  const loading = ref(false)
  const creating = ref(false)
  const apiKeys = ref<ApiKey[]>([])
  const showCreateDialog = ref(false)
  const showKeyDialog = ref(false)
  const newApiKey = ref('')

  const formRef = ref<FormInstance>()
  const form = reactive({ name: '' })

  const rules: FormRules = {
    name: [{ required: true, message: '请输入 API Key 名称', trigger: 'blur' }]
  }

  const { copy, isSupported } = useClipboard()

  async function loadApiKeys() {
    loading.value = true
    try {
      const res = await fetchGetApiKeys()
      apiKeys.value = res || []
    } finally {
      loading.value = false
    }
  }

  async function handleCreate() {
    const valid = await formRef.value?.validate().catch(() => false)
    if (!valid) return

    creating.value = true
    try {
      const res = await fetchCreateApiKey({ name: form.name })
      newApiKey.value = res.api_key
      showCreateDialog.value = false
      showKeyDialog.value = true
      form.name = ''
      formRef.value?.resetFields()
      await loadApiKeys()
    } finally {
      creating.value = false
    }
  }

  function closeKeyDialog() {
    showKeyDialog.value = false
    newApiKey.value = ''
  }

  async function copyApiKey() {
    if (!isSupported.value) {
      ElMessage.warning('浏览器不支持复制功能')
      return
    }
    try {
      await copy(newApiKey.value)
      ElMessage.success('API Key 已复制到剪贴板')
    } catch {
      ElMessage.error('复制失败')
    }
  }

  async function handleDelete(row: ApiKey) {
    await ElMessageBox.confirm(`确定删除 API Key "${row.name}" 吗？删除后无法恢复。`, '确认删除', {
      type: 'warning'
    })
    try {
      await fetchDeleteApiKey(row.id)
      ElMessage.success('删除成功')
      await loadApiKeys()
    } catch (error) {
      ElMessage.error('删除失败')
    }
  }

  onMounted(() => {
    loadApiKeys()
  })
</script>

<style scoped lang="scss">
  .api-key-management {
    .api-key-display {
      background: var(--el-fill-color-light);
      padding: 16px;
      border-radius: 4px;
    }
  }
</style>
