import { AppRouteRecord } from '@/types/router'
import { exceptionRoutes } from './exception'
import {
  overviewRoutes,
  analyticsRoutes,
  appsRoutes,
  rulesRoutes,
  clockRoutes,
  threatIntelRoutes,
  pageResourcesRoutes,
  whitelistRoutes,
  scoringRoutes,
  accessLogsRoutes,
  auditLogsRoutes,
  rbacRoutes,
  profileRoutes
} from './fangyu'

/**
 * 导出所有模块化路由
 *
 * 一级菜单结构：所有业务路由平铺，权限管理保留二级，异常页在末尾。
 */
export const routeModules: AppRouteRecord[] = [
  overviewRoutes,
  analyticsRoutes,
  appsRoutes,
  rulesRoutes,
  clockRoutes,
  threatIntelRoutes,
  pageResourcesRoutes,
  whitelistRoutes,
  scoringRoutes,
  accessLogsRoutes,
  auditLogsRoutes,
  rbacRoutes,
  profileRoutes,
  exceptionRoutes
]
