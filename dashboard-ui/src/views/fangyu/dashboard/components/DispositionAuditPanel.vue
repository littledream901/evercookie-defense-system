<!-- 处置动作逻辑合规性占位面板 -->
<template>
  <ElCard class="audit-card" shadow="never" :body-style="{ padding: '12px 16px' }">
    <template #header>
      <div class="flex-b items-center">
        <div class="flex items-center gap-2">
          <span class="font-medium">处置动作逻辑合规性</span>
          <ElTooltip placement="top">
            <template #content>
              三层处置模型（裁决 + 机制 + 目标）全链路静态走查结论。<br />
              覆盖 shared 契约、网关流水线、决策响应、四份适配器与后台配置面。<br />
              修复后请同步删除 dispositionAudit.ts 中的对应条目。
            </template>
            <ElIcon class="text-g-400 cursor-help"><QuestionFilled /></ElIcon>
          </ElTooltip>
        </div>
        <div class="flex items-center gap-2">
          <ElTag v-for="s in riskSummary" :key="s.risk" :type="s.tagType" size="small">
            {{ s.label }} {{ s.count }}
          </ElTag>
        </div>
      </div>
    </template>

    <ElAlert
      v-if="criticalCount > 0"
      type="error"
      :closable="false"
      class="mb-3"
      :title="`存在 ${criticalCount} 项致命缺陷：人机挑战（challenge）无验证闭环，配置该机制等价于永久阻断`"
      show-icon
    />

    <ElTable
      :data="rows"
      size="small"
      row-key="id"
      :max-height="320"
      :default-sort="{ prop: 'risk', order: 'ascending' }"
    >
      <ElTableColumn type="expand">
        <template #default="{ row }: { row: DispositionAuditItem }">
          <div class="px-4 py-2 text-xs leading-relaxed">
            <p class="mb-2"><span class="font-medium">问题成因：</span>{{ row.cause }}</p>
            <p><span class="font-medium">修复建议：</span>{{ row.fix }}</p>
          </div>
        </template>
      </ElTableColumn>

      <ElTableColumn prop="id" label="动作 ID" width="130" />

      <ElTableColumn prop="action" label="处置动作" min-width="170" show-overflow-tooltip />

      <ElTableColumn prop="location" label="配置位置" min-width="260">
        <template #default="{ row }: { row: DispositionAuditItem }">
          <span class="font-mono text-xs text-g-600">{{ row.location }}</span>
        </template>
      </ElTableColumn>

      <ElTableColumn prop="issueType" label="问题类型" width="110">
        <template #default="{ row }: { row: DispositionAuditItem }">
          <ElTag :type="ISSUE_TYPE_TAGS[row.issueType]" size="small">
            {{ row.issueType }}
          </ElTag>
        </template>
      </ElTableColumn>

      <ElTableColumn prop="risk" label="风险等级" width="100" sortable :sort-method="sortByRisk">
        <template #default="{ row }: { row: DispositionAuditItem }">
          <ElTag :type="RISK_TAGS[row.risk]" size="small" effect="dark">
            {{ RISK_LABELS[row.risk] }}
          </ElTag>
        </template>
      </ElTableColumn>

      <template #empty>
        <ElEmpty description="处置动作逻辑合规性检查全部通过" :image-size="48" />
      </template>
    </ElTable>
  </ElCard>
</template>

<script setup lang="ts">
  import { QuestionFilled } from '@element-plus/icons-vue'
  import {
    sortedAuditItems,
    RISK_TAGS,
    RISK_LABELS,
    RISK_ORDER,
    ISSUE_TYPE_TAGS,
    type AuditRisk,
    type DispositionAuditItem
  } from '@/constants/dispositionAudit'

  defineOptions({ name: 'DispositionAuditPanel' })

  const rows = sortedAuditItems()

  const criticalCount = computed(() => rows.filter((r) => r.risk === 'critical').length)

  /** 等级汇总，只显示存在的等级 */
  const riskSummary = computed(() => {
    const order: AuditRisk[] = ['critical', 'high', 'medium', 'low']
    return order
      .map((risk) => ({
        risk,
        label: RISK_LABELS[risk],
        tagType: RISK_TAGS[risk],
        count: rows.filter((r) => r.risk === risk).length
      }))
      .filter((s) => s.count > 0)
  })

  /** 表头排序按风险权重，而非字母序 */
  function sortByRisk(a: DispositionAuditItem, b: DispositionAuditItem) {
    return RISK_ORDER[a.risk] - RISK_ORDER[b.risk]
  }
</script>

<style scoped lang="scss">
  .audit-card {
    :deep(.el-card__header) {
      padding: 12px 16px;
    }
  }
</style>
