import request from '@/utils/http'

/** 获取全局默认处置（site_id=0） */
export function fetchGetGlobalDefaultDisposition() {
  return request.get<Api.Fangyu.DefaultDisposition>({
    url: '/api/v2/default-disposition/global'
  })
}

/** 保存全局默认处置（PUT，全量覆盖） */
export function fetchPutGlobalDefaultDisposition(data: Api.Fangyu.DefaultDispositionPayload) {
  return request.put<Api.Fangyu.DefaultDisposition>({
    url: '/api/v2/default-disposition/global',
    data
  })
}

/** 重置全局默认处置 */
export function fetchResetGlobalDefaultDisposition() {
  return request.del<{ deleted: boolean }>({
    url: '/api/v2/default-disposition/global'
  })
}

/** 获取站点默认处置 */
export function fetchGetDefaultDisposition(siteId: number) {
  return request.get<Api.Fangyu.DefaultDisposition>({
    url: `/api/v2/sites/${siteId}/default-disposition`
  })
}

/** 保存站点默认处置（PUT，全量覆盖） */
export function fetchPutDefaultDisposition(siteId: number, data: Api.Fangyu.DefaultDispositionPayload) {
  return request.put<Api.Fangyu.DefaultDisposition>({
    url: `/api/v2/sites/${siteId}/default-disposition`,
    data
  })
}

/** 删除站点默认处置（回退到全局/系统默认） */
export function fetchResetDefaultDisposition(siteId: number) {
  return request.del<{ deleted: boolean }>({
    url: `/api/v2/sites/${siteId}/default-disposition`
  })
}
