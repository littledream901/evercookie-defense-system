<template>
  <div class="art-full-height">
    <div class="mb-3">
      <h2 class="text-lg font-medium text-g-900">页面资源</h2>
      <p class="mt-1 text-sm text-g-600">serve_alt 处置机制的投放内容库</p>
    </div>

    <ElCard class="art-table-card">
      <ArtTableHeader :loading="loading" v-model:columns="columnChecks" @refresh="refreshData">
        <template #left>
          <ElSpace wrap>
            <ElSelect v-model="filterKind" placeholder="全部类型" clearable class="w-32" @change="getData">
              <ElOption label="safe（正常分支）" value="safe" />
              <ElOption label="landing（阻断/质疑）" value="landing" />
            </ElSelect>
            <ElButton v-auth="'app.write'" @click="showDialog('add')">新建资源</ElButton>
            <ElButton v-auth="'app.write'" @click="openTemplateDialog">从模板载入</ElButton>
          </ElSpace>
        </template>
      </ArtTableHeader>
      <ArtTable
        :loading="loading" :data="data" :columns="columns" :pagination="pagination"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>

    <ElDialog v-model="dialogVisible" :title="dialogType === 'add' ? '新建页面资源' : '编辑页面资源'" width="680px" destroy-on-close>
      <ElForm ref="resFormRef" :model="resForm" :rules="resRules" label-width="110px">
        <ElFormItem label="名称" prop="name">
          <ElInput v-model="resForm.name" />
        </ElFormItem>
        <ElFormItem label="类型">
          <ElSelect v-model="resForm.kind" class="w-48">
            <ElOption label="safe（正常分支）" value="safe" />
            <ElOption label="landing（阻断/质疑）" value="landing" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="Content-Type">
          <ElSelect v-model="resForm.content_type" class="w-64" allow-create filterable>
            <ElOption label="text/html; charset=utf-8" value="text/html; charset=utf-8" />
            <ElOption label="application/json" value="application/json" />
            <ElOption label="text/plain; charset=utf-8" value="text/plain; charset=utf-8" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="内容" prop="content">
          <ElInput v-model="resForm.content" type="textarea" :rows="12" class="font-mono text-sm" />
        </ElFormItem>
        <ElFormItem label="启用">
          <ElSwitch v-model="resForm.enabled" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="saving" @click="submitResource">保存</ElButton>
      </template>
    </ElDialog>

    <!-- 模板选择：载入后仍需在新建表单里确认名称与内容，不直接落库 -->
    <ElDialog v-model="templateDialogVisible" title="从模板载入" width="720px">
      <div v-loading="templatesLoading" class="template-list">
        <div v-for="t in templates" :key="t.id" class="template-item">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="text-sm font-medium">{{ t.name }}</span>
              <ElTag :type="t.kind === 'safe' ? 'success' : 'warning'" size="small">
                {{ t.kind === 'safe' ? '正常分支' : '阻断/质疑' }}
              </ElTag>
              <span class="text-xs text-g-400 font-mono">{{ t.content_type }}</span>
            </div>
            <div class="mt-1 text-xs text-g-500 leading-relaxed">{{ t.description }}</div>
            <div class="mt-1 text-xs text-g-400">
              建议资源名：<span class="font-mono">{{ t.suggested_name }}</span>
            </div>
          </div>
          <ElButton size="small" type="primary" @click="applyTemplate(t)">载入</ElButton>
        </div>
        <ElEmpty
          v-if="!templatesLoading && !templates.length"
          description="暂无可用模板"
          :image-size="48"
        />
      </div>
    </ElDialog>
  </div>
</template>
<script setup lang="ts">
import ArtButtonTable from '@/components/core/forms/art-button-table/index.vue'
import { useTable } from '@/hooks/core/useTable'
import { fetchGetPageResourceList, fetchCreatePageResource, fetchUpdatePageResource, fetchDeletePageResource, fetchGetPageResourceTemplates } from '@/api/page-resources'
import { formatTime } from '@/utils/format'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

defineOptions({ name: 'FangyuPageResources' })

type PageResource = Api.Fangyu.PageResource

const filterKind = ref<string>()
const dialogVisible = ref(false)
const dialogType = ref<'add' | 'edit'>('add')
const saving = ref(false)
const resFormRef = ref<FormInstance>()
const currentId = ref<number>()
const resForm = reactive({
  name: '',
  kind: 'landing' as Api.Fangyu.PageResourceKind,
  content_type: 'text/html; charset=utf-8',
  content: '',
  enabled: true
})

