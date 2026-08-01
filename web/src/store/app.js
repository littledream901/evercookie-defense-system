import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    collapsed: false,
    themeMode: localStorage.getItem('themeMode') || 'light',
    locale: localStorage.getItem('lang') || 'zh-CN',
  }),
  actions: {
    toggleCollapsed() {
      this.collapsed = !this.collapsed
    },
    setThemeMode(mode) {
      this.themeMode = mode
      localStorage.setItem('themeMode', mode)
    },
    toggleTheme() {
      this.setThemeMode(this.themeMode === 'dark' ? 'light' : 'dark')
    },
    setLocale(lang) {
      this.locale = lang
      localStorage.setItem('lang', lang)
    },
  },
})
