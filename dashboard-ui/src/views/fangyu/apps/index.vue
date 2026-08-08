<template>
  <div class="art-full-height">
    <div class="mb-3">
      <h2 class="text-lg font-medium text-g-900">站点管理</h2>
      <p class="mt-1 text-sm text-g-600">接入站点配置、站点 ID（API Key）、域名与防御规则</p>
    </div>

    <AppSearch
      v-show="showSearchBar"
      v-model="searchForm"
      @search="handleSearch"
      @reset="resetSearchParams"
    />

    <ElCard class="art-table-card" :style="{ 'margin-top': showSearchBar ? '12px' : '0' }">
      <ArtTableHeader
        v-model:columns="columnChecks"
        v-model:showSearchBar="showSearchBar"
        :loading="loading"
        @refresh="refreshData"
      >
        <template #left>
          <ElSpace wrap>
            <ElButton v-auth="'app.write'" @click="showDialog('add')" v-ripple>新建站点</ElButton>

            <template v-if="selectedRows.length">
              <ElDivider direction="vertical" />
              <span class="text-sm text-g-600">已选 {{ selectedRows.length }} 项</span>
              <ElButton
                v-auth="'app.write'"
                type="primary"
                plain
                :loading="batchLoading"
                @click="batchPublish"
              >
                批量发布
              </ElButton>
              <ElButton
                v-auth="'app.write'"
                type="success"
                plain
                :loading="batchLoading"
                @click="batchToggle(true)"
              >
                批量启用
              </ElButton>
              <ElButton
                v-auth="'app.write'"
                type="warning"
                plain
                :loading="batchLoading"
                @click="batchToggle(false)"
              >
                批量停用
              </ElButton>
              <ElButton
                v-auth="'app.write'"
                plain
                :loading="batchLoading"
                @click="batchEditVisible = true"
              >
                批量编辑
              </ElButton>
              <ElButton
                v-auth="'app.write'"
                type="danger"
                plain
                :loading="batchLoading"
                @click="batchDelete"
              >
                批量删除
              </ElButton>
              <ElButton link @click="clearSelection">取消选择</ElButton>
            </template>
          </ElSpace>
        </template>
      </ArtTableHeader>

      <ArtTable
        ref="tableRef"
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        row-key="id"
        @selection-change="handleSelectionChange"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      >
        <!-- 站点名 / 域名列 -->
        <template #domain="{ row }">
          <div style="line-height: 1.8; padding: 2px 0">
            <div class="font-medium text-[13px]">{{ row.name }}</div>
            <div
              class="text-[12px] font-mono text-g-600"
              style="font-family: ui-monospace, 'Cascadia Code', monospace"
            >
              {{ row.domain }}
            </div>
            <template v-if="row.alt_domains?.length">
              <div
                v-for="d in row.alt_domains"
                :key="d"
                class="text-[12px] font-mono text-g-400"
                style="font-family: ui-monospace, 'Cascadia Code', monospace"
              >
                ↳ {{ d }}
              </div>
            </template>
          </div>
        </template>

        <!-- 站点 ID / API Key 列 -->
        <template #site_id="{ row }">
          <div v-if="row.site_id" class="flex items-center gap-1 min-w-0">
            <span
              class="text-[12px] text-g-500 truncate"
              style="font-family: ui-monospace, 'Cascadia Code', monospace; max-width: 160px"
              :title="row.site_id"
            >{{ row.site_id }}</span>
            <ElButton link type="primary" :icon="CopyDocument" size="small" @click.stop="copyAppId(row.site_id)" />
          </div>
          <span v-else class="text-g-400 text-[12px]">—</span>
        </template>

        <!-- App Secret 列（默认掩码，可展开查看/复制） -->
        <template #app_secret="{ row }">
          <div v-if="row.app_secret" class="flex items-center gap-1 min-w-0">
            <span
              class="text-[12px] text-g-500 truncate"
              style="font-family: ui-monospace, 'Cascadia Code', monospace; max-width: 190px"
              :title="revealedSecrets.has(row.id) ? row.app_secret : '点击右侧眼睛图标查看'"
            >
              {{ revealedSecrets.has(row.id) ? row.app_secret : maskSecret(row.app_secret) }}
            </span>
            <ElButton
              link
              type="primary"
              size="small"
              :icon="revealedSecrets.has(row.id) ? Hide : View"
              :title="revealedSecrets.has(row.id) ? '隐藏' : '查看'"
              @click.stop="toggleSecret(row.id)"
            />
            <ElButton
              link
              type="primary"
              size="small"
              :icon="CopyDocument"
              title="复制 App Secret"
              @click.stop="copyText(row.app_secret, 'App Secret')"
            />
          </div>
          <span v-else class="text-g-400 text-[12px]">—</span>
        </template>

        <!-- 绑定规则列 -->
        <template #rules="{ row }">
          <div v-if="row.rules?.length" class="flex items-center gap-1">
            <ElTooltip
              :disabled="row.rules.length <= 1"
              placement="top"
              :show-after="200"
            >
              <template #content>
                <div class="rule-tooltip-list">
                  <div
                    v-for="(rule, idx) in row.rules"
                    :key="idx"
                    class="rule-tooltip-item"
                  >
                    <span class="rule-tooltip-name">{{ rule.name }}</span>
                    <ElTag
                      size="small"
                      :type="RULE_STATUS_TAGS[rule.status] ?? 'info'"
                      class="ml-2"
                    >{{ RULE_STATUS_LABELS[rule.status] ?? rule.status }}</ElTag>
                  </div>
                </div>
              </template>
              <span class="text-[13px] text-primary cursor-help">
                {{ row.rules.length }} 条规则
              </span>
            </ElTooltip>
          </div>
          <span v-else class="text-g-400 text-[12px]">未绑定</span>
        </template>

        <!-- 接入模式列 -->
        <template #access_mode="{ row }">
          <ElTag :type="row.access_mode === 'sdk' ? 'success' : 'info'" size="small">
            {{ row.access_mode === 'sdk' ? 'SDK 接入' : '适配器' }}
          </ElTag>
        </template>

        <!-- 启用状态开关列 -->
        <template #is_active="{ row }">
          <ElSwitch
            :model-value="row.is_active"
            :loading="togglingIds.has(row.id)"
            :disabled="togglingIds.has(row.id)"
            active-text="启用"
            inactive-text="停用"
            inline-prompt
            :aria-label="`${row.is_active ? '停用' : '启用'}站点 ${row.name}`"
            @change="(val: string | number | boolean) => toggleActive(row, Boolean(val))"
          />
        </template>

        <!-- 操作列 -->
        <template #actions="{ row }">
          <ElSpace :size="4">
            <ElButton link type="primary" size="small" :icon="Connection" @click="showIntegration(row)">
              接入
            </ElButton>
            <ElButton link type="primary" size="small" :icon="Edit" @click="showDialog('edit', row)">
              编辑
            </ElButton>
            <ElButton link type="primary" size="small" :icon="Upload" @click="publishSnapshot(row)">
              发布
            </ElButton>
            <ElButton link type="warning" size="small" :icon="RefreshRight" @click="rotateKey(row)">
              轮换
            </ElButton>
            <ElButton link type="danger" size="small" :icon="Delete" @click="deleteSite(row)">
              删除
            </ElButton>
          </ElSpace>
        </template>
      </ArtTable>
    </ElCard>

    <AppDialog
      v-model:visible="dialogVisible"
      :type="dialogType"
      :app-data="currentSiteData"
      @submit="handleDialogSubmit"
      @created="handleSiteCreated"
    />

    <SecretRevealModal
      v-if="newSiteData"
      v-model="secretRevealVisible"
      :site="newSiteData"
      :mode="secretRevealMode"
      @closed="newSiteData = null"
    />

    <AppIntegrationDrawer
      v-model:visible="integrationVisible"
      :app="integrationSite"
    />

    <!-- 批量编辑：仅提交勾选了的字段，其余保持原值 -->
    <ElDialog v-model="batchEditVisible" title="批量编辑站点" width="520px" align-center>
      <ElAlert type="info" :closable="false" class="mb-3">
        <template #title>
          将对已选中的 {{ selectedRows.length }} 个站点生效；未勾选的字段保持各站点原值。
        </template>
      </ElAlert>

      <ElForm label-width="120px">
        <ElFormItem>
          <ElCheckbox v-model="batchFields.access_mode">修改接入模式</ElCheckbox>
          <ElSelect
            v-model="batchForm.access_mode"
            :disabled="!batchFields.access_mode"
            class="ml-2"
            style="width: 160px"
          >
            <ElOption label="适配器" value="adapter" />
            <ElOption label="SDK 接入" value="sdk" />
          </ElSelect>
        </ElFormItem>

        <ElFormItem>
          <ElCheckbox v-model="batchFields.clock_stats_enabled">修改频控统计</ElCheckbox>
          <ElSwitch
            v-model="batchForm.clock_stats_enabled"
            :disabled="!batchFields.clock_stats_enabled"
            class="ml-2"
          />
        </ElFormItem>

        <ElFormItem>
          <ElCheckbox v-model="batchFields.log_retention_days">修改日志保留天数</ElCheckbox>
          <ElInputNumber
            v-model="batchForm.log_retention_days"
            :disabled="!batchFields.log_retention_days"
            :min="1"
            :max="365"
            class="ml-2"
          />
        </ElFormItem>
      </ElForm>

      <template #footer>
        <ElButton @click="batchEditVisible = false">取消</ElButton>
        <ElButton
          type="primary"
          :loading="batchLoading"
          :disabled="!hasBatchField"
          @click="submitBatchEdit"
        >
          应用到 {{ selectedRows.length }} 个站点
        </ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { useTable } from '@/hooks/core/useTable'
  import { formatTime } from '@/utils/format'
  import {
    fetchGetAppList,
    fetchDeleteApp,
    fetchPublishSnapshot,
    fetchBatchPublishApps,
    fetchRotateAppKey,
    fetchUpdateApp,
    fetchBatchDeleteApps,
    fetchBatchToggleApps,
    fetchBatchUpdateApps
  } from '@/api/apps'
  import { APP_STATUS_TAGS, APP_STATUS_OPTIONS, pruneParams, RULE_STATUS_TAGS, RULE_STATUS_LABELS } from '@/constants/fangyu'
  import AppSearch from './modules/app-search.vue'
  import AppDialog from './modules/app-dialog.vue'
  import AppIntegrationDrawer from './modules/app-integration-drawer.vue'
  import SecretRevealModal from './modules/secret-reveal-modal.vue'
  import { ElTag, ElButton, ElMessage, ElMessageBox, ElSpace } from 'element-plus'
  import {
    Connection,
    Edit,
    Upload,
    RefreshRight,
    Delete,
    CopyDocument,
    View,
    Hide
  } from '@element-plus/icons-vue'
  import type { DialogType } from '@/types'

  defineOptions({ name: 'FangyuApps' })

  type SiteItem = Api.Fangyu.Site
  type SearchForm = { keyword?: string; status?: string; access_mode?: string }

  const showSearchBar = ref(false)
  const dialogType = ref<DialogType>('add')
  const dialogVisible = ref(false)
  const currentSiteData = ref<Partial<SiteItem>>({})
  const newSiteData = ref<Api.Fangyu.SiteCreateResponse | null>(null)
  const secretRevealVisible = ref(false)
  const secretRevealMode = ref<'create' | 'rotate'>('create')
  const integrationVisible = ref(false)
  const integrationSite = ref<Partial<SiteItem> | null>(null)

  const searchForm = ref<SearchForm>({
    keyword: undefined,
    status: undefined,
    access_mode: undefined
  })

  // ── App Secret 显隐 ────────────────────────────────────────────────────────
  /** 已展开明文的行 id；默认掩码，避免共享屏幕时误泄露 */
  const revealedSecrets = ref(new Set<number>())

  const maskSecret = (secret: string) =>
    secret.length <= 8 ? '••••••••' : `${secret.slice(0, 4)}${'•'.repeat(12)}${secret.slice(-4)}`

  const toggleSecret = (id: number) => {
    const next = new Set(revealedSecrets.value)
    next.has(id) ? next.delete(id) : next.add(id)
    revealedSecrets.value = next
  }

  const copyText = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success(`已复制${label}`)
    } catch {
      ElMessage.error('复制失败，请手动选择复制')
    }
  }

  // ── 单行启用 / 停用 ────────────────────────────────────────────────────────
  const togglingIds = ref(new Set<number>())

  const toggleActive = async (row: SiteItem, next: boolean) => {
    if (!next) {
      const confirmed = await ElMessageBox.confirm(
        `停用「${row.name}」后，网关将不再接受该站点的决策请求，该站点的防护立即失效。确认停用？`,
        '停用站点',
        { confirmButtonText: '停用', cancelButtonText: '取消', type: 'warning' }
      ).catch(() => false)
      if (!confirmed) return
    }

    togglingIds.value = new Set(togglingIds.value).add(row.id)
    try {
      await fetchUpdateApp(row.id, { is_active: next })
      ElMessage.success(`站点「${row.name}」已${next ? '启用' : '停用'}`)
      await refreshUpdate()
    } catch {
      ElMessage.error(`${next ? '启用' : '停用'}失败，请稍后重试`)
    } finally {
      const rest = new Set(togglingIds.value)
      rest.delete(row.id)
      togglingIds.value = rest
    }
  }

  // ── 批量操作 ───────────────────────────────────────────────────────────────
  const tableRef = useTemplateRef<{ elTableRef?: { clearSelection: () => void } }>('tableRef')
  const selectedRows = ref<SiteItem[]>([])
  const batchLoading = ref(false)
  const batchEditVisible = ref(false)

  const batchFields = reactive({
    access_mode: false,
    clock_stats_enabled: false,
    log_retention_days: false
  })

  const batchForm = reactive({
    access_mode: 'adapter' as 'adapter' | 'sdk',
    clock_stats_enabled: true,
    log_retention_days: 30
  })

  const hasBatchField = computed(() => Object.values(batchFields).some(Boolean))

  const handleSelectionChange = (rows: SiteItem[]) => {
    selectedRows.value = rows
  }

  const clearSelection = () => {
    tableRef.value?.elTableRef?.clearSelection()
    selectedRows.value = []
  }

  /** 统一提示批量结果：部分失败时逐条列出原因 */
  const reportBatchResult = (res: Api.Fangyu.SiteBatchResult, action: string) => {
    const okCount = res.succeeded?.length ?? 0
    const failed = res.failed ?? []
    if (!failed.length) {
      ElMessage.success(`已${action} ${okCount} 个站点`)
      return
    }
    ElMessageBox.alert(
      failed.map((f) => `站点 #${f.id}：${f.reason}`).join('\n'),
      `${okCount} 个成功，${failed.length} 个失败`,
      { confirmButtonText: '知道了', type: 'warning' }
    ).catch(() => undefined)
  }

  const batchToggle = async (isActive: boolean) => {
    if (!selectedRows.value.length) return
    const action = isActive ? '启用' : '停用'
    const confirmed = await ElMessageBox.confirm(
      isActive
        ? `将启用选中的 ${selectedRows.value.length} 个站点，网关将立即开始处理这些站点的请求。`
        : `将停用选中的 ${selectedRows.value.length} 个站点，这些站点的防护会立即失效，网关不再接受其决策请求。`,
      `批量${action}`,
      { confirmButtonText: action, cancelButtonText: '取消', type: 'warning' }
    ).catch(() => false)
    if (!confirmed) return

    batchLoading.value = true
    try {
      const res = await fetchBatchToggleApps(
        selectedRows.value.map((r) => r.id),
        isActive
      )
      reportBatchResult(res, action)
      clearSelection()
      await refreshUpdate()
    } catch {
      ElMessage.error(`批量${action}失败，请稍后重试`)
    } finally {
      batchLoading.value = false
    }
  }

  const batchDelete = async () => {
    if (!selectedRows.value.length) return
    const names = selectedRows.value.slice(0, 3).map((r) => r.name).join('、')
    const suffix = selectedRows.value.length > 3 ? ` 等 ${selectedRows.value.length} 个站点` : ''
    const confirmed = await ElMessageBox.confirm(
      `确定删除「${names}」${suffix}吗？站点的规则、快照与密钥将一并失效，操作不可恢复。` +
        `处于启用状态的站点会被跳过，需先停用。`,
      '批量删除站点',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'error' }
    ).catch(() => false)
    if (!confirmed) return

    batchLoading.value = true
    try {
      const res = await fetchBatchDeleteApps(selectedRows.value.map((r) => r.id))
      reportBatchResult(res, '删除')
      clearSelection()
      await refreshRemove()
    } catch {
      ElMessage.error('批量删除失败，请稍后重试')
    } finally {
      batchLoading.value = false
    }
  }

  const submitBatchEdit = async () => {
    if (!selectedRows.value.length || !hasBatchField.value) return

    const payload: Api.Fangyu.SiteBatchUpdatePayload = {
      ids: selectedRows.value.map((r) => r.id)
    }
    if (batchFields.access_mode) payload.access_mode = batchForm.access_mode
    if (batchFields.clock_stats_enabled)
      payload.clock_stats_enabled = batchForm.clock_stats_enabled
    if (batchFields.log_retention_days)
      payload.log_retention_days = batchForm.log_retention_days

    batchLoading.value = true
    try {
      const res = await fetchBatchUpdateApps(payload)
      reportBatchResult(res, '更新')
      batchEditVisible.value = false
      clearSelection()
      await refreshUpdate()
    } catch {
      ElMessage.error('批量更新失败，请稍后重试')
    } finally {
      batchLoading.value = false
    }
  }

  const batchPublish = async () => {
    if (!selectedRows.value.length) return
    const confirmed = await ElMessageBox.confirm(
      `将同步 ${selectedRows.value.length} 个站点的已发布规则到 Redis，网关立即生效。确认发布？`,
      '批量发布',
      { confirmButtonText: '发布', cancelButtonText: '取消', type: 'warning' }
    ).catch(() => false)
    if (!confirmed) return

    batchLoading.value = true
    try {
      const res = await fetchBatchPublishApps(selectedRows.value.map((r) => r.id))
      reportBatchResult(res, '发布')
      clearSelection()
    } catch {
      ElMessage.error('批量发布失败，请稍后重试')
    } finally {
      batchLoading.value = false
    }
  }

  const showIntegration = (row: SiteItem) => {
    integrationSite.value = row
    integrationVisible.value = true
  }

  const showDialog = (type: DialogType, row?: SiteItem) => {
    dialogType.value = type
    currentSiteData.value = row || {}
    nextTick(() => { dialogVisible.value = true })
  }

  const publishSnapshot = async (row: SiteItem) => {
    const confirmed = await ElMessageBox.confirm(
      `将「${row.name}」的当前配置发布到网关节点，期间请求处理逻辑将切换为最新规则。确认发布？`,
      '发布快照',
      { confirmButtonText: '发布', cancelButtonText: '取消', type: 'warning' }
    ).catch(() => false)
    if (!confirmed) return

    try {
      await fetchPublishSnapshot(row.id)
      ElMessage.success('快照发布成功，网关节点已更新')
    } catch {
      ElMessage.error('发布失败，请稍后重试')
    }
  }

  const rotateKey = async (row: SiteItem) => {
    const confirmed = await ElMessageBox.confirm(
      `轮换「${row.name}」的 App ID 与 App Secret 后，旧密钥立即失效，所有适配器需同步更新配置。确认轮换？`,
      '轮换密钥',
      { confirmButtonText: '确认轮换', cancelButtonText: '取消', type: 'warning' }
    ).catch(() => false)
    if (!confirmed) return

    try {
      const res = await fetchRotateAppKey(row.id)
      secretRevealMode.value = 'rotate'
      newSiteData.value = res
      secretRevealVisible.value = true
      await refreshUpdate()
    } catch {
      ElMessage.error('轮换失败，请稍后重试')
    }
  }

  const deleteSite = async (row: SiteItem) => {
    const confirmed = await ElMessageBox.confirm(
      `确定删除站点「${row.name}（${row.domain}）」吗？该站点的规则、快照与密钥将一并失效，操作不可恢复。`,
      '删除站点',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'error' }
    ).catch(() => false)
    if (!confirmed) return

    try {
      await fetchDeleteApp(row.id)
      ElMessage.success(`站点「${row.name}」已删除`)
      await refreshRemove()
    } catch {
      ElMessage.error('删除失败，请稍后重试')
    }
  }

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
      apiFn: fetchGetAppList,
      apiParams: { page: 1, pageSize: 20 },
      columnsFactory: () => [
        { type: 'selection', width: 50 },
        { prop: 'id', label: 'ID', width: 60 },
        {
          prop: 'domain',
          label: '站点 / 域名',
          minWidth: 150,
          useSlot: true
        },
        {
          prop: 'site_id',
          label: 'Site ID',
          minWidth: 150,
          useSlot: true
        },
        {
          prop: 'app_secret',
          label: 'App Secret',
          minWidth: 250,
          useSlot: true
        },
        {
          prop: 'rule_name',
          label: '绑定规则',
          minWidth: 100,
          useSlot: true
        },
        {
          prop: 'rule_status',
          label: '规则状态',
          width: 100,
          useSlot: true
        },
        {
          prop: 'access_mode',
          label: '接入模式',
          width: 100,
          useSlot: true
        },
        {
          prop: 'is_active',
          label: '启用状态',
          width: 100,
          useSlot: true
        },
        {
          prop: 'created_at',
          label: '创建时间',
          width: 170,
          formatter: (row: any) => formatTime(row.created_at)
        },
        {
          prop: 'actions',
          label: '操作',
          width: 280,
          fixed: 'right',
          useSlot: true
        }
      ]
    }
  })

  const handleSearch = (params: SearchForm) => {
    replaceSearchParams(pruneParams(params))
    getData()
  }

  const handleDialogSubmit = async () => {
    currentSiteData.value = {}
    await refreshUpdate()
  }

  const handleSiteCreated = (site: Api.Fangyu.SiteCreateResponse) => {
    secretRevealMode.value = 'create'
    newSiteData.value = site
    secretRevealVisible.value = true
    refreshCreate()
  }

  const copyAppId = async (appId: string) => {
    try {
      await navigator.clipboard.writeText(appId)
      ElMessage.success('已复制 App ID')
    } catch {
      ElMessage.error('复制失败，请手动复制')
    }
  }
</script>

<style scoped lang="scss">
.readonly-text {
  color: var(--el-text-color-regular);
  font-size: 14px;
}

.alt-domain-badge {
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  line-height: 1.2;
  color: var(--el-color-info);
  background-color: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
}

.rule-tooltip-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 400px;
}

.rule-tooltip-item {
  display: flex;
  align-items: center;
  padding: 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);

  &:last-child {
    border-bottom: none;
  }
}

.rule-tooltip-name {
  flex: 1;
  font-size: 13px;
  color: #fff;
}
</style>
