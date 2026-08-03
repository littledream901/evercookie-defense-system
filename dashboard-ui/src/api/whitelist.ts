import request from '@/utils/http'

// ── 全局白名单 ─────────────────────────────────────────────────────────
export function fetchGetWhitelistList() {
  return request.get<Api.Fangyu.WhitelistEntry[]>({ url: '/api/v2/whitelist' })
}

export function fetchAddWhitelistEntry(data: Api.Fangyu.WhitelistPayload) {
  return request.post<Api.Fangyu.WhitelistEntry>({ url: '/api/v2/whitelist', data })
}

export function fetchDeleteWhitelistEntry(params: { dimension: string; value: string }) {
  return request.del<{ removed: boolean }>({ url: '/api/v2/whitelist', params })
}

export function fetchDeleteAllWhitelist() {
  return request.del<{ removed: number }>({
    url: '/api/v2/whitelist/all',
    params: { confirm: true }
  })
}

// ── 按站点白名单（保留兼容）────────────────────────────────────────────
export function fetchGetSiteWhitelistList(siteId: number) {
  return request.get<Api.Fangyu.WhitelistEntry[]>({
    url: `/api/v2/sites/${siteId}/whitelist`
  })
}
