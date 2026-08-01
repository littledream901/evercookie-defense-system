const Layout = () => import('@/layout/index.vue')

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { requiresAuth: false, title: '登录' },
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('@/views/error/403.vue'),
    meta: { requiresAuth: false, title: '无权限' },
  },
  {
    path: '/404',
    name: 'NotFound',
    component: () => import('@/views/error/404.vue'),
    meta: { requiresAuth: false, title: '页面不存在' },
  },
  {
    path: '/',
    component: Layout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '数据概览', icon: 'ion:speedometer-outline', permission: 'analytics.read' },
      },
      {
        path: 'analytics',
        name: 'Analytics',
        component: () => import('@/views/analytics/index.vue'),
        meta: { title: '分析看板', icon: 'ion:analytics-outline', permission: 'analytics.read' },
      },
      {
        path: 'apps',
        name: 'Apps',
        component: () => import('@/views/apps/index.vue'),
        meta: { title: '应用管理', icon: 'ion:apps-outline', permission: 'app.read' },
      },
      {
        path: 'rules',
        name: 'Rules',
        component: () => import('@/views/rules/index.vue'),
        meta: { title: '风控规则', icon: 'ion:shield-checkmark-outline', permission: 'rule.read' },
      },
      {
        path: 'clock',
        name: 'Clock',
        component: () => import('@/views/clock/index.vue'),
        meta: { title: '频控配置', icon: 'ion:timer-outline', permission: 'clock.read' },
      },
      {
        path: 'threat-intel',
        name: 'ThreatIntel',
        component: () => import('@/views/threat-intel/index.vue'),
        meta: { title: '威胁情报', icon: 'ion:bug-outline', permission: 'threat_intel.read' },
      },
      {
        path: 'access-logs',
        name: 'AccessLogs',
        component: () => import('@/views/access-logs/index.vue'),
        meta: { title: '访问日志', icon: 'ion:list-outline', permission: 'analytics.read' },
      },
      {
        path: 'audit-logs',
        name: 'AuditLogs',
        component: () => import('@/views/audit-logs/index.vue'),
        meta: { title: '审计日志', icon: 'ion:document-text-outline', permission: 'audit.read' },
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/users/index.vue'),
        meta: { title: '用户管理', icon: 'ion:person-outline', permission: 'user.read' },
      },
      {
        path: 'roles',
        name: 'Roles',
        component: () => import('@/views/roles/index.vue'),
        meta: { title: '角色管理', icon: 'ion:people-outline', permission: 'role.read' },
      },
      {
        path: 'permissions',
        name: 'Permissions',
        component: () => import('@/views/permissions/index.vue'),
        meta: { title: '权限管理', icon: 'ion:key-outline', permission: 'permission.read' },
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/profile/index.vue'),
        meta: { title: '个人中心', icon: 'ion:person-circle-outline', hidden: true },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/404' },
]

export default routes
