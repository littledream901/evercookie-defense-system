import request from '@/utils/http'

/** 爬虫分析查询参数 */
export interface CrawlerAnalyticsQuery {
  siteId?: number
  start?: string
  end?: string
  granularity?: 'minute' | 'hour' | 'day'
  limit?: number
}

/** 爬虫流量概览 */
export function fetchGetCrawlerOverview(params: CrawlerAnalyticsQuery) {
  return request.get<Record<string, unknown>>({
    url: '/api/v2/access-logs/crawler/overview',
    params
  })
}

/** 爬虫厂商分布 */
export function fetchGetCrawlerVendorDistribution(params: CrawlerAnalyticsQuery) {
  return request.get<Record<string, unknown>[]>({
    url: '/api/v2/access-logs/crawler/vendor-distribution',
    params
  })
}

/** 爬虫分类分布 */
export function fetchGetCrawlerCategoryDistribution(params: CrawlerAnalyticsQuery) {
  return request.get<Record<string, unknown>[]>({
    url: '/api/v2/access-logs/crawler/category-distribution',
    params
  })
}

/** 爬虫访问频率 Top 排行 */
export function fetchGetCrawlerTopList(params: CrawlerAnalyticsQuery) {
  return request.get<Record<string, unknown>[]>({
    url: '/api/v2/access-logs/crawler/top-list',
    params
  })
}

/** 爬虫流量时间趋势 */
export function fetchGetCrawlerTimeline(params: CrawlerAnalyticsQuery) {
  return request.get<Record<string, unknown>[]>({
    url: '/api/v2/access-logs/crawler/timeline',
    params
  })
}

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
