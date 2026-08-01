<template>
  <CommonPage title="频控配置" subtitle="按应用维护频率阈值与封禁">
    <template #action>
      <n-select
        v-model:value="appId"
        :options="appOptions"
        placeholder="选择应用"
        style="width: 180px"
        @update:value="loadAll"
      />
      <n-button :disabled="!appId" @click="confirmReset">恢复默认</n-button>
      <n-button type="primary" :disabled="!appId" :loading="saving" @click="save">保存阈值</n-button>
    </template>

    <n-spin :show="loading">
      <n-card title="阈值设置" size="small" class="section">
        <n-space align="center" class="switches">
          <n-switch v-model:value="limits.enabled">
            <template #checked>频控已启用</template>
            <template #unchecked>频控已停用</template>
          </n-switch>
          <n-switch v-model:value="limits.banEnabled">
            <template #checked>超限自动封禁</template>
            <template #unchecked>仅拦截不封禁</template>
          </n-switch>
          <span class="ban-seconds">
            封禁时长（秒）
            <n-input-number
              v-model:value="limits.banSeconds"
              :min="1"
              :max="MAX_BAN_SECONDS"
              style="width: 140px"
            />
          </span>
        </n-space>

        <n-alert type="info" :bordered="false" class="hint">
          阈值为「单位窗口内允许的最大请求数」，留空或 0 表示该窗口不限制。窗口宽度由后端定义，避免前后端各写一套。
        </n-alert>

        <n-table :single-line="false" size="small">
          <thead>
            <tr>
              <th style="width: 200px">窗口</th>
              <th style="width: 120px">宽度</th>
              <th>阈值（次）</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="w in windows" :key="w.name">
              <td><code>{{ w.name }}</code></td>
              <td>{{ formatSeconds(w.seconds) }}</td>
              <td>
                <n-input-number
                  v-model:value="limits.windows[w.name]"
                  :min="0"
                  placeholder="不限制"
                  clearable
                  style="width: 180px"
                />
              </td>
            </tr>
          </tbody>
        </n-table>
      </n-card>

      <n-card title="封禁管理" size="small" class="section">
        <n-alert type="warning" :bordered="false" class="hint">
          维度为 IP 时，取值必须是网关侧同算法的 IP 哈希（sha256 前 32 位），填明文 IP 不会命中。
        </n-alert>

        <div class="ban-form">
          <n-select v-model:value="banForm.dimension" :options="dimensionOptions" style="width: 140px" />
          <n-input v-model:value="banForm.value" placeholder="IP 哈希 / 指纹" style="width: 300px" />
          <n-input-number v-model:value="banForm.seconds" :min="1" placeholder="秒" style="width: 120px" />
          <n-input v-model:value="banForm.reason" placeholder="封禁原因" style="width: 180px" />
          <n-button type="error" :disabled="!canOperateBan" @click="createBan">封禁</n-button>
          <n-button :disabled="!canOperateBan" @click="queryBan">查询</n-button>
          <n-button :disabled="!canOperateBan" @click="removeBan">解封</n-button>
        </div>

        <n-descriptions v-if="banResult" :column="4" bordered size="small" class="ban-result">
          <n-descriptions-item label="维度">{{ banResult.dimension }}</n-descriptions-item>
          <n-descriptions-item label="取值">
            <code>{{ banResult.value }}</code>
          </n-descriptions-item>
          <n-descriptions-item label="原因">{{ banResult.reason || '-' }}</n-descriptions-item>
          <n-descriptions-item label="剩余">{{ formatSeconds(banResult.ttlSeconds) }}</n-descriptions-item>
        </n-descriptions>
        <n-empty v-else-if="banQueried" description="该对象当前未被封禁" class="ban-result" />
      </n-card>
    </n-spin>
  </CommonPage>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import CommonPage from '@/components/CommonPage.vue'
import { appsApi } from '@/api/apps'
import { clockApi } from '@/api/clock'

const MAX_BAN_SECONDS = 86400 * 7

const message = useMessage()
const dialog = useDialog()
const appId = ref(null)
const appOptions = ref([])
const windows = ref([])
const loading = ref(false)
const saving = ref(false)
const banResult = ref(null)
const banQueried = ref(false)

