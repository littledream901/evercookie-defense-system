import http from '@/utils/http'

export const analyticsApi = {
  timeline: (data) => http.post('/v2/analytics/timeline', data),
  disposition: (data) => http.post('/v2/analytics/disposition-breakdown', data),
  topEntities: (data) => http.post('/v2/analytics/top-entities', data),
}
