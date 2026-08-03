import request from '@/utils/http'

/** 决策数量时间线（POST + body） */
export function fetchGetTimeline(data: Api.Fangyu.TimelineParams) {
  return request.post<Api.Fangyu.TimelineBucket[]>({
    url: '/api/v2/analytics/timeline',
    data
  })
}

/** 处置分布（POST + body） */
export function fetchGetDispositionBreakdown(data: Api.Fangyu.AnalyticsParams) {
  return request.post<Api.Fangyu.DispositionBucket[]>({
    url: '/api/v2/analytics/disposition-breakdown',
    data
  })
}

/** Top 实体（POST + body） */
export function fetchGetTopEntities(data: Api.Fangyu.TopEntitiesParams) {
  return request.post<Api.Fangyu.TopEntity[]>({
    url: '/api/v2/analytics/top-entities',
    data
  })
}
