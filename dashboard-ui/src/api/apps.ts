import request from '@/utils/http'

// ==================== V3 应用管理 API ====================

/** 应用列表 */
export function fetchGetApplicationList(params?: Api.Fangyu.ApplicationListParams) {
  return request.get<Api.Common.PageResponse<Api.Fangyu.Application>>({
    url: '/api/v2/applications',
    params
  })
}

/** 应用详情 */
export function fetchGetApplication(id: number) {
  return request.get<Api.Fangyu.Application>({
    url: `/api/v2/applications/${id}`
  })
}

/** 创建应用（响应含一次性 app_secret） */
export function fetchCreateApplication(data: Api.Fangyu.ApplicationCreatePayload) {
  return request.post<Api.Fangyu.ApplicationDetail>({
    url: '/api/v2/applications',
    data
  })
}

/** 更新应用 */
export function fetchUpdateApplication(id: number, data: Api.Fangyu.ApplicationUpdatePayload) {
  return request.put<Api.Fangyu.Application>({
    url: `/api/v2/applications/${id}`,
    data
  })
}

/** 删除应用 */
export function fetchDeleteApplication(id: number) {
  return request.del<null>({
    url: `/api/v2/applications/${id}`
  })
}

/** 轮换应用密钥（响应含一次性 app_secret 明文） */
export function fetchRotateApplicationSecret(id: number) {
  return request.post<Api.Fangyu.AppSecretRotateResult>({
    url: `/api/v2/applications/${id}/rotate-secret`
  })
}

/** 获取应用下的站点列表 */
export function fetchGetApplicationSites(appId: number) {
  return request.get<{ items: Api.Fangyu.Site[]; total: number }>({
    url: `/api/v2/applications/${appId}/sites`
  })
}

// ==================== V3 站点管理 API ====================

/** 站点列表 */
export function fetchGetSiteList(params?: Api.Fangyu.SiteListParams) {
  return request.get<Api.Common.PageResponse<Api.Fangyu.Site>>({
    url: '/api/v2/sites',
    params
  })
}

/** 站点详情 */
export function fetchGetSite(id: number) {
  return request.get<Api.Fangyu.SiteDetail>({
    url: `/api/v2/sites/${id}`
  })
}

/** 创建站点（响应含一次性 site_secret） */
export function fetchCreateSite(data: Api.Fangyu.SiteCreatePayload) {
  return request.post<Api.Fangyu.SiteDetail>({
    url: '/api/v2/sites',
    data
  })
}

/** 更新站点 */
export function fetchUpdateSite(id: number, data: Api.Fangyu.SiteUpdatePayload) {
  return request.put<Api.Fangyu.Site>({
    url: `/api/v2/sites/${id}`,
    data
  })
}

/** 删除站点 */
export function fetchDeleteSite(id: number) {
  return request.del<null>({
    url: `/api/v2/sites/${id}`
  })
}

/** 轮换站点密钥（响应含一次性 site_secret 明文） */
export function fetchRotateSiteSecret(id: number) {
  return request.post<Api.Fangyu.SiteSecretRotateResult>({
    url: `/api/v2/sites/${id}/rotate-secret`
  })
}

/** 把站点已发布规则全量重建到 Redis 分片 */
export function fetchPublishSiteRules(id: number) {
  return request.post<{ site_id: number; synced: number }>({
    url: `/api/v2/sites/${id}/publish`
  })
}

// ==================== 站点批量操作 ====================

/** 批量删除站点（需先停用） */
export function fetchBatchDeleteSites(ids: number[]) {
  return request.post<Api.Fangyu.SiteBatchResult>({
    url: '/api/v2/sites/batch-delete',
    data: { ids }
  })
}

/** 批量启用 / 停用站点 */
export function fetchBatchToggleSites(ids: number[], isActive: boolean) {
  return request.post<Api.Fangyu.SiteBatchResult>({
    url: '/api/v2/sites/batch-toggle',
    data: { ids, is_active: isActive }
  })
}

/** 批量重建站点规则缓存 */
export function fetchBatchPublishSites(ids: number[]) {
  return request.post<Api.Fangyu.SiteBatchResult>({
    url: '/api/v2/sites/batch-publish',
    data: { ids }
  })
}

/** 批量修改站点通用配置（未传字段保持原值） */
export function fetchBatchUpdateSites(data: Api.Fangyu.SiteBatchUpdatePayload) {
  return request.post<Api.Fangyu.SiteBatchResult>({
    url: '/api/v2/sites/batch-update',
    data
  })
}
