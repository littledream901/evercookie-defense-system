<template>
  <div class="app-expand-row">
    <div class="app-expand-row__section">
      <div class="app-expand-row__label">站点 ID</div>
      <div class="app-expand-row__value app-expand-row__copyable">
        <span class="app-expand-row__mono">{{ site.site_id || '—' }}</span>
        <ElButton v-if="site.site_id" link type="primary" :icon="CopyDocument" @click="copy(site.site_id, '站点 ID（API Key）')" />
      </div>
    </div>

    <div class="app-expand-row__section">
      <div class="app-expand-row__label">域名</div>
      <div class="app-expand-row__value app-expand-row__domains">
        <div class="app-expand-row__domain-row">
          <span class="app-expand-row__mono">{{ site.domain }}</span>
          <ElTag size="small" type="info" class="ml-1">主域名</ElTag>
        </div>
        <template v-if="site.alt_domains && site.alt_domains.length">
          <div
            v-for="d in site.alt_domains"
            :key="d"
            class="app-expand-row__domain-row"
          >
            <span class="app-expand-row__mono text-g-500">{{ d }}</span>
            <ElTag size="small" class="ml-1">备用</ElTag>
          </div>
        </template>
      </div>
    </div>

    <div class="app-expand-row__section">
      <div class="app-expand-row__label">接入模式</div>
      <div class="app-expand-row__value">
        <ElTag size="small" :type="site.access_mode === 'sdk' ? 'success' : 'info'">
          {{ site.access_mode === 'sdk' ? 'SDK 接入' : '适配器' }}
        </ElTag>
        <span v-if="site.sdk_version" class="text-xs text-g-500 ml-2">v{{ site.sdk_version }}</span>
      </div>
    </div>

    <div v-if="site.remark" class="app-expand-row__section">
      <div class="app-expand-row__label">备注</div>
      <div class="app-expand-row__value text-sm text-g-600">{{ site.remark }}</div>
    </div>

    <div class="app-expand-row__actions">
      <ElButton size="small" :icon="Connection" @click="$emit('integrate', site)">接入指引</ElButton>
      <ElButton v-auth="'app.write'" size="small" :icon="Edit" @click="$emit('edit', site)">编辑</ElButton>
      <ElButton v-auth="'app.write'" size="small" :icon="Upload" @click="$emit('publish', site)">发布快照</ElButton>
      <ElButton v-auth="'app.write'" size="small" :icon="RefreshRight" @click="$emit('rotate', site)">轮换密钥</ElButton>
      <ElButton v-auth="'app.write'" size="small" type="danger" plain :icon="Delete" @click="$emit('delete', site)">删除</ElButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { CopyDocument, Connection, Edit, Upload, Delete, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

type SiteItem = Api.Fangyu.Site

const props = defineProps<{ site: SiteItem }>()

defineEmits<{
  (e: 'integrate', site: SiteItem): void
  (e: 'edit', site: SiteItem): void
  (e: 'publish', site: SiteItem): void
  (e: 'rotate', site: SiteItem): void
  (e: 'delete', site: SiteItem): void
}>()

const copy = async (text: string, label: string) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(`已复制 ${label}`)
  } catch {
    ElMessage.error('复制失败，请手动选择复制')
  }
}
</script>

<style scoped>
.app-expand-row {
  padding: 12px 24px 12px 48px;
  background: var(--art-bg-color, #fafafa);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.app-expand-row__section {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.app-expand-row__label {
  flex-shrink: 0;
  width: 72px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding-top: 2px;
}

.app-expand-row__value {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.app-expand-row__apikey {
  flex-wrap: nowrap;
}

.app-expand-row__domains {
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.app-expand-row__domain-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.app-expand-row__copyable {
  flex-wrap: nowrap;
}

.app-expand-row__mono {
  font-family: ui-monospace, 'Cascadia Code', monospace;
  font-size: 12px;
  word-break: break-all;
  color: var(--el-text-color-primary);
}

.app-expand-row__actions {
  display: flex;
  gap: 8px;
  padding-top: 4px;
  flex-wrap: wrap;
}
</style>
