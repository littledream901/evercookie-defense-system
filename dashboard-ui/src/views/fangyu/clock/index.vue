<!-- 频控配置 -->
<template>
  <div class="art-full-height">
    <div class="mb-3">
      <h2 class="text-lg font-medium text-g-900">频控配置</h2>
      <p class="mt-1 text-sm text-g-600">请求频率限制、超限封禁阈值与封禁管理</p>
    </div>

    <ElAlert v-if="loadError" type="error" :closable="false" class="mb-3" :title="loadError">
      <template #default>
        <ElButton link type="primary" :loading="configLoading" @click="loadConfig()">重新加载</ElButton>
      </template>
    </ElAlert>

    <ElRow :gutter="16">
      <!-- 阈值配置 -->
      <ElCol :span="14">
        <ElCard shadow="never" header="频控阈值" v-loading="configLoading">
          <ElForm ref="limitsFormRef" :model="limitsForm" label-width="120px">
            <ElFormItem label="启用频控">
              <ElSwitch v-model="limitsForm.enabled" />
            </ElFormItem>
            <ElFormItem label="启用封禁">
              <ElSwitch v-model="limitsForm.banEnabled" :disabled="!limitsForm.enabled" />
            </ElFormItem>
            <ElFormItem label="封禁时长（秒）">
              <ElInputNumber v-model="limitsForm.banSeconds" :min="60" :max="86400" :disabled="!limitsForm.banEnabled" />
            </ElFormItem>
            <template v-if="windows.length">
              <ElDivider content-position="left">窗口阈值</ElDivider>
              <ElFormItem v-for="w in windows" :key="w.name" :label="w.name">
                <ElInputNumber
                  v-model="limitsForm.limits[w.name]"
                  :min="0" :placeholder="'0 = 不限'"
                  :disabled="!limitsForm.enabled"
                />
              </ElFormItem>
            </template>
          </ElForm>
          <div class="mt-4 flex flex-wrap items-center gap-2">
            <ElButton
              type="primary"
              v-auth="'clock.write'"
              :loading="saving"
              :disabled="configLoading || !configReady"
              @click="saveLimits"
            >
              保存配置
            </ElButton>
            <ElButton v-auth="'clock.write'" :disabled="configLoading" @click="resetLimits">
              恢复默认
            </ElButton>
            <ElButton v-auth="'clock.write'" :disabled="configLoading" @click="resyncLimits">
              同步到网关
            </ElButton>
            <span v-if="!configReady && !configLoading" class="text-sm text-g-500">
              配置未成功加载，保存已禁用
            </span>
          </div>
        </ElCard>
      </ElCol>

      <!-- 封禁管理 -->
      <ElCol :span="10">
        <ElCard shadow="never" header="封禁查询 / 手动封禁" v-loading="banLoading">
          <ElForm :model="banQuery" label-width="90px">
            <ElFormItem label="维度">
              <ElSelect v-model="banQuery.dimension" class="w-full">
                <ElOption label="IP" value="ip" />
                <ElOption label="设备指纹" value="fingerprint" />
              </ElSelect>
            </ElFormItem>
            <ElFormItem label="值">
              <ElInput
                v-model="banQuery.value"
                :placeholder="banQuery.dimension === 'ip' ? '如 203.0.113.5' : '设备指纹值'"
                @keyup.enter="lookupBan"
              />
            </ElFormItem>
          </ElForm>
          <div class="flex gap-2 mb-3">
            <ElButton @click="lookupBan" size="small">查询</ElButton>
            <ElButton type="danger" size="small" v-auth="'clock.write'" @click="handleUnban">解封</ElButton>
          </div>
          <ElDescriptions v-if="banResult" :column="1" border size="small">
            <ElDescriptionsItem label="剩余(秒)">{{ banResult.ttlSeconds }}</ElDescriptionsItem>
            <ElDescriptionsItem label="原因">{{ banResult.reason ?? '-' }}</ElDescriptionsItem>
          </ElDescriptions>
          <ElDivider content-position="left">手动封禁</ElDivider>
          <ElForm :model="banForm" label-width="90px">
            <ElFormItem label="维度">
              <ElSelect v-model="banForm.dimension" class="w-full">
                <ElOption label="IP" value="ip" /><ElOption label="设备指纹" value="fingerprint" />
              </ElSelect>
            </ElFormItem>
            <ElFormItem label="值">
              <ElInput
                v-model="banForm.value"
                :placeholder="banForm.dimension === 'ip' ? '如 203.0.113.5 或 203.0.113.0/24' : '设备指纹值'"
              />
            </ElFormItem>
            <ElFormItem label="时长（秒）">
              <ElInputNumber v-model="banForm.seconds" :min="60" :max="86400" />
              <span class="ml-2 text-sm text-g-500">约 {{ formatDuration(banForm.seconds) }}</span>
            </ElFormItem>
            <ElFormItem label="封禁原因">
              <ElInput v-model="banForm.reason" placeholder="选填，便于事后审计追溯" />
            </ElFormItem>
          </ElForm>
          <ElButton type="warning" size="small" v-auth="'clock.write'" @click="createBan">封禁</ElButton>
        </ElCard>
      </ElCol>
    </ElRow>
  </div>
