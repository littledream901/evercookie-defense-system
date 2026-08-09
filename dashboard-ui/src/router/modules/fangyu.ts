import { AppRouteRecord } from '@/types/router'

/**
 * 防御系统业务路由（新菜单结构）
 *
 * `meta.permission` 为后端权限码，菜单与路由访问权限由 MenuProcessor 统一按此过滤。
 */

/** 数据概览 - 一级菜单 */
export const overviewRoutes: AppRouteRecord = {
  name: 'FangyuDashboard',
  path: '/overview/dashboard',
  component: '/fangyu/dashboard',
  meta: {
    title: '数据概览',
    icon: 'ri:pie-chart-2-line',
    permission: 'analytics.read',
    keepAlive: false,
    fixedTab: true
  }
}

/** 分析看板 - 一级菜单，包含二级 */
export const analyticsRoutes: AppRouteRecord = {
  name: 'Analytics',
  path: '/analytics',
  component: '/index/index',
  meta: {
    title: '分析看板',
    icon: 'ri:bar-chart-box-line'
  },
  children: [
    {
      path: 'overview',
      name: 'FangyuAnalytics',
      component: '/fangyu/analytics',
      meta: {
        title: '分析看板',
        permission: 'analytics.read',
        keepAlive: true
      }
    },
    {
      path: 'crawler',
      name: 'FangyuCrawlerAnalytics',
      component: '/fangyu/crawler-analytics',
      meta: {
        title: '爬虫分析',
        icon: 'ri:robot-line',
        permission: 'analytics.read',
        keepAlive: true
      }
    }
  ]
}

/** 应用管理 - 一级菜单 */
export const applicationsRoutes: AppRouteRecord = {
  name: 'FangyuApplications',
  path: '/defense/applications',
  component: '/fangyu/applications',
  meta: {
    title: '应用管理',
    icon: 'ri:stack-line',
    permission: 'app.read',
    keepAlive: true,
    authList: [
      { title: '新建', authMark: 'app.write' },
      { title: '编辑', authMark: 'app.write' },
      { title: '删除', authMark: 'app.write' }
    ]
  }
}

/** 站点管理 - 一级菜单 */
export const appsRoutes: AppRouteRecord = {
  name: 'FangyuApps',
  path: '/defense/apps',
  component: '/fangyu/apps',
  meta: {
    title: '站点管理',
    icon: 'ri:apps-line',
    permission: 'app.read',
    keepAlive: true,
    authList: [
      { title: '新建', authMark: 'app.write' },
      { title: '编辑', authMark: 'app.write' },
      { title: '删除', authMark: 'app.write' }
    ]
  }
}

/** 风控规则 - 一级菜单 */
export const rulesRoutes: AppRouteRecord = {
  name: 'FangyuRules',
  path: '/defense/rules',
  component: '/fangyu/rules',
  meta: {
    title: '风控规则',
    icon: 'ri:shield-check-line',
    permission: 'rule.read',
    keepAlive: true,
    authList: [
      { title: '新建', authMark: 'rule.write' },
      { title: '发布', authMark: 'rule.publish' }
    ]
  }
}

/** 访问日志 - 一级菜单 */
export const accessLogsRoutes: AppRouteRecord = {
  name: 'FangyuAccessLogs',
  path: '/logs/access',
  component: '/fangyu/access-logs',
  meta: {
    title: '访问日志',
    icon: 'ri:file-list-3-line',
    permission: 'analytics.read',
    keepAlive: true
  }
}

