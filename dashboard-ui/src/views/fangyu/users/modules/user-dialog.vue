<template>
  <ElDialog
    v-model="dialogVisible"
    :title="isEdit ? '编辑用户' : '新建用户'"
    width="480px"
    align-center
  >
    <ElForm ref="formRef" :model="formData" :rules="rules" label-width="80px">
      <ElFormItem label="用户名" prop="username">
        <ElInput v-model="formData.username" :disabled="isEdit" placeholder="请输入用户名" />
      </ElFormItem>
      <ElFormItem label="邮箱" prop="email">
        <ElInput v-model="formData.email" placeholder="请输入邮箱" />
      </ElFormItem>
      <ElFormItem label="显示名" prop="display_name">
        <ElInput v-model="formData.display_name" placeholder="请输入显示名" />
      </ElFormItem>
      <template v-if="!isEdit">
        <ElFormItem label="密码" prop="password">
          <ElInput
            v-model="formData.password"
            show-password
            placeholder="至少 10 位，含大小写字母与数字"
          />
          <div class="mt-1 text-xs text-g-500">
            密码需至少 10 位，且同时包含大写字母、小写字母与数字
          </div>
        </ElFormItem>
        <ElFormItem label="确认密码" prop="confirmPassword">
          <ElInput
            v-model="formData.confirmPassword"
            show-password
            placeholder="请再次输入密码"
          />
        </ElFormItem>
      </template>
      <ElFormItem v-if="isEdit" label="状态" prop="status">
        <ElSelect v-model="formData.status" placeholder="请选择状态">
          <ElOption
            v-for="item in USER_STATUS_OPTIONS"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </ElSelect>
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
  import { fetchCreateUser, fetchUpdateUser } from '@/api/rbac'
  import { USER_STATUS_OPTIONS } from '@/constants/fangyu'
  import { DialogType } from '@/types'

  interface Props {
    visible: boolean
    type: DialogType
    userData?: Api.Fangyu.User
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

  const formRef = ref<FormInstance>()
  const submitting = ref(false)

  const formData = reactive({
    username: '',
    email: '',
    display_name: '',
    password: '',
    confirmPassword: '',
    status: 'active'
  })

  const validatePasswordStrength = (_rule: unknown, value: string, callback: (e?: Error) => void) => {
    if (!value) return callback(new Error('请输入密码'))
    if (value.length < 10) return callback(new Error('密码至少 10 位'))
    if (!/[A-Z]/.test(value)) return callback(new Error('密码需包含大写字母'))
    if (!/[a-z]/.test(value)) return callback(new Error('密码需包含小写字母'))
    if (!/\d/.test(value)) return callback(new Error('密码需包含数字'))
    // 密码变化后同步校验确认密码，避免残留旧的通过状态
    if (formData.confirmPassword) formRef.value?.validateField('confirmPassword')
    callback()
  }

  const validateConfirmPassword = (_rule: unknown, value: string, callback: (e?: Error) => void) => {
    if (!value) return callback(new Error('请再次输入密码'))
    if (value !== formData.password) return callback(new Error('两次输入的密码不一致'))
    callback()
  }

  const rules: FormRules = {
    username: [
      { required: true, message: '请输入用户名', trigger: 'blur' },
      {
        pattern: /^[a-zA-Z0-9_.-]{3,32}$/,
        message: '用户名为 3-32 位字母、数字、下划线、点或连字符',
        trigger: 'blur'
      }
    ],
    email: [
      { required: true, message: '请输入邮箱', trigger: 'blur' },
      { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
    ],
    password: [{ required: true, validator: validatePasswordStrength, trigger: 'blur' }],
    confirmPassword: [{ required: true, validator: validateConfirmPassword, trigger: 'blur' }]
  }

  const initFormData = () => {
    const row = props.userData
    Object.assign(formData, {
      username: isEdit.value ? row?.username || '' : '',
      email: isEdit.value ? row?.email || '' : '',
      display_name: isEdit.value ? row?.display_name || '' : '',
      password: '',
      confirmPassword: '',
      status: isEdit.value ? row?.status || 'active' : 'active'
    })
  }

  watch(
    () => [props.visible, props.type, props.userData] as const,
    ([visible]) => {
      if (!visible) {
        // 关闭后清理明文密码，避免驻留内存
        formData.password = ''
        formData.confirmPassword = ''
        return
      }
      initFormData()
      nextTick(() => formRef.value?.clearValidate())
    },
    { immediate: true }
  )

  const handleSubmit = async () => {
    if (!formRef.value) return

    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return

    submitting.value = true
    try {
      if (isEdit.value && props.userData) {
        await fetchUpdateUser(props.userData.id, {
          email: formData.email,
          display_name: formData.display_name,
          status: formData.status
        })
        ElMessage.success(`用户「${props.userData.username}」已更新`)
      } else {
        await fetchCreateUser({
          username: formData.username,
          email: formData.email,
          display_name: formData.display_name,
          password: formData.password
        })
        ElMessage.success(`用户「${formData.username}」创建成功，请为其分配角色后方可使用`)
      }
      dialogVisible.value = false
      emit('submit', props.type)
    } finally {
      submitting.value = false
    }
  }
</script>
