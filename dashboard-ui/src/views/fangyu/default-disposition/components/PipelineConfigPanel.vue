<!-- 流水线配置组件 -->
<template>
  <ElCard shadow="never">
    <template #header>
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span>决策流水线配置</span>
          <ElTooltip placement="top" :show-after="300">
            <template #content>
              控制决策流水线各阶段是否执行。关闭后该阶段将被跳过，不执行任何检查逻辑。<br />
              未配置时默认全部启用。配置后约 30 秒同步到网关节点生效。
            </template>
            <ElIcon class="text-g-400 cursor-help"><QuestionFilled /></ElIcon>
          </ElTooltip>
        </div>
        <ElButton
          v-if="modelValue && !inheritGlobal"
          link
          type="primary"
          size="small"
          @click="$emit('reset')"
        >
          恢复默认
        </ElButton>
      </div>
    </template>

    <ElAlert
      v-if="inheritGlobal && mode === 'site'"
      type="success"
      show-icon
      :closable="false"
      class="mb-4"
    >
      当前站点继承全局流水线配置
    </ElAlert>

    <div class="flex flex-col gap-3">
      <div
        v-for="(stage, idx) in pipelineStages"
        :key="stage.key"
        class="flex items-start gap-3 rounded border px-4 py-3"
        :class="getStageEnabled(stage.key) ? 'border-g-200 bg-white' : 'border-g-200 bg-g-50'"
      >
        <span
          class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-medium"
          :class="getStageEnabled(stage.key) ? 'bg-primary text-white' : 'bg-g-200 text-g-500'"
        >{{ idx + 1 }}</span>
        
        <div class="min-w-0 flex-1">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="text-sm font-medium" :class="getStageEnabled(stage.key) ? 'text-g-800' : 'text-g-400'">
                {{ stage.label }}
              </span>
              <ElTag v-if="stage.badge" size="small" :type="stage.badgeType">{{ stage.badge }}</ElTag>
            </div>
            <ElSwitch
              :model-value="getStageEnabled(stage.key)"
              :disabled="disabled || loading"
              @change="(val: string | number | boolean) => setStageEnabled(stage.key, val as boolean)"
            />
          </div>
          <div class="mt-1 text-xs" :class="getStageEnabled(stage.key) ? 'text-g-500' : 'text-g-400'">
            {{ stage.description }}
          </div>
        </div>
      </div>
    </div>
  </ElCard>
</template>

<script setup lang="ts">
import { QuestionFilled } from '@element-plus/icons-vue'

interface PipelineStage {
  key: 'whitelistEnabled' | 'clockEnabled' | 'threatIntelEnabled' | 'securityEnabled' | 'rulesEnabled' | 'scoringEnabled'
  label: string
  description: string
  badge?: string
  badgeType?: 'success' | 'info' | 'warning'
}

interface Props {
  modelValue: Api.Fangyu.PipelineConfigPayload | null
  mode: 'global' | 'site'
  inheritGlobal?: boolean
  disabled?: boolean
  loading?: boolean
}

interface Emits {
  (e: 'update:modelValue', value: Api.Fangyu.PipelineConfigPayload): void
  (e: 'reset'): void
}

const props = withDefaults(defineProps<Props>(), {
  inheritGlobal: false,
  disabled: false,
  loading: false
})

const emit = defineEmits<Emits>()

const pipelineStages: PipelineStage[] = [
  {
    key: 'whitelistEnabled',
    label: '白名单',
    description: 'IP / 指纹白名单，命中直接放行，跳过后续所有检查（误封兜底通道）',
    badge: '最前',
    badgeType: 'success'
  },
  {
    key: 'clockEnabled',
    label: '频控',
    description: '访问频率限制与封禁检查，超限立即拦截（前置于缓存，确保每个请求都被计数）'
  },
  {
    key: 'threatIntelEnabled',
    label: '威胁情报',
    description: 'IP 威胁情报检查，检测已知恶意 IP、僵尸网络、代理池等'
  },
  {
    key: 'securityEnabled',
    label: '安全检查',
    description: '基础安全检查：Scanner / VPN+数据中心 / Tor / 黑名单 / 地理围栏'
  },
  {
    key: 'rulesEnabled',
    label: '决策规则',
    description: '自定义决策规则匹配，支持多维度条件组合与 allowlist 组兜底',
    badge: '核心',
    badgeType: 'warning'
  },
  {
    key: 'scoringEnabled',
    label: '风险评分',
    description: '多维度风险评分聚合（IP 声誉、代理检测、UA、设备、行为等），分数决定裁决'
  }
]

const getStageEnabled = (key: PipelineStage['key']): boolean => {
  if (!props.modelValue) return true // 默认全部启用
  return props.modelValue[key] ?? true
}

const setStageEnabled = (key: PipelineStage['key'], enabled: boolean) => {
  const newValue = props.modelValue ? { ...props.modelValue } : {
    whitelistEnabled: true,
    clockEnabled: true,
    threatIntelEnabled: true,
    securityEnabled: true,
    rulesEnabled: true,
    scoringEnabled: true
  }
  newValue[key] = enabled
  emit('update:modelValue', newValue)
}
</script>

<style scoped>
/* 自定义样式 */
</style>