/** 设置和诊断 - 一级菜单，包含二级 */
export const settingsRoutes: AppRouteRecord = {
  name: 'Settings',
  path: '/settings',
  component: '/index/index',
  meta: {
    title: '设置和诊断',
    icon: 'ri:settings-3-line'
  },
  children: [
    {
      path: 'clock',
      name: 'FangyuClock',
      component: '/fangyu/clock',
      meta: {
        title: '频控配置',
        permission: 'clock.read',
        keepAlive: true,
        authList: [{ title: '保存', authMark: 'clock.write' }]
      }
    },
    {
      path: 'threat-intel',
      name: 'FangyuThreatIntel',
      component: '/fangyu/threat-intel',
      meta: {
        title: '情报与画像',
        permission: 'threat_intel.read',
        keepAlive: true,
        authList: [
          { title: '新增', authMark: 'threat_intel.write' },
          { title: '停用', authMark: 'threat_intel.write' }
        ]
      }
    },
    {
      path: 'page-resources',
      name: 'FangyuPageResources',
      component: '/fangyu/page-resources',
      meta: {
        title: '页面资源',
        permission: 'app.read',
        keepAlive: true,
        authList: [
          { title: '新建', authMark: 'app.write' },
          { title: '编辑', authMark: 'app.write' },
          { title: '删除', authMark: 'app.write' }
        ]
      }
    },
    {
      path: 'whitelist',
      name: 'FangyuWhitelist',
      component: '/fangyu/whitelist',
      meta: {
        title: 'IP 白名单',
        permission: 'app.read',
        keepAlive: true,
        authList: [
          { title: '新增', authMark: 'app.write' },
          { title: '删除', authMark: 'app.write' }
        ]
      }
    },
    {
      path: 'scoring',
      name: 'FangyuScoring',
      component: '/fangyu/scoring',
      meta: {
        title: '评分配置',
        permission: 'app.read',
        keepAlive: true,
        authList: [{ title: '保存', authMark: 'app.write' }]
      }
    },
    {
      path: 'sdk-diagnostics',
      name: 'FangyuSdkDiagnostics',
      component: '/fangyu/sdk-diagnostics',
      meta: {
        title: '诊断',
        permission: 'app.read',
        keepAlive: true
      }
    }
  ]
}

/** 权限管理 - 一级菜单，包含二级 */
export const rbacRoutes: AppRouteRecord = {
  name: 'Rbac',
  path: '/rbac',
  component: '/index/index',
  meta: {
    title: '权限管理',
    icon: 'ri:user-settings-line'
  },
  children: [
    {
      path: 'users',
      name: 'FangyuUsers',
      component: '/fangyu/users',
      meta: {
        title: '用户管理',
        permission: 'user.read',
        keepAlive: true,
        authList: [
          { title: '新建', authMark: 'user.write' },
          { title: '编辑', authMark: 'user.write' },
          { title: '删除', authMark: 'user.write' }
        ]
      }
    },
    {
      path: 'roles',
      name: 'FangyuRoles',
      component: '/fangyu/roles',
      meta: {
        title: '角色管理',
        permission: 'role.read',
        keepAlive: true,
        authList: [
          { title: '新建', authMark: 'role.write' },
          { title: '编辑', authMark: 'role.write' }
        ]
      }
    },
    {
      path: 'audit',
      name: 'FangyuAuditLogs',
      component: '/fangyu/audit-logs',
      meta: {
        title: '审计日志',
        permission: 'audit.read',
        keepAlive: true
      }
    },
    {
      path: 'permissions',
      name: 'FangyuPermissions',
      component: '/fangyu/permissions',
      meta: {
        title: '权限元数据',
        permission: 'permission.read',
        keepAlive: true,
        authList: [{ title: '新增', authMark: 'permission.write' }]
      }
    }
  ]
}

/** 个人中心（不在菜单展示） */
export const profileRoutes: AppRouteRecord = {
  name: 'Account',
  path: '/account',
  component: '/index/index',
  meta: {
    title: '个人中心',
    icon: 'ri:user-line',
    isHide: true
  },
  children: [
    {
      path: 'profile',
      name: 'FangyuProfile',
      component: '/fangyu/profile',
      meta: {
        title: '个人中心',
        isHide: true
      }
    }
  ]
}

// 向后兼容别名
export const defenseRoutes = rulesRoutes
export const logRoutes = accessLogsRoutes
