<template>
  <ElDrawer
    v-model="showDrawer"
    :title="`请求详情 — ${requestId || '...'}`"
    size="860px"
    direction="rtl"
    destroy-on-close
  >
    <div v-loading="loading" class="drawer-body">
      <template v-if="detail">

        <!-- ── 顶部摘要卡片 ── -->
        <div class="summary-bar">
          <div class="summary-item">
            <span class="summary-label">裁决</span>
            <ElTag :type="VERDICT_TAGS[detail.verdict || ''] || 'info'" size="small" effect="dark">
              {{ VERDICT_LABELS[detail.verdict || ''] || detail.verdict || '-' }}
            </ElTag>
          </div>
          <div class="summary-item">
            <span class="summary-label">机制</span>
            <ElTag :type="MECHANISM_TAGS[detail.mechanism || ''] || 'info'" size="small">
              {{ MECHANISM_LABELS[detail.mechanism || ''] || detail.mechanism || '-' }}
            </ElTag>
          </div>
          <div class="summary-item">
            <span class="summary-label">来源</span>
            <span class="summary-val">{{ DECIDED_BY_LABELS[detail.decided_by || ''] || detail.decided_by || '-' }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">评分</span>
            <span class="summary-val" :class="scoreClass(detail.score)">{{ detail.score ?? '-' }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">耗时</span>
            <span class="summary-val">{{ detail.decision_cost_ms != null ? `${detail.decision_cost_ms}ms` : '-' }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">时间</span>
            <span class="summary-val">{{ fmtTime(detail.occurred_at) }}</span>
          </div>
        </div>

        <ElTabs v-model="activeTab">

          <!-- ── Tab 1: 请求概览 ── -->
          <ElTabPane label="请求概览" name="meta">
            <div class="single-col">
              <!-- 请求信息 -->
              <div class="section-title">请求信息</div>
              <ElDescriptions :column="2" border size="small" label-min-width="100px">
                <ElDescriptionsItem label="Request ID" :span="2">
                  <ElText code class="text-xs">{{ detail.request_id || '-' }}</ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="请求路径" :span="2">
                  <a v-if="detail.path" :href="detail.path.startsWith('http') ? detail.path : `https://${detail.path}`" target="_blank" class="link-text">{{ detail.path }}</a>
                  <span v-else>-</span>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="来路 Referer" :span="2">
                  <ElText class="text-xs" style="word-break:break-all">{{ detail.referer || '-' }}</ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="设备指纹" :span="2">
                  <ElText code class="text-xs">{{ detail.fingerprint || '-' }}</ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="客户端语言" :span="2">
                  {{ detail.accept_language || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="Evercookie 复活">
                  <ElTag v-if="detail.evercookie_restore" type="danger" size="small">是</ElTag>
                  <span v-else class="text-g-400">否</span>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="是否爬虫">
                  <ElTag v-if="detail.is_bot" type="warning" size="small">
                    {{ detail.crawler_vendor || detail.crawler_category || 'bot' }}
                  </ElTag>
                  <span v-else class="text-g-400">否</span>
                </ElDescriptionsItem>
              </ElDescriptions>

              <!-- 访客设备 -->
              <div class="section-title mt-4">访客设备</div>
              <ElDescriptions :column="2" border size="small" label-min-width="100px">
                <ElDescriptionsItem label="设备类型">{{ detail.device_type || '-' }}</ElDescriptionsItem>
                <ElDescriptionsItem label="操作系统">{{ detail.os || '-' }}</ElDescriptionsItem>
                <ElDescriptionsItem label="浏览器">{{ detail.browser || '-' }}</ElDescriptionsItem>
                <ElDescriptionsItem label="客户端 IP">
                  <ElText code>{{ detail.ip || '-' }}</ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="User-Agent" :span="2">
                  <ElText class="text-xs" style="word-break:break-all">{{ detail.user_agent || '-' }}</ElText>
                </ElDescriptionsItem>
              </ElDescriptions>
            </div>
          </ElTabPane>

          <!-- ── Tab 2: 决策链路 ── -->
          <ElTabPane label="决策链路" name="decision">
            <!-- 决策流水线时序：各阶段可视化 -->
            <div class="pipeline-flow">
              <div
                v-for="stage in pipelineStages"
                :key="stage.key"
                class="pipeline-step"
                :class="{ 'pipeline-step--active': stage.key === detail.stage }"
              >
                <div class="pipeline-dot" :class="stage.key === detail.stage ? 'dot-active' : 'dot-idle'" />
                <div class="pipeline-label">{{ stage.label }}</div>
              </div>
            </div>

            <ElDescriptions :column="2" border size="small" label-min-width="100px" class="mt-3">
              <ElDescriptionsItem label="处置来源">
                {{ DECIDED_BY_LABELS[detail.decided_by || ''] || detail.decided_by || '-' }}
              </ElDescriptionsItem>
              <ElDescriptionsItem label="命中阶段">{{ detail.stage || '-' }}</ElDescriptionsItem>
              <ElDescriptionsItem label="命中规则 ID">{{ detail.rule_id ?? '-' }}</ElDescriptionsItem>
              <ElDescriptionsItem label="风险评分">
                <ElText :type="scoreTextType(detail.score)" strong>{{ detail.score ?? '-' }}</ElText>
              </ElDescriptionsItem>
              <ElDescriptionsItem label="原始原因" :span="2">
                <ElText class="text-xs reason-text">{{ detail.reason || '-' }}</ElText>
              </ElDescriptionsItem>
              <ElDescriptionsItem label="决策耗时">
                {{ detail.decision_cost_ms != null ? `${detail.decision_cost_ms} ms` : '-' }}
              </ElDescriptionsItem>
            </ElDescriptions>

            <!-- 评分明细 -->
            <template v-if="detail.scorer_scores && Object.keys(detail.scorer_scores).length > 0">
              <div class="section-title mt-4">评分明细</div>
              <ElDescriptions :column="2" border size="small" label-min-width="120px">
                <ElDescriptionsItem label="总分">
                  <ElText :type="scoreTextType(detail.score)" strong>{{ detail.score ?? 0 }} 分</ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="阈值说明">
                  <span class="text-xs text-g-500">&lt; 30 可信，30-74 可疑，≥ 75 敌对</span>
                </ElDescriptionsItem>
                <ElDescriptionsItem
                  v-for="(score, name) in detail.scorer_scores"
                  :key="name"
                  :label="SCORER_LABELS[name] || name"
                >
                  <ElText :type="scorerTextType(score)">{{ score }} 分</ElText>
                </ElDescriptionsItem>
              </ElDescriptions>
            </template>

            <ElDescriptions :column="2" border size="small" label-min-width="100px" class="mt-3">
              <ElDescriptionsItem label="HTTP 状态">
                <ElTag :type="httpStatusTag(detail.http_status)" size="small">
                  {{ detail.http_status || '-' }}
                </ElTag>
              </ElDescriptionsItem>
              <ElDescriptionsItem label="影子规则" :span="2">
                <template v-if="detail.shadow_rule_ids?.length">
                  <ElTag
                    v-for="id in detail.shadow_rule_ids"
                    :key="id"
                    type="primary"
                    size="small"
                    class="mr-1"
                  >#{{ id }}</ElTag>
                </template>
                <span v-else class="text-g-400">无</span>
              </ElDescriptionsItem>
            </ElDescriptions>
          </ElTabPane>

          <!-- ── Tab 3: 行为分析 ── -->
          <ElTabPane label="行为分析" name="behavior">
            <div class="behavior-section">
              <!-- 访客画像卡片 -->
              <div class="behavior-cards">
                <div class="behavior-card" :class="detail.is_bot ? 'card-danger' : 'card-normal'">
                  <div class="card-icon">🤖</div>
                  <div class="card-label">爬虫识别</div>
                  <div class="card-value">{{ detail.is_bot ? (detail.crawler_vendor || detail.crawler_category || '是') : '否' }}</div>
                </div>
                <div class="behavior-card" :class="detail.evercookie_restore ? 'card-danger' : 'card-normal'">
                  <div class="card-icon">🍪</div>
                  <div class="card-label">Evercookie 复活</div>
                  <div class="card-value">{{ detail.evercookie_restore ? '检测到' : '未检测' }}</div>
                </div>
                <div class="behavior-card" :class="(detail.is_vpn || detail.is_proxy) ? 'card-warn' : 'card-normal'">
                  <div class="card-icon">🌐</div>
                  <div class="card-label">匿名代理</div>
                  <div class="card-value">
                    <span v-if="detail.is_vpn">VPN</span>
                    <span v-if="detail.is_proxy">代理</span>
                    <span v-if="!detail.is_vpn && !detail.is_proxy">否</span>
                  </div>
                </div>
                <div class="behavior-card" :class="scoreCardClass(detail.score)">
                  <div class="card-icon">📊</div>
                  <div class="card-label">风险评分</div>
                  <div class="card-value score-value" :class="scoreClass(detail.score)">
                    {{ detail.score ?? '-' }}
                  </div>
                </div>
              </div>

              <!-- 信号明细 -->
              <div class="section-title mt-4">信号明细</div>
              <ElDescriptions :column="2" border size="small" label-min-width="110px">
                <ElDescriptionsItem label="访问来源">
                  {{ detail.referer || '直接访问' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="IP 类型">
                  <ElTag
                    :type="CONNECTION_TYPE_TAGS[detail.connection_type || ''] || 'info'"
                    size="small"
                  >
                    {{ detail.connection_type || '-' }}
                  </ElTag>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="爬虫类别">
                  {{ detail.crawler_category || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="爬虫厂商">
                  {{ detail.crawler_vendor || '-' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="设备指纹">
                  <ElText code class="text-xs">{{ detail.fingerprint || '-' }}</ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="Repeat Key">
                  <ElText code class="text-xs">{{ detail.repeat_key || '-' }}</ElText>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="Repeat Value">
                  <ElText code class="text-xs">{{ detail.repeat_value || '-' }}</ElText>
                </ElDescriptionsItem>
              </ElDescriptions>
            </div>
          </ElTabPane>

          <!-- ── Tab 4: IP 画像 ── -->
          <ElTabPane label="IP 画像" name="ip">
            <ElDescriptions :column="2" border size="small" label-min-width="110px">
              <ElDescriptionsItem label="IP 地址">
                <ElText code>{{ detail.ip || '-' }}</ElText>
              </ElDescriptionsItem>
              <ElDescriptionsItem label="IP 类型">{{ detail.ip_type || '-' }}</ElDescriptionsItem>
              <ElDescriptionsItem label="国家/地区">{{ detail.country || '-' }}</ElDescriptionsItem>
              <ElDescriptionsItem label="ASN">
                {{ detail.asn ? `AS${detail.asn}` : '-' }}
              </ElDescriptionsItem>
              <ElDescriptionsItem label="网络类型">
                <ElTag
                  v-if="detail.connection_type"
                  :type="CONNECTION_TYPE_TAGS[detail.connection_type] || 'info'"
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
          </ElTabPane>

          <!-- ── Tab 5: 快速操作 ── -->
          <ElTabPane label="快速操作" name="actions">
            <div class="action-section">
              <ElAlert type="info" :closable="false" class="mb-4">
                对该请求的 IP 或指纹执行快速处置。封禁操作会立即写入 Redis 黑名单并在下次决策中生效。
              </ElAlert>
              <ElForm label-width="90px">
                <ElFormItem label="封禁时长">
                  <ElSelect v-model="blockDuration" style="width:200px">
                    <ElOption label="1 小时"  :value="3600"   />
                    <ElOption label="24 小时" :value="86400"  />
                    <ElOption label="7 天"    :value="604800" />
                    <ElOption label="永久"    :value="-1"     />
                  </ElSelect>
                </ElFormItem>
                <ElFormItem label="备注">
                  <ElInput v-model="blockReason" placeholder="拉黑原因（可选）" style="width:300px" />
                </ElFormItem>
              </ElForm>
              <ElSpace wrap>
                <ElButton type="danger" :loading="blocking" :disabled="!detail.ip" @click="blockIp">
                  拉黑 IP {{ detail.ip }}
                </ElButton>
                <ElButton type="warning" :loading="blocking" :disabled="!detail.fingerprint" @click="blockFingerprint">
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
  import { fetchGetAccessLog } from '@/api/logs'
  import { fetchBlacklistIps, fetchBlacklistFingerprints } from '@/api/blacklist'
  import { VERDICT_TAGS, MECHANISM_TAGS, DECIDED_BY_LABELS } from '@/constants/disposition'
  import { CONNECTION_TYPE_TAGS, httpStatusTag } from '@/constants/fangyu'
  import { ElMessage, ElMessageBox } from 'element-plus'

  const VERDICT_LABELS: Record<string, string> = {
    trusted: '放行', suspect: '可疑', hostile: '拦截'
  }
  const MECHANISM_LABELS: Record<string, string> = {
    pass: '放行', serve_alt: '替代内容', redirect: '跳转',
    challenge: '人机挑战', deny: '拒绝', not_found: '假装404'
  }

  /** 评分器名称映射 */
  const SCORER_LABELS: Record<string, string> = {
    ip_reputation: 'IP 声誉',
    proxy: '代理检测',
    user_agent: 'UA 检测',
    interaction: '人机交互',
    device: '设备异常',
    frequency: '访问频率',
    geo: '地理位置'
  }

  /** 决策流水线阶段顺序（用于时序可视化） */
  const pipelineStages = [
    { key: 'allowlist',     label: '白名单' },
    { key: 'threat_intel',  label: '威胁情报' },
    { key: 'hybrid_lookup', label: '混合层查询' },
    { key: 'decision_rule', label: '决策规则' },
    { key: 'scoring',       label: '风险评分' },
    { key: 'default',       label: '兜底策略' },
  ]

  function fmtTime(raw?: string | null): string {
    if (!raw) return '-'
    // ClickHouse 存的是 UTC，aiochclient 返回不带时区的 naive datetime，
    // FastAPI 序列化后无 Z 后缀。若直接交给 new Date 会被当本地时区，
    // 导致东八区多加 8 小时。这里强制补 Z 让浏览器按 UTC 解析。
    const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(raw) ? raw : `${raw}Z`
    const d = new Date(iso)
    if (isNaN(d.getTime())) return raw
    // 转换为本地时区，格式：2024/1/1 16:00:00
    return d.toLocaleString('zh-CN', { hour12: false })
  }

  function scoreClass(score?: number | null): string {
    if (score == null) return ''
    if (score >= 70) return 'score-danger'
    if (score >= 30) return 'score-warning'
    return 'score-ok'
  }

  function scoreCardClass(score?: number | null): string {
    if (score == null) return 'card-normal'
    if (score >= 70) return 'card-danger'
    if (score >= 30) return 'card-warn'
    return 'card-normal'
  }

  interface Props {
    visible:   boolean
    requestId: string
    siteId?:    number
  }
  interface Emits {
    (e: 'update:visible', v: boolean): void
  }

  const props = defineProps<Props>()
  const emit  = defineEmits<Emits>()

  const showDrawer = computed({
    get: () => props.visible,
    set: (v) => emit('update:visible', v),
  })

  const loading    = ref(false)
  const activeTab  = ref('meta')
  const detail     = ref<Api.Fangyu.AccessLog | null>(null)

  const blocking      = ref(false)
  const blockDuration = ref(3600)
  const blockReason   = ref('')

  // 请求序号：防止快速切换记录时先发后至的响应覆盖当前记录
  let loadSeq = 0

  async function loadDetail() {
    if (!props.requestId) return
    const seq = ++loadSeq
    loading.value = true
    detail.value  = null
    try {
      const res = await fetchGetAccessLog(props.requestId, { siteId: props.siteId })
      if (seq !== loadSeq) return
      detail.value = res ?? null
    } catch (err) {
      if (seq !== loadSeq) return
      console.error('加载日志详情失败:', err)
    } finally {
      if (seq === loadSeq) loading.value = false
    }
  }

  // 合并为单个 watch：避免 requestId 与 visible 同时变化时重复发起两次请求
  watch(
    () => [props.requestId, props.visible] as const,
    ([id, visible]) => {
      if (!visible || !id) return
      activeTab.value = 'meta'
      loadDetail()
    }
  )

  function scoreTextType(score?: number | null): '' | 'danger' | 'warning' | 'success' {
    if (score == null) return ''
    if (score >= 70) return 'danger'
    if (score >= 30) return 'warning'
    return 'success'
  }

  function scorerTextType(score?: number | null): '' | 'danger' | 'warning' | 'success' {
    if (score == null || score === 0) return ''
    if (score >= 20) return 'danger'
    if (score >= 10) return 'warning'
    return 'success'
  }

  /** 拉黑前的二次确认：永久拉黑不可自动恢复，必须让用户明确知晓 */
  async function confirmBlock(target: string, label: string): Promise<boolean> {
    const isPermanent = blockDuration.value === 0
    const scope = isPermanent
      ? '永久拉黑（不会自动解除，需手动到封禁管理中移除）'
      : `拉黑 ${blockDuration.value} 秒`
    const ok = await ElMessageBox.confirm(
      `即将对${label} ${target} 执行${scope}。期间其所有请求将被直接阻断，请确认该对象确实为恶意流量。`,
      '确认拉黑',
      {
        confirmButtonText: isPermanent ? '永久拉黑' : '确认拉黑',
        cancelButtonText: '取消',
        type: isPermanent ? 'error' : 'warning'
      }
    ).catch(() => false)
    return Boolean(ok)
  }

  async function blockIp() {
    const ip = detail.value?.ip
    if (!ip) return
    if (!(await confirmBlock(ip, 'IP'))) return
    blocking.value = true
    try {
      await fetchBlacklistIps({
        ips:              [ip],
        duration_seconds: blockDuration.value,
        reason:           blockReason.value || '访问日志快速拉黑',
      })
      ElMessage.success(`IP ${ip} 已拉黑，该地址后续请求将被阻断`)
    } finally { blocking.value = false }
  }

  async function blockFingerprint() {
    const fp = detail.value?.fingerprint
    if (!fp) return
    if (!(await confirmBlock(fp, '设备指纹'))) return
    blocking.value = true
    try {
      await fetchBlacklistFingerprints({
        fingerprints:     [fp],
        duration_seconds: blockDuration.value,
        reason:           blockReason.value || '访问日志快速拉黑',
      })
      ElMessage.success('设备指纹已拉黑，该设备后续请求将被阻断')
    } finally { blocking.value = false }
  }

  function exportJson() {
    const blob = new Blob([JSON.stringify(detail.value, null, 2)], { type: 'application/json' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `access-log-${props.requestId}.json`
    a.click()
    URL.revokeObjectURL(url)
  }
</script>

<style scoped>
.drawer-body { padding: 4px 0; }

/* ── 顶部摘要栏 ── */
.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px 32px;
  padding: 12px 16px;
  background: #f7f8fa;
  border-radius: 6px;
  margin-bottom: 16px;
  align-items: center;
}
.summary-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.summary-label {
  font-size: 12px;
  color: #909399;
}
.summary-val {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}
.score-danger  { color: #f56c6c; font-weight: 700; }
.score-warning { color: #e6a23c; font-weight: 700; }
.score-ok      { color: #67c23a; }

/* ── 请求概览单列 ── */
.single-col { display: flex; flex-direction: column; }

/* ── 请求概览两列（保留备用） ── */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid #409eff;
}
.link-text {
  color: #409eff;
  text-decoration: none;
  font-size: 12px;
  word-break: break-all;
}
.link-text:hover { text-decoration: underline; }

/* ── 决策流水线时序 ── */
.pipeline-flow {
  display: flex;
  align-items: flex-start;
  gap: 0;
  padding: 12px 0 16px;
  overflow-x: auto;
}
.pipeline-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  min-width: 80px;
  position: relative;
}
.pipeline-step:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 7px;
  left: 50%;
  width: 100%;
  height: 2px;
  background: #dcdfe6;
  z-index: 0;
}
.pipeline-step--active .pipeline-dot {
  background: #409eff;
  box-shadow: 0 0 0 4px rgba(64, 158, 255, 0.2);
}
.pipeline-step--active .pipeline-label {
  color: #409eff;
  font-weight: 600;
}
.pipeline-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #dcdfe6;
  position: relative;
  z-index: 1;
}
.dot-active { background: #409eff; }
.dot-idle   { background: #dcdfe6; }
.pipeline-label {
  font-size: 11px;
  color: #909399;
  margin-top: 6px;
  text-align: center;
}
.reason-text {
  word-break: break-all;
  font-size: 12px;
  color: #606266;
}

/* ── 行为分析卡片 ── */
.behavior-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 4px;
}
.behavior-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 16px 12px;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  background: #fff;
  text-align: center;
}
.card-normal { border-color: #e4e7ed; }
.card-danger { border-color: #fbc4c4; background: #fef0f0; }
.card-warn   { border-color: #fcd09a; background: #fdf6ec; }
.card-icon   { font-size: 24px; line-height: 1; }
.card-label  { font-size: 12px; color: #909399; }
.card-value  { font-size: 13px; font-weight: 600; color: #303133; }
.score-value { font-size: 22px; }

/* ── 操作区 ── */
.action-section { padding: 8px 0; }
.mt-3 { margin-top: 12px; }
.mt-4 { margin-top: 16px; }
.mr-1 { margin-right: 4px; }
.mb-4 { margin-bottom: 16px; }
</style>
