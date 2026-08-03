/**
 * 快速入口配置
 * 包含：应用列表、快速链接等配置
 */
import type { FastEnterConfig } from '@/types/config'

const fastEnterConfig: FastEnterConfig = {
  // 显示条件（屏幕宽度）
  minWidth: 1200,
  // 应用列表（routeName 必须存在于 router/modules/fangyu.ts，否则点击无法跳转）
  applications: [
    {
      name: '概览',
      description: '防护态势与核心指标',
      icon: 'ri:dashboard-line',
      iconColor: '#377dff',
      enabled: true,
      order: 1,
      routeName: 'FangyuDashboard'
    },
    {
      name: '应用管理',
      description: '站点接入与密钥管理',
      icon: 'ri:apps-line',
      iconColor: '#00b42a',
      enabled: true,
      order: 2,
      routeName: 'FangyuApps'
    },
    {
      name: '规则管理',
      description: '风控规则配置与发布',
      icon: 'ri:shield-keyhole-line',
      iconColor: '#ffb100',
      enabled: true,
      order: 3,
      routeName: 'FangyuRules'
    },
    {
      name: '访问日志',
      description: '决策明细与请求追溯',
      icon: 'ri:file-list-3-line',
      iconColor: '#ff6b6b',
      enabled: true,
      order: 4,
      routeName: 'FangyuAccessLogs'
    }
  ],
  // 快速链接
  quickLinks: [
    {
      name: '登录',
      enabled: true,
      order: 1,
      routeName: 'Login'
    },
    {
      name: '注册',
      enabled: true,
      order: 2,
      routeName: 'Register'
    },
    {
      name: '忘记密码',
      enabled: true,
      order: 3,
      routeName: 'ForgetPassword'
    },
    {
      name: '个人中心',
      enabled: true,
      order: 4,
      routeName: 'FangyuProfile'
    }
  ]
}

export default Object.freeze(fastEnterConfig)