const limits = reactive({
  enabled: true,
  banEnabled: true,
  banSeconds: 900,
  windows: {},
})

const banForm = reactive({
  dimension: 'ip',
  value: '',
  seconds: 900,
  reason: '',
})

const dimensionOptions = [
  { label: 'IP', value: 'ip' },
  { label: '指纹', value: 'fingerprint' },
]

const canOperateBan = computed(() => Boolean(appId.value && banForm.value.trim()))

function formatSeconds(sec) {
  const n = Number(sec) || 0
  if (n <= 0) return '-'
  if (n < 60) return `${n} 秒`
  if (n < 3600) return `${Math.round(n / 60)} 分钟`
  if (n < 86400) return `${(n / 3600).toFixed(1)} 小时`
  return `${(n / 86400).toFixed(1)} 天`
}

async function loadApps() {
  const resp = await appsApi.list({ page: 1, pageSize: 100 })
  appOptions.value = (resp.data?.items || []).map((a) => ({ label: a.name, value: a.id }))
  if (!appId.value && appOptions.value[0]) appId.value = appOptions.value[0].value
}

async function loadAll() {
  if (!appId.value) return
  loading.value = true
  banResult.value = null
  banQueried.value = false
  try {
    const [winResp, limitResp] = await Promise.all([
      clockApi.listWindows(appId.value),
      clockApi.getLimits(appId.value),
    ])
    windows.value = winResp.data || []

    const data = limitResp.data || {}
    limits.enabled = data.enabled ?? true
    limits.banEnabled = data.banEnabled ?? true
    limits.banSeconds = data.banSeconds ?? 900
    // 用后端窗口清单初始化，未配置的窗口显示为空而不是消失
    const next = {}
    windows.value.forEach((w) => {
      next[w.name] = data.windows?.[w.name] ?? null
    })
    limits.windows = next
  } catch (e) {
    message.error(e.message || '加载频控配置失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    // 只提交有正整数阈值的窗口，null/0 视为不限制
    const payload = {}
    Object.entries(limits.windows).forEach(([name, value]) => {
      if (value !== null && value !== '' && Number(value) > 0) payload[name] = Number(value)
    })
    await clockApi.putLimits(appId.value, {
      enabled: limits.enabled,
      banEnabled: limits.banEnabled,
      banSeconds: limits.banSeconds,
      windows: payload,
    })
    message.success('阈值已保存并同步至网关')
    await loadAll()
  } catch (e) {
    message.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function confirmReset() {
  dialog.warning({
    title: '恢复默认阈值',
    content: '将清除该应用的自定义阈值，网关回退到系统默认值。确定继续？',
    positiveText: '恢复',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await clockApi.resetLimits(appId.value)
        message.success('已恢复默认')
        await loadAll()
      } catch (e) {
        message.error(e.message || '操作失败')
      }
    },
  })
}

async function createBan() {
  try {
    await clockApi.createBan(appId.value, {
      dimension: banForm.dimension,
      value: banForm.value.trim(),
      seconds: banForm.seconds,
      reason: banForm.reason,
    })
    message.success('已封禁')
    await queryBan()
  } catch (e) {
    message.error(e.message || '封禁失败')
  }
}

async function queryBan() {
  try {
    const resp = await clockApi.getBan(appId.value, {
      dimension: banForm.dimension,
      value: banForm.value.trim(),
    })
    banResult.value = resp.data || null
    banQueried.value = true
  } catch (e) {
    message.error(e.message || '查询失败')
  }
}

async function removeBan() {
  try {
    const resp = await clockApi.deleteBan(appId.value, {
      dimension: banForm.dimension,
      value: banForm.value.trim(),
    })
    if (resp.data?.removed) {
      message.success('已解封')
    } else {
      message.info('该对象本来就未被封禁')
    }
    banResult.value = null
    banQueried.value = true
  } catch (e) {
    message.error(e.message || '解封失败')
  }
}

onMounted(async () => {
  await loadApps()
  await loadAll()
})
</script>

<style scoped>
.section {
  margin-bottom: 16px;
}
.switches {
  margin-bottom: 12px;
}
.ban-seconds {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.hint {
  margin-bottom: 12px;
}
.ban-form {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.ban-result {
  margin-top: 12px;
}
</style>
