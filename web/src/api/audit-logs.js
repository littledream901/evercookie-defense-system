import http from '@/utils/http'

export const auditLogsApi = {
  list: (params) => http.get('/v2/audit-logs', { params }),
}
