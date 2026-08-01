import http from '@/utils/http'

export const authApi = {
  login: (data) => http.post('/v2/auth/login', data, { noAuth: true }),
  refresh: (data) => http.post('/v2/auth/refresh', data, { noAuth: true }),
  me: () => http.get('/v2/auth/me'),
  changePassword: (data) => http.post('/v2/auth/change-password', data),
  logout: () => http.post('/v2/auth/logout'),
}
