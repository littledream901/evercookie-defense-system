<template>
  <n-layout has-sider class="h-screen">
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="220"
      :collapsed="appStore.collapsed"
      show-trigger
      @collapse="appStore.toggleCollapsed"
      @expand="appStore.toggleCollapsed"
    >
      <SideLogo :collapsed="appStore.collapsed" />
      <n-menu
        :collapsed="appStore.collapsed"
        :collapsed-width="64"
        :collapsed-icon-size="22"
        :options="menuOptions"
        :value="activeKey"
        @update:value="onSelect"
      />
    </n-layout-sider>
    <n-layout>
      <n-layout-header bordered class="h-56px">
        <AppHeader />
      </n-layout-header>
      <n-layout-content class="p-16px" content-style="min-height: calc(100vh - 56px);">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup>
import { computed, h } from 'vue'
import { useRouter, useRoute, RouterLink } from 'vue-router'
import { NIcon } from 'naive-ui'
import { Icon } from '@iconify/vue'
import { useAppStore } from '@/store/app'
import { useUserStore } from '@/store/user'
import routes from '@/router/routes'
import SideLogo from './components/SideLogo.vue'
import AppHeader from './components/AppHeader.vue'

const appStore = useAppStore()
const userStore = useUserStore()
const router = useRouter()
const route = useRoute()

const activeKey = computed(() => route.name)

const menuOptions = computed(() => {
  const rootLayout = routes.find((r) => r.path === '/')
  if (!rootLayout) return []
  return rootLayout.children
    .filter((c) => !c.meta?.hidden)
    .filter((c) => !c.meta?.permission || userStore.hasPermission(c.meta.permission))
    .map((c) => ({
      key: c.name,
      label: () => h(RouterLink, { to: '/' + c.path }, { default: () => c.meta?.title }),
      icon: () => h(NIcon, null, { default: () => h(Icon, { icon: c.meta?.icon || 'ion:apps-outline' }) }),
    }))
})

function onSelect(key) {
  const rootLayout = routes.find((r) => r.path === '/')
  const target = rootLayout?.children.find((c) => c.name === key)
  if (target) router.push('/' + target.path)
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
