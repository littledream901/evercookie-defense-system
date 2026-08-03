import { AppRouteRecord } from '@/types/router'

/**
 * 防御系统业务路由（一级菜单结构，权限管理除外保留二级）
 *
 * `meta.permission` 为后端权限码，菜单与路由访问权限由 MenuProcessor 统一按此过滤。
 */

/** 数据概览 */
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

/** 分析看板 */
export const analyticsRoutes: AppRouteRecord = {
  name: 'FangyuAnalytics',
  path: '/overview/analytics',
  component: '/fangyu/analytics',
  meta: {
    title: '分析看板',
    icon: 'ri:bar-chart-box-line',
    permission: 'analytics.read',
    keepAlive: true
  }
}

/** 应用管理 */
export const appsRoutes: AppRouteRecord = {
  name: 'FangyuApps',
  path: '/defense/apps',
  component: '/fangyu/apps',
  meta: {
    title: '应用管理',
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

/** 风控规则 */
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

/** 频控配置 */
export const clockRoutes: AppRouteRecord = {
  name: 'FangyuClock',
  path: '/defense/clock',
  component: '/fangyu/clock',
  meta: {
    title: '频控配置',
    icon: 'ri:time-line',
    permission: 'clock.read',
    keepAlive: true,
    authList: [{ title: '保存', authMark: 'clock.write' }]
  }
}

/** 威胁情报 */
export const threatIntelRoutes: AppRouteRecord = {
  name: 'FangyuThreatIntel',
  path: '/defense/threat-intel',
  component: '/fangyu/threat-intel',
  meta: {
    title: '威胁情报',
    icon: 'ri:alert-line',
    permission: 'threat_intel.read',
    keepAlive: true,
    authList: [
      { title: '新增', authMark: 'threat_intel.write' },
      { title: '停用', authMark: 'threat_intel.write' }
    ]
  }
}

/** 页面资源 */
export const pageResourcesRoutes: AppRouteRecord = {
  name: 'FangyuPageResources',
  path: '/defense/page-resources',
  component: '/fangyu/page-resources',
  meta: {
    title: '页面资源',
    icon: 'ri:pages-line',
    permission: 'app.read',
    keepAlive: true,
    authList: [
      { title: '新建', authMark: 'app.write' },
      { title: '编辑', authMark: 'app.write' },
      { title: '删除', authMark: 'app.write' }
    ]
  }
}

/** IP 白名单 */
export const whitelistRoutes: AppRouteRecord = {
  name: 'FangyuWhitelist',
  path: '/defense/whitelist',
  component: '/fangyu/whitelist',
  meta: {
    title: 'IP 白名单',
    icon: 'ri:list-check-3',
    permission: 'app.read',
    keepAlive: true,
    authList: [
      { title: '新增', authMark: 'app.write' },
      { title: '删除', authMark: 'app.write' }
    ]
  }
}

/** 评分配置 */
export const scoringRoutes: AppRouteRecord = {
  name: 'FangyuScoring',
  path: '/defense/scoring',
  component: '/fangyu/scoring',
  meta: {
    title: '评分配置',
    icon: 'ri:equalizer-line',
    permission: 'app.read',
    keepAlive: true,
    authList: [{ title: '保存', authMark: 'app.write' }]
  }
}

/** 访问日志 */
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

/** 审计日志 */
export const auditLogsRoutes: AppRouteRecord = {
  name: 'FangyuAuditLogs',
  path: '/logs/audit',
  component: '/fangyu/audit-logs',
  meta: {
    title: '审计日志',
    icon: 'ri:file-search-line',
    permission: 'audit.read',
    keepAlive: true
  }
}

/** 权限管理（保留二级结构） */
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
