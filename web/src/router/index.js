import { createRouter, createWebHistory } from 'vue-router'
import { getAccessToken } from '@/utils/token'
import { useUserStore } from '@/store/user'
import routes from './routes'

const router = createRouter({
  history: createWebHistory('/'),
  routes,
})

router.beforeEach(async (to) => {
  const token = getAccessToken()
  if (to.meta?.requiresAuth === false) {
    if (to.path === '/login' && token) return { path: '/' }
    return true
  }
  if (!token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  const userStore = useUserStore()
  if (!userStore.userInfo) {
    try {
      await userStore.fetchProfile()
    } catch (e) {
      return { path: '/login' }
    }
  }
  if (to.meta?.permission && !userStore.hasPermission(to.meta.permission)) {
    return { path: '/403' }
  }
  return true
})

router.afterEach((to) => {
  const title = to.meta?.title
  document.title = title ? `${title} · 防御系统` : '防御系统 · 管理台'
})

export default router
