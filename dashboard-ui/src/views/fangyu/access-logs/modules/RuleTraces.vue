<template>
  <div class="rule-traces-section">
    <ElCollapse v-model="activeCollapse">
      <ElCollapseItem name="traces">
        <template #title>
          <div class="traces-header">
            <span class="traces-title">
              <i class="icon">🔍</i>
              规则条件命中明细
            </span>
            <div class="traces-badges">
              <ElTag v-if="traces.length > 0" type="success" size="small" effect="dark">
                {{ traces.length }} 条
              </ElTag>
              <ElTag v-else-if="loaded" type="info" size="small" effect="plain">
                暂无数据
              </ElTag>
              <ElTag type="warning" size="small" effect="plain">
                <i class="el-icon-time"></i>
                保留 7 天
              </ElTag>
            </div>
          </div>
        </template>
        
        <div v-loading="loading" class="traces-content" element-loading-text="加载规则明细中...">
          <!-- 有数据 -->
          <template v-if="traces.length > 0">
            <div
              v-for="(trace, idx) in groupedTraces"
              :key="idx"
              class="trace-group"
            >
              <!-- 规则组头部 -->
              <div class="trace-group-header">
                <div class="rule-info">
                  <span class="rule-badge">#{{ trace.ruleId }}</span>
                  <span v-if="trace.ruleName" class="rule-name">{{ trace.ruleName }}</span>
                </div>
                <div class="rule-stats">
                  <span class="stat-item matched">
                    ✓ {{ trace.matchedCount }}
                  </span>
                  <span class="stat-item unmatched">
                    ✗ {{ trace.unmatchedCount }}
                  </span>
                </div>
              </div>

              <!-- 条件列表 -->
              <div class="conditions-list">
                <div
                  v-for="(condition, cidx) in trace.conditions"
                  :key="cidx"
                  class="condition-item"
                  :class="{ matched: condition.matched, unmatched: !condition.matched }"
                >
                  <div class="condition-status">
                    <i :class="condition.matched ? 'icon-check' : 'icon-cross'">
                      {{ condition.matched ? '✓' : '✗' }}
                    </i>
                  </div>
                  <div class="condition-content">
                    <div class="condition-field">
                      <ElTag size="small" effect="plain" class="field-tag">
                        {{ condition.field }}
                      </ElTag>
                      <span class="operator">{{ getOperatorLabel(condition.op) }}</span>
                    </div>
                    <div class="condition-values">
                      <div class="value-item expected">
                        <span class="value-label">期望</span>
                        <ElText code class="value-content">{{ condition.expected }}</ElText>
                      </div>
                      <i class="arrow">→</i>
                      <div class="value-item actual">
                        <span class="value-label">实际</span>
                        <ElText code class="value-content">{{ condition.actual }}</ElText>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- 空状态 -->
          <ElEmpty 
            v-else-if="loaded" 
            description="该请求无规则条件明细，或数据已过期（保留期 7 天）" 
            :image-size="100"
          >
            <template #image>
              <div class="empty-icon">📋</div>
            </template>
          </ElEmpty>
        </div>
      </ElCollapseItem>
    </ElCollapse>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref } from 'vue'
  import { OPERATOR_LABELS } from '@/constants/accessLogDetail'

  interface Props {
    traces: Api.Fangyu.DecisionTrace[]
    loading: boolean
    loaded: boolean
  }

  const props = defineProps<Props>()

  const activeCollapse = ref<string[]>([])

  /** 按规则分组的 traces */
  interface GroupedTrace {
    ruleId: number
    ruleName: string | null
    matchedCount: number
    unmatchedCount: number
    conditions: Api.Fangyu.DecisionTrace[]
  }

  const groupedTraces = computed<GroupedTrace[]>(() => {
    const groups = new Map<number, GroupedTrace>()
    
    props.traces.forEach(trace => {
      if (!groups.has(trace.rule_id)) {
        groups.set(trace.rule_id, {
          ruleId: trace.rule_id,
          ruleName: trace.rule_name,
          matchedCount: 0,
          unmatchedCount: 0,
          conditions: []
        })
      }
      
      const group = groups.get(trace.rule_id)!
      group.conditions.push(trace)
      
      if (trace.matched) {
        group.matchedCount++
      } else {
        group.unmatchedCount++
      }
    })
    
    return Array.from(groups.values())
  })

  /** 获取操作符显示名称 */
  function getOperatorLabel(op: string): string {
    return OPERATOR_LABELS[op] || op
  }
