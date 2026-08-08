<template>
  <ElDrawer
    v-model="showDrawer"
    :title="drawerTitle"
    size="900px"
    direction="rtl"
    destroy-on-close
    class="log-detail-drawer"
  >
    <div v-loading="loading" class="drawer-body" element-loading-text="加载详情中...">
      <template v-if="detail">
        <!-- ── 顶部摘要卡片 ── -->
        <div class="summary-card">
          <div class="summary-row">
            <div class="summary-item">
              <span class="label">裁决</span>
              <ElTag :type="VERDICT_TAGS[detail.verdict || '']" size="large" effect="dark" round>
                {{ VERDICT_LABELS[detail.verdict || ''] || detail.verdict || '-' }}
              </ElTag>
            </div>
            <div class="summary-item">
              <span class="label">机制</span>
              <ElTag :type="MECHANISM_TAGS[detail.mechanism || '']" size="large" round>
                {{ MECHANISM_LABELS[detail.mechanism || ''] || detail.mechanism || '-' }}
              </ElTag>
            </div>
            <div class="summary-item">
              <span class="label">来源</span>
              <span class="value">{{ DECIDED_BY_LABELS[detail.decided_by || ''] || detail.decided_by || '-' }}</span>
            </div>
          </div>
          <div class="summary-row">
            <div class="summary-item">
              <span class="label">评分</span>
              <span class="value score" :class="getScoreClass(detail.score)">
                {{ detail.score ?? '-' }}
              </span>
            </div>
            <div class="summary-item">
              <span class="label">耗时</span>
              <span class="value">{{ formatDuration(detail.decision_cost_ms) }}</span>
            </div>
            <div class="summary-item">
              <span class="label">时间</span>
              <span class="value">{{ formatLogTime(detail.occurred_at) }}</span>
            </div>
          </div>
        </div>

        <!-- ── Tabs ── -->
        <ElTabs v-model="activeTab" class="detail-tabs" @tab-change="handleTabChange">
          <!-- Tab 1: 请求概览 -->
          <ElTabPane label="请求概览" name="meta">
            <div class="tab-content">
              <SectionTitle icon="📝">请求信息</SectionTitle>
              <ElDescriptions :column="2" border size="default">
                <ElDescriptionsItem label="Request ID" :span="2">
                  <ElText type="primary" tag="code">{{ detail.request_id || '-' }}</ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="请求路径" :span="2">
                  <a v-if="detail.host && detail.path" :href="getFullUrl(detail)" target="_blank" class="link">
                    {{ detail.path }}
                  </a>
                  <span v-else>{{ detail.path || '-' }}</span>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="来路 Referer" :span="2">
                  <ElText class="text-wrap">{{ detail.referer || '-' }}</ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="设备指纹" :span="2">
                  <ElText type="primary" tag="code">{{ detail.fingerprint || '-' }}</ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="客户端语言">
                  {{ detail.accept_language || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="接入方式">
                  <ElTag v-if="detail.ingress" size="small">{{ detail.ingress }}</ElTag>
                  <span v-else>-</span>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="Evercookie 复活">
                  <ElTag v-if="detail.evercookie_restore" type="danger" size="small">是</ElTag>
                  <span v-else class="text-secondary">否</span>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="是否爬虫">
                  <ElTag v-if="detail.is_bot" type="warning" size="small">
                    {{ detail.crawler_vendor || detail.crawler_category || 'bot' }}
                  </ElTag>
                  <span v-else class="text-secondary">否</span>
                </ElDescriptionsItem>
              </ElDescriptions>

              <SectionTitle icon="💻" class="mt-4">访客设备</SectionTitle>
              <ElDescriptions :column="2" border size="default">
                <ElDescriptionsItem label="设备类型">
                  {{ detail.device_type || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="操作系统">
                  {{ detail.os || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="浏览器">
                  {{ detail.browser || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="客户端 IP">
                  <ElText type="primary" tag="code">{{ detail.ip || '-' }}</ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="User-Agent" :span="2">
                  <ElText class="text-wrap text-small">{{ detail.user_agent || '-' }}</ElText>
                </ElDescriptionsItem>
              </ElDescriptions>
            </div>
          </ElTabPane>

          <!-- Tab 2: 决策链路 -->
          <ElTabPane label="决策链路" name="decision">
            <div class="tab-content">
              <!-- 决策流水线 -->
              <SectionTitle icon="🔄">决策流水线</SectionTitle>
              <div class="pipeline">
                <div
                  v-for="(stage, idx) in PIPELINE_STAGES"
                  :key="stage.key"
                  class="pipeline-node"
                  :class="{ active: stage.key === detail.stage }"
                >
                  <div class="node-icon">{{ stage.icon }}</div>
                  <div class="node-label">{{ stage.label }}</div>
                  <div v-if="idx < PIPELINE_STAGES.length - 1" class="node-connector"></div>
                </div>
              </div>

              <SectionTitle icon="⚙️" class="mt-4">决策详情</SectionTitle>
              <ElDescriptions :column="2" border size="default">
                <ElDescriptionsItem label="处置来源">
                  {{ DECIDED_BY_LABELS[detail.decided_by || ''] || detail.decided_by || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="命中阶段">
                  {{ detail.stage || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="命中规则 ID">
                  <ElTag v-if="detail.rule_id" type="primary" size="small">#{{ detail.rule_id }}</ElTag>
                  <span v-else>-</span>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="风险评分">
                  <ElText :type="getScoreTextType(detail.score)" strong>
                    {{ detail.score ?? '-' }}
                  </ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="原始原因" :span="2">
                  <ElText class="text-wrap">{{ detail.reason || '-' }}</ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="决策耗时">
                  {{ formatDuration(detail.decision_cost_ms) }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="HTTP 状态">
                  <ElTag :type="getHttpStatusType(detail.http_status)" size="small">
                    {{ detail.http_status || '-' }}
                  </ElTag>
                </ElDescriptionsItem>
              </ElDescriptions>

              <!-- 评分明细 -->
              <template v-if="detail.scorer_scores && Object.keys(detail.scorer_scores).length > 0">
                <SectionTitle icon="📊" class="mt-4">评分明细</SectionTitle>
                <div class="scorer-grid">
                  <div
                    v-for="(score, name) in detail.scorer_scores"
                    :key="name"
                    class="scorer-card"
                  >
                    <div class="scorer-name">{{ SCORER_LABELS[name] || name }}</div>
                    <div class="scorer-value" :class="getScoreClass(score)">
                      {{ score }}
                    </div>
                  </div>
                </div>
              </template>

              <!-- 影子规则 -->
              <template v-if="detail.shadow_rule_ids?.length">
                <SectionTitle icon="👻" class="mt-4">影子规则</SectionTitle>
                <div class="shadow-rules">
                  <ElTag
                    v-for="id in detail.shadow_rule_ids"
                    :key="id"
                    type="info"
                    size="small"
                    effect="plain"
                  >
                    #{{ id }}
                  </ElTag>
                </div>
              </template>

              <!-- 规则命中明细 -->
              <RuleTraces
                :traces="traces"
                :loading="tracesLoading"
                :loaded="tracesLoaded"
              />
            </div>
          </ElTabPane>

          <!-- Tab 3: 行为分析 -->
          <ElTabPane label="行为分析" name="behavior">
            <div class="tab-content">
              <div class="behavior-cards">
                <div class="behavior-card" :class="detail.is_bot ? 'danger' : 'normal'">
                  <div class="card-icon">🤖</div>
                  <div class="card-label">爬虫识别</div>
                  <div class="card-value">
                    {{ detail.is_bot ? (detail.crawler_vendor || detail.crawler_category || '是') : '否' }}
                  </div>
                </div>
                <div class="behavior-card" :class="detail.evercookie_restore ? 'danger' : 'normal'">
                  <div class="card-icon">🍪</div>
                  <div class="card-label">Evercookie 复活</div>
                  <div class="card-value">{{ detail.evercookie_restore ? '检测到' : '未检测' }}</div>
                </div>
                <div class="behavior-card" :class="(detail.is_vpn || detail.is_proxy) ? 'warning' : 'normal'">
                  <div class="card-icon">🌐</div>
                  <div class="card-label">匿名代理</div>
                  <div class="card-value">
                    <span v-if="detail.is_vpn">VPN</span>
                    <span v-if="detail.is_proxy">代理</span>
                    <span v-if="!detail.is_vpn && !detail.is_proxy">否</span>
                  </div>
                </div>
                <div class="behavior-card" :class="getScoreCardClass(detail.score)">
                  <div class="card-icon">📊</div>
                  <div class="card-label">风险评分</div>
                  <div class="card-value score" :class="getScoreClass(detail.score)">
                    {{ detail.score ?? '-' }}
                  </div>
                </div>
              </div>

              <SectionTitle icon="📡" class="mt-4">信号明细</SectionTitle>
              <ElDescriptions :column="2" border size="default">
                <ElDescriptionsItem label="访问来源">
                  {{ detail.referer || '直接访问' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="IP 类型">
                  <ElTag v-if="detail.ip_type" size="small">{{ detail.ip_type }}</ElTag>
                  <span v-else>-</span>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="连接类型">
                  <ElTag
                    v-if="detail.connection_type"
                    :type="CONNECTION_TYPE_TAGS[detail.connection_type]"
                    size="small"
                  >
                    {{ detail.connection_type }}
                  </ElTag>
                  <span v-else>-</span>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="爬虫类别">
                  {{ detail.crawler_category || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="爬虫厂商">
                  {{ detail.crawler_vendor || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="设备指纹">
                  <ElText type="primary" tag="code">{{ detail.fingerprint || '-' }}</ElText>
                </ElDescriptionsItem>
              </ElDescriptions>
            </div>
          </ElTabPane>

          <!-- Tab 4: IP 画像 -->
          <ElTabPane label="IP 画像" name="ip">
            <div class="tab-content">
              <SectionTitle icon="🌍">IP 信息</SectionTitle>
              <ElDescriptions :column="2" border size="default">
                <ElDescriptionsItem label="IP 地址">
                  <ElText type="primary" tag="code">{{ detail.ip || '-' }}</ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="IP 类型">
                  {{ detail.ip_type || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="国家/地区">
                  {{ detail.country || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="ASN">
                  {{ detail.asn ? `AS${detail.asn}` : '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="ASN 组织">
                  {{ detail.asn_org || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="网络类型">
                  <ElTag
                    v-if="detail.connection_type"
                    :type="CONNECTION_TYPE_TAGS[detail.connection_type]"
                    size="small"
                  >
                    {{ detail.connection_type }}
                  </ElTag>
                  <span v-else>-</span>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="VPN">
                  <ElTag :type="detail.is_vpn ? 'warning' : 'success'" size="small">
                    {{ detail.is_vpn ? '是' : '否' }}
                  </ElTag>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="代理">
                  <ElTag :type="detail.is_proxy ? 'warning' : 'success'" size="small">
                    {{ detail.is_proxy ? '是' : '否' }}
                  </ElTag>
                </ElDescriptionsItem>
              </ElDescriptions>
            </div>
          </ElTabPane>

          <!-- Tab 5: 快速操作 -->
          <ElTabPane label="快速操作" name="actions">
            <div class="tab-content">
              <ElAlert type="info" :closable="false" class="mb-4">
                对该请求的 IP 或指纹执行快速处置。封禁操作会立即写入 Redis 黑名单并在下次决策中生效。
              </ElAlert>
              <ElForm label-width="100px">
                <ElFormItem label="封禁时长">
                  <ElSelect v-model="blockDuration" style="width:220px">
                    <ElOption label="1 小时" :value="3600" />
                    <ElOption label="24 小时" :value="86400" />
                    <ElOption label="7 天" :value="604800" />
                    <ElOption label="永久" :value="-1" />
                  </ElSelect>
                </ElFormItem>
                <ElFormItem label="备注">
                  <ElInput
                    v-model="blockReason"
                    placeholder="拉黑原因（可选）"
                    style="width:400px"
                  />
                </ElFormItem>
              </ElForm>
              <ElSpace wrap :size="12">
                <ElButton
                  type="danger"
                  :loading="blocking"
                  :disabled="!detail.ip"
                  @click="blockIp"
                >
                  拉黑 IP {{ detail.ip }}
                </ElButton>
                <ElButton
                  type="warning"
                  :loading="blocking"
                  :disabled="!detail.fingerprint"
                  @click="blockFingerprint"
                >
                  拉黑指纹
                </ElButton>
                <ElButton @click="exportJson">导出 JSON</ElButton>
              </ElSpace>
            </div>
          </ElTabPane>
        </ElTabs>
      </template>

      <ElEmpty v-else-if="!loading" description="未找到记录，该日志可能已超出保留期限" />
    </div>
  </ElDrawer>
</template>

<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { fetchBlacklistIps, fetchBlacklistFingerprints } from '@/api/blacklist'
  import { VERDICT_TAGS, MECHANISM_TAGS, DECIDED_BY_LABELS } from '@/constants/disposition'
  import { CONNECTION_TYPE_TAGS } from '@/constants/fangyu'
  import {
    VERDICT_LABELS,
    MECHANISM_LABELS,
    SCORER_LABELS,
    PIPELINE_STAGES
  } from '@/constants/accessLogDetail'
  import {
    formatLogTime,
    formatDuration,
    getScoreClass,
    getScoreCardClass,
    getScoreTextType,
    getHttpStatusType
  } from '@/utils/accessLogFormatter'
  import { useAccessLogDetail } from '@/composables/useAccessLogDetail'
  import RuleTraces from './RuleTraces.vue'
  import SectionTitle from './SectionTitle.vue'

  interface Props {
    visible: boolean
    requestId: string
    siteId?: number
  }

  interface Emits {
    (e: 'update:visible', v: boolean): void
  }

  const props = defineProps<Props>()
  const emit = defineEmits<Emits>()

  const showDrawer = computed({
    get: () => props.visible,
    set: (v) => emit('update:visible', v)
  })

  const drawerTitle = computed(() => {
    return props.requestId ? `请求详情 — ${props.requestId}` : '请求详情'
  })

  const activeTab = ref('meta')
  const blocking = ref(false)
  const blockDuration = ref(3600)
  const blockReason = ref('')

  // 使用 Composable Hook
  const {
    loading,
    detail,
    traces,
    tracesLoading,
    tracesLoaded,
    loadTraces
  } = useAccessLogDetail(props)

  /** 处理 Tab 切换 */
  function handleTabChange(tabName: string | number) {
    // 切换到决策链路时，加载规则明细
    if (tabName === 'decision' && !tracesLoaded.value) {
      loadTraces()
    }
  }

  /** 获取完整 URL */
  function getFullUrl(log: Api.Fangyu.AccessLog): string {
    return `https://${log.host}${log.path || '/'}`
  }

  /** 拉黑 IP */
  async function blockIp() {
    if (!detail.value?.ip) return

    try {
      await ElMessageBox.confirm(
        `确定要拉黑 IP ${detail.value.ip} 吗？`,
        '确认操作',
        { type: 'warning' }
      )

      blocking.value = true
      await fetchBlacklistIps({
        ips: [detail.value.ip],
        duration_seconds: blockDuration.value,
        reason: blockReason.value || '手动拉黑'
      })
      ElMessage.success('IP 已加入黑名单')
    } catch (err: any) {
      if (err !== 'cancel') {
        ElMessage.error(err?.message || '操作失败')
      }
    } finally {
      blocking.value = false
    }
  }

  /** 拉黑指纹 */
  async function blockFingerprint() {
    if (!detail.value?.fingerprint) return

    try {
      await ElMessageBox.confirm(
        '确定要拉黑该设备指纹吗？',
        '确认操作',
        { type: 'warning' }
      )

      blocking.value = true
      await fetchBlacklistFingerprints({
        fingerprints: [detail.value.fingerprint],
        duration_seconds: blockDuration.value,
        reason: blockReason.value || '手动拉黑'
      })
      ElMessage.success('指纹已加入黑名单')
    } catch (err: any) {
      if (err !== 'cancel') {
        ElMessage.error(err?.message || '操作失败')
      }
    } finally {
      blocking.value = false
    }
  }

  /** 导出 JSON */
  function exportJson() {
    if (!detail.value) return

    const dataStr = JSON.stringify(detail.value, null, 2)
    const blob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `access-log-${props.requestId}.json`
    a.click()
    URL.revokeObjectURL(url)
  }
</script>

<style scoped lang="scss">
/* ======================================
   访问日志详情抽屉 - 现代化UI设计
   ====================================== */

.log-detail-drawer {
  :deep(.el-drawer__header) {
    padding: 20px 24px;
    margin-bottom: 0;
    border-bottom: 1px solid #e4e7ed;
    background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  }

  :deep(.el-drawer__title) {
    font-size: 18px;
    font-weight: 600;
    color: #303133;
  }

  :deep(.el-drawer__body) {
    padding: 0;
  }
}

.drawer-body {
  padding: 20px 24px;
  min-height: calc(100vh - 80px);
}

/* ── 顶部摘要卡片 ── */
.summary-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px;
  margin-bottom: 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);
}

.summary-row {
  display: flex;
  align-items: center;
  gap: 24px;
  flex-wrap: wrap;
}

.summary-item {
  display: flex;
  align-items: center;
  gap: 8px;
  
  .label {
    font-size: 13px;
    color: rgba(255, 255, 255, 0.8);
    font-weight: 500;
  }
  
  .value {
    font-size: 15px;
    font-weight: 600;
    color: #ffffff;
    
    &.score {
      font-size: 18px;
      font-family: 'SF Mono', 'Cascadia Code', Consolas, monospace;
      padding: 2px 12px;
      border-radius: 20px;
      background: rgba(255, 255, 255, 0.2);
      
      &.score-danger {
        color: #f56c6c;
        background: rgba(255, 255, 255, 0.95);
      }
      
      &.score-warning {
        color: #e6a23c;
        background: rgba(255, 255, 255, 0.95);
      }
      
      &.score-ok {
        color: #67c23a;
        background: rgba(255, 255, 255, 0.95);
      }
    }
  }
}

/* ── Tabs ── */
.detail-tabs {
  :deep(.el-tabs__header) {
    margin-bottom: 20px;
    background: #fafafa;
    padding: 0 12px;
    border-radius: 8px;
  }

  :deep(.el-tabs__nav-wrap::after) {
    display: none;
  }

  :deep(.el-tabs__item) {
    padding: 0 20px;
    height: 44px;
    line-height: 44px;
    font-weight: 500;
    color: #606266;
    transition: all 0.3s;

    &:hover {
      color: #409eff;
    }

    &.is-active {
      color: #409eff;
      font-weight: 600;
    }
  }

  :deep(.el-tabs__active-bar) {
    height: 3px;
    border-radius: 2px;
    background: linear-gradient(90deg, #409eff 0%, #667eea 100%);
  }
}

.tab-content {
  padding: 0 4px;
}

/* ── 决策流水线 ── */
.pipeline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px 12px;
  background: linear-gradient(135deg, #f5f7fa 0%, #f0f2f5 100%);
  border-radius: 12px;
  margin-bottom: 20px;
  overflow-x: auto;
}

.pipeline-node {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 80px;
  transition: all 0.3s;

  .node-icon {
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    background: #ffffff;
    border: 2px solid #e4e7ed;
    border-radius: 50%;
    transition: all 0.3s;
    z-index: 2;
  }

  .node-label {
    font-size: 12px;
    color: #909399;
    text-align: center;
    font-weight: 500;
    transition: all 0.3s;
  }

  .node-connector {
    position: absolute;
    top: 24px;
    left: 50%;
    width: 100%;
    height: 2px;
    background: #e4e7ed;
    z-index: 1;
  }

  &.active {
    .node-icon {
      border-color: #409eff;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
      transform: scale(1.1);
    }

    .node-label {
      color: #409eff;
      font-weight: 600;
    }
  }
}

/* ── 评分明细网格 ── */
.scorer-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.scorer-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  transition: all 0.3s;

  &:hover {
    border-color: #409eff;
    box-shadow: 0 2px 8px rgba(64, 158, 255, 0.1);
    transform: translateY(-2px);
  }

  .scorer-name {
    font-size: 12px;
    color: #909399;
    text-align: center;
  }

  .scorer-value {
    font-size: 20px;
    font-weight: 700;
    font-family: 'SF Mono', 'Cascadia Code', Consolas, monospace;

    &.score-danger {
      color: #f56c6c;
    }

    &.score-warning {
      color: #e6a23c;
    }

    &.score-ok {
      color: #67c23a;
    }
  }
}

/* ── 影子规则 ── */
.shadow-rules {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

/* ── 行为卡片 ── */
.behavior-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.behavior-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px 16px;
  border-radius: 12px;
  border: 2px solid #e4e7ed;
  background: #ffffff;
  transition: all 0.3s;

  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  }

  &.normal {
    border-color: #67c23a;
    background: linear-gradient(135deg, #f0f9ff 0%, #e6f7ff 100%);
  }

  &.warning {
    border-color: #e6a23c;
    background: linear-gradient(135deg, #fef5e7 0%, #fdebd0 100%);
  }

  &.danger {
    border-color: #f56c6c;
    background: linear-gradient(135deg, #fef0f0 0%, #fde2e2 100%);
  }

  .card-icon {
    font-size: 32px;
  }

  .card-label {
    font-size: 13px;
    color: #909399;
    font-weight: 500;
  }

  .card-value {
    font-size: 16px;
    font-weight: 600;
    color: #303133;
    text-align: center;

    &.score {
      font-size: 24px;
      font-family: 'SF Mono', 'Cascadia Code', Consolas, monospace;
    }
  }
}

/* ── 描述列表优化 ── */
:deep(.el-descriptions) {
  border-radius: 8px;
  overflow: hidden;

  .el-descriptions__label {
    font-weight: 500;
    color: #606266;
    background: #fafafa;
  }

  .el-descriptions__content {
    color: #303133;
  }
}

/* ── 工具类 ── */
.link {
  color: #409eff;
  text-decoration: none;
  word-break: break-all;

  &:hover {
    text-decoration: underline;
  }
}

.text-wrap {
  word-break: break-all;
  line-height: 1.6;
}

.text-small {
  font-size: 12px;
}

.text-secondary {
  color: #909399;
}

.mt-4 {
  margin-top: 16px;
}

.mb-4 {
  margin-bottom: 16px;
}

.score-danger {
  color: #f56c6c;
  font-weight: 700;
}

.score-warning {
  color: #e6a23c;
  font-weight: 700;
}

.score-ok {
  color: #67c23a;
  font-weight: 600;
}
</style>
