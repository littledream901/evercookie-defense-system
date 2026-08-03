<template>
  <ElDialog v-model="dialogVisible" title="新增权限" width="480px" align-center>
    <ElForm ref="formRef" :model="formData" :rules="rules" label-width="80px">
      <ElFormItem label="权限码" prop="code">
        <ElInput v-model="formData.code" placeholder="示例：user.read" />
      </ElFormItem>
      <ElFormItem label="描述" prop="description">
        <ElInput v-model="formData.description" placeholder="请输入权限描述" />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <div class="dialog-footer">
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="saving" @click="handleSubmit" v-ripple>保存</ElButton>
      </div>
    </template>
  </ElDialog>
</template>

<script setup lang="ts">
  import { fetchUpsertPermission } from '@/api/rbac'
  import type { FormInstance, FormRules } from 'element-plus'

  interface Props {
    visible: boolean
  }

  interface Emits {
    (e: 'update:visible', value: boolean): void
    (e: 'submit'): void
  }

  const props = defineProps<Props>()
  const emit = defineEmits<Emits>()

  /**
   * 弹窗显示控制
   */
  const dialogVisible = computed({
    get: () => props.visible,
    set: (value) => emit('update:visible', value)
  })

  const formRef = ref<FormInstance>()
  const saving = ref(false)

  /**
   * 表单数据
   */
  const formData = reactive({
    code: '',
    description: ''
  })

  /**
   * 表单校验规则
   */
  const rules: FormRules = {
    code: [{ required: true, message: '请输入权限码', trigger: 'blur' }]
  }

  watch(
    () => props.visible,
    (visible) => {
      if (visible) {
        Object.assign(formData, { code: '', description: '' })
        nextTick(() => {
          formRef.value?.clearValidate()
        })
      }
    },
    { immediate: true }
  )

  /**
   * 提交表单
   */
  const handleSubmit = async () => {
    if (!formRef.value) return

    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return

    saving.value = true
    try {
      await fetchUpsertPermission({
        code: formData.code,
        description: formData.description || undefined
      })
      ElMessage.success('新增成功')
      dialogVisible.value = false
      emit('submit')
    } finally {
      saving.value = false
    }
  }
</script>
