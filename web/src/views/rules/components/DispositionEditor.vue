<template>
  <div class="disposition-editor">
    <div class="disp-presets">
      <span class="disp-presets__label">快速预设</span>
      <n-button
        v-for="preset in DISPOSITION_PRESETS"
        :key="preset.value"
        size="tiny"
        secondary
        @click="applyPreset(preset)"
      >
        {{ preset.label }}
      </n-button>
    </div>

    <div class="disp-row">
      <div class="disp-field">
        <span class="disp-field__label">裁决（为什么）</span>
        <n-select
          :value="modelValue.verdict"
          :options="VERDICT_OPTIONS"
          @update:value="(v) => patch({ verdict: v })"
        />
      </div>
      <div class="disp-field">
        <span class="disp-field__label">机制（怎么做）</span>
        <n-select
          :value="modelValue.mechanism"
          :options="MECHANISM_OPTIONS"
          @update:value="onMechanismChange"
        />
      </div>
    </div>

    <div class="disp-row">
      <div class="disp-field">
        <span class="disp-field__label">目标类型（去哪）</span>
        <n-select
          :value="modelValue.target?.kind"
          :options="TARGET_KIND_OPTIONS"
          @update:value="(v) => patchTarget({ kind: v })"
        />
      </div>
      <div v-if="needsUrl" class="disp-field disp-field--grow">
        <span class="disp-field__label">
          目标 URL
          <n-tooltip placement="top-start">
            <template #trigger><span class="disp-hint">占位符</span></template>
            支持 {host} {path} {query} {url} {app_id} {request_id}，由网关按每次请求渲染
          </n-tooltip>
        </span>
        <n-input
          :value="modelValue.target?.url"
          placeholder="https://{host}/verify?from={path}"
          @update:value="(v) => patchTarget({ url: v || null })"
        />
      </div>
    </div>

    <div class="disp-row">
      <div v-if="modelValue.mechanism === 'challenge'" class="disp-field">
        <span class="disp-field__label">挑战类型</span>
        <n-select
          :value="modelValue.challengeKind"
          :options="CHALLENGE_KIND_OPTIONS"
          @update:value="(v) => patch({ challengeKind: v })"
        />
      </div>
      <div class="disp-field">
        <span class="disp-field__label">HTTP 状态码</span>
        <n-input-number
          :value="modelValue.target?.httpStatus"
          :placeholder="`默认 ${defaultStatus}`"
          :min="100"
          :max="599"
          clearable
          @update:value="(v) => patchTarget({ httpStatus: v })"
        />
      </div>
      <div class="disp-field">
        <span class="disp-field__label">缓存时长（秒）</span>
        <n-input-number
          :value="modelValue.ttlSeconds"
          :min="0"
          :max="86400"
          @update:value="(v) => patch({ ttlSeconds: v ?? 0 })"
        />
      </div>
    </div>

    <n-alert v-if="errorMsg" type="warning" :bordered="false" class="disp-alert">
      {{ errorMsg }}
    </n-alert>
    <div v-else class="disp-summary">
      <n-tag :type="VERDICT_TAGS[modelValue.verdict]" size="small">
        {{ modelValue.verdict }}
      </n-tag>
      <span class="disp-summary__arrow">→</span>
      <n-tag :type="MECHANISM_TAGS[modelValue.mechanism]" size="small">
        {{ modelValue.mechanism }}
      </n-tag>
      <span class="disp-summary__text">
        HTTP {{ modelValue.target?.httpStatus || defaultStatus }}
        <template v-if="modelValue.target?.url">· {{ modelValue.target.url }}</template>
        · 缓存 {{ modelValue.ttlSeconds }}s
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { NAlert, NButton, NInput, NInputNumber, NSelect, NTag, NTooltip } from 'naive-ui'
import {
  CHALLENGE_KIND_OPTIONS,
  DISPOSITION_PRESETS,
  MECHANISM_OPTIONS,
  MECHANISM_STATUS,
  MECHANISM_TAGS,
  TARGET_KIND_OPTIONS,
  URL_REQUIRED_MECHANISMS,
  URL_REQUIRED_TARGET_KINDS,
  VERDICT_OPTIONS,
  VERDICT_TAGS,
  validateDisposition,
} from '../utils/dispositionDefs'

const props = defineProps({
  modelValue: { type: Object, required: true },
})
const emit = defineEmits(['update:modelValue'])

const needsUrl = computed(
  () =>
    URL_REQUIRED_MECHANISMS.includes(props.modelValue.mechanism) ||
    URL_REQUIRED_TARGET_KINDS.includes(props.modelValue.target?.kind),
)

const defaultStatus = computed(() => MECHANISM_STATUS[props.modelValue.mechanism] ?? 200)
const errorMsg = computed(() => validateDisposition(props.modelValue))

function patch(partial) {
  emit('update:modelValue', { ...props.modelValue, ...partial })
}

function patchTarget(partial) {
  patch({ target: { ...(props.modelValue.target || {}), ...partial } })
}

// 机制切换时同步收敛互斥字段，避免提交时被后端校验器拒绝
function onMechanismChange(mechanism) {
  const next = { ...props.modelValue, mechanism }
  if (mechanism !== 'challenge') {
    next.challengeKind = null
  } else if (!next.challengeKind) {
    next.challengeKind = 'captcha'
  }
  if (mechanism === 'redirect' && next.target?.kind === 'origin') {
    next.target = { ...next.target, kind: 'url' }
  }
  emit('update:modelValue', next)
}

function applyPreset(preset) {
  emit('update:modelValue', preset.build())
}
</script>

<style scoped>
.disposition-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.disp-presets {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.disp-presets__label {
  font-size: 12px;
  color: #888;
  margin-right: 2px;
}
.disp-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}
.disp-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 150px;
  flex: 1;
}
.disp-field--grow {
  flex: 2;
}
.disp-field__label {
  font-size: 12px;
  color: #666;
}
.disp-hint {
  margin-left: 4px;
  font-size: 11px;
  color: #2080f0;
  cursor: help;
  border-bottom: 1px dashed #2080f0;
}
.disp-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: #fafafa;
  border-radius: 3px;
  font-size: 12px;
}
.disp-summary__arrow {
  color: #aaa;
}
.disp-summary__text {
  color: #666;
  font-family: monospace;
}
.disp-alert {
  padding: 6px 10px;
  font-size: 12px;
}
</style>
