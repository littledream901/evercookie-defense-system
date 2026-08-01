<template>
  <div class="condition-builder">
    <div v-for="(cond, idx) in modelValue" :key="idx" class="condition-row">
      <div class="condition-row__index">
        <span v-if="idx > 0" class="cond-logic">AND</span>
        <span v-else class="cond-logic cond-logic--placeholder">条件</span>
      </div>

      <n-select
        class="condition-row__field"
        :value="cond.field"
        :options="fieldOptions"
        filterable
        placeholder="选择字段"
        @update:value="(v) => onFieldChange(idx, v)"
      />

      <n-select
        class="condition-row__op"
        :value="cond.op"
        :options="getOpOptions(cond.field)"
        placeholder="操作符"
        @update:value="(v) => update(idx, 'op', v)"
      />

      <component
        :is="getValueComponent(cond)"
        v-bind="getValueProps(cond, idx)"
        class="condition-row__value"
        @update="(v) => update(idx, 'value', v)"
      />

      <n-button text class="condition-row__del" title="删除该条件" @click="remove(idx)">
        <div class="i-ion-close text-16px" />
      </n-button>
    </div>

    <div class="condition-builder__footer">
      <n-button dashed size="small" @click="addCondition">
        <template #icon><div class="i-ion-add" /></template>
        添加条件
      </n-button>
      <n-tooltip v-if="modelValue.length > 0" placement="top-start">
        <template #trigger>
          <span class="cond-preview">{{ previewText }}</span>
        </template>
        当前条件逻辑：所有条件同时满足（AND）才命中规则
      </n-tooltip>
    </div>
  </div>
</template>

<script setup>
import { computed, h } from 'vue'
import { NDynamicTags, NInput, NInputNumber, NSelect, NSwitch } from 'naive-ui'
import { FIELD_GROUPS, FIELD_MAP, OPERATOR_LABELS, getOperatorOptions } from '../utils/fieldDefs'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const fieldOptions = FIELD_GROUPS.map((g) => ({
  type: 'group',
  label: g.label,
  key: g.label,
  children: g.fields.map((f) => ({ label: `${f.label}  (${f.value})`, value: f.value })),
}))

function getOpOptions(fieldValue) {
  return getOperatorOptions(fieldValue)
}

function onFieldChange(idx, newField) {
  const list = [...props.modelValue]
  const def = FIELD_MAP[newField]
  const defaultOp = def?.ops?.[0] ?? 'eq'
  const defaultValue = defaultValueFor(def?.type ?? 'string', defaultOp)
  list[idx] = { field: newField, op: defaultOp, value: defaultValue }
  emit('update:modelValue', list)
}

function update(idx, key, val) {
  const list = [...props.modelValue]
  if (key === 'op') {
    const def = FIELD_MAP[list[idx].field]
    list[idx] = { ...list[idx], op: val, value: defaultValueFor(def?.type ?? 'string', val) }
  } else {
    list[idx] = { ...list[idx], [key]: val }
  }
  emit('update:modelValue', list)
}

function remove(idx) {
  const list = [...props.modelValue]
  list.splice(idx, 1)
  emit('update:modelValue', list)
}

function addCondition() {
  emit('update:modelValue', [...props.modelValue, { field: '', op: 'eq', value: '' }])
}

function defaultValueFor(type, op) {
  if (['in', 'not_in', 'in_ci', 'not_in_ci', 'asn_in', 'asn_not_in', 'cidr_list_in', 'cidr_list_not_in'].includes(op)) return []
  if (type === 'bool') return true
  if (type === 'number' || type === 'asn') return null
  return ''
}

const BOOL_OPS = new Set(['eq'])
const LIST_OPS = new Set(['in', 'not_in', 'in_ci', 'not_in_ci', 'asn_in', 'asn_not_in', 'cidr_list_in', 'cidr_list_not_in'])

function getValueComponent(cond) {
  const def = FIELD_MAP[cond.field]
  const type = def?.type ?? 'string'
  const op = cond.op

  if (LIST_OPS.has(op)) return ValueListInput
  if (type === 'bool') return ValueBoolInput
  if (type === 'number' || type === 'asn') return ValueNumberInput
  if (type === 'enum' && def?.options) return ValueEnumInput
  return ValueStringInput
}

