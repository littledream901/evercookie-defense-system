import http from '@/utils/http'

export const accessLogsApi = {
  list: (params) => http.get('/v2/access-logs', { params }),
  get: (requestId, params) => http.get(`/v2/access-logs/${requestId}`, { params }),
  stats: (params) => http.get('/v2/access-logs/stats/summary', { params }),
}
