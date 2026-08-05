<template>
  <div class="art-full-height">
    <div class="mb-3">
      <h2 class="text-lg font-medium text-g-900">威胁情报</h2>
      <p class="mt-1 text-sm text-g-600">
        分两类：<b>黑名单</b>（IP 威胁 / ASN 情报 / 指纹情报 / 爬虫特征）直接携带风险分参与判定；
        <b>画像</b>（IP 画像 / GeoIP 录入）只标注网络属性，供规则条件引用。
      </p>
    </div>

    <ElCard class="art-table-card threat-intel-card">
      <ArtTableHeader :loading="false" @refresh="refreshAll">
        <template #left>
          <ElSpace wrap>
            <ElButton v-auth="'threat_intel.write'" :loading="syncing" @click="handleSyncRedis">
              同步 Redis
            </ElButton>
          </ElSpace>
        </template>
      </ArtTableHeader>

      <ElTabs v-model="activeTab" class="intel-tabs" @tab-change="onTabChange">
        <!-- ── 总览 ── -->
        <ElTabPane label="总览" name="overview">
          <div v-loading="overviewLoading" class="pane-scroll">
            <ElAlert
              v-if="overview?.health?.profile_missing_total"
              type="warning"
              :closable="false"
              class="mb-3"
            >
              存在 {{ overview.health.profile_missing_total }} 条情报缺少标准画像字段，建议补齐后再用于规则编排。
            </ElAlert>
            <ElRow :gutter="12" class="mb-4">
              <ElCol :span="6" v-for="card in overviewCards" :key="card.label">
                <ElCard shadow="never">
                  <div class="text-xs text-g-500 mb-1">{{ card.label }}</div>
                  <div class="text-2xl font-semibold">{{ card.value }}</div>
                  <div class="text-xs text-g-400 mt-1">{{ card.desc }}</div>
                </ElCard>
              </ElCol>
            </ElRow>
            <ElDescriptions v-if="overview?.counts" title="各类型情报数量" :column="4" border size="small">
              <ElDescriptionsItem
                v-for="(count, type) in overview.counts"
                :key="type"
                :label="String(type)"
              >
                {{ count }}
              </ElDescriptionsItem>
            </ElDescriptions>
          </div>
        </ElTabPane>

        <!-- ── IP 威胁情报 ── -->
        <ElTabPane name="ip_threat">
          <template #label>
            <span>IP 威胁</span>
            <span class="text-xs text-g-400 ml-1.5">恶意 IP 黑名单</span>
          </template>
          <ElCard class="mb-3" size="small">
            <div class="flex flex-wrap items-center gap-2">
              <ElSelect
                v-model="ipFilters.category"
                placeholder="威胁分类"
                clearable
                style="width: 130px"
                @change="handleIpFilterChange"
              >
                <ElOption v-for="o in THREAT_CATEGORY_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </ElSelect>
              <ElSelect
                v-model="ipFilters.severity"
                placeholder="严重度"
                clearable
                style="width: 110px"
                @change="handleIpFilterChange"
              >
                <ElOption v-for="o in THREAT_SEVERITY_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </ElSelect>
              <ElButton v-auth="'threat_intel.write'" type="primary" @click="openAddDialog('ip_threat')">新增</ElButton>
              <ElButton v-auth="'threat_intel.write'" @click="triggerCsvInput">导入 JSON</ElButton>
            </div>
          </ElCard>
          <ElAlert v-if="ipError" type="error" :closable="false" class="mb-3" :title="ipError">
            <template #default>
              <ElButton link type="primary" @click="loadIpData()">重试</ElButton>
            </template>
          </ElAlert>
          <div class="table-wrap">
            <ArtTable
              :loading="ipLoading"
              :data="ipData"
              :columns="ipColumns"
              :pagination="ipPagination"
              :show-table-header="false"
              @pagination:size-change="(s: number) => { ipPagination.size = s; ipPagination.current = 1; loadIpData() }"
              @pagination:current-change="(p: number) => { ipPagination.current = p; loadIpData() }"
            />
          </div>
        </ElTabPane>

        <!-- ── ASN 情报 ── -->
        <ElTabPane name="asn">
          <template #label>
            <span>ASN 情报</span>
            <span class="text-xs text-g-400 ml-1.5">高风险 ASN 黑名单</span>
          </template>
          <IntelTabBase
            ref="asnTabRef"
            intel-type="asn"
            :columns="asnColumns"
            search-placeholder="ASN号/运营商名称"
            :filter-fields="asnFilters"
            @add="openAddDialog('asn')"
          >
            <template #footer>
              <IntelSourceCard
                mode="preset"
                intel-type="asn"
                @synced="asnTabRef?.fetchData()"
              />
            </template>
          </IntelTabBase>
        </ElTabPane>

        <!-- ── 爬虫特征 ── -->
        <ElTabPane name="crawler">
          <template #label>
            <span>爬虫特征</span>
            <span class="text-xs text-g-400 ml-1.5">UA / IP 匹配规则</span>
          </template>
          <IntelTabBase
            ref="crawlerTabRef"
            intel-type="crawler"
            :columns="crawlerColumns"
            search-placeholder="搜索特征关键词"
            :filter-fields="crawlerFilters"
            :exportable="true"
            @add="openAddDialog('crawler')"
          >
            <template #footer>
              <IntelSourceCard
                mode="preset"
                intel-type="crawler"
                @synced="crawlerTabRef?.fetchData()"
              />
            </template>
          </IntelTabBase>
        </ElTabPane>

        <!-- ── 指纹情报 ── -->
        <ElTabPane name="fingerprint">
          <template #label>
            <span>指纹情报</span>
            <span class="text-xs text-g-400 ml-1.5">设备指纹黑名单</span>
          </template>
          <IntelTabBase
            ref="fingerprintTabRef"
            intel-type="fingerprint"
            :columns="fingerprintColumns"
            search-placeholder="搜索 FingerID"
            :filter-fields="fingerprintFilters"
            :exportable="true"
            @add="openAddDialog('fingerprint')"
          />
        </ElTabPane>

        <!-- ── GeoIP 手工录入 ── -->
        <ElTabPane name="geo_ip">
          <template #label>
            <span>GeoIP 录入</span>
            <span class="text-xs text-g-400 ml-1.5">IP 归属地修正</span>
          </template>
          <IntelTabBase
            ref="geoIpTabRef"
            intel-type="geo_ip"
            :columns="geoIpColumns"
            search-placeholder="搜索 IP/CIDR"
            @add="openAddDialog('geo_ip')"
          />
        </ElTabPane>

        <!-- ── IP 画像 ── -->
        <ElTabPane name="ip_profile">
          <template #label>
            <span>IP 画像</span>
            <span class="text-xs text-g-400 ml-1.5">IP 网络属性标注</span>
          </template>
          <IntelTabBase
            ref="ipProfileTabRef"
            intel-type="ip_profile"
            :columns="ipProfileColumns"
            search-placeholder="搜索 IP/CIDR"
            :filter-fields="profileFilters"
            @add="openAddDialog('ip_profile')"
          />
        </ElTabPane>

        <!-- ── GeoIP 管理（MMDB） ── -->
        <ElTabPane label="GeoIP 管理" name="mmdb">
          <div v-loading="mmdbStatusLoading" class="pane-scroll">
            <div v-for="f in mmdbFiles" :key="f.file_type" class="flex items-center gap-3 py-2 border-b last:border-0">
              <ElTag :type="f.exists ? 'success' : 'info'" size="small" class="w-20 text-center shrink-0">
                {{ f.file_type === 'country' ? 'Country' : 'ASN' }}
              </ElTag>
              <span class="text-sm text-g-600 flex-1 truncate">
                <template v-if="f.exists">
                  {{ formatBytes(f.size_bytes) }} · {{ f.modified_at ?? '-' }}
                </template>
                <span v-else class="text-g-400">文件不存在，功能降级为仅 IP 归因</span>
              </span>
              <ElButton size="small" :loading="mmdbUploading === f.file_type" @click="triggerMmdbInput(f.file_type as 'country' | 'asn')">上传 .mmdb</ElButton>
              <ElButton v-if="f.exists" size="small" type="danger" plain :loading="mmdbDeleting === f.file_type" @click="handleMmdbDelete(f.file_type as 'country' | 'asn')">删除</ElButton>
            </div>

            <ElProgress
              v-if="mmdbUploadProgress !== null"
              :percentage="mmdbUploadProgress"
              :stroke-width="10"
              striped
              striped-flow
              :duration="10"
              class="my-2"
            />

            <ElDivider content-position="left">IP 快速测试</ElDivider>
            <div class="flex gap-2 items-center">
              <ElInput v-model="testIp" placeholder="留空 = 使用当前客户端 IP" size="small" clearable class="w-64" />
              <ElButton size="small" :loading="testLoading" @click="handleMmdbTest">测试</ElButton>
              <ElButton v-if="testResult" size="small" link @click="testResult = null">清除</ElButton>
            </div>
            <ElDescriptions v-if="testResult" :column="3" border size="small" class="mt-3">
              <ElDescriptionsItem v-for="(v, k) in testResult" :key="k" :label="String(k)">{{ v ?? '-' }}</ElDescriptionsItem>
            </ElDescriptions>
          </div>
        </ElTabPane>

        <!-- ── 外部情报源 ── -->
        <ElTabPane label="外部情报源" name="external_sources">
          <div v-loading="extLoading" class="pane-scroll">
            <ElAlert type="info" :closable="false" class="mb-4">
              定时任务每 6 小时自动拉取一次；你也可以点击「立即同步」手动触发。
              AbuseIPDB 需在服务器配置环境变量 <code>ABUSEIPDB_API_KEY</code>。
            </ElAlert>

            <div class="flex justify-end mb-3">
              <ElButton
                v-auth="'threat_intel.write'"
                type="primary"
                :loading="extSyncing"
                @click="handleSyncExternal"
              >
                立即同步全部
              </ElButton>
            </div>

            <ElTable :data="extSources" border stripe>
              <ElTableColumn label="情报源" width="180">
                <template #default="{ row }">
                  <span class="font-medium">{{ row.name }}</span>
                </template>
              </ElTableColumn>
              <ElTableColumn label="状态" width="100">
                <template #default="{ row }">
                  <ElTag
                    :type="row.enabled ? (row.requiresApiKey && !row.configured ? 'warning' : 'success') : 'info'"
                    size="small"
                  >
                    {{ row.enabled ? (row.requiresApiKey && !row.configured ? '未配置 Key' : '已启用') : '已禁用' }}
                  </ElTag>
                </template>
              </ElTableColumn>
              <ElTableColumn label="需要 API Key" width="120" align="center">
                <template #default="{ row }">
                  <ElTag :type="row.requiresApiKey ? 'warning' : 'success'" size="small">
                    {{ row.requiresApiKey ? '是' : '否' }}
                  </ElTag>
                </template>
              </ElTableColumn>
              <ElTableColumn prop="url" label="来源 URL" min-width="240" show-overflow-tooltip />
              <ElTableColumn prop="description" label="说明" min-width="200" show-overflow-tooltip />
            </ElTable>

            <ElDescriptions v-if="extLastResult" title="上次同步结果" :column="3" border size="small" class="mt-4">
              <ElDescriptionsItem label="写入条目">{{ extLastResult.imported }}</ElDescriptionsItem>
              <ElDescriptionsItem label="跳过（重复）">{{ extLastResult.skipped ?? 0 }}</ElDescriptionsItem>
              <ElDescriptionsItem label="来源">{{ (extLastResult.sources ?? []).join(' / ') }}</ElDescriptionsItem>
            </ElDescriptions>
          </div>
        </ElTabPane>
      </ElTabs>
    </ElCard>

    <input ref="csvInputRef" type="file" accept=".json" style="display:none" @change="onCsvFile" />
    <input ref="mmdbInputRef" type="file" accept=".mmdb" style="display:none" @change="onMmdbFile" />

    <!-- 新增弹窗（各 Tab 独立表单） -->
    <ElDialog v-model="addDialogVisible" :title="addDialogTitle" width="520px" destroy-on-close>
      <!-- IP 威胁 -->
      <ElForm v-if="activeDialogType === 'ip_threat'" :model="addFormData" label-width="90px">
        <ElFormItem label="IP 地址" required><ElInput v-model="addFormData.ip" placeholder="例：1.2.3.4" /></ElFormItem>
        <ElFormItem label="威胁分类" required>
          <ElSelect v-model="addFormData.category" style="width:100%">
            <ElOption v-for="o in THREAT_CATEGORY_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="严重度" required>
          <ElSelect v-model="addFormData.severity" style="width:100%">
            <ElOption v-for="o in THREAT_SEVERITY_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="置信度">
          <ElSlider v-model="addFormData.confidence" :min="0" :max="100" show-input :input-size="'small'" />
        </ElFormItem>
        <ElFormItem label="备注"><ElInput v-model="addFormData.description" type="textarea" :rows="2" /></ElFormItem>
        <ElFormItem label="过期时间"><ElDatePicker v-model="addFormData.expires_at" type="datetime" style="width:100%" value-format="YYYY-MM-DDTHH:mm:ss" /></ElFormItem>
      </ElForm>

      <!-- ASN 情报 -->
      <ElForm v-else-if="activeDialogType === 'asn'" :model="addFormData" label-width="90px">
        <ElFormItem label="ASN" required><ElInputNumber v-model="addFormData.asn" :min="1" style="width:100%" /></ElFormItem>
        <ElFormItem label="运营商" required><ElInput v-model="addFormData.operator" /></ElFormItem>
        <ElFormItem label="网络类型">
          <ElSelect v-model="addFormData.network_type" style="width:100%">
            <ElOption v-for="o in NETWORK_TYPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="风险评分"><ElInputNumber v-model="addFormData.risk_score" :min="0" :max="100" style="width:100%" /></ElFormItem>
        <ElFormItem label="备注"><ElInput v-model="addFormData.note" type="textarea" :rows="2" /></ElFormItem>
      </ElForm>

      <!-- 爬虫特征 -->
      <ElForm v-else-if="activeDialogType === 'crawler'" :model="addFormData" label-width="90px">
        <ElFormItem label="特征类型">
          <ElSelect v-model="addFormData.feature_type" style="width:100%">
            <ElOption label="User-Agent" value="user_agent" />
            <ElOption label="Accept-Language" value="accept_language" />
            <ElOption label="IP CIDR" value="ip_cidr" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="匹配模式" required><ElInput v-model="addFormData.pattern" placeholder="支持正则" /></ElFormItem>
        <ElFormItem label="爬虫分类">
          <ElSelect v-model="addFormData.crawler_category" style="width:100%">
            <ElOption label="搜索引擎" value="search_engine" />
            <ElOption label="监控 Bot" value="monitor" />
            <ElOption label="恶意爬虫" value="malicious" />
            <ElOption label="数据采集" value="scraper" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="爬虫名称"><ElInput v-model="addFormData.crawler_name" /></ElFormItem>
        <ElFormItem label="合法爬虫"><ElSwitch v-model="addFormData.is_legitimate" /></ElFormItem>
        <ElFormItem label="风险评分"><ElInputNumber v-model="addFormData.risk_score" :min="0" :max="100" style="width:100%" /></ElFormItem>
        <ElFormItem label="备注"><ElInput v-model="addFormData.note" type="textarea" :rows="2" /></ElFormItem>
      </ElForm>

      <!-- 指纹情报 -->
      <ElForm v-else-if="activeDialogType === 'fingerprint'" :model="addFormData" label-width="90px">
        <ElFormItem label="FingerID" required><ElInput v-model="addFormData.finger_id" /></ElFormItem>
        <ElFormItem label="指纹类型">
          <ElSelect v-model="addFormData.finger_type" style="width:100%">
            <ElOption label="设备指纹" value="device" />
            <ElOption label="Canvas 哈希" value="canvas" />
            <ElOption label="复合指纹" value="composite" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="风险评分"><ElInputNumber v-model="addFormData.risk_score" :min="0" :max="100" style="width:100%" /></ElFormItem>
        <ElFormItem label="来源"><ElInput v-model="addFormData.source" /></ElFormItem>
        <ElFormItem label="备注"><ElInput v-model="addFormData.note" type="textarea" :rows="2" /></ElFormItem>
      </ElForm>

      <!-- GeoIP 录入 -->
      <ElForm v-else-if="activeDialogType === 'geo_ip'" :model="addFormData" label-width="90px">
        <ElFormItem label="CIDR" required><ElInput v-model="addFormData.cidr" placeholder="例：192.168.0.0/16" /></ElFormItem>
        <ElFormItem label="国家代码" required><ElInput v-model="addFormData.country" placeholder="例：CN" maxlength="2" /></ElFormItem>
        <ElFormItem label="地区"><ElInput v-model="addFormData.region" /></ElFormItem>
        <ElFormItem label="城市"><ElInput v-model="addFormData.city" /></ElFormItem>
        <ElFormItem label="启用"><ElSwitch v-model="addFormData.is_active" /></ElFormItem>
        <ElFormItem label="备注"><ElInput v-model="addFormData.note" type="textarea" :rows="2" /></ElFormItem>
      </ElForm>

      <!-- IP 画像 -->
      <ElForm v-else-if="activeDialogType === 'ip_profile'" :model="addFormData" label-width="90px">
        <ElFormItem label="CIDR" required><ElInput v-model="addFormData.cidr" placeholder="例：1.2.3.0/24" /></ElFormItem>
        <ElFormItem label="网络类型">
          <ElSelect v-model="addFormData.network_type" style="width:100%">
            <ElOption v-for="o in NETWORK_TYPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="VPN"><ElSwitch v-model="addFormData.is_vpn" /></ElFormItem>
        <ElFormItem label="代理"><ElSwitch v-model="addFormData.is_proxy" /></ElFormItem>
        <ElFormItem label="Tor"><ElSwitch v-model="addFormData.is_tor" /></ElFormItem>
        <ElFormItem label="风险评分"><ElInputNumber v-model="addFormData.risk_score" :min="0" :max="100" style="width:100%" /></ElFormItem>
        <ElFormItem label="启用"><ElSwitch v-model="addFormData.is_active" /></ElFormItem>
        <ElFormItem label="备注"><ElInput v-model="addFormData.note" type="textarea" :rows="2" /></ElFormItem>
      </ElForm>

      <template #footer>
        <ElButton @click="addDialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="addSaving" @click="submitAdd">确认</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
