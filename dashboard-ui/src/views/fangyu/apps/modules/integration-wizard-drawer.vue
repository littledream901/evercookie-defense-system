<!-- 站点接入向导：新手友好的分步接入指引 -->
<template>
  <ElDrawer
    v-model="drawerVisible"
    :title="`接入向导 · ${site?.name || '站点'}`"
    direction="rtl"
    size="720px"
    destroy-on-close
  >
    <div class="wizard-container">
      <!-- 步骤指示器 -->
      <ElSteps :active="currentStep" finish-status="success" class="mb-6">
        <ElStep title="选择接入方式" />
        <ElStep title="获取配置代码" />
        <ElStep title="测试连通性" />
        <ElStep title="等待首次流量" />
      </ElSteps>

      <!-- 步骤 1: 选择接入方式 -->
      <div v-if="currentStep === 0" class="step-content">
        <h3 class="text-lg font-medium mb-4">选择适合您的接入方式</h3>
        <div class="grid grid-cols-2 gap-4">
          <ElCard 
            v-for="method in integrationMethods" 
            :key="method.value"
            shadow="hover"
            :class="['method-card', { 'selected': selectedMethod === method.value }]"
            @click="selectedMethod = method.value"
          >
            <div class="flex flex-col items-center text-center">
              <ElIcon :size="48" class="mb-3" :color="method.color">
                <component :is="method.icon" />
              </ElIcon>
              <h4 class="font-medium mb-2">{{ method.label }}</h4>
              <p class="text-sm text-g-600 mb-2">{{ method.desc }}</p>
              <div class="flex gap-1 flex-wrap justify-center">
                <ElTag 
                  v-for="tag in method.tags" 
                  :key="tag" 
                  size="small"
                  :type="method.recommended ? 'success' : undefined"
                >
                  {{ tag }}
                </ElTag>
              </div>
            </div>
          </ElCard>
        </div>

        <ElAlert type="info" :closable="false" class="mt-4" show-icon>
          <template #title>选择建议</template>
          <p class="text-sm">
            • <strong>服务端模式</strong>（Nginx/CF Worker/WordPress）：密钥安全，推荐用于高价值场景<br>
            • <strong>客户端模式</strong>（SDK/Shopify）：快速接入，适合无法修改服务端的场景<br>
            • <strong>直接API</strong>：自研后端需要主动调用风险决策接口
          </p>
        </ElAlert>
      </div>

      <!-- 步骤 2: 获取配置代码 -->
      <div v-if="currentStep === 1" class="step-content">
        <h3 class="text-lg font-medium mb-4">复制以下代码到您的项目</h3>
        
        <ElAlert type="success" :closable="false" class="mb-4" show-icon>
          <template #title>代码已自动填入站点密钥</template>
          <p class="text-sm">
            Site Key: <code class="font-mono text-xs">{{ site?.site_key }}</code>
          </p>
        </ElAlert>

        <div class="code-section">
          <div class="code-header">
            <span>{{ getMethodLabel(selectedMethod) }} 接入代码</span>
            <ElButton size="small" @click="copyCode">
              <ElIcon class="mr-1"><CopyDocument /></ElIcon>
              复制代码
            </ElButton>
          </div>
          <pre class="code-block">{{ integrationCode }}</pre>
        </div>

        <ElAlert type="warning" :closable="false" class="mt-4" show-icon>
          <template #title>重要提示</template>
          <p class="text-sm">
            请妥善保管密钥，不要将 <strong>Site Secret</strong> 暴露在前端代码中。
            配置完成后，请部署到生产环境并继续下一步。
          </p>
        </ElAlert>
      </div>

      <!-- 步骤 3: 测试连通性 -->
      <div v-if="currentStep === 2" class="step-content">
        <h3 class="text-lg font-medium mb-4">测试网关连通性</h3>
        
        <div class="test-panel">
          <div v-if="!testResult" class="text-center py-8">
            <ElIcon :size="64" color="#409EFF" class="mb-4"><Connection /></ElIcon>
            <p class="text-g-600 mb-4">点击下方按钮测试站点与网关的连通性</p>
            <ElButton 
              type="primary" 
              size="large"
              :loading="testing"
              @click="runConnectionTest"
            >
              <ElIcon class="mr-2"><Connection /></ElIcon>
              开始测试
            </ElButton>
          </div>

          <div v-else-if="testResult.ok" class="test-success">
            <ElResult icon="success" title="✅ 连通性测试通过">
              <template #sub-title>
                <p class="text-sm">{{ testResult.message }}</p>
                <p class="text-xs text-g-500 mt-2">{{ testResult.detail }}</p>
              </template>
              <template #extra>
                <ElButton type="primary" @click="currentStep = 3">
                  继续下一步
                </ElButton>
                <ElButton @click="runConnectionTest">重新测试</ElButton>
              </template>
            </ElResult>
          </div>

          <div v-else class="test-failure">
            <ElResult icon="error" :title="`❌ ${testResult.error}`">
              <template #sub-title>
                <p class="text-sm text-g-700">{{ testResult.detail }}</p>
              </template>
              <template #extra>
                <ElButton type="primary" @click="runConnectionTest">
                  重新测试
                </ElButton>
                <ElButton link type="primary" @click="showTroubleshooting = true">
                  查看故障排查
                </ElButton>
              </template>
            </ElResult>
          </div>
        </div>

        <!-- 故障排查 -->
        <ElCollapse v-if="showTroubleshooting" v-model="troubleshootingActive" class="mt-4">
          <ElCollapseItem title="常见问题排查" name="troubleshooting">
            <div class="text-sm space-y-2">
              <p><strong>1. 无法连接到网关</strong></p>
              <ul class="list-disc pl-5 text-g-600">
                <li>检查网关地址是否正确配置</li>
                <li>确认服务器能够访问外网</li>
                <li>检查防火墙规则</li>
              </ul>

              <p><strong>2. 身份验证失败 (401)</strong></p>
              <ul class="list-disc pl-5 text-g-600">
                <li>确认 Site Key 是否正确填写</li>
                <li>检查 Site Secret 是否匹配</li>
                <li>验证签名算法实现是否正确</li>
              </ul>

              <p><strong>3. 请求参数错误 (400)</strong></p>
              <ul class="list-disc pl-5 text-g-600">
                <li>检查必填字段是否完整</li>
                <li>确认字段格式是否符合要求</li>
              </ul>
            </div>
          </ElCollapseItem>
        </ElCollapse>
      </div>

      <!-- 步骤 4: 等待首次流量 -->
      <div v-if="currentStep === 3" class="step-content">
        <h3 class="text-lg font-medium mb-4">等待首次决策请求</h3>
        
        <div v-if="!firstTrafficDetected" class="waiting-panel">
          <div class="text-center py-8">
            <ElIcon :size="64" class="mb-4 rotating"><Loading /></ElIcon>
            <h4 class="font-medium mb-2">正在监听流量...</h4>
            <p class="text-sm text-g-600 mb-4">
              请访问您的网站，我们会自动检测首次决策请求
            </p>
            <p class="text-xs text-g-500">
              已等待: <span class="font-mono">{{ waitingTime }}s</span>
            </p>
          </div>

          <ElAlert type="info" :closable="false" show-icon>
            <template #title>提示</template>
            <p class="text-sm">
              • 确保已将代码部署到生产环境<br>
              • 访问您的网站触发决策请求<br>
              • 系统每 5 秒自动检测一次
            </p>
          </ElAlert>
        </div>

        <div v-else class="success-panel">
          <ElResult icon="success" title="🎉 接入成功！">
            <template #sub-title>
              <p class="text-sm">
                检测到首次决策请求，站点已成功接入防护系统！
              </p>
              <div class="mt-4 p-4 bg-g-50 rounded">
                <ElDescriptions :column="2" size="small" border>
                  <ElDescriptionsItem label="首次流量时间">
                    {{ formatTime(firstTrafficTime) }}
                  </ElDescriptionsItem>
                  <ElDescriptionsItem label="接入方式">
                    {{ firstTrafficIngress }}
                  </ElDescriptionsItem>
                  <ElDescriptionsItem label="总请求数">
                    {{ totalRequests }}
                  </ElDescriptionsItem>
                  <ElDescriptionsItem label="判定结果">
                    <ElTag size="small">{{ firstVerdict }}</ElTag>
                  </ElDescriptionsItem>
                </ElDescriptions>
              </div>
            </template>
            <template #extra>
              <ElButton type="primary" @click="goToRules">
                配置防护规则
              </ElButton>
              <ElButton @click="goToDashboard">
                查看仪表盘
              </ElButton>
            </template>
          </ElResult>
        </div>
      </div>
    </div>

    <!-- 底部操作按钮 -->
    <template #footer>
      <div class="flex justify-between">
        <ElButton v-if="currentStep > 0" @click="prevStep">
          上一步
        </ElButton>
        <div v-else></div>
        <div>
          <ElButton @click="drawerVisible = false">取消</ElButton>
          <ElButton 
            v-if="currentStep < 3"
            type="primary" 
            :disabled="!canProceed"
            @click="nextStep"
          >
            下一步
          </ElButton>
        </div>
      </div>
    </template>
  </ElDrawer>
