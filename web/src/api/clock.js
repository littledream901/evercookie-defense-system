import http from '@/utils/http'

// 所有接口都挂在 /v2/apps/{appId}/clock 之下：频控阈值是站点级配置，
// 不存在跨应用的全局阈值。
export const clockApi = {
  getLimits: (appId) => http.get(`/v2/apps/${appId}/clock/limits`),
  putLimits: (appId, data) => http.put(`/v2/apps/${appId}/clock/limits`, data),
  resetLimits: (appId) => http.delete(`/v2/apps/${appId}/clock/limits`),
  listWindows: (appId) => http.get(`/v2/apps/${appId}/clock/windows`),
  resync: (appId) => http.post(`/v2/apps/${appId}/clock/limits/resync`),

  createBan: (appId, data) => http.post(`/v2/apps/${appId}/clock/bans`, data),
  getBan: (appId, params) => http.get(`/v2/apps/${appId}/clock/bans`, { params }),
  deleteBan: (appId, params) => http.delete(`/v2/apps/${appId}/clock/bans`, { params }),
}
