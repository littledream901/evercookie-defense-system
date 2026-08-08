import { request } from '@/utils/request'

export interface AccessLogQuery {
  siteId?: number
  start?: string
  end?: string
  requestId?: string
  ip?: string
  fingerprint?: string
  verdict?: string
  mechanism?: string
  decidedBy?: string
  country?: string
  deviceType?: string
  crawlerCategory?: string
  connectionType?: string
  path?: string
  isBot?: boolean
  isCrawler?: boolean
  page?: number
  pageSize?: number
}

export interface CrawlerAnalyticsQuery {
  siteId?: number
  start?: string
  end?: string
  granularity?: 'minute' | 'hour' | 'day'
  limit?: number
}

/**
 * 获取访问日志列表
 */
export function getAccessLogs(params: AccessLogQuery) {
  return request({
    url: '/v2/access-logs',
    method: 'get',
    params
  })
}

/**
 * 获取访问日志详情
 */
export function getAccessLogDetail(requestId: string, siteId?: number) {
  return request({
    url: `/v2/access-logs/${requestId}`,
    method: 'get',
    params: { siteId }
  })
}

/**
 * 获取访问日志规则命中轨迹
 */
export function getAccessLogTraces(requestId: string, siteId?: number) {
  return request({
    url: `/v2/access-logs/${requestId}/traces`,
    method: 'get',
    params: { siteId }
  })
}

/**
 * 获取访问日志统计摘要
 */
export function getAccessLogStats(params: { siteId?: number; start?: string; end?: string }) {
  return request({
    url: '/v2/access-logs/stats/summary',
    method: 'get',
    params
  })
}

/**
 * 获取影子规则影响面分析
 */
export function getAccessLogShadowImpact(params: { siteId?: number; start?: string; end?: string }) {
  return request({
    url: '/v2/access-logs/shadow/impact',
    method: 'get',
    params
  })
}

/**
 * 获取地址池命中分布
 */
export function getAccessLogPoolDistribution(params: { siteId: number; ruleId?: number; start?: string; end?: string }) {
  return request({
    url: '/v2/access-logs/pool/distribution',
    method: 'get',
    params
  })
}

/**
 * 获取爬虫流量概览
 */
export function getAccessLogCrawlerOverview(params: CrawlerAnalyticsQuery) {
  return request({
    url: '/v2/access-logs/crawler/overview',
    method: 'get',
    params
  })
}

/**
 * 获取爬虫厂商分布
 */
export function getAccessLogCrawlerVendorDistribution(params: CrawlerAnalyticsQuery) {
  return request({
    url: '/v2/access-logs/crawler/vendor-distribution',
    method: 'get',
    params
  })
}

/**
 * 获取爬虫分类分布
 */
export function getAccessLogCrawlerCategoryDistribution(params: CrawlerAnalyticsQuery) {
  return request({
    url: '/v2/access-logs/crawler/category-distribution',
    method: 'get',
    params
  })
}

/**
 * 获取爬虫访问频率Top排行
 */
export function getAccessLogCrawlerTopList(params: CrawlerAnalyticsQuery) {
  return request({
    url: '/v2/access-logs/crawler/top-list',
    method: 'get',
    params
  })
}

/**
 * 获取爬虫流量时间趋势
 */
export function getAccessLogCrawlerTimeline(params: CrawlerAnalyticsQuery) {
  return request({
    url: '/v2/access-logs/crawler/timeline',
    method: 'get',
    params
  })
}
