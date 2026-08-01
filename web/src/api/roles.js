import http from '@/utils/http'

export const rolesApi = {
  list: (params) => http.get('/v2/roles', { params }),
  get: (id) => http.get(`/v2/roles/${id}`),
  create: (data) => http.post('/v2/roles', data),
  update: (id, data) => http.patch(`/v2/roles/${id}`, data),
  remove: (id) => http.delete(`/v2/roles/${id}`),
}
