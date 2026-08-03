import request from '@/utils/http'

// ── 全局频控配置 ────────────────────────────────────────────────────────

export function fetchGetClockLimits() {
  return request.get<Api.Fangyu.ClockLimits>({ url: '/api/v2/clock/limits' })
}

export function fetchPutClockLimits(data: Api.Fangyu.ClockLimits) {
  return request.put<Api.Fangyu.ClockLimits>({ url: '/api/v2/clock/limits', data })
}

export function fetchResetClockLimits() {
  return request.del<Api.Fangyu.ClockLimits>({ url: '/api/v2/clock/limits' })
}

export function fetchGetClockWindows() {
  return request.get<Api.Fangyu.ClockWindow[]>({ url: '/api/v2/clock/windows' })
}

export function fetchResyncClockLimits() {
  return request.post<Record<string, unknown>>({ url: '/api/v2/clock/limits/resync' })
}

export function fetchCreateClockBan(
  data: { dimension: string; value: string; seconds: number; reason?: string }
) {
  return request.post<Api.Fangyu.ClockBan>({ url: '/api/v2/clock/bans', data })
}

export function fetchGetClockBan(params: { dimension: string; value: string }) {
  return request.get<Api.Fangyu.ClockBan | null>({ url: '/api/v2/clock/bans', params })
}

export function fetchDeleteClockBan(params: { dimension: string; value: string }) {
  return request.del<{ removed: boolean }>({ url: '/api/v2/clock/bans', params })
}
