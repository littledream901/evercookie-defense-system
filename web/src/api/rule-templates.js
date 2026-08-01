import http from '@/utils/http'

export const ruleTemplatesApi = {
  list: () => http.get('/v2/rules/templates'),
}
