<template>
  <ElDialog
    v-model="dialogVisible"
    :title="isEdit ? '编辑应用' : '新建应用'"
    width="520px"
    align-center
    :close-on-click-modal="false"
  >
    <ElForm ref="formRef" :model="form" :rules="rules" label-width="100px">
      <ElFormItem v-if="isEdit" label="App Key">
        <span class="readonly-text">{{ appData?.app_key }}</span>
      </ElFormItem>

      <ElFormItem label="应用名称" prop="name">
        <ElInput v-model="form.name" placeholder="如：电商业务线" />
      </ElFormItem>

      <ElFormItem label="描述">
        <ElInput
          v-model="form.description"
          type="textarea"
          :rows="3"
          placeholder="应用用途说明（选填）"
        />
      </ElFormItem>

      <ElFormItem v-if="isEdit" label="启用状态">
        <ElSwitch v-model="form.is_active" />
      </ElFormItem>
    </ElForm>

    <template #footer>
      <ElButton @click="dialogVisible = false">取消</ElButton>
      <ElButton type="primary" :loading="saving" @click="handleSubmit" v-ripple>
        {{ isEdit ? '保存' : '创建应用' }}
      </ElButton>
    </template>
  </ElDialog>
</template>

<script setup lang="ts">
  import { ElMessage } from 'element-plus'
  import type { FormInstance, FormRules } from 'element-plus'
  import type { DialogType } from '@/types'
  import { fetchCreateApplication, fetchUpdateApplication } from '@/api/apps'

  interface Props {
    visible: boolean
    type: DialogType
    appData?: Partial<Api.Fangyu.Application>
  }

  interface Emits {
    (e: 'update:visible', value: boolean): void
    (e: 'submit'): void
    (e: 'created', app: Api.Fangyu.ApplicationDetail): void
  }

  const props = defineProps<Props>()
  const emit = defineEmits<Emits>()

  const dialogVisible = computed({
    get: () => props.visible,
    set: (value) => emit('update:visible', value)
  })

  const isEdit = computed(() => props.type === 'edit')
  const formRef = ref<FormInstance>()
  const saving = ref(false)

  const defaultForm = () => ({
    name: '',
    description: '',
    is_active: true
  })

  const form = reactive(defaultForm())

  const rules: FormRules = {
    name: [{ required: true, message: '请输入应用名称', trigger: 'blur' }]
  }

  watch(
    () => [props.visible, props.type, props.appData],
    ([visible]) => {
      if (!visible) return
      const d = defaultForm()
      if (isEdit.value && props.appData) {
        Object.assign(form, {
          ...d,
          name: props.appData.name || '',
          description: props.appData.description || '',
          is_active: props.appData.is_active ?? true
        })
      } else {
        Object.assign(form, d)
      }
      nextTick(() => formRef.value?.clearValidate())
    },
    { immediate: true }
  )

  const handleSubmit = async () => {
    if (!formRef.value) return
    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return

    saving.value = true
    try {
      if (isEdit.value && props.appData?.id) {
        await fetchUpdateApplication(props.appData.id, {
          name: form.name,
          description: form.description,
          is_active: form.is_active
        })
        ElMessage.success('应用已更新')
        dialogVisible.value = false
        emit('submit')
      } else {
        const res = await fetchCreateApplication({
          name: form.name,
          description: form.description
        })
        dialogVisible.value = false
        emit('created', res)
      }
    } catch {
      ElMessage.error(isEdit.value ? '更新失败，请稍后重试' : '创建失败，请稍后重试')
    } finally {
      saving.value = false
    }
  }
</script>

<style scoped lang="scss">
  .readonly-text {
    font-family: ui-monospace, 'Cascadia Code', monospace;
    font-size: 13px;
    color: var(--art-text-gray-600);
  }
</style>