</template>
<script setup lang="ts">
  import {
    fetchGetClockLimits, fetchPutClockLimits, fetchResetClockLimits,
    fetchGetClockWindows, fetchResyncClockLimits,
    fetchCreateClockBan, fetchGetClockBan, fetchDeleteClockBan
  } from '@/api/clock'
  import { ElMessage, ElMessageBox } from 'element-plus'

  defineOptions({ name: 'FangyuClock' })

  const configLoading = ref(false)
  const banLoading = ref(false)
  const saving = ref(false)
  const limitsFormRef = ref()
  const windows = ref<Api.Fangyu.ClockWindow[]>([])
  const banResult = ref<Api.Fangyu.ClockBan | null>(null)

  const limitsForm = reactive<Api.Fangyu.ClockLimits>({
    enabled: false, banEnabled: false, banSeconds: 300, limits: {}
  })
  const banQuery = reactive({ dimension: 'ip', value: '' })
  const banForm = reactive({ dimension: 'ip', value: '', seconds: 300, reason: '' })

  const loadError = ref('')
  const configReady = ref(false)

  /** IPv4 / IPv6 / CIDR 基础校验 */
  const IPV4_RE = /^(\d{1,3}\.){3}\d{1,3}(\/\d{1,2})?$/
  const IPV6_RE = /^[0-9a-fA-F:]+(\/\d{1,3})?$/

  const validateDimensionValue = (dimension: string, value: string): string => {
    const trimmed = value.trim()
    if (!trimmed) return dimension === 'ip' ? '请输入 IP 地址' : '请输入设备指纹值'

    if (dimension === 'ip') {
      if (IPV4_RE.test(trimmed)) {
        const [addr, prefix] = trimmed.split('/')
        if (addr.split('.').some((seg) => Number(seg) > 255)) return 'IPv4 每段取值需在 0-255 之间'
        if (prefix !== undefined && Number(prefix) > 32) return 'IPv4 掩码长度需在 0-32 之间'
        return ''
      }
      if (trimmed.includes(':') && IPV6_RE.test(trimmed)) return ''
      return 'IP 格式不正确，请输入合法的 IPv4 / IPv6 地址或 CIDR'
    }

    if (trimmed.length < 8) return '指纹值长度过短，请确认是否完整'
    return ''
  }

  const formatDuration = (seconds: number) => {
    if (seconds >= 3600) return `${(seconds / 3600).toFixed(1)} 小时`
    if (seconds >= 60) return `${Math.round(seconds / 60)} 分钟`
    return `${seconds} 秒`
  }

  const loadConfig = async () => {
    configLoading.value = true
    loadError.value = ''
    try {
      const [limits, wins] = await Promise.all([
        fetchGetClockLimits(),
        fetchGetClockWindows()
      ])
      Object.assign(limitsForm, limits)
      windows.value = wins
      configReady.value = true
    } catch (err) {
      configReady.value = false
      loadError.value = '频控配置加载失败，当前显示的不是线上配置。为避免覆盖生产配置，保存已被禁用。'
      console.error('加载频控配置失败:', err)
    } finally { configLoading.value = false }
  }

  const saveLimits = async () => {
    if (limitsForm.banEnabled && !limitsForm.enabled) {
      ElMessage.warning('未启用频控时封禁不会生效，请先启用频控')
      return
    }

    const activeWindows = windows.value.filter((w) => (limitsForm.limits[w.name] ?? 0) > 0)
    if (limitsForm.enabled && !activeWindows.length) {
      ElMessage.warning('已启用频控但所有窗口阈值均为 0（不限），请至少设置一个窗口阈值')
      return
    }

    const banHint = limitsForm.banEnabled
      ? `超限来源将被自动封禁 ${formatDuration(limitsForm.banSeconds)}。`
      : '超限来源不会被自动封禁。'
    const confirmed = await ElMessageBox.confirm(
      `保存后新的频控阈值将同步到网关节点并立即对线上请求生效。${banHint}确认保存？`,
      '保存频控配置',
      { confirmButtonText: '保存', cancelButtonText: '取消', type: 'warning' }
    ).catch(() => false)
    if (!confirmed) return

    saving.value = true
    try {
      await fetchPutClockLimits({ ...limitsForm })
      ElMessage.success('频控配置已保存并同步到网关节点')
    } catch {
      ElMessage.error('保存失败，线上配置未变更，请稍后重试')
    } finally { saving.value = false }
  }

  const resetLimits = async () => {
    const confirmed = await ElMessageBox.confirm(
      '将恢复默认频控配置，当前的窗口阈值与封禁设置会立即被覆盖并同步到网关节点，操作不可撤销。',
      '恢复默认',
      { confirmButtonText: '恢复默认', cancelButtonText: '取消', type: 'warning' }
    ).catch(() => false)
    if (!confirmed) return

    try {
      const defaults = await fetchResetClockLimits()
      Object.assign(limitsForm, defaults)
      ElMessage.success('已恢复默认频控配置')
    } catch {
      ElMessage.error('恢复失败，请稍后重试')
    }
  }

  const resyncLimits = async () => {
    try {
      await fetchResyncClockLimits()
      ElMessage.success('已将当前频控配置重新同步到网关节点')
    } catch {
      ElMessage.error('同步失败，请稍后重试')
    }
  }

  const lookupBan = async () => {
    const err = validateDimensionValue(banQuery.dimension, banQuery.value)
    if (err) {
      ElMessage.warning(err)
      return
    }

    banLoading.value = true
    try {
      banResult.value = await fetchGetClockBan({
        dimension: banQuery.dimension,
        value: banQuery.value.trim()
      })
      if (!banResult.value) ElMessage.info(`${banQuery.value.trim()} 当前无封禁记录`)
    } catch {
      banResult.value = null
      ElMessage.error('查询失败，请稍后重试')
    } finally { banLoading.value = false }
  }

  const handleUnban = async () => {
    const err = validateDimensionValue(banQuery.dimension, banQuery.value)
    if (err) {
      ElMessage.warning(err)
      return
    }

    const target = banQuery.value.trim()
    const confirmed = await ElMessageBox.confirm(
      `确认解封「${target}」吗？解封后该来源将立即恢复访问，直到再次触发频控阈值。`,
      '解除封禁',
      { confirmButtonText: '解封', cancelButtonText: '取消', type: 'warning' }
    ).catch(() => false)
    if (!confirmed) return

    try {
      await fetchDeleteClockBan({ dimension: banQuery.dimension, value: target })
      banResult.value = null
      ElMessage.success(`${target} 已解封`)
    } catch {
      ElMessage.error('解封失败，请稍后重试')
    }
  }

  const createBan = async () => {
    const err = validateDimensionValue(banForm.dimension, banForm.value)
    if (err) {
      ElMessage.warning(err)
      return
    }

    const target = banForm.value.trim()
    const confirmed = await ElMessageBox.confirm(
      `确认封禁「${target}」${formatDuration(banForm.seconds)}吗？封禁生效后该来源的所有请求将被网关直接拦截。`,
      '手动封禁',
      { confirmButtonText: '封禁', cancelButtonText: '取消', type: 'warning' }
    ).catch(() => false)
    if (!confirmed) return

    try {
      await fetchCreateClockBan({ ...banForm, value: target })
      ElMessage.success(`${target} 已封禁 ${formatDuration(banForm.seconds)}`)
      Object.assign(banForm, { value: '', seconds: 300, reason: '' })
    } catch {
      ElMessage.error('封禁失败，请稍后重试')
    }
  }

  onMounted(loadConfig)
</script>
