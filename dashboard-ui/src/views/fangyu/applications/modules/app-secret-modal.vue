<template>
  <ElDialog
    v-model="visible"
    :title="mode === 'rotate' ? '密钥轮换成功' : '应用创建成功'"
    width="520px"
    align-center
    @closed="emit('closed')"
  >
    <ElAlert
      v-if="mode === 'rotate'"
      type="warning"
      :closable="false"
      class="mb-4"
      show-icon
    >
      <template #title>
        <span class="font-medium">
          旧 App Secret 已立即失效，所有使用旧密钥的接入端需同步更新配置。
        </span>
      </template>
    </ElAlert>
    <ElAlert v-else type="success" :closable="false" class="mb-4" show-icon>
      <template #title>
        <span class="font-medium">应用已创建，以下凭证仅此一次可见，请立即保存。</span>
      </template>
    </ElAlert>

    <div class="secret-item">
      <span class="secret-item__label">App Key</span>
      <div class="secret-item__value">
        <span class="secret-item__mono">{{ appKey }}</span>
        <ElButton link type="primary" :icon="CopyDocument" @click="copy(appKey, 'App Key')" />
      </div>
    </div>

    <div class="secret-item">
      <span class="secret-item__label">App Secret</span>
      <div class="secret-item__value">
        <span class="secret-item__mono secret-item__secret">{{ appSecret }}</span>
        <ElButton link type="primary" :icon="CopyDocument" @click="copy(appSecret, 'App Secret')" />
      </div>
    </div>

    <div class="mt-3">
      <span class="text-sm text-g-500">
        关闭本弹窗后无法再次查看 App Secret，遗失只能轮换。
      </span>
    </div>

    <template #footer>
      <ElButton type="primary" @click="visible = false">我已保存</ElButton>
    </template>
  </ElDialog>
</template>

<script setup lang="ts">
  import { CopyDocument } from '@element-plus/icons-vue'
  import { ElMessage } from 'element-plus'

  interface Props {
    modelValue: boolean
    appKey: string
    appSecret: string
    mode?: 'create' | 'rotate'
  }

  const props = withDefaults(defineProps<Props>(), { mode: 'create' })

  const emit = defineEmits<{
    (e: 'update:modelValue', value: boolean): void
    (e: 'closed'): void
  }>()

  const visible = computed({
    get: () => props.modelValue,
    set: (value) => emit('update:modelValue', value)
  })

  const copy = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success(`已复制${label}`)
    } catch {
      ElMessage.error('复制失败，请手动选择复制')
    }
  }
</script>

<style scoped lang="scss">
  .secret-item {
    display: flex;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid var(--art-border-color);

    &__label {
      width: 110px;
      font-size: 13px;
      color: var(--art-text-gray-600);
    }

    &__value {
      display: flex;
      flex: 1;
      align-items: center;
      gap: 6px;
      min-width: 0;
    }

    &__mono {
      font-family: ui-monospace, 'Cascadia Code', monospace;
      font-size: 13px;
      word-break: break-all;
    }

    &__secret {
      color: var(--el-color-danger);
    }
  }
</style>
