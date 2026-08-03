import request from '@/utils/http'

/** 访问日志列表 */
export function fetchGetAccessLogList(params: Api.Fangyu.AccessLogListParams) {
  return request.get<Api.Common.PageResponse<Api.Fangyu.AccessLog>>({
    url: '/api/v2/access-logs',
    params
  })
}

/** 访问日志详情 */
export function fetchGetAccessLog(requestId: string, params?: { siteId?: number }) {
  return request.get<Api.Fangyu.AccessLog>({
    url: `/api/v2/access-logs/${requestId}`,
    params
  })
}

/** 访问日志汇总统计 */
export function fetchGetAccessLogStats(params: { siteId: number; start?: string; end?: string }) {
  return request.get<Record<string, unknown>>({
    url: '/api/v2/access-logs/stats/summary',
    params
  })
}

/** 地址池命中分布 */
export function fetchGetPoolDistribution(params: {
  siteId: number
  ruleId?: number
  start?: string
  end?: string
}) {
  return request.get<Api.Fangyu.PoolDistributionItem[]>({
    url: '/api/v2/access-logs/pool/distribution',
    params
  })
}

/** 审计日志列表 */
export function fetchGetAuditLogList(params?: Api.Fangyu.AuditLogListParams) {
  return request.get<Api.Common.PageResponse<Api.Fangyu.AuditLog>>({
    url: '/api/v2/audit-logs',
    params
  })
}
