<template>
  <div class="min-h-screen flex-center bg-gradient-to-br from-primary/10 to-info/10 p-16px">
    <n-card class="w-380px shadow-2xl" :bordered="false">
      <div class="text-center mb-24px">
        <div class="i-ion-shield-checkmark text-primary text-48px mx-auto" />
        <div class="text-20px font-semibold mt-8px">{{ t('auth.loginTitle') }}</div>
        <div class="text-12px text-gray-500 mt-4px">{{ t('auth.loginSubtitle') }}</div>
      </div>
      <n-form ref="formRef" :model="form" :rules="rules" size="large" @submit.prevent="onSubmit">
        <n-form-item path="username" :show-label="false">
          <n-input v-model:value="form.username" :placeholder="t('auth.username')" @keyup.enter="onSubmit">
            <template #prefix><div class="i-ion-person-outline" /></template>
          </n-input>
        </n-form-item>
        <n-form-item path="password" :show-label="false">
          <n-input
            v-model:value="form.password"
            type="password"
            show-password-on="click"
            :placeholder="t('auth.password')"
            @keyup.enter="onSubmit"
          >
            <template #prefix><div class="i-ion-lock-closed-outline" /></template>
          </n-input>
        </n-form-item>
        <n-button type="primary" size="large" block :loading="loading" @click="onSubmit">
          {{ t('auth.loginButton') }}
        </n-button>
      </n-form>
    </n-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/store/user'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const userStore = useUserStore()
const message = useMessage()

const formRef = ref(null)
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: { required: true, message: '请输入用户名', trigger: ['blur', 'input'] },
  password: { required: true, message: '请输入密码', trigger: ['blur', 'input'] },
}

async function onSubmit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await userStore.login({ username: form.username, password: form.password })
    message.success('登录成功')
    const redirect = route.query.redirect || '/'
    router.replace(redirect)
  } catch (e) {
    message.error(e.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>
