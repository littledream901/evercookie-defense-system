<template>
  <div class="applications-page art-full-height">
    <ElCard class="art-table-card" shadow="never">
      <template #header>
        <div class="flex items-center justify-between">
          <div>
            <div class="text-[16px] font-medium">应用管理</div>
            <div class="text-[12px] text-g-500 mt-1">
              应用是站点的业务分组容器；验签身份由其下的站点承载
            </div>
          </div>
          <ElSpace>
            <ElButton type="primary" :icon="Plus" v-ripple @click="handleCreate">新建应用</ElButton>
          </ElSpace>
        </div>
      </template>

      <ArtTable
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      >
        <template #app_key="{ row }">
          <div class="flex items-center gap-1 min-w-0">
            <span
              class="text-[12px] text-g-500 truncate"
              style="font-family: ui-monospace, 'Cascadia Code', monospace; max-width: 160px"
              :title="row.app_key"
            >{{ row.app_key }}</span>
            <ElButton link type="primary" :icon="CopyDocument" size="small" @click.stop="copyText(row.app_key, 'App Key')" />
          </div>
        </template>

        <template #site_count="{ row }">
          <ElButton link type="primary" @click="goToSites(row.id)">
            {{ row.site_count ?? 0 }} 个站点
          </ElButton>
        </template>

        <template #is_active="{ row }">
          <ElSwitch :model-value="row.is_active" @change="handleToggle(row)" />
        </template>

        <template #actions="{ row }">
          <ElSpace>
            <ElButton link type="primary" :icon="Edit" @click="handleEdit(row)">编辑</ElButton>
            <ElButton link type="warning" :icon="RefreshRight" @click="handleRotate(row)">轮换密钥</ElButton>
            <ElButton link type="danger" :icon="Delete" @click="handleDelete(row)">删除</ElButton>
          </ElSpace>
        </template>
      </ArtTable>
    </ElCard>

    <ApplicationDialog
      v-model:visible="dialogVisible"
      :type="dialogType"
      :app-data="currentApp"
      @submit="handleDialogSubmit"
      @created="handleAppCreated"
    />

    <AppSecretModal
      v-if="secretData"
      v-model="secretVisible"
      :app-key="secretData.app_key"
      :app-secret="secretData.app_secret"
      :mode="secretMode"
      @closed="secretData = null"
    />
  </div>
</template>

<script setup lang="ts">
  import { Plus, Edit, Delete, RefreshRight, CopyDocument } from '@element-plus/icons-vue'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { useRouter } from 'vue-router'
  import { useTable } from '@/hooks/core/useTable'
  import { formatTime } from '@/utils/format'
  import type { DialogType } from '@/types'
  import {
    fetchGetApplicationList,
    fetchUpdateApplication,
    fetchDeleteApplication,
    fetchRotateApplicationSecret
  } from '@/api/apps'
  import ApplicationDialog from './modules/application-dialog.vue'
  import AppSecretModal from './modules/app-secret-modal.vue'

  defineOptions({ name: 'FangyuApplications' })

  type AppItem = Api.Fangyu.Application

  const router = useRouter()

  const dialogVisible = ref(false)
  const dialogType = ref<DialogType>('add')
  const currentApp = ref<Partial<AppItem>>({})

  const secretVisible = ref(false)
  const secretMode = ref<'create' | 'rotate'>('create')
  const secretData = ref<{ app_key: string; app_secret: string } | null>(null)

  const copyText = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success(`已复制${label}`)
    } catch {
      ElMessage.error('复制失败，请手动选择复制')
    }
  }

  const goToSites = (appId: number) => {
    router.push({ path: '/fangyu/apps', query: { appId: String(appId) } })
  }

  const {
    columns,
    data,
    loading,
    pagination,
    handleSizeChange,
    handleCurrentChange,
    refreshCreate,
    refreshUpdate,
    refreshRemove
  } = useTable({
    core: {
      apiFn: fetchGetApplicationList,
      apiParams: { page: 1, pageSize: 20 },
      columnsFactory: () => [
        { prop: 'id', label: 'ID', width: 60 },
        { prop: 'name', label: '应用名称', minWidth: 140 },
        { prop: 'app_key', label: 'App Key', minWidth: 180, useSlot: true },
        { prop: 'description', label: '描述', minWidth: 160 },
        { prop: 'site_count', label: '站点数', width: 110, useSlot: true },
        { prop: 'is_active', label: '启用状态', width: 100, useSlot: true },
        {
          prop: 'created_at',
          label: '创建时间',
          width: 170,
          formatter: (row: AppItem) => formatTime(row.created_at)
        },
        { prop: 'actions', label: '操作', width: 240, fixed: 'right', useSlot: true }
      ]
    }
  })

  const handleCreate = () => {
    dialogType.value = 'add'
    currentApp.value = {}
    dialogVisible.value = true
  }

  const handleEdit = (row: AppItem) => {
    dialogType.value = 'edit'
    currentApp.value = { ...row }
    dialogVisible.value = true
  }

  const handleToggle = async (row: AppItem) => {
    const next = !row.is_active
    try {
      await fetchUpdateApplication(row.id, { is_active: next })
      ElMessage.success(next ? `应用「${row.name}」已启用` : `应用「${row.name}」已停用`)
      await refreshUpdate()
    } catch {
      ElMessage.error('操作失败，请稍后重试')
    }
  }

  const handleRotate = async (row: AppItem) => {
    try {
      await ElMessageBox.confirm(
        `轮换后旧密钥立即失效，需同步更新所有使用该应用密钥的接入端。确定轮换「${row.name}」的密钥？`,
        '轮换应用密钥',
        { type: 'warning', confirmButtonText: '确定轮换', cancelButtonText: '取消' }
      )
    } catch {
      return
    }

    try {
      const res = await fetchRotateApplicationSecret(row.id)
      secretMode.value = 'rotate'
      secretData.value = { app_key: res.app_key, app_secret: res.app_secret }
      secretVisible.value = true
    } catch {
      ElMessage.error('轮换失败，请稍后重试')
    }
  }

  const handleDelete = async (row: AppItem) => {
    if ((row.site_count ?? 0) > 0) {
      ElMessage.warning(`应用「${row.name}」下仍有 ${row.site_count} 个站点，请先删除站点`)
      return
    }

    try {
      await ElMessageBox.confirm(`确定删除应用「${row.name}」？此操作不可恢复。`, '删除应用', {
        type: 'warning',
        confirmButtonText: '确定删除',
        cancelButtonText: '取消'
      })
    } catch {
      return
    }

    try {
      await fetchDeleteApplication(row.id)
      ElMessage.success(`应用「${row.name}」已删除`)
      await refreshRemove()
    } catch {
      ElMessage.error('删除失败，请稍后重试')
    }
  }

  const handleDialogSubmit = async () => {
    currentApp.value = {}
    await refreshUpdate()
  }

  const handleAppCreated = (app: Api.Fangyu.ApplicationDetail) => {
    if (app.app_secret) {
      secretMode.value = 'create'
      secretData.value = { app_key: app.app_key, app_secret: app.app_secret }
      secretVisible.value = true
    }
    refreshCreate()
  }
</script>
