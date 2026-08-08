<template>
  <ElDialog
    v-model="visible"
    :title="mode === 'rotate' ? '密钥轮换成功' : '站点创建成功'"
    width="520px"
    align-center
    :close-on-click-modal="true"
    :close-on-press-escape="true"
    @closed="handleClosed"
  >
    <div class="secret-reveal">
      <ElAlert
        v-if="mode === 'rotate'"
        type="warning"
        :closable="false"
        class="mb-4"
      >
        <template #title>
          <span class="font-medium">
            旧 Site Secret 已立即失效，所有使用旧密钥的适配器（Nginx-Lua、CF Worker、WordPress 插件等）
            需同步更新配置，否则签名验证将失败，站点防护中断。
          </span>
        </template>
      </ElAlert>
      <ElAlert
        v-else
        type="success"
        :closable="false"
        class="mb-4"
        show-icon
      >
        <template #title>
          <span class="font-medium">站点已创建，以下凭证仅此一次可见，请立即保存。</span>
        </template>
      </ElAlert>

      <div class="secret-reveal__item">
        <span class="secret-reveal__label">Site ID</span>
        <div class="secret-reveal__value">
          <span class="secret-reveal__mono">{{ site.id }}</span>
          <ElButton link type="primary" :icon="CopyDocument" @click="copy(String(site.id), 'Site ID')" />
        </div>
      </div>

      <div class="secret-reveal__item">
        <span class="secret-reveal__label">Site Key</span>
        <div class="secret-reveal__value">
          <span class="secret-reveal__mono">{{ site.site_key }}</span>
          <ElButton link type="primary" :icon="CopyDocument" @click="copy(String(site.site_key), 'Site Key')" />
        </div>
      </div>

      <div class="secret-reveal__item">
        <span class="secret-reveal__label">Site Secret</span>
        <div class="secret-reveal__value">
          <span class="secret-reveal__mono secret-reveal__secret">{{ site.site_secret }}</span>
          <ElButton link type="primary" :icon="CopyDocument" @click="copy(String(site.site_secret), 'Site Secret')" />
        </div>
      </div>

      <div class="secret-reveal__hint">
        <span class="text-sm text-g-500">
          Site Key 用作 <code>X-App-Key</code> 请求头；Site Secret 用于 HMAC 验签，
          关闭本弹窗后无法再次查看，遗失只能轮换。
        </span>
      </div>
    </div>

    <template #footer>
      <ElButton type="primary" @click="visible = false">关闭</ElButton>
    </template>
  </ElDialog>
</template>

<script setup lang="ts">
import { CopyDocument } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

interface Props {
  modelValue: boolean
  site: Api.Fangyu.SiteDetail
  /** 'create' = 新建后展示；'rotate' = 轮换后展示 */
  mode?: 'create' | 'rotate'
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  /** 关闭后通知父组件清理明文凭证 */
  (e: 'closed'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const copy = async (text: string, label: string) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(`已复制 ${label}`)
  } catch {
    ElMessage.error('复制失败，请手动选择复制')
  }
}

/** 弹窗动画结束后再清理，避免关闭过程中模板读取到 undefined */
const handleClosed = () => {
  emit('closed')
}
</script>

<style scoped>
.secret-reveal {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.secret-reveal__item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.secret-reveal__label {
  flex-shrink: 0;
  width: 80px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.secret-reveal__value {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.secret-reveal__mono {
  flex: 1;
  font-family: ui-monospace, 'Cascadia Code', monospace;
  font-size: 12px;
  word-break: break-all;
  color: var(--el-text-color-primary);
}

.secret-reveal__secret {
  color: var(--el-color-warning);
  font-weight: 600;
}

.secret-reveal__hint {
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  border-left: 3px solid var(--el-color-info-light-5);
}
</style>
