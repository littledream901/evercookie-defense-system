import request from '@/utils/http'

export interface BlacklistIpPayload {
  ips: string[]
  duration_seconds: number
  reason?: string
}

export interface BlacklistFingerprintPayload {
  fingerprints: string[]
  duration_seconds: number
  reason?: string
}

export interface BlacklistResult {
  ok: boolean
  count: number
}

/** 批量拉黑 IP（加入频控封禁名单） */
export function fetchBlacklistIps(data: BlacklistIpPayload) {
  return request.post<BlacklistResult>({
    url: '/api/v2/blacklist/ips',
    data
  })
}

/** 批量拉黑设备指纹 */
export function fetchBlacklistFingerprints(data: BlacklistFingerprintPayload) {
  return request.post<BlacklistResult>({
    url: '/api/v2/blacklist/fingerprints',
    data
  })
}

/** 解封 IP */
export function fetchUnblockIp(ip: string) {
  return request.del<{ ok: boolean }>({
    url: `/api/v2/blacklist/ips/${encodeURIComponent(ip)}`
  })
}

/** 解封指纹 */
export function fetchUnblockFingerprint(fingerId: string) {
  return request.del<{ ok: boolean }>({
    url: `/api/v2/blacklist/fingerprints/${encodeURIComponent(fingerId)}`
  })
}
