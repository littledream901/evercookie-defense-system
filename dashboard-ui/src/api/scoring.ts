import request from '@/utils/http'

/** 获取全局评分配置 */
export function fetchGetGlobalScoringConfig() {
  return request.get<Api.Fangyu.ScoringConfig>({
    url: '/api/v2/scoring/global'
  })
}

/** 保存全局评分配置（PUT，全量覆盖） */
export function fetchPutGlobalScoringConfig(data: Api.Fangyu.ScoringConfigPayload) {
  return request.put<Api.Fangyu.ScoringConfig>({
    url: '/api/v2/scoring/global',
    data
  })
}

/** 重置全局评分配置 */
export function fetchResetGlobalScoringConfig() {
  return request.del<{ deleted: boolean }>({
    url: '/api/v2/scoring/global'
  })
}

/** 获取站点评分配置 */
export function fetchGetScoringConfig(siteId: number) {
  return request.get<Api.Fangyu.ScoringConfig>({
    url: `/api/v2/sites/${siteId}/scoring`
  })
}

/** 保存评分配置（PUT，全量覆盖） */
export function fetchPutScoringConfig(siteId: number, data: Api.Fangyu.ScoringConfigPayload) {
  return request.put<Api.Fangyu.ScoringConfig>({
    url: `/api/v2/sites/${siteId}/scoring`,
    data
  })
}

/** 重置为默认配置 */
export function fetchResetScoringConfig(siteId: number) {
  return request.del<{ deleted: boolean }>({
    url: `/api/v2/sites/${siteId}/scoring`
  })
}

/** 获取系统支持的评分维度列表 */
export function fetchGetScoringDimensions() {
  return request.get<
    Array<{ key: string; label: string; description: string; defaultWeight: number }>
  >({
    url: '/api/v2/scoring/dimensions'
  })
}
