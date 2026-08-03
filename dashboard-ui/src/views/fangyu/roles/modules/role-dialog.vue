<template>
  <ElDialog
    v-model="dialogVisible"
    :title="isEdit ? '编辑角色' : '新建角色'"
    width="560px"
    align-center
  >
    <ElForm ref="formRef" :model="formData" :rules="rules" label-width="80px">
      <ElFormItem label="角色名" prop="name">
        <ElInput v-model="formData.name" :disabled="isSystem" placeholder="请输入角色名" />
      </ElFormItem>
      <ElFormItem label="描述" prop="description">
        <ElInput v-model="formData.description" placeholder="请输入描述" />
      </ElFormItem>
      <ElFormItem label="权限清单" prop="permissions">
        <ElSelect
          v-model="formData.permissions"
          multiple
          filterable
          class="w-full"
          placeholder="选择权限（至少一项）"
          :loading="permissionLoading"
        >
          <ElOption
            v-for="item in permissionOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </ElSelect>
        <div v-if="permissionError" class="mt-1 flex items-center gap-2 text-xs text-error">
          <span>{{ permissionError }}</span>
          <ElButton link type="primary" size="small" @click="loadPermissions()">重试</ElButton>
        </div>
      </ElFormItem>
    </ElForm>
    <template #footer>
      <div class="dialog-footer">
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="handleSubmit" v-ripple>保存</ElButton>
      </div>
    </template>
  </ElDialog>
</template>

<script setup lang="ts">
  import { ElMessage } from 'element-plus'
  import type { FormInstance, FormRules } from 'element-plus'
  import { fetchCreateRole, fetchGetPermissionList, fetchUpdateRole } from '@/api/rbac'
  import { DialogType } from '@/types'

  interface Props {
    visible: boolean
    type: DialogType
    roleData?: Api.Fangyu.Role
  }

  interface Emits {
    (e: 'update:visible', value: boolean): void
    (e: 'submit', type: DialogType): void
  }

  const props = defineProps<Props>()
  const emit = defineEmits<Emits>()

  const dialogVisible = computed({
    get: () => props.visible,
    set: (value) => emit('update:visible', value)
  })

  const isEdit = computed(() => props.type === 'edit')
  const isSystem = computed(() => Boolean(isEdit.value && props.roleData?.is_system))

  const formRef = ref<FormInstance>()
  const submitting = ref(false)
  const permissionLoading = ref(false)
  const permissionOptions = ref<{ label: string; value: string }[]>([])

  const formData = reactive({
    name: '',
    description: '',
    permissions: [] as string[]
  })

  const permissionError = ref('')

  const rules: FormRules = {
    name: [
      { required: true, message: '请输入角色名', trigger: 'blur' },
      { min: 2, max: 32, message: '角色名长度需为 2-32 个字符', trigger: 'blur' }
    ],
    permissions: [
      {
        required: true,
        type: 'array',
        min: 1,
        message: '请至少选择一项权限，否则该角色无任何可用功能',
        trigger: 'change'
      }
    ]
  }

  const loadPermissions = async () => {
    if (permissionOptions.value.length) return

    permissionLoading.value = true
    permissionError.value = ''
    try {
      const list = await fetchGetPermissionList()
      permissionOptions.value = (list || []).map((item) => ({
        label: `${item.code} - ${item.description}`,
        value: item.code
      }))
    } catch (err) {
      permissionError.value = '权限清单加载失败，请重试后再保存'
      console.error('加载权限清单失败:', err)
    } finally {
      permissionLoading.value = false
    }
  }

  const initFormData = () => {
    const row = props.roleData
    Object.assign(formData, {
      name: isEdit.value ? row?.name || '' : '',
      description: isEdit.value ? row?.description || '' : '',
      permissions: isEdit.value ? [...(row?.permissions || [])] : []
    })
  }

  watch(
    () => [props.visible, props.type, props.roleData],
    ([visible]) => {
      if (visible) {
        initFormData()
        loadPermissions()
        nextTick(() => formRef.value?.clearValidate())
      }
    },
    { immediate: true }
  )

  const handleSubmit = async () => {
    if (!formRef.value) return
    if (permissionError.value) {
      ElMessage.warning(permissionError.value)
      return
    }

    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return

    submitting.value = true
    try {
      if (isEdit.value && props.roleData) {
        await fetchUpdateRole(props.roleData.id, {
          description: formData.description,
          permissions: formData.permissions
        })
        ElMessage.success(
          `角色「${props.roleData.name}」已更新，已绑定用户的权限将在下次请求时生效`
        )
      } else {
        await fetchCreateRole({
          name: formData.name.trim(),
          description: formData.description,
          permissions: formData.permissions
        })
        ElMessage.success(`角色「${formData.name.trim()}」创建成功`)
      }
      dialogVisible.value = false
      emit('submit', props.type)
    } finally {
      submitting.value = false
    }
  }
</script>
