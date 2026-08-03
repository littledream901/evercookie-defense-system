import request from '@/utils/http'

/** 站点列表 */
export function fetchGetAppList(params?: Api.Fangyu.SiteListParams) {
  return request.get<Api.Common.PageResponse<Api.Fangyu.Site>>({
    url: '/api/v2/sites',
    params
  })
}

/** 站点详情 */
export function fetchGetApp(id: number) {
  return request.get<Api.Fangyu.Site>({
    url: `/api/v2/sites/${id}`
  })
}

/** 新建站点（响应含一次性 app_secret） */
export function fetchCreateApp(data: Api.Fangyu.SiteCreatePayload) {
  return request.post<Api.Fangyu.SiteCreateResponse>({
    url: '/api/v2/sites',
    data
  })
}

/** 更新站点（PATCH，不含 domain） */
export function fetchUpdateApp(id: number, data: Api.Fangyu.SiteUpdatePayload) {
  return request.request<Api.Fangyu.Site>({
    url: `/api/v2/sites/${id}`,
    method: 'PATCH',
    data
  })
}

/** 删除站点 */
export function fetchDeleteApp(id: number) {
  return request.del<null>({
    url: `/api/v2/sites/${id}`
  })
}

/** 轮换 App ID + Secret（响应含一次性 app_secret） */
export function fetchRotateAppKey(id: number) {
  return request.post<Api.Fangyu.SiteCreateResponse>({
    url: `/api/v2/sites/${id}/rotate-key`
  })
}

/** 发布快照（将当前配置推送至网关节点） */
export function fetchPublishSnapshot(id: number) {
  return request.post<{ ok: boolean; published_at: string }>({
    url: `/api/v2/sites/${id}/publish`
  })
}

/** 批量删除站点 */
export function fetchBatchDeleteApps(ids: number[]) {
  return request.post<Api.Fangyu.SiteBatchResult>({
    url: '/api/v2/sites/batch-delete',
    data: { ids }
  })
}

/** 批量启用 / 停用站点 */
export function fetchBatchToggleApps(ids: number[], isActive: boolean) {
  return request.post<Api.Fangyu.SiteBatchResult>({
    url: '/api/v2/sites/batch-toggle',
    data: { ids, is_active: isActive }
  })
}

/** 批量发布：同步各站点已发布规则到 Redis */
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