function getValueProps(cond, idx) {
  const def = FIELD_MAP[cond.field]
  return { value: cond.value, def, idx }
}

const previewText = computed(() => {
  if (!props.modelValue.length) return ''
  const parts = props.modelValue.map((c) => {
    const fieldDef = FIELD_MAP[c.field]
    const fieldLabel = fieldDef?.label ?? c.field
    const opLabel = OPERATOR_LABELS[c.op] ?? c.op
    const valLabel = Array.isArray(c.value) ? `[${c.value.join(', ')}]` : String(c.value ?? '')
    return `${fieldLabel} ${opLabel} ${valLabel}`
  })
  return parts.join(' AND ')
})

const ValueStringInput = {
  props: ['value', 'def'],
  emits: ['update'],
  setup(props, { emit }) {
    return () =>
      h(NInput, {
        value: props.value,
        placeholder: props.def?.hint ?? '输入值',
        clearable: true,
        'onUpdate:value': (v) => emit('update', v),
      })
  },
}

const ValueNumberInput = {
  props: ['value', 'def'],
  emits: ['update'],
  setup(props, { emit }) {
    const isAsn = props.def?.type === 'asn'
    return () =>
      h(NInputNumber, {
        value: props.value,
        min: isAsn ? 1 : undefined,
        max: isAsn ? 4294967295 : undefined,
        placeholder: isAsn ? 'ASN 号，如 4134' : '数值',
        'onUpdate:value': (v) => emit('update', v),
      })
  },
}

const ValueBoolInput = {
  props: ['value'],
  emits: ['update'],
  setup(props, { emit }) {
    return () =>
      h(NSwitch, {
        value: props.value === true || props.value === 'true',
        checkedValue: true,
        uncheckedValue: false,
        'onUpdate:value': (v) => emit('update', v),
      })
  },
}

const ValueEnumInput = {
  props: ['value', 'def'],
  emits: ['update'],
  setup(props, { emit }) {
    return () => {
      const opts = (props.def?.options ?? []).map((o) => ({ label: o, value: o }))
      const isMulti = Array.isArray(props.value)
      return h(NSelect, {
        value: props.value,
        options: opts,
        multiple: isMulti,
        filterable: true,
        placeholder: '选择值',
        'onUpdate:value': (v) => emit('update', v),
      })
    }
  },
}

const ValueListInput = {
  props: ['value', 'def'],
  emits: ['update'],
  setup(props, { emit }) {
    return () => {
      const def = props.def
      if (def?.options?.length) {
        const opts = def.options.map((o) => ({ label: o, value: o }))
        return h(NSelect, {
          value: Array.isArray(props.value) ? props.value : [],
          options: opts,
          multiple: true,
          filterable: true,
          placeholder: '多选',
          'onUpdate:value': (v) => emit('update', v),
        })
      }
      return h(NDynamicTags, {
        value: Array.isArray(props.value) ? props.value : [],
        placeholder: def?.type === 'asn' ? '输入 ASN 后回车，如 4134 / AS4134' : '输入后回车添加',
        'onUpdate:value': (v) => emit('update', v),
      })
    }
  },
}
</script>

<style scoped>
.condition-builder {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.condition-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.condition-row__index {
  width: 36px;
  flex-shrink: 0;
  text-align: right;
}
.cond-logic {
  font-size: 11px;
  color: var(--n-color-target);
  background: var(--n-color);
  padding: 1px 4px;
  border-radius: 3px;
  user-select: none;
}
.cond-logic--placeholder {
  color: #888;
  background: transparent;
}
.condition-row__field { flex: 2; min-width: 160px; }
.condition-row__op    { flex: 1.2; min-width: 120px; }
.condition-row__value { flex: 2; min-width: 140px; }
.condition-row__del   { flex-shrink: 0; color: #aaa; }
.condition-row__del:hover { color: #f00; }
.condition-builder__footer {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-top: 4px;
}
.cond-preview {
  font-size: 12px;
  color: #888;
  font-family: monospace;
  max-width: 480px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: default;
}
</style>