const resRules: FormRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  content: [{ required: true, message: '请输入内容', trigger: 'blur' }]
}

const { columns, columnChecks, data, loading, pagination, getData, fetchData,
  handleSizeChange, handleCurrentChange, refreshData } = useTable({
  core: {
    apiFn: async (params: any) => {
      return fetchGetPageResourceList({ page: params.page, pageSize: params.pageSize, kind: filterKind.value as any })
    },
    apiParams: { page: 1, pageSize: 20 },
    immediate: true,
    columnsFactory: () => [
      { prop: 'id', label: 'ID', width: 70 },
      { prop: 'name', label: '名称', showOverflowTooltip: true },
      { prop: 'kind', label: '类型', width: 120,
        formatter: (r: PageResource) => r.kind === 'safe' ? '正常分支' : '阻断/质疑' },
      { prop: 'content_type', label: 'Content-Type', width: 200, showOverflowTooltip: true },
      { prop: 'enabled', label: '启用', width: 70,
        formatter: (r: PageResource) => h('span', { class: r.enabled ? 'text-green-600' : 'text-gray-400' }, r.enabled ? '是' : '否') },
      { prop: 'updated_at', label: '更新时间', width: 170,
        formatter: (r: PageResource) => formatTime(r.updated_at) },
      { prop: 'operation', label: '操作', width: 120, fixed: 'right',
        formatter: (r: PageResource) => h('div', [
          h(ArtButtonTable, { type: 'edit', onClick: () => showDialog('edit', r) }),
          h(ArtButtonTable, { type: 'delete', onClick: () => deleteResource(r) })
        ]) }
    ]
  }
})

function showDialog(type: 'add' | 'edit', row?: PageResource) {
  dialogType.value = type
  currentId.value = row?.id
  if (type === 'edit' && row) {
    Object.assign(resForm, { name: row.name, kind: row.kind, content_type: row.content_type, content: row.content, enabled: row.enabled })
  } else {
    nextTick(() => resFormRef.value?.resetFields())
    Object.assign(resForm, { name: '', kind: 'landing', content_type: 'text/html; charset=utf-8', content: '', enabled: true })
  }
  dialogVisible.value = true
}

async function submitResource() {
  const valid = await resFormRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    if (dialogType.value === 'add') {
      await fetchCreatePageResource({ ...resForm })
    } else if (currentId.value) {
      await fetchUpdatePageResource(currentId.value, { ...resForm })
    }
    ElMessage.success(dialogType.value === 'add' ? '创建成功' : '更新成功')
    dialogVisible.value = false
    await fetchData()
  } finally { saving.value = false }
}

// ── 模板载入 ────────────────────────────────────────────────────────────
const templateDialogVisible = ref(false)
const templatesLoading = ref(false)
const templates = ref<Api.Fangyu.PageResourceTemplate[]>([])

async function openTemplateDialog() {
  templateDialogVisible.value = true
  // 模板是后端静态清单，取一次即可，无需每次打开都请求
  if (templates.value.length) return
  templatesLoading.value = true
  try {
    templates.value = (await fetchGetPageResourceTemplates()) ?? []
  } finally {
    templatesLoading.value = false
  }
}

/**
 * 载入模板到新建表单。
 *
 * 不直接落库：资源名在同一 app 下需唯一，且模板内容通常要按站点品牌调整，
 * 因此走一遍新建表单让运维确认后再保存。
 */
function applyTemplate(t: Api.Fangyu.PageResourceTemplate) {
  templateDialogVisible.value = false
  dialogType.value = 'add'
  currentId.value = undefined
  Object.assign(resForm, {
    name: t.suggested_name,
    kind: t.kind,
    content_type: t.content_type,
    content: t.content,
    enabled: true
  })
  dialogVisible.value = true
  ElMessage.success(`已载入模板「${t.name}」，确认后保存`)
}

function deleteResource(row: PageResource) {
  ElMessageBox.confirm(`确定删除资源「${row.name}」吗？引用此资源的规则处置将失效。`, '删除资源', { type: 'error' })
    .then(async () => {
      await fetchDeletePageResource(row.id)
      ElMessage.success('已删除')
      await fetchData()
    })
}
</script>

<style scoped lang="scss">
.template-list {
  min-height: 120px;
  max-height: 60vh;
  overflow-y: auto;
}

.template-item {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 12px 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);

  &:last-child {
    border-bottom: 0;
  }
}
</style>
