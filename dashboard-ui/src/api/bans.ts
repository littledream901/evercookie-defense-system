import request from '@/utils/http'

export function fetchGetBanList(
  siteId: number,
  params?: { dimension?: string; cursor?: number; count?: number }
) {
  return request.get<Api.Fangyu.BanListResponse>({
    url: `/api/v2/sites/${siteId}/bans`,
    params
  })
}

export function fetchDeleteBan(
  siteId: number,
  params: { dimension: string; value: string }
) {
  return request.del<{ removed: boolean }>({
    url: `/api/v2/sites/${siteId}/bans`,
    params
  })
}

export function fetchBatchUnban(
  siteId: number,
  items: Array<{ dimension: string; value: string }>
) {
  return request.post<{ requested: number; removed: number }>({
    url: `/api/v2/sites/${siteId}/bans/batch-unban`,
    data: { items }
  })
}
