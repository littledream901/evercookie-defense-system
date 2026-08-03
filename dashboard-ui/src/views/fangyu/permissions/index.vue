<!-- 权限元数据页面 -->
<template>
  <div class="art-full-height">
    <div class="mb-3">
      <h2 class="text-lg font-medium text-g-900">权限元数据</h2>
      <p class="mt-1 text-sm text-g-600">维护 resource.action 权限元数据</p>
    </div>

    <ElCard class="art-table-card">
      <!-- 表格头部 -->
      <ArtTableHeader v-model:columns="columnChecks" :loading="loading" @refresh="refreshData">
        <template #left>
          <ElSpace wrap>
            <ElButton v-auth="'permission.write'" @click="dialogVisible = true" v-ripple>
              新增权限
            </ElButton>
          </ElSpace>
        </template>
      </ArtTableHeader>

      <!-- 表格：后端不分页，useTable 会自动识别纯数组响应 -->
      <ArtTable :loading="loading" :data="data" :columns="columns"></ArtTable>
    </ElCard>

    <!-- 权限弹窗 -->
    <PermissionDialog v-model:visible="dialogVisible" @submit="refreshData" />
  </div>
</template>

<script setup lang="ts">
  import { useTable } from '@/hooks/core/useTable'
  import { fetchGetPermissionList } from '@/api/rbac'
  import PermissionDialog from './modules/permission-dialog.vue'

  defineOptions({ name: 'FangyuPermissions' })

  const dialogVisible = ref(false)

  const { columns, columnChecks, data, loading, refreshData } = useTable({
    core: {
      apiFn: fetchGetPermissionList,
      columnsFactory: () => [
        { prop: 'code', label: '权限码' },
        { prop: 'description', label: '描述' },
        { prop: 'created_at', label: '创建时间' }
      ]
    }
  })
</script>
