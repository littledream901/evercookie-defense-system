import { AppRouteRecord } from '@/types/router'
import { exceptionRoutes } from './exception'
import {
  overviewRoutes,
  analyticsRoutes,
  applicationsRoutes,
  appsRoutes,
  rulesRoutes,
  accessLogsRoutes,
  settingsRoutes,
  rbacRoutes,
  profileRoutes
} from './fangyu'

/**
 * 菜单路由注册表（新结构）
 *
 * 菜单顺序：
 * 1. 数据概览（一级）
 * 2. 应用管理（一级）
 * 3. 站点管理（一级）
 * 4. 风控规则（一级）
 * 5. 访问日志（一级）
 * 6. 分析看板（一级 + 二级：分析看板、爬虫分析）
 * 7. 设置和诊断（一级 + 二级：频控、情报、资源、白名单、评分、诊断）
 * 8. 权限管理（一级 + 二级：用户、角色、审计、权限元数据）
 */
export const routeModules: AppRouteRecord[] = [
  overviewRoutes,
  applicationsRoutes,
  appsRoutes,
  rulesRoutes,
  accessLogsRoutes,
  analyticsRoutes,
  settingsRoutes,
  rbacRoutes,
  profileRoutes,
  exceptionRoutes
]