</template>

<script setup lang="ts">
  import { computed, ref, watch, onUnmounted } from 'vue'
  import { useRouter } from 'vue-router'
  import { ElMessage } from 'element-plus'
  import { 
    Loading, 
    Connection, 
    CopyDocument,
    Monitor,
    Cloudy,
    Document,
    Link
  } from '@element-plus/icons-vue'
  import { testSiteConnection } from '@/api/diagnostics'
  import { fetchGetIntegrationDiagnostics } from '@/api/diagnostics'
  import { formatTime } from '@/utils/format'

  interface SiteInfo {
    id: number
    name: string
    domain: string
    site_key?: string
    gateway_url?: string
    siteId?: number
  }

  interface Props {
    visible: boolean
    site: SiteInfo | null
  }

  const props = withDefaults(defineProps<Props>(), { visible: false })
  const emit = defineEmits<{ 'update:visible': [value: boolean] }>()

  const router = useRouter()

  const drawerVisible = computed({
    get: () => props.visible,
    set: (val) => emit('update:visible', val)
  })

  const currentStep = ref(0)
  const selectedMethod = ref('nginx')
  const testing = ref(false)
  const testResult = ref<{ success?: boolean; ok?: boolean; error?: string; detail?: string; message?: string } | null>(null)
  const showTroubleshooting = ref(false)
  const troubleshootingActive = ref<string | string[]>([])
  const firstTrafficDetected = ref(false)
  const waitingTime = ref(0)
  const firstTrafficTime = ref<string | null>(null)
  const firstTrafficIngress = ref('')
  const totalRequests = ref(0)
  const firstVerdict = ref('')

  let pollingTimer: number | null = null
  let waitingTimer: number | null = null

  const integrationMethods = [
    {
      value: 'nginx',
      label: 'Nginx-Lua',
      desc: '自建服务器，高性能',
      icon: Monitor,
      color: '#67C23A',
      tags: ['服务端', '推荐'],
      recommended: true
    },
    {
      value: 'cf',
      label: 'Cloudflare Worker',
      desc: '边缘计算，全球加速',
      icon: Cloudy,
      color: '#F56C6C',
      tags: ['服务端', '无需服务器']
    },
    {
      value: 'wp',
      label: 'WordPress',
      desc: 'WP插件，零代码',
      icon: Document,
      color: '#409EFF',
      tags: ['服务端', '零代码']
    },
    {
      value: 'sdk',
      label: '网站 SDK',
      desc: '纯静态页面',
      icon: Link,
      color: '#E6A23C',
      tags: ['客户端']
    }
  ]

  const canProceed = computed(() => {
    if (currentStep.value === 0) return !!selectedMethod.value
    if (currentStep.value === 2) return testResult.value?.ok
    return true
  })

  const integrationCode = computed(() => {
    const gw = props.site?.gateway_url || 'https://gateway.yourdomain.com'
    const siteKey = props.site?.site_key || 'YOUR_SITE_KEY'
    const siteId = props.site?.id || 0

    const codes: Record<string, string> = {
      nginx: `# nginx.conf — server 块内添加：
set $fangyu_gateway_url  "${gw}";
set $fangyu_site_key     "${siteKey}";
set $fangyu_site_id      "${siteId}";
set $fangyu_site_secret  "YOUR_SITE_SECRET";
set $fangyu_fail_mode    "open";
set $fy_sdk_snippet      "";

access_by_lua_file /etc/nginx/lua/fangyu/defense.lua;`,
      cf: `# wrangler.toml
[vars]
FANGYU_GATEWAY_URL = "${gw}"
FANGYU_SITE_KEY    = "${siteKey}"
FANGYU_SITE_ID     = "${siteId}"
FANGYU_FAIL_MODE   = "open"`,
      wp: `<?php
// wp-config.php
define('FANGYU_GATEWAY_URL', '${gw}');
define('FANGYU_SITE_KEY',    '${siteKey}');
define('FANGYU_SITE_ID',     ${siteId});
define('FANGYU_SITE_SECRET', 'YOUR_SITE_SECRET');`,
      sdk: `<!-- 放在 <head> 内尽量靠前 -->
<script src="${gw}/sdk/sd-sdk.min.js"><\/script>
<script>
  SdSdk.guard({
    apiBase: '${gw}',
    apiKey:  '${siteKey}',
    siteId:   ${siteId}
  });
<\/script>`
    }

    return codes[selectedMethod.value] || ''
  })

  const getMethodLabel = (method: string) => {
    return integrationMethods.find(m => m.value === method)?.label || method
  }

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(integrationCode.value)
      ElMessage.success('代码已复制到剪贴板')
    } catch {
      ElMessage.error('复制失败，请手动选择复制')
    }
  }

  const runConnectionTest = async () => {
    if (!props.site?.id) return

    testing.value = true
    testResult.value = null

    try {
      testResult.value = await testSiteConnection(props.site.id)
    } catch (error: any) {
      testResult.value = {
        ok: false,
        error: '测试失败',
        detail: error.message || '未知错误'
      }
    } finally {
      testing.value = false
    }
  }

  const startWaitingForTraffic = () => {
    waitingTime.value = 0
    firstTrafficDetected.value = false

    // 每秒更新等待时间
    waitingTimer = window.setInterval(() => {
      waitingTime.value++
    }, 1000)

    // 每5秒轮询一次诊断接口
    pollingTimer = window.setInterval(async () => {
      await checkFirstTraffic()
    }, 5000)

    // 立即检查一次
    checkFirstTraffic()
  }

  const checkFirstTraffic = async () => {
    if (!props.site?.id || firstTrafficDetected.value) return

    try {
      const diagnostics = await fetchGetIntegrationDiagnostics(props.site.id, 1) // 查询最近1小时
      
      if (diagnostics.total_requests > 0) {
        firstTrafficDetected.value = true
        firstTrafficTime.value = diagnostics.last_seen_at
        totalRequests.value = diagnostics.total_requests
        firstTrafficIngress.value = diagnostics.ingress_stats[0]?.ingress || 'unknown'
        
        // 从 findings 中提取判定结果
        const cleanCount = diagnostics.ingress_stats[0]?.clean_count || 0
        const suspiciousCount = diagnostics.ingress_stats[0]?.suspicious_count || 0
        const hostileCount = diagnostics.ingress_stats[0]?.hostile_count || 0
        
        if (cleanCount > 0) firstVerdict.value = 'clean'
        else if (suspiciousCount > 0) firstVerdict.value = 'suspicious'
        else if (hostileCount > 0) firstVerdict.value = 'hostile'
        else firstVerdict.value = 'unknown'

        stopPolling()
      }
    } catch (error) {
      console.error('检查流量失败:', error)
    }
  }

  const stopPolling = () => {
    if (pollingTimer) {
      clearInterval(pollingTimer)
      pollingTimer = null
    }
    if (waitingTimer) {
      clearInterval(waitingTimer)
      waitingTimer = null
    }
  }

  const nextStep = () => {
    if (currentStep.value < 3 && canProceed.value) {
      currentStep.value++
      
      // 进入步骤4时开始轮询
      if (currentStep.value === 3) {
        startWaitingForTraffic()
      }
    }
  }

  const prevStep = () => {
    if (currentStep.value > 0) {
      currentStep.value--
      stopPolling()
    }
  }

  const goToRules = () => {
    router.push('/defense/rules')
    drawerVisible.value = false
  }

  const goToDashboard = () => {
    router.push('/defense/dashboard')
    drawerVisible.value = false
  }

  // 监听抽屉关闭，停止轮询
  watch(() => props.visible, (visible) => {
    if (!visible) {
      stopPolling()
      currentStep.value = 0
      testResult.value = null
      firstTrafficDetected.value = false
    }
  })

  onUnmounted(() => {
    stopPolling()
  })
</script>

<style scoped lang="scss">
.wizard-container {
  padding: 0 4px;
}

.step-content {
  min-height: 400px;
}

.method-card {
  cursor: pointer;
  transition: all 0.3s;
  
  &:hover {
    transform: translateY(-4px);
  }
  
  &.selected {
    border-color: var(--el-color-primary);
    box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
  }
}

.code-section {
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  overflow: hidden;
}

.code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color);
  font-size: 13px;
  font-weight: 500;
}

.code-block {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 16px;
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
}

.rotating {
  animation: rotate 2s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.grid {
  display: grid;
}

.grid-cols-2 {
  grid-template-columns: repeat(2, 1fr);
}

.gap-4 {
  gap: 16px;
}

.space-y-2 > * + * {
  margin-top: 8px;
}
</style>
