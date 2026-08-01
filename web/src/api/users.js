import http from '@/utils/http'

export const usersApi = {
  list: (params) => http.get('/v2/users', { params }),
  get: (id) => http.get(`/v2/users/${id}`),
  create: (data) => http.post('/v2/users', data),
  update: (id, data) => http.patch(`/v2/users/${id}`, data),
  remove: (id) => http.delete(`/v2/users/${id}`),
  resetPassword: (id, data) => http.post(`/v2/users/${id}/reset-password`, data),
  assignRoles: (id, data) => http.post(`/v2/users/${id}/roles`, data),
}
