import request from '@/utils/http'

/** 站点 SDK / Adapter 接入诊断（只读遥测，不向网关发探测请求） */
export function fetchGetIntegrationDiagnostics(siteId: number, hours = 24) {
  return request.get<Api.Fangyu.IntegrationDiagnostics>({
    url: `/api/v2/sites/${siteId}/integration-diagnostics`,
    params: { hours }
  })
}

/** 测试站点网关连通性 */
export function testSiteConnection(siteId: number) {
  return request.post<{
    ok: boolean
    message?: string
    error?: string
    detail?: string
    status_code?: number
    response?: any
  }>({
    url: `/api/v2/sites/${siteId}/test-connection`
  })
}

/** 批量诊断站点接入健康度 */
export function fetchBatchDiagnostics(siteIds: number[], hours = 24) {
  return request.post<Api.Fangyu.SiteDiagnosticsSummary[]>({
    url: '/api/v2/sites/batch-diagnostics',
    data: { site_ids: siteIds, hours }
  })
}
