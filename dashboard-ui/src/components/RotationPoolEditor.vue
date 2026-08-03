<template>
  <div class="rotation-pool-editor">
    <!-- 策略选择 -->
    <ElFormItem label="轮询策略" label-width="70px">
      <ElSelect v-model="localRotation.strategy" class="w-full" @change="emit('update:rotation', localRotation)">
        <ElOption
          v-for="opt in ROTATION_STRATEGY_OPTIONS"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        >
          <div class="flex items-center justify-between w-full">
            <span>{{ opt.label }}</span>
            <ElTag
              :type="ROTATION_STRATEGY_TAGS[opt.value]"
              size="small"
              effect="plain"
              class="ml-2"
            >
              {{ opt.value }}
            </ElTag>
          </div>
          <div v-if="opt.desc" class="text-xs text-g-400 mt-1">{{ opt.desc }}</div>
        </ElOption>
      </ElSelect>
    </ElFormItem>

    <!-- 地址池列表 -->
    <ElFormItem label="地址池" label-width="70px">
      <div class="w-full space-y-2">
        <div
          v-for="(entry, idx) in localRotation.entries"
          :key="idx"
          class="flex items-start gap-2 p-2 rounded"
          :class="entry.enabled ? 'bg-g-50' : 'bg-g-25'"
        >
          <div class="flex-1">
            <ElInput
              v-model="entry.url"
              placeholder="https://example.com 支持变量"
              size="small"
              @input="emit('update:rotation', localRotation)"
            >
              <template #prepend>
                <span class="text-xs text-g-500 w-8 text-center">{{ idx + 1 }}</span>
              </template>
            </ElInput>
            <!-- 权重滑块 -->
            <div v-if="showWeights" class="flex items-center gap-2 mt-1">
              <span class="text-xs text-g-500 w-12">权重</span>
              <ElSlider
                v-model="entry.weight"
                :min="0"
                :max="100"
                :show-tooltip="true"
                class="flex-1"
                @change="emit('update:rotation', localRotation)"
              />
              <ElInputNumber
                v-model="entry.weight"
                :min="0"
                :max="100"
                :step="1"
                size="small"
                style="width:70px"
                @change="emit('update:rotation', localRotation)"
              />
            </div>
            <!-- 配额控制 -->
            <div v-if="quotaEnabled[idx]" class="flex items-center gap-2 mt-1">
              <span class="text-xs text-g-500 w-12">配额</span>
              <ElInputNumber
                v-model="entry.dailyQuota"
                :min="1"
                :max="999999999"
                placeholder="每日上限"
                size="small"
                style="width:120px"
                clearable
                @change="emit('update:rotation', localRotation)"
              >
                <template #suffix>
                  <span class="text-xs text-g-400">/日</span>
                </template>
              </ElInputNumber>
              <ElInputNumber
                v-model="entry.hourlyQuota"
                :min="1"
                :max="999999999"
                placeholder="每小时上限"
                size="small"
                style="width:120px"
                clearable
                @change="emit('update:rotation', localRotation)"
              >
                <template #suffix>
                  <span class="text-xs text-g-400">/时</span>
                </template>
              </ElInputNumber>
            </div>
          </div>
          <div class="flex items-center gap-1 pt-0.5">
            <ElSwitch
              v-model="quotaEnabled[idx]"
              size="small"
              active-text="配额"
              inactive-text="不限"
              inline-prompt
              @change="toggleQuota(idx)"
            />
            <ElSwitch
              v-model="entry.enabled"
              size="small"
              :active-text="entry.enabled ? '启用' : '禁用'"
              inline-prompt
              @change="emit('update:rotation', localRotation)"
            />
            <ElButton
              type="danger"
              size="small"
              text
              :icon="Delete"
              :disabled="localRotation.entries.length <= 1"
              @click="removeEntry(idx)"
            />
          </div>
        </div>

        <ElButton
          type="primary"
          size="small"
          text
          :icon="Plus"
          :disabled="localRotation.entries.length >= 32"
          @click="addEntry"
        >
          添加地址 ({{ localRotation.entries.length }}/32)
        </ElButton>
      </div>
    </ElFormItem>

    <!-- 策略说明 -->
    <ElAlert
      v-if="strategyTip"
      :title="strategyTip"
      type="info"
      :closable="false"
      show-icon
      class="mt-2"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'
import {
  ROTATION_STRATEGY_OPTIONS,
  ROTATION_STRATEGY_TAGS,
  createPoolEntry
} from '@/constants/disposition'

interface Props {
  rotation: Api.Fangyu.Rotation
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:rotation': [rotation: Api.Fangyu.Rotation]
}>()

const localRotation = ref<Api.Fangyu.Rotation>({ ...props.rotation })

// 配额开关状态（根据 dailyQuota/hourlyQuota 是否为 null 推导）
const quotaEnabled = ref<boolean[]>(
  props.rotation.entries.map((e) => e.dailyQuota !== null || e.hourlyQuota !== null)
)

watch(
  () => props.rotation,
  (newVal) => {
    localRotation.value = { ...newVal }
    quotaEnabled.value = newVal.entries.map((e) => e.dailyQuota !== null || e.hourlyQuota !== null)
  },
  { deep: true }
)

const showWeights = computed(() => localRotation.value.strategy === 'weighted')

/**
 * 切换配额开关
 *
 * 开启时给每日上限一个默认值而非留空：两个字段都是 null 等于没配额，
 * 开关显示「已开启」却毫无约束，是最容易被误读为生效的状态。
 * 关闭时清空两个字段——后端以 null 判定不限流。
 */
function toggleQuota(idx: number) {
  const entry = localRotation.value.entries[idx]
  if (quotaEnabled.value[idx]) {
    entry.dailyQuota = 1000
    entry.hourlyQuota = null
  } else {
    entry.dailyQuota = null
    entry.hourlyQuota = null
  }
  emit('update:rotation', localRotation.value)
}

const strategyTip = computed(() => {
  const tips: Record<string, string> = {
    hash: '无状态哈希分摊：按请求 ID 取模，近似均匀但短时间内可能倾斜',
    weighted: '权重分配：按权重比例分流,适合灰度放量(90% 主 + 10% 灰度)',
    sticky: '访客粘性：同一访客固定地址,保证会话连续性,牺牲分摊均匀度',
    round_robin: '严格轮转：需 Redis 计数器,每次决策多一次写操作',
    failover: '主备容灾：按顺序优先,健康检查失败才切换到下一个'
  }
  return tips[localRotation.value.strategy] || ''
})

function addEntry() {
  if (localRotation.value.entries.length >= 32) return
  localRotation.value.entries.push(createPoolEntry())
  quotaEnabled.value.push(false)
  emit('update:rotation', localRotation.value)
}

function removeEntry(idx: number) {
  if (localRotation.value.entries.length <= 1) return
  localRotation.value.entries.splice(idx, 1)
  quotaEnabled.value.splice(idx, 1)
  emit('update:rotation', localRotation.value)
}
</script>

<style scoped>
.rotation-pool-editor {
  width: 100%;
}
</style>
