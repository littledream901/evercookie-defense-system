<!-- 智能值输入器 -->
<template>
  <div class="smart-value-input">
    <!-- Bool 类型 -->
    <ElSelect
      v-if="fieldType === 'bool'"
      :model-value="modelValue"
      class="w-full"
      @update:model-value="handleChange"
    >
      <ElOption label="是 (true)" :value="true" />
      <ElOption label="否 (false)" :value="false" />
    </ElSelect>

    <!-- Enum 类型：有预定义选项 -->
    <template v-else-if="fieldType === 'enum' && options.length > 0">
      <!-- 列表操作符：多选 -->
      <ElSelect
        v-if="isMultiple"
        :model-value="modelValue"
        class="w-full"
        multiple
        collapse-tags
        collapse-tags-tooltip
        filterable
        @update:model-value="handleChange"
      >
        <ElOption
          v-for="opt in options"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        >
          <div class="option-item">
            <ElIcon v-if="opt.icon" class="option-icon">
              <component :is="opt.icon" />
            </ElIcon>
            <div class="option-content">
              <span class="option-label">{{ opt.label }}</span>
              <span v-if="opt.desc" class="option-desc">{{ opt.desc }}</span>
            </div>
          </div>
        </ElOption>
      </ElSelect>

      <!-- 单选 -->
      <ElSelect
        v-else
        :model-value="modelValue"
        class="w-full"
        filterable
        @update:model-value="handleChange"
      >
        <!-- 可空字段提供"空"选项 -->
        <ElOption
          v-if="nullable && !isMultiple"
          label="空（无数据）"
          :value="NULL_SENTINEL"
        />
        <ElOption
          v-for="opt in options"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        >
          <div class="option-item">
            <ElIcon v-if="opt.icon" class="option-icon">
              <component :is="opt.icon" />
            </ElIcon>
            <div class="option-content">
              <span class="option-label">{{ opt.label }}</span>
              <span v-if="opt.desc" class="option-desc">{{ opt.desc }}</span>
            </div>
          </div>
        </ElOption>
      </ElSelect>
    </template>

    <!-- 列表操作符（in/not_in）：多值标签输入 -->
    <ElSelect
      v-else-if="isMultiple"
      :model-value="modelValue"
      class="w-full"
      multiple
      allow-create
      filterable
      default-first-option
      :reserve-keyword="false"
      :placeholder="placeholder || '输入后按 Enter 确认'"
      @update:model-value="handleChange"
    >
      <!-- 常用值推荐 -->
      <ElOptionGroup v-if="commonValues.length > 0" label="常用值">
        <ElOption
          v-for="cv in commonValues"
          :key="cv.value"
          :label="cv.label"
          :value="cv.value"
        >
          <div class="option-item">
            <span class="option-label">{{ cv.label }}</span>
            <ElTag v-if="cv.count" size="small" type="info" effect="plain" class="ml-2">
              {{ cv.count }}
            </ElTag>
          </div>
        </ElOption>
      </ElOptionGroup>
    </ElSelect>

    <!-- 数字输入 -->
    <template v-else-if="fieldType === 'number'">
      <ElInputNumber
        :model-value="modelValue"
        class="w-full"
        :placeholder="placeholder"
        :min="range?.min"
        :max="range?.max"
        :step="getNumberStep()"
        @update:model-value="handleChange"
      />
      <div v-if="unit || recommendations.length > 0" class="input-helper">
        <span v-if="unit" class="unit-label">单位：{{ unit }}</span>
        <div v-if="recommendations.length > 0" class="recommendations">
          <span class="rec-label">建议：</span>
          <ElTag
            v-for="(rec, i) in recommendations.slice(0, 3)"
            :key="i"
            :type="rec.color"
            size="small"
            effect="plain"
            class="rec-tag"
            @click="handleRecommendationClick(rec)"
          >
            {{ rec.label }}
          </ElTag>
        </div>
      </div>
    </template>

    <!-- 文本输入 -->
    <template v-else>
      <ElInput
        :model-value="modelValue"
        :placeholder="placeholder || metadata?.hint || '请输入值'"
        clearable
        @update:model-value="handleChange"
      >
        <template v-if="examples.length > 0" #append>
          <ElDropdown @command="handleExampleSelect">
            <ElButton :icon="Guide" />
            <template #dropdown>
              <ElDropdownMenu>
                <ElDropdownItem
                  v-for="(ex, i) in examples.slice(0, 5)"
                  :key="i"
                  :command="ex"
                >
                  <code class="example-code">{{ formatExample(ex) }}</code>
                </ElDropdownItem>
              </ElDropdownMenu>
            </template>
          </ElDropdown>
        </template>
      </ElInput>
      <div v-if="recommendations.length > 0 || caseSensitive !== undefined" class="input-helper">
        <ElAlert
          v-if="caseSensitive === false"
          type="info"
          :closable="false"
          show-icon
          class="case-tip"
        >
          此字段不区分大小写
        </ElAlert>
        <div v-if="recommendations.length > 0" class="recommendations">
          <span class="rec-label">建议：</span>
          <ElTag
            v-for="(rec, i) in recommendations.slice(0, 3)"
            :key="i"
            :type="rec.color"
            size="small"
            effect="plain"
            class="rec-tag"
            @click="handleRecommendationClick(rec)"
          >
            {{ rec.label }}
          </ElTag>
        </div>
      </div>
    </template>

    <!-- 字段提示信息 -->
    <div v-if="showHint && metadata?.hint" class="field-hint">
      <ElIcon><InfoFilled /></ElIcon>
      <span>{{ metadata.hint }}</span>
      <ElLink
        v-if="metadata.learnMore"
        :href="metadata.learnMore"
        type="primary"
        :underline="false"
        target="_blank"
        class="ml-2"
      >
        了解更多
      </ElLink>
    </div>

    <!-- 风险提示 -->
    <ElAlert
      v-if="riskHint"
      :type="riskLevel === 'high' ? 'error' : 'warning'"
      :closable="false"
      show-icon
      class="risk-alert"
    >
      {{ riskHint }}
    </ElAlert>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { InfoFilled, Guide } from '@element-plus/icons-vue'
