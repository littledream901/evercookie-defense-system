<!-- 用户管理 -->
<template>
  <div class="art-full-height">
    <UserSearch
      v-show="showSearchBar"
      v-model="searchForm"
      @search="handleSearch"
      @reset="handleReset"
    ></UserSearch>

    <ElCard class="art-table-card" :style="{ 'margin-top': showSearchBar ? '12px' : '0' }">
      <ArtTableHeader
        v-model:columns="columnChecks"
        v-model:showSearchBar="showSearchBar"
        :loading="loading"
        @refresh="refreshData"
      >
        <template #left>
          <ElSpace wrap>
            <ElButton v-auth="'user.write'" @click="showDialog('add')" v-ripple>新建用户</ElButton>
          </ElSpace>
        </template>
      </ArtTableHeader>

      <ArtTable
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      >
      </ArtTable>
    </ElCard>

    <UserDialog
      v-model:visible="dialogVisible"
      :type="dialogType"
      :user-data="currentUser"
      @submit="handleDialogSubmit"
    />

    <UserRolesDialog
      v-model:visible="rolesDialogVisible"
      :user-data="currentUser"
      @submit="refreshUpdate"
    />
  </div>
</template>

<script setup lang="ts">
  import { ElButton, ElMessage, ElMessageBox, ElTag } from 'element-plus'
  import ArtButtonMore, {
    type ButtonMoreItem
  } from '@/components/core/forms/art-button-more/index.vue'
  import { useTable } from '@/hooks/core/useTable'
  import { fetchDeleteUser, fetchGetUserList, fetchResetUserPassword } from '@/api/rbac'
  import { formatTime } from '@/utils/format'
  import { USER_STATUS_OPTIONS, USER_STATUS_TAGS } from '@/constants/fangyu'
  import { DialogType } from '@/types'
  import UserSearch from './modules/user-search.vue'
  import UserDialog from './modules/user-dialog.vue'
  import UserRolesDialog from './modules/user-roles-dialog.vue'

  defineOptions({ name: 'FangyuUsers' })

  type User = Api.Fangyu.User

  const showSearchBar = ref(false)
  const dialogVisible = ref(false)
  const rolesDialogVisible = ref(false)
  const dialogType = ref<DialogType>('add')
  const currentUser = ref<User | undefined>(undefined)

  const searchForm = ref<Api.Fangyu.UserListParams>({
    keyword: undefined,
    status: undefined
  })

  const statusLabel = (status: string) =>
    USER_STATUS_OPTIONS.find((item) => item.value === status)?.label || status

  const {
    columns,
    columnChecks,
    data,
    loading,
    pagination,
    getData,
    replaceSearchParams,
    resetSearchParams,
    handleSizeChange,
    handleCurrentChange,
    refreshData,
    refreshCreate,
    refreshUpdate,
    refreshRemove
  } = useTable({
    core: {
      apiFn: fetchGetUserList,
      apiParams: {
        page: 1,
        pageSize: 20,
        ...searchForm.value
      },
      columnsFactory: () => [
        { prop: 'id', label: 'ID', width: 80 },
        { prop: 'username', label: '用户名', minWidth: 120 },
        { prop: 'email', label: '邮箱', minWidth: 180 },
        { prop: 'display_name', label: '显示名', minWidth: 120 },
        {
          prop: 'status',
          label: '状态',
          width: 100,
          formatter: (row: User) =>
            h(ElTag, { type: USER_STATUS_TAGS[row.status] || 'info' }, () => statusLabel(row.status))
        },
        { prop: 'created_at', label: '创建时间', width: 180,
          formatter: (row: User) => formatTime(row.created_at) },
        {
          prop: 'operation',
          label: '操作',
          width: 80,
          fixed: 'right',
          formatter: (row: User) =>
            h('div', [
              h(ArtButtonMore, {
                list: [
                  { key: 'edit', label: '编辑', icon: 'ri:edit-2-line', auth: 'user.write' },
                  { key: 'roles', label: '分配角色', icon: 'ri:user-3-line', auth: 'user.write' },
                  {
                    key: 'reset',
                    label: '重置密码',
                    icon: 'ri:lock-password-line',
                    auth: 'user.write'
                  },
                  {
                    key: 'delete',
                    label: '删除',
                    icon: 'ri:delete-bin-4-line',
                    color: '#f56c6c',
                    auth: 'user.write'
                  }
                ],
                onClick: (item: ButtonMoreItem) => handleMoreClick(item, row)
              })
            ])
        }
      ]
    }
  })

  const handleSearch = (params: Api.Fangyu.UserListParams) => {
    replaceSearchParams(params)
    getData()
  }

  const handleReset = () => {
    resetSearchParams()
  }

  const showDialog = (type: DialogType, row?: User) => {
    dialogType.value = type
    currentUser.value = row
    nextTick(() => {
      dialogVisible.value = true
    })
  }

  const showRolesDialog = (row: User) => {
    currentUser.value = row
    nextTick(() => {
      rolesDialogVisible.value = true
    })
  }

  const handleDialogSubmit = (type: DialogType) => {
    if (type === 'add') {
      refreshCreate()
    } else {
      refreshUpdate()
    }
  }

  /** 使用 CSPRNG 生成满足复杂度要求的随机密码 */
  const generatePassword = (length = 16) => {
    const groups = [
      'ABCDEFGHJKLMNPQRSTUVWXYZ',
      'abcdefghijkmnopqrstuvwxyz',
      '23456789',
      '!@#$%^&*-_=+'
    ]
    const alphabet = groups.join('')
    const bytes = new Uint32Array(length)
    crypto.getRandomValues(bytes)

    // 前 4 位分别取自各字符组，保证复杂度；其余随机
    const chars = groups.map((group, i) => group[bytes[i] % group.length])
    for (let i = groups.length; i < length; i++) {
      chars.push(alphabet[bytes[i] % alphabet.length])
    }

    // Fisher-Yates 洗牌，避免固定的字符组顺序
    const shuffle = new Uint32Array(chars.length)
    crypto.getRandomValues(shuffle)
    for (let i = chars.length - 1; i > 0; i--) {
      const j = shuffle[i] % (i + 1)
      ;[chars[i], chars[j]] = [chars[j], chars[i]]
    }
    return chars.join('')
  }

  const copyText = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success(`已复制${label}`)
    } catch {
      ElMessage.error('复制失败，请手动选择复制')
    }
  }

  const resetPassword = async (row: User) => {
    const confirmed = await ElMessageBox.confirm(
      `确定重置用户「${row.username}」的密码吗？重置后该用户当前所有登录会话将立即失效，需使用新密码重新登录。新密码仅展示一次，关闭后无法再次查看。`,
      '重置密码',
      { confirmButtonText: '生成新密码', cancelButtonText: '取消', type: 'warning' }
    ).catch(() => false)
    if (!confirmed) return

    const password = generatePassword()
    await fetchResetUserPassword(row.id, { new_password: password })

    await ElMessageBox({
      title: '密码已重置',
      showCancelButton: false,
      confirmButtonText: '我已保存，关闭',
      closeOnClickModal: false,
      closeOnPressEscape: false,
      message: () =>
        h('div', { class: 'flex flex-col gap-3' }, [
          h(
            'div',
            { class: 'text-sm' },
            `用户「${row.username}」的新密码如下，仅此一次展示，请立即复制并通过安全渠道转交。`
          ),
          h(
            'div',
            {
              class: 'flex items-center gap-2 rounded px-3 py-2',
              style: 'background: var(--el-fill-color-light)'
            },
            [
              h(
                'span',
                {
                  class: 'flex-1 break-all font-semibold',
                  style: 'font-family: ui-monospace, monospace'
                },
                password
              ),
              h(
                ElButton,
                { link: true, type: 'primary', onClick: () => copyText(password, '新密码') },
                () => '复制'
              )
            ]
          )
        ])
    }).catch(() => undefined)
  }

  const deleteUser = async (row: User) => {
    const confirmed = await ElMessageBox.confirm(
      `确定删除用户「${row.username}」吗？该用户的账号、角色绑定与登录会话将一并清除，操作不可恢复。`,
      '删除用户',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'error' }
    ).catch(() => false)
    if (!confirmed) return

    await fetchDeleteUser(row.id)
    ElMessage.success(`用户「${row.username}」已删除`)
    refreshRemove()
  }

  const handleMoreClick = (item: ButtonMoreItem, row: User) => {
    switch (item.key) {
      case 'edit':
        showDialog('edit', row)
        break
      case 'roles':
        showRolesDialog(row)
        break
      case 'reset':
        resetPassword(row)
        break
      case 'delete':
        deleteUser(row)
        break
    }
  }
</script>
