<!-- 角色管理 -->
<template>
  <div class="art-full-height">
    <ElCard class="art-table-card">
      <ArtTableHeader v-model:columns="columnChecks" :loading="loading" @refresh="refreshData">
        <template #left>
          <ElSpace wrap>
            <ElButton v-auth="'role.write'" @click="showDialog('add')" v-ripple>新建角色</ElButton>
          </ElSpace>
        </template>
      </ArtTableHeader>

      <ArtTable :loading="loading" :data="data" :columns="columns"> </ArtTable>
    </ElCard>

    <RoleDialog
      v-model:visible="dialogVisible"
      :type="dialogType"
      :role-data="currentRole"
      @submit="handleDialogSubmit"
    />
  </div>
</template>

<script setup lang="ts">
  import { ElMessage, ElMessageBox, ElTag } from 'element-plus'
  import ArtButtonTable from '@/components/core/forms/art-button-table/index.vue'
  import { useTable } from '@/hooks/core/useTable'
  import { fetchDeleteRole, fetchGetRoleList } from '@/api/rbac'
  import { DialogType } from '@/types'
  import RoleDialog from './modules/role-dialog.vue'

  defineOptions({ name: 'FangyuRoles' })

  type Role = Api.Fangyu.Role

  const dialogVisible = ref(false)
  const dialogType = ref<DialogType>('add')
  const currentRole = ref<Role | undefined>(undefined)

  const { columns, columnChecks, data, loading, refreshData, refreshCreate, refreshUpdate } =
    useTable({
      core: {
        apiFn: fetchGetRoleList,
        columnsFactory: () => [
          { prop: 'id', label: 'ID', width: 80 },
          { prop: 'name', label: '角色名', minWidth: 140 },
          { prop: 'description', label: '描述', minWidth: 180, showOverflowTooltip: true },
          {
            prop: 'is_system',
            label: '类型',
            width: 100,
            formatter: (row: Role) =>
              h(ElTag, { type: row.is_system ? 'warning' : 'info' }, () =>
                row.is_system ? '系统' : '自定义'
              )
          },
          {
            prop: 'permissions',
            label: '权限数',
            width: 100,
            formatter: (row: Role) => row.permissions?.length ?? 0
          },
          {
            prop: 'operation',
            label: '操作',
            width: 120,
            fixed: 'right',
            formatter: (row: Role) =>
              h('div', [
                h(ArtButtonTable, {
                  type: 'edit',
                  title: `编辑角色 ${row.name}`,
                  onClick: () => showDialog('edit', row)
                }),
                h(ArtButtonTable, {
                  type: 'delete',
                  // 系统角色走真禁用：不可点击、不可聚焦，并就地说明原因
                  disabled: row.is_system,
                  title: row.is_system ? '系统角色不可删除' : `删除角色 ${row.name}`,
                  onClick: () => deleteRole(row)
                })
              ])
          }
        ]
      }
    })

  const showDialog = (type: DialogType, row?: Role) => {
    dialogType.value = type
    currentRole.value = row
    nextTick(() => {
      dialogVisible.value = true
    })
  }

  const handleDialogSubmit = (type: DialogType) => {
    if (type === 'add') {
      refreshCreate()
    } else {
      refreshUpdate()
    }
  }

  const deleteRole = async (row: Role) => {
    if (row.is_system) {
      ElMessage.warning('系统角色不可删除')
      return
    }

    const boundUsers = row.permissions?.length ?? 0
    const confirmed = await ElMessageBox.confirm(
      `确定删除角色「${row.name}」吗？删除后，已绑定该角色的用户将立即失去本角色包含的 ${boundUsers} 项权限，且不可恢复。`,
      '删除角色',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'error'
      }
    ).catch(() => false)
    if (!confirmed) return

    await fetchDeleteRole(row.id)
    ElMessage.success(`角色「${row.name}」已删除，相关用户权限已同步收回`)
    refreshData()
  }
</script>
