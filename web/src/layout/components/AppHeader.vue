<template>
  <div class="flex-between h-full px-16px">
    <n-breadcrumb>
      <n-breadcrumb-item>{{ currentTitle }}</n-breadcrumb-item>
    </n-breadcrumb>
    <n-space :size="12" align="center">
      <n-button quaternary circle @click="appStore.toggleTheme">
        <template #icon>
          <div :class="appStore.themeMode === 'dark' ? 'i-ion-sunny-outline' : 'i-ion-moon-outline'" />
        </template>
      </n-button>
      <n-dropdown :options="langOptions" @select="onSelectLang">
        <n-button quaternary circle>
          <template #icon><div class="i-ion-language-outline" /></template>
        </n-button>
      </n-dropdown>
      <n-dropdown :options="userOptions" @select="onSelectUser">
        <div class="flex items-center cursor-pointer gap-8px">
          <n-avatar round size="small" :style="{ background: '#18a058' }">
            {{ userStore.userInfo?.username?.[0]?.toUpperCase() || 'U' }}
          </n-avatar>
          <span class="text-14px">{{ userStore.userInfo?.display_name || userStore.userInfo?.username }}</span>
        </div>
      </n-dropdown>
    </n-space>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/store/app'
import { useUserStore } from '@/store/user'
import { setLocale } from '@/i18n'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()
const { t } = useI18n()

const currentTitle = computed(() => route.meta?.title || '')

const langOptions = [
  { label: '简体中文', key: 'zh-CN' },
  { label: 'English', key: 'en-US' },
]

const userOptions = computed(() => [
  { label: t('menu.profile'), key: 'profile' },
  { type: 'divider' },
  { label: t('auth.logout'), key: 'logout' },
])

function onSelectLang(key) {
  setLocale(key)
  appStore.setLocale(key)
}

async function onSelectUser(key) {
  if (key === 'profile') router.push('/profile')
  if (key === 'logout') {
    await userStore.logout()
    router.push('/login')
  }
}
</script>
