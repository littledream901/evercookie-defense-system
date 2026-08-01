import http from '@/utils/http'

export const threatIntelApi = {
  list: (params) => http.get('/v2/threat-intel', { params }),
  add: (data) => http.post('/v2/threat-intel', data),
  remove: (ip) => http.delete(`/v2/threat-intel/${ip}`),
  bulkImport: (records) => http.post('/v2/threat-intel/bulk-import', records),
  syncRedis: () => http.post('/v2/threat-intel/sync-redis'),
  redisStats: () => http.get('/v2/threat-intel/stats/redis'),
}