</script>

<style scoped lang="scss">
.rule-traces-section {
  margin-top: 16px;
}

/* ── 折叠面板头部 ── */
.traces-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 12px;
}

.traces-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  
  .icon {
    font-size: 16px;
  }
}

.traces-badges {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── 内容区域 ── */
.traces-content {
  padding: 16px 0;
  min-height: 100px;
}

/* ── 规则组 ── */
.trace-group {
  margin-bottom: 20px;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  overflow: hidden;
  background: #ffffff;
  transition: all 0.2s;

  &:hover {
    border-color: #c0c4cc;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  }

  &:last-child {
    margin-bottom: 0;
  }
}

/* ── 规则组头部 ── */
.trace-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f5f7fa 0%, #f0f2f5 100%);
  border-bottom: 1px solid #e4e7ed;
}

.rule-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.rule-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #409eff;
  background: rgba(64, 158, 255, 0.1);
  border: 1px solid rgba(64, 158, 255, 0.3);
  border-radius: 12px;
  font-family: 'SF Mono', 'Cascadia Code', Consolas, monospace;
}

.rule-name {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
}

.rule-stats {
  display: flex;
  align-items: center;
  gap: 12px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  
  &.matched {
    color: #67c23a;
  }
  
  &.unmatched {
    color: #f56c6c;
  }
}

/* ── 条件列表 ── */
.conditions-list {
  padding: 4px;
}

.condition-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  margin: 4px;
  border-radius: 6px;
  border: 1px solid transparent;
  transition: all 0.2s;

  &.matched {
    background: linear-gradient(135deg, #f0f9ff 0%, #e6f7ff 100%);
    border-left: 3px solid #67c23a;
    
    &:hover {
      background: linear-gradient(135deg, #e6f7ff 0%, #d9f0ff 100%);
      border-color: #67c23a;
    }
  }

  &.unmatched {
    background: linear-gradient(135deg, #fef0f0 0%, #fde2e2 100%);
    border-left: 3px solid #f56c6c;
    
    &:hover {
      background: linear-gradient(135deg, #fde2e2 0%, #fcd5d5 100%);
      border-color: #f56c6c;
    }
  }
}

.condition-status {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 14px;
  font-weight: bold;
  
  .icon-check {
    color: #67c23a;
  }
  
  .icon-cross {
    color: #f56c6c;
  }
}

.condition-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.condition-field {
  display: flex;
  align-items: center;
  gap: 8px;
}

.field-tag {
  font-family: 'SF Mono', 'Cascadia Code', Consolas, monospace;
  font-weight: 500;
}

.operator {
  font-size: 12px;
  font-weight: 500;
  color: #909399;
  padding: 2px 8px;
  background: #f5f7fa;
  border-radius: 4px;
}

.condition-values {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.value-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 300px;
}

.value-label {
  font-size: 11px;
  color: #909399;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.value-content {
  font-size: 12px;
  word-break: break-all;
  line-height: 1.5;
}

.arrow {
  color: #c0c4cc;
  font-size: 16px;
  font-weight: bold;
  align-self: center;
  margin-top: 10px;
}

/* ── 空状态 ── */
.empty-icon {
  font-size: 64px;
  opacity: 0.5;
}

:deep(.el-collapse-item__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-radius: 6px;
  transition: all 0.2s;

  &:hover {
    background: #f5f7fa;
  }
}

:deep(.el-collapse-item__wrap) {
  border: none;
}

:deep(.el-collapse-item__content) {
  padding: 0;
}
</style>