import { ALL_FIELDS, type FieldMetadata } from '@/constants/fieldMetadata'

// 空值哨兵
const NULL_SENTINEL = '__NULL__'

// ========== Props & Emits ==========
interface Props {
  modelValue: any
  fieldKey: string
  operator?: string
  showHint?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  operator: 'eq',
  showHint: false
})

const emit = defineEmits<{
  'update:modelValue': [value: any]
  'change': [value: any]
}>()

// ========== Computed ==========
// 字段元数据
const metadata = computed<FieldMetadata | undefined>(() => ALL_FIELDS[props.fieldKey])

// 字段类型
const fieldType = computed(() => metadata.value?.type || 'string')

// 是否多选（in/not_in 操作符）
const isMultiple = computed(() => {
  const listOps = ['in', 'not_in', 'contains_all', 'contains_any']
  return listOps.includes(props.operator)
})

// 预定义选项
const options = computed(() => metadata.value?.options || [])

// 是否可空
const nullable = computed(() => metadata.value?.nullable || false)

// 占位符
const placeholder = computed(() => metadata.value?.placeholder || '')

// 数字范围
const range = computed(() => metadata.value?.range)

// 单位
const unit = computed(() => metadata.value?.unit || '')

// 示例值
const examples = computed(() => metadata.value?.examples || [])

// 大小写敏感
const caseSensitive = computed(() => metadata.value?.caseSensitive)

// 常用值
const commonValues = computed(() => metadata.value?.commonValues || [])

// 推荐值
const recommendations = computed(() => metadata.value?.recommendations || [])

// 风险级别
const riskLevel = computed(() => metadata.value?.riskLevel || 'low')

// 风险提示
const riskHint = computed(() => {
  if (!metadata.value) return ''
  
  // 脏字段警告
  if (metadata.value.nullable && props.operator === 'eq' && props.modelValue === NULL_SENTINEL) {
    return '⚠️ 该字段可能为空，使用 "等于空" 可能导致规则落空'
  }
  
  // 否定操作符 + 可空字段 = 误杀风险
  const negativeOps = ['neq', 'not_in', 'not_contains']
  if (metadata.value.nullable && negativeOps.includes(props.operator)) {
    return '⚠️ 该字段可能为空，使用否定操作符会排除所有空值数据，可能导致误杀'
  }
  
  return ''
})

// ========== Methods ==========
function handleChange(value: any) {
  emit('update:modelValue', value)
  emit('change', value)
}

function handleExampleSelect(example: any) {
  handleChange(example)
}

function handleRecommendationClick(rec: any) {
  if (rec.value !== undefined) {
    handleChange(rec.value)
  }
}

function formatExample(value: any): string {
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (value === null) return 'null'
  return String(value)
}

function getNumberStep(): number {
  if (!metadata.value?.range) return 1
  const diff = metadata.value.range.max - metadata.value.range.min
  if (diff > 1000) return 100
  if (diff > 100) return 10
  return 1
}
</script>

<style scoped lang="scss">
.smart-value-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

// ========== 选项条目 ==========
.option-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;

  .option-icon {
    flex-shrink: 0;
    color: var(--el-text-color-secondary);
  }

  .option-content {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
    min-width: 0;
  }

  .option-label {
    font-size: 13px;
    color: var(--el-text-color-primary);
  }

  .option-desc {
    font-size: 11px;
    color: var(--el-text-color-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

// ========== 输入辅助信息 ==========
.input-helper {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;

  .unit-label {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .recommendations {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;

    .rec-label {
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }

    .rec-tag {
      cursor: pointer;
      transition: all 0.2s;

      &:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
      }
    }
  }

  .case-tip {
    padding: 4px 8px;
    font-size: 12px;

    :deep(.el-alert__content) {
      padding: 0;
    }
  }
}

// ========== 字段提示 ==========
.field-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;

  .el-icon {
    color: var(--el-color-info);
    flex-shrink: 0;
  }
}

// ========== 风险提示 ==========
.risk-alert {
  margin-top: 4px;
  font-size: 12px;

  :deep(.el-alert__content) {
    padding: 0;
  }
}

// ========== 示例代码 ==========
.example-code {
  font-size: 12px;
  padding: 2px 6px;
  background: var(--el-fill-color-light);
  border-radius: 3px;
  color: var(--el-text-color-regular);
  font-family: 'Monaco', 'Consolas', monospace;
}
</style>
