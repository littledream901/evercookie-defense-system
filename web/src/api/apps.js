import http from '@/utils/http'

export const appsApi = {
  list: (params) => http.get('/v2/apps', { params }),
  get: (id) => http.get(`/v2/apps/${id}`),
  create: (data) => http.post('/v2/apps', data),
  update: (id, data) => http.patch(`/v2/apps/${id}`, data),
  remove: (id) => http.delete(`/v2/apps/${id}`),
  rotateKey: (id) => http.post(`/v2/apps/${id}/rotate-key`),
}
