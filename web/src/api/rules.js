import http from '@/utils/http'

export const rulesApi = {
  list: (appId, params) => http.get(`/v2/apps/${appId}/rules`, { params }),
  get: (appId, ruleId) => http.get(`/v2/apps/${appId}/rules/${ruleId}`),
  create: (appId, data) => http.post(`/v2/apps/${appId}/rules`, data),
  update: (appId, ruleId, data) => http.put(`/v2/apps/${appId}/rules/${ruleId}`, data),
  remove: (appId, ruleId) => http.delete(`/v2/apps/${appId}/rules/${ruleId}`),
  publish: (appId, ruleId, data) => http.post(`/v2/apps/${appId}/rules/${ruleId}/publish`, data),
  disable: (appId, ruleId) => http.post(`/v2/apps/${appId}/rules/${ruleId}/disable`),
  archive: (appId, ruleId) => http.post(`/v2/apps/${appId}/rules/${ruleId}/archive`),
  rollback: (appId, ruleId, data) => http.post(`/v2/apps/${appId}/rules/${ruleId}/rollback`, data),
  versions: (appId, ruleId) => http.get(`/v2/apps/${appId}/rules/${ruleId}/versions`),
  syncCache: (appId) => http.post(`/v2/apps/${appId}/rules/sync-cache`),
  test: (data) => http.post('/v2/rules/preview', data),
}