/* .el-card__body 只有 height:100%，不是 flex 容器，高度链会在此断裂 */
.threat-intel-card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
}

/* ElTabs 高度链：让 tab 面板撑满卡片剩余空间，使 ArtTable 可以正常滚动 */
.intel-tabs {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.intel-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.intel-tabs :deep(.el-tab-pane) {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 表格容器：占据面板内筛选卡片之外的剩余空间，供 ArtTable 内部按 100% 计算 */
.table-wrap {
  flex: 1;
  min-height: 0;
}

/* ArtTable 的 .el-table 自带 10px 上边距用于隔开 ArtTableHeader；
   这里没有 header（show-table-header=false），该边距不计入高度换算，会顶掉分页器 */
.table-wrap :deep(.el-table) {
  margin-top: 0;
}

/* 总览 / MMDB / 外部情报源等非表格面板：内容超出时自身滚动 */
.pane-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
</style>

<script setup lang="ts">
import { h } from 'vue'
import { ElMessage, ElMessageBox, ElTag } from 'element-plus'
import IntelTabBase from './components/IntelTabBase.vue'
import IntelSourceCard from './components/IntelSourceCard.vue'
import type { FilterField } from './components/IntelTabBase.vue'
import { formatTime } from '@/utils/format'
import {
  fetchGetThreatIntelList,
  fetchAddThreatIntel,
  fetchRemoveThreatIntel,
  fetchBulkImportThreatIntel,
  fetchSyncThreatIntelRedis,
  fetchAddIntel,
  fetchDeleteIntel,
  fetchGetIntelOverview,
  fetchGetExternalSources,
  fetchSyncExternalIntel,
  type IntelOverviewStats,
  type ExternalSourceStatus
} from '@/api/threat-intel'
import {
  fetchMmdbStatus,
  fetchUploadMmdb,
  fetchDeleteMmdb,
  fetchTestMmdbIp
} from '@/api/threat-intel'

const THREAT_CATEGORY_OPTIONS = [
  { label: '恶意 IP',   value: 'malicious' },
  { label: '代理',      value: 'proxy' },
  { label: 'Tor 出口',  value: 'tor' },
  { label: 'VPN',       value: 'vpn' },
  { label: '扫描器',    value: 'scanner' },
  { label: 'Botnet',    value: 'botnet' },
  { label: '垃圾邮件',  value: 'spam' },
  { label: '钓鱼站点',  value: 'phishing' },
  { label: 'C2 服务器', value: 'c2' },
  { label: '暴力破解',  value: 'brute_force' },
  { label: '恶意软件',  value: 'malware' },
  { label: '漏洞利用',  value: 'exploit' },
  { label: '撞库攻击',  value: 'credential_stuffing' },
  { label: '挖矿程序',  value: 'cryptomining' },
  { label: 'DDoS 来源', value: 'ddos' },
]

const THREAT_SEVERITY_OPTIONS = [
  { label: '严重', value: 'critical' },
  { label: '高危', value: 'high' },
  { label: '中危', value: 'medium' },
  { label: '低危', value: 'low' },
]

const NETWORK_TYPE_OPTIONS = [
  { label: '数据中心/IDC', value: 'DATACENTER' },
  { label: '住宅宽带',     value: 'RESIDENTIAL' },
  { label: '移动网络',     value: 'MOBILE' },
  { label: '自定义',       value: 'CUSTOM' },
]

const activeTab = ref('overview')

const overviewLoading = ref(false)
const overview = ref<IntelOverviewStats | null>(null)
const syncing = ref(false)

const overviewCards = computed(() => [
  {
    label: '情报总条数',
    value: overview.value?.total_entries ?? '-',
    desc: '覆盖所有类型'
  },
  {
    label: '画像条目数',
    value: overview.value?.profile_field_count ?? '-',
    desc: 'IP 画像 + GeoIP 录入'
  },
  {
    label: '缺失画像',
    value: overview.value?.health?.profile_missing_total ?? 0,
    desc: '建议补齐'
  },
  {
    label: '最后同步',
    value: overview.value?.last_sync_time
      ? formatTime(overview.value.last_sync_time)
      : '未同步',
    desc: 'Redis 同步时间'
  }
])

async function loadOverview() {
  overviewLoading.value = true
  try {
    overview.value = await fetchGetIntelOverview()
  } catch {
    overview.value = null
  } finally {
    overviewLoading.value = false
  }
}

async function handleSyncRedis() {
  syncing.value = true
  try {
    await fetchSyncThreatIntelRedis()
    ElMessage.success('Redis 同步成功')
    loadOverview()
  } catch {
    ElMessage.error('同步失败')
  } finally {
    syncing.value = false
  }
}

function refreshAll() {
  loadOverview()
}

function onTabChange(rawName: string | number) {
  const name = String(rawName)
  if (name === 'overview') loadOverview()
  if (name === 'mmdb') loadMmdbStatus()
  if (name === 'ip_threat') loadIpData()
  if (name === 'external_sources') loadExternalSources()
}

// ── 外部情报源 Tab ──────────────────────────────────────────────────────────────

const extLoading   = ref(false)
const extSyncing   = ref(false)
const extSources   = ref<ExternalSourceStatus[]>([])
const extLastResult = ref<{ imported: number; skipped?: number; sources?: string[] } | null>(null)

async function loadExternalSources() {
  extLoading.value = true
  try {
    const res = await fetchGetExternalSources()
    extSources.value = res?.sources ?? []
  } catch {
    extSources.value = []
  } finally {
    extLoading.value = false
  }
}

async function handleSyncExternal() {
  extSyncing.value = true
  try {
    const res = await fetchSyncExternalIntel()
    extLastResult.value = res
    ElMessage.success(`同步完成，写入 ${res.imported} 条`)
    loadExternalSources()
    loadOverview()
  } catch {
    ElMessage.error('外部情报源同步失败')
  } finally {
    extSyncing.value = false
  }
}

// ── IP 威胁 Tab ──────────────────────────────────────────────────────────────

const ipLoading  = ref(false)
const ipData     = ref<Api.Fangyu.ThreatIntel[]>([])
const ipFilters  = reactive({ category: '', severity: '' })
// 字段名需与 ArtTable 的 pagination 契约一致（current / size / total）
const ipPagination = reactive({ current: 1, size: 20, total: 0 })
const ipError = ref('')
const csvInputRef = ref<HTMLInputElement>()

const ipColumns = [
  { prop: 'ip', label: 'IP 地址', width: 150 },
  {
    prop: 'category', label: '威胁分类', width: 120,
    formatter: (row: Api.Fangyu.ThreatIntel) =>
      h(ElTag, { size: 'small' }, () => THREAT_CATEGORY_OPTIONS.find(o => o.value === row.category)?.label ?? row.category)
  },
  {
    prop: 'severity', label: '严重度', width: 90,
    formatter: (row: Api.Fangyu.ThreatIntel) => {
      const map: Record<string, string> = { critical: 'danger', high: 'warning', medium: '', low: 'info' }
      return h(ElTag, { type: map[row.severity] as any, size: 'small' }, () => row.severity)
    }
  },
  { prop: 'confidence', label: '置信度', width: 80 },
  { prop: 'description', label: '描述', minWidth: 160, showOverflowTooltip: true },
  { prop: 'expires_at', label: '过期时间', width: 160 },
  {
    label: '操作', width: 80, fixed: 'right' as const,
    formatter: (row: Api.Fangyu.ThreatIntel) =>
      h(ElButton, {
        size: 'small', type: 'danger', link: true,
        onClick: () => handleRemoveIp(row.ip)
      }, () => '删除')
  }
]

async function loadIpData() {
  ipLoading.value = true
  ipError.value = ''
  try {
    const params: Api.Fangyu.ThreatIntelListParams = {
      page: ipPagination.current,
      page_size: ipPagination.size
    }
    if (ipFilters.category) params.category = ipFilters.category
    if (ipFilters.severity) params.severity = ipFilters.severity
    const res = await fetchGetThreatIntelList(params)
    ipData.value  = res?.items ?? (res as any)?.data ?? []
    ipPagination.total = res?.total ?? 0
  } catch (err) {
    ipData.value = []
    ipPagination.total = 0
    ipError.value = '加载 IP 威胁情报失败，请检查网络后重试'
    console.error('加载 IP 威胁情报失败:', err)
  } finally {
    ipLoading.value = false
  }
}

/** 筛选条件变化时回到第一页，避免停留在越界页码上出现空列表 */
function handleIpFilterChange() {
  ipPagination.current = 1
  loadIpData()
}

async function handleRemoveIp(ip: string) {
  const confirmed = await ElMessageBox.confirm(
    `确认移除 IP「${ip}」的威胁情报吗？移除后该 IP 将不再被此情报命中，操作不可恢复。`,
    '移除威胁情报',
    { confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning' }
  ).catch(() => false)
  if (!confirmed) return

  try {
    await fetchRemoveThreatIntel(ip)
    ElMessage.success(`已移除 ${ip} 的威胁情报`)
    // 删除最后一页唯一记录时回退一页
    if (ipData.value.length === 1 && ipPagination.current > 1) ipPagination.current -= 1
    loadIpData()
  } catch {
    ElMessage.error('移除失败，请稍后重试')
  }
}

function triggerCsvInput() {
  csvInputRef.value?.click()
}

async function onCsvFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const text = await file.text()
    const records = JSON.parse(text)
    if (!Array.isArray(records)) throw new Error('需要 JSON 数组')
    const res = await fetchBulkImportThreatIntel(records)
    ElMessage.success(`批量导入成功：${res.imported} 条`)
    loadIpData()
  } catch (err: any) {
    ElMessage.error(`导入失败：${err.message ?? '格式错误'}`)
  } finally {
    if (csvInputRef.value) csvInputRef.value.value = ''
  }
}

// ── 多类型 Tab ref ─────────────────────────────────────────────────────────

const asnTabRef         = ref<InstanceType<typeof IntelTabBase>>()
const crawlerTabRef     = ref<InstanceType<typeof IntelTabBase>>()
const fingerprintTabRef = ref<InstanceType<typeof IntelTabBase>>()
const geoIpTabRef       = ref<InstanceType<typeof IntelTabBase>>()
const ipProfileTabRef   = ref<InstanceType<typeof IntelTabBase>>()
const asnProfileTabRef  = ref<InstanceType<typeof IntelTabBase>>()

// ── 表格列定义 ────────────────────────────────────────────────────────────────

const mkDeleteBtn = (type: string, idGetter: (row: any) => number | string) =>
  (row: any) =>
    h(ElButton, {
      size: 'small', type: 'danger', link: true,
      onClick: async () => {
        await ElMessageBox.confirm('确认删除该条记录？', '提示', { type: 'warning' })
        await fetchDeleteIntel(type, idGetter(row))
        ElMessage.success('已删除')
        switch (type) {
          case 'asn':         asnTabRef.value?.fetchData(); break
          case 'crawler':     crawlerTabRef.value?.fetchData(); break
          case 'fingerprint': fingerprintTabRef.value?.fetchData(); break
          case 'geo_ip':      geoIpTabRef.value?.fetchData(); break
          case 'ip_profile':  ipProfileTabRef.value?.fetchData(); break
        }
      }
    }, () => '删除')

const asnColumns = [
  { prop: 'asn',          label: 'ASN',    width: 100 },
  { prop: 'operator',     label: '运营商',  minWidth: 160 },
  { prop: 'network_type', label: '网络类型',width: 120 },
  { prop: 'country',      label: '国家',    width: 80 },
  { prop: 'risk_score',   label: '风险分',  width: 80 },
  { prop: 'note',         label: '备注',    minWidth: 120, showOverflowTooltip: true },
  { label: '操作', width: 80, fixed: 'right' as const, formatter: mkDeleteBtn('asn', r => r.id) }
]

const crawlerColumns = [
  { prop: 'feature_type',    label: '特征类型', width: 120 },
  { prop: 'pattern',         label: '匹配模式', minWidth: 200, showOverflowTooltip: true },
  { prop: 'crawler_name',    label: '爬虫名称', width: 140 },
  { prop: 'crawler_category',label: '分类',     width: 110 },
  {
    prop: 'is_legitimate', label: '合法', width: 80,
    formatter: (row: any) => h(ElTag, { type: row.is_legitimate ? 'success' : 'danger', size: 'small' }, () => row.is_legitimate ? '是' : '否')
  },
  { prop: 'risk_score', label: '风险分', width: 80 },
  { label: '操作', width: 80, fixed: 'right' as const, formatter: mkDeleteBtn('crawler', r => r.id) }
]

const fingerprintColumns = [
  { prop: 'finger_id',   label: 'FingerID',  minWidth: 200, showOverflowTooltip: true },
  { prop: 'finger_type', label: '指纹类型',  width: 120 },
  { prop: 'risk_score',  label: '风险分',    width: 80 },
  { prop: 'hit_count',   label: '命中次数',  width: 90 },
  { prop: 'source',      label: '来源',      width: 120 },
  { prop: 'created_at',  label: '录入时间',  width: 160,
    formatter: (row: any) => formatTime(row.created_at) },
  { label: '操作', width: 80, fixed: 'right' as const, formatter: mkDeleteBtn('fingerprint', r => r.id) }
]

const geoIpColumns = [
  { prop: 'cidr',       label: 'CIDR',    width: 150 },
  { prop: 'country',    label: '国家',    width: 80 },
  { prop: 'region',     label: '地区',    width: 120 },
  { prop: 'city',       label: '城市',    width: 120 },
  {
    prop: 'is_active', label: '状态', width: 80,
    formatter: (row: any) => h(ElTag, { type: row.is_active ? 'success' : 'info', size: 'small' }, () => row.is_active ? '启用' : '禁用')
  },
  { label: '操作', width: 80, fixed: 'right' as const, formatter: mkDeleteBtn('geo_ip', r => r.id) }
]

const ipProfileColumns = [
  { prop: 'cidr',         label: 'CIDR',    width: 150 },
  { prop: 'network_type', label: '网络类型', width: 120 },
  {
    label: 'VPN/代理/Tor', width: 120,
    formatter: (row: any) => h('span', [
      row.is_vpn   ? h(ElTag, { size: 'small', class: 'mr-1' }, () => 'VPN')   : null,
      row.is_proxy ? h(ElTag, { size: 'small', class: 'mr-1' }, () => '代理')  : null,
      row.is_tor   ? h(ElTag, { size: 'small', type: 'danger' }, () => 'Tor') : null,
    ])
  },
  { prop: 'risk_score', label: '风险分', width: 80 },
  { label: '操作', width: 80, fixed: 'right' as const, formatter: mkDeleteBtn('ip_profile', r => r.id) }
]

// ── 筛选配置 ──────────────────────────────────────────────────────────────────

const asnFilters: FilterField[] = [
  { key: 'network_type', type: 'select', placeholder: '网络类型', options: NETWORK_TYPE_OPTIONS }
]

const crawlerFilters: FilterField[] = [
  {
    key: 'crawler_category', type: 'select', placeholder: '爬虫分类', options: [
      { label: '搜索引擎', value: 'search_engine' },
      { label: '监控 Bot', value: 'monitor' },
      { label: '恶意爬虫', value: 'malicious' },
      { label: '数据采集', value: 'scraper' },
    ]
  },
  {
    key: 'is_legitimate', type: 'select', placeholder: '是否合法', options: [
      { label: '合法', value: true },
      { label: '非法', value: false },
    ]
  }
]

const fingerprintFilters: FilterField[] = [
  {
    key: 'finger_type', type: 'select', placeholder: '指纹类型', options: [
      { label: '设备指纹', value: 'device' },
      { label: 'Canvas',  value: 'canvas' },
      { label: '复合',    value: 'composite' },
    ]
  }
]

const profileFilters: FilterField[] = [
  { key: 'network_type', type: 'select', placeholder: '网络类型', options: NETWORK_TYPE_OPTIONS }
]

// ── 新增弹窗 ──────────────────────────────────────────────────────────────────

const addDialogVisible  = ref(false)
const activeDialogType  = ref('')
const addFormData       = ref<Record<string, any>>({})
const addSaving         = ref(false)

const addDialogTitle = computed(() => {
  const map: Record<string, string> = {
    ip_threat: '新增 IP 威胁情报', asn: '新增 ASN 情报',
    crawler: '新增爬虫特征', fingerprint: '新增指纹情报',
    geo_ip: '新增 GeoIP 条目', ip_profile: '新增 IP 画像'
  }
  return map[activeDialogType.value] ?? '新增情报'
})

const defaultForms: Record<string, Record<string, any>> = {
  ip_threat:   { ip: '', category: '', severity: 'high', confidence: 80, description: '', expires_at: null },
  asn:         { asn: undefined, operator: '', network_type: 'DATACENTER', country: '', risk_score: 50, note: '' },
  crawler:     { feature_type: 'user_agent', pattern: '', crawler_category: 'malicious', crawler_name: '', is_legitimate: false, risk_score: 60, note: '' },
  fingerprint: { finger_id: '', finger_type: 'device', risk_score: 60, source: '', note: '' },
  geo_ip:      { cidr: '', country: '', region: '', city: '', is_active: true, note: '' },
  ip_profile:  { cidr: '', network_type: 'DATACENTER', is_vpn: false, is_proxy: false, is_tor: false, risk_score: 0, is_active: true, note: '' },
}

function openAddDialog(type: string) {
  activeDialogType.value = type
  addFormData.value = { ...(defaultForms[type] ?? {}) }
  addDialogVisible.value = true
}

async function submitAdd() {
  addSaving.value = true
  try {
    if (activeDialogType.value === 'ip_threat') {
      await fetchAddThreatIntel(addFormData.value as any)
      loadIpData()
    } else {
      await fetchAddIntel(activeDialogType.value, addFormData.value)
      switch (activeDialogType.value) {
        case 'asn':         asnTabRef.value?.fetchData(); break
        case 'crawler':     crawlerTabRef.value?.fetchData(); break
        case 'fingerprint': fingerprintTabRef.value?.fetchData(); break
        case 'geo_ip':      geoIpTabRef.value?.fetchData(); break
        case 'ip_profile':  ipProfileTabRef.value?.fetchData(); break
      }
    }
    ElMessage.success('添加成功')
    addDialogVisible.value = false
  } catch {
    ElMessage.error('添加失败')
  } finally {
    addSaving.value = false
  }
}

// ── MMDB 管理 ──────────────────────────────────────────────────────────────────

const mmdbStatusLoading = ref(false)
const mmdbFiles = ref<{ file_type: string; exists: boolean; size_bytes: number; modified_at: string | null }[]>([])
const mmdbUploading    = ref<'country' | 'asn' | null>(null)
const mmdbDeleting     = ref<'country' | 'asn' | null>(null)
const mmdbUploadProgress = ref<number | null>(null)
const mmdbInputRef     = ref<HTMLInputElement>()
const mmdbCurrentType  = ref<'country' | 'asn'>('country')
const testIp           = ref('')
const testLoading      = ref(false)
const testResult       = ref<Record<string, unknown> | null>(null)

async function loadMmdbStatus() {
  mmdbStatusLoading.value = true
  try {
    const res = await fetchMmdbStatus()
    mmdbFiles.value = Array.isArray(res) ? res : (res as any).files ?? []
  } catch {
    mmdbFiles.value = [
      { file_type: 'country', exists: false, size_bytes: 0, modified_at: null },
      { file_type: 'asn',     exists: false, size_bytes: 0, modified_at: null },
    ]
  } finally {
    mmdbStatusLoading.value = false
  }
}

function triggerMmdbInput(type: 'country' | 'asn') {
  mmdbCurrentType.value = type
  mmdbInputRef.value?.click()
}

async function onMmdbFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return

  const MAX_BYTES = 100 * 1024 * 1024
  if (file.size > MAX_BYTES) {
    ElMessage.error(`文件过大（最大 100 MB），当前 ${formatBytes(file.size)}`)
    if (mmdbInputRef.value) mmdbInputRef.value.value = ''
    return
  }

  const type = mmdbCurrentType.value
  mmdbUploading.value  = type
  mmdbUploadProgress.value = 0
  try {
    await fetchUploadMmdb(type, file, (pct) => { mmdbUploadProgress.value = pct })
    ElMessage.success(`${type === 'country' ? 'Country' : 'ASN'} 数据库上传成功`)
    loadMmdbStatus()
  } catch {
    ElMessage.error('上传失败，请检查文件是否为有效 MMDB 格式')
  } finally {
    mmdbUploading.value  = null
    mmdbUploadProgress.value = null
    if (mmdbInputRef.value) mmdbInputRef.value.value = ''
  }
}

async function handleMmdbDelete(type: 'country' | 'asn') {
  await ElMessageBox.confirm(`确认删除 ${type === 'country' ? 'Country' : 'ASN'} 数据库？删除后 GeoIP 功能降级。`, '警告', { type: 'warning' })
  mmdbDeleting.value = type
  try {
    await fetchDeleteMmdb(type)
    ElMessage.success('已删除')
    loadMmdbStatus()
  } catch {
    ElMessage.error('删除失败')
  } finally {
    mmdbDeleting.value = null
  }
}

async function handleMmdbTest() {
  testLoading.value = true
  try {
    testResult.value = await fetchTestMmdbIp(testIp.value || undefined)
  } catch {
    ElMessage.error('测试失败')
  } finally {
    testLoading.value = false
  }
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function formatBytes(bytes: number, dec = 1): string {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / k ** i).toFixed(dec)} ${sizes[i]}`
}

onMounted(() => {
  loadOverview()
})
</script>
