import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'
import { setTokens, clearTokens } from '@/utils/token'

export const useUserStore = defineStore('user', {
  state: () => ({
    userInfo: null,
    permissions: [],
    roles: [],
  }),
  getters: {
    isSuperAdmin: (s) => s.permissions.includes('*'),
  },
  actions: {
    hasPermission(code) {
      if (!code) return true
      if (this.permissions.includes('*')) return true
      if (this.permissions.includes(code)) return true
      const [resource] = code.split('.')
      return this.permissions.includes(`${resource}.*`)
    },
    async login(payload) {
      const resp = await authApi.login(payload)
      const inner = resp?.data ?? resp
      const tokens = inner?.tokens ?? {}
      setTokens(tokens.access_token, tokens.refresh_token)
      this.userInfo = inner?.user ?? null
      this.permissions = inner?.permissions ?? []
      this.roles = inner?.roles ?? []
      return inner
    },
    async fetchProfile() {
      const resp = await authApi.me()
      const inner = resp?.data ?? resp
      this.userInfo = inner?.user ?? null
      this.permissions = inner?.permissions ?? []
      this.roles = inner?.roles ?? []
      return inner
    },
    async logout() {
      try {
        await authApi.logout()
      } catch (_) { /* 忽略 */ }
      clearTokens()
      this.userInfo = null
      this.permissions = []
      this.roles = []
    },
  },
})
