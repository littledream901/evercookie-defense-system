import http from '@/utils/http'

export const permissionsApi = {
  list: () => http.get('/v2/permissions'),
  upsert: (data) => http.post('/v2/permissions', data),
}
