import request from '@/utils/http'

// ── 全局页面资源 ────────────────────────────────────────────────────────
export function fetchGetPageResourceList(params?: Api.Fangyu.PageResourceListParams) {
  return request.get<Api.Common.PageResponse<Api.Fangyu.PageResource>>({
    url: '/api/v2/page-resources',
    params
  })
}

export function fetchCreatePageResource(data: Api.Fangyu.PageResourcePayload) {
  return request.post<Api.Fangyu.PageResource>({ url: '/api/v2/page-resources', data })
}

export function fetchUpdatePageResource(id: number, data: Partial<Api.Fangyu.PageResourcePayload>) {
  return request.put<Api.Fangyu.PageResource>({ url: `/api/v2/page-resources/${id}`, data })
}

export function fetchDeletePageResource(id: number) {
  return request.del<null>({ url: `/api/v2/page-resources/${id}` })
}

export function fetchSyncPageResources() {
  return request.post<{ synced: number }>({ url: '/api/v2/page-resources/sync' })
}

/** 内置页面资源模板清单（静态，随后端版本演进） */
export function fetchGetPageResourceTemplates() {
  return request.get<Api.Fangyu.PageResourceTemplate[]>({
    url: '/api/v2/page-resources/templates'
  })
}

// ── 按站点（保留兼容）──────────────────────────────────────────────────
export function fetchGetSitePageResourceList(siteId: number, params?: Api.Fangyu.PageResourceListParams) {
  return request.get<Api.Common.PageResponse<Api.Fangyu.PageResource>>({
    url: `/api/v2/sites/${siteId}/page-resources`,
    params
  })
}
