import request from '@/utils/http'

/** 站点 SDK / Adapter 接入诊断（只读遥测，不向网关发探测请求） */
export function fetchGetIntegrationDiagnostics(siteId: number, hours = 24) {
  return request.get<Api.Fangyu.IntegrationDiagnostics>({
    url: `/api/v2/sites/${siteId}/integration-diagnostics`,
    params: { hours }
  })
}
