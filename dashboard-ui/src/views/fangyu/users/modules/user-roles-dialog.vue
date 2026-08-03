<template>
  <ElDialog
    v-model="dialogVisible"
    :title="userData ? `分配角色 - ${userData.username}` : '分配角色'"
    width="480px"
    align-center
  >
    <div v-loading="loading" class="min-h-30">
      <ElAlert
        v-if="loadError"
        type="error"
        :closable="false"
        title="角色数据加载失败"
        description="为避免误写权限，保存已被禁用。请重试加载。"
        class="mb-3"
      />
      <ElButton v-if="loadError" @click="userData && loadData(userData.id)">重新加载</ElButton>

      <ElEmpty v-else-if="!loading && !allRoles.length" description="暂无可分配的角色" />

      <ElCheckboxGroup v-else v-model="selectedRoleIds">
        <div class="flex flex-col gap-2">
          <ElCheckbox v-for="role in allRoles" :key="role.id" :value="role.id" :label="role.name" />
        </div>
      </ElCheckboxGroup>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton
          type="primary"
          :loading="submitting"
          :disabled="loading || loadError || !canSubmit"
          @click="handleSubmit"
          v-ripple
        >
          保存
        </ElButton>
      </div>
    </template>
  </ElDialog>
</template>

<script setup lang="ts">
  import { ElMessage } from 'element-plus'
  import { fetchAssignUserRoles, fetchGetRoleList, fetchGetUserDetail } from '@/api/rbac'

  interface Props {
    visible: boolean
    userData?: Api.Fangyu.User
  }

  interface Emits {
    (e: 'update:visible', value: boolean): void
    (e: 'submit'): void
  }

  const props = defineProps<Props>()
  const emit = defineEmits<Emits>()

  const dialogVisible = computed({
    get: () => props.visible,
    set: (value) => emit('update:visible', value)
  })

  const loading = ref(false)
  const submitting = ref(false)
  const loadError = ref(false)
  const allRoles = ref<Api.Fangyu.Role[]>([])
  const selectedRoleIds = ref<number[]>([])
  /** 已成功加载角色的用户 ID，防止把 A 用户的选择写到 B 用户身上 */
  const loadedUserId = ref<number | null>(null)

  const canSubmit = computed(
    () => typeof props.userData?.id === 'number' && loadedUserId.value === props.userData.id
  )

  let loadSeq = 0

  const loadData = async (userId: number) => {
    const seq = ++loadSeq
    loading.value = true
    loadError.value = false
    // 先清空残留状态，避免加载失败时沿用上一个用户的勾选
    allRoles.value = []
    selectedRoleIds.value = []
    loadedUserId.value = null

    try {
      const [roles, detail] = await Promise.all([
        fetchGetRoleList(),
        fetchGetUserDetail(userId)
      ])
      if (seq !== loadSeq) return
      allRoles.value = roles || []
      const assigned = detail?.roles
      selectedRoleIds.value =
        assigned && assigned.length ? assigned.map((item) => item.id) : detail?.role_ids || []
      loadedUserId.value = userId
    } catch (err) {
      if (seq !== loadSeq) return
      loadError.value = true
      console.error('加载用户角色失败:', err)
    } finally {
      if (seq === loadSeq) loading.value = false
    }
  }

  watch(
    () => [props.visible, props.userData?.id] as const,
    ([visible, userId]) => {
      if (!visible || typeof userId !== 'number') return
      loadData(userId)
    }
  )

  const handleSubmit = async () => {
    const userId = props.userData?.id
    // 仅允许提交当前已成功加载的用户，避免错写
    if (typeof userId !== 'number' || loadedUserId.value !== userId) {
      ElMessage.warning('角色数据未加载完成，请重试后再保存')
      return
    }

    submitting.value = true
    try {
      await fetchAssignUserRoles(userId, { role_ids: selectedRoleIds.value })
      ElMessage.success(`已更新「${props.userData?.username}」的角色，权限将在其下次请求时生效`)
      dialogVisible.value = false
      emit('submit')
    } finally {
      submitting.value = false
    }
  }
</script>
