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

/** 轮换应用密钥（响应含一次性 app_secret） */
export function fetchRotateApplicationSecret(id: number) {
  return request.post<Api.Fangyu.ApplicationDetail>({
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

/** 轮换站点密钥（响应含一次性 site_secret） */
export function fetchRotateSiteSecret(id: number) {
  return request.post<Api.Fangyu.SiteDetail>({
    url: `/api/v2/sites/${id}/rotate-secret`
  })
}

// ==================== V2 兼容 API（旧站点管理）====================

/** @deprecated V2 站点列表（兼容旧代码） */
export function fetchGetAppList(params?: Api.Fangyu.SiteListParams) {
  return request.get<Api.Common.PageResponse<Api.Fangyu.SiteLegacy>>({
    url: '/api/v2/sites',
    params
  })
}

/** @deprecated V2 站点详情 */
export function fetchGetApp(id: number) {
  return request.get<Api.Fangyu.SiteLegacy>({
    url: `/api/v2/sites/${id}`
  })
}

/** @deprecated V2 新建站点 */
export function fetchCreateApp(data: Api.Fangyu.SiteCreatePayload) {
  return request.post<Api.Fangyu.SiteDetail>({
    url: '/api/v2/sites',
    data
  })
}

/** @deprecated V2 更新站点 */
export function fetchUpdateApp(id: number, data: Api.Fangyu.SiteUpdatePayload) {
  return request.request<Api.Fangyu.Site>({
    url: `/api/v2/sites/${id}`,
    method: 'PATCH',
    data
  })
}

/** @deprecated V2 删除站点 */
export function fetchDeleteApp(id: number) {
  return request.del<null>({
    url: `/api/v2/sites/${id}`
  })
}

/** @deprecated V2 轮换密钥 */
export function fetchRotateAppKey(id: number) {
  return request.post<Api.Fangyu.SiteDetail>({
    url: `/api/v2/sites/${id}/rotate-key`
  })
}

/** @deprecated V2 发布快照 */
export function fetchPublishSnapshot(id: number) {
  return request.post<{ ok: boolean; published_at: string }>({
    url: `/api/v2/sites/${id}/publish`
  })
}

/** @deprecated V2 批量删除站点 */
export function fetchBatchDeleteApps(ids: number[]) {
  return request.post<Api.Fangyu.SiteBatchResult>({
    url: '/api/v2/sites/batch-delete',
    data: { ids }
  })
}

/** @deprecated V2 批量启用 / 停用站点 */
export function fetchBatchToggleApps(ids: number[], isActive: boolean) {
  return request.post<Api.Fangyu.SiteBatchResult>({
    url: '/api/v2/sites/batch-toggle',
    data: { ids, is_active: isActive }
  })
}

/** @deprecated V2 批量发布 */
export function fetchBatchPublishApps(ids: number[]) {
  return request.post<Api.Fangyu.SiteBatchResult>({
    url: '/api/v2/sites/batch-publish',
    data: { ids }
  })
}

/** 批量修改站点通用配置（未传字段保持原值） */
export function fetchBatchUpdateApps(data: Api.Fangyu.SiteBatchUpdatePayload) {
  return request.post<Api.Fangyu.SiteBatchResult>({
    url: '/api/v2/sites/batch-update',
    data
  })
}
