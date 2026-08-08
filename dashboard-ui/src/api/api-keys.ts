import request from '@/utils/http'

/* ------------------------------ API Key ------------------------------ */

export interface ApiKey {
  id: number
  user_id: number
  name: string
  key_prefix: string
  last_used_at: string | null
  status: string
  created_at: string
}

export interface ApiKeyCreatedResponse {
  key: ApiKey
  api_key: string
}

/** 创建 API Key */
export function fetchCreateApiKey(data: { name: string }) {
  return request.post<ApiKeyCreatedResponse>({
    url: '/api/v2/api-keys',
    data
  })
}

/** 获取当前用户的所有 API Key */
export function fetchGetApiKeys() {
  return request.get<ApiKey[]>({
    url: '/api/v2/api-keys'
  })
}

/** 删除 API Key */
export function fetchDeleteApiKey(keyId: number) {
  return request.del<null>({
    url: `/api/v2/api-keys/${keyId}`
  })
}
