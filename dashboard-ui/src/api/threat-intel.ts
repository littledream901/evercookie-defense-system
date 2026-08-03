import request from '@/utils/http'

/**
 * 通用情报分页响应
 */
export interface IntelPageResponse<T = Record<string, unknown>> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/**
 * 通用情报查询参数
 */
export interface IntelListParams {
  page?: number
  page_size?: number
  keyword?: string
  [key: string]: unknown
}

/**
 * ASN 情报记录
 */
export interface AsnIntel {
  id?: number
  asn: number
  operator: string
  network_type: string
  risk_score: number
  is_active: boolean
  note?: string | null
  created_at?: string | null
}

/**
 * 爬虫特征记录
 */
export interface CrawlerIntel {
  id?: number
  feature_type: string
  pattern: string
  crawler_category: string
  crawler_name?: string | null
  is_legitimate: boolean
  risk_score: number
  note?: string | null
  created_at?: string | null
}

/**
 * 指纹情报记录
 */
export interface FingerprintIntel {
  id?: number
  finger_id: string
  finger_type: string
  risk_score: number
  hit_count?: number
  source?: string | null
  canvas_hash?: string | null
  webgl_params?: unknown
  audio_hash?: string | null
  screen_info?: string | null
  note?: string | null
  created_at?: string | null
}

/**
 * GeoIP 记录（手工录入，覆盖 MMDB）
 */
export interface GeoIpIntel {
  id?: number
  cidr: string
  country: string
  region?: string | null
  city?: string | null
  is_active: boolean
  note?: string | null
  created_at?: string | null
}

/**
 * IP 画像记录
 */
export interface IpProfileIntel {
  id?: number
  cidr: string
  network_type: string
  is_vpn: boolean
  is_proxy: boolean
  is_tor: boolean
  risk_score: number
  is_active: boolean
  note?: string | null
  created_at?: string | null
}

/**
 * ASN 画像记录
 */
export interface AsnProfileIntel {
  id?: number
  asn: number
  operator: string
  network_type: string
  country?: string | null
  risk_score: number
  is_active: boolean
  note?: string | null
  created_at?: string | null
}

/**
 * 情报统计概览
 */
export interface IntelOverviewStats {
  total_entries: number
  profile_field_count: number
  last_sync_time: string | null
  health?: {
    profile_missing_total: number
  }
  counts?: Record<string, number>
}

// ── IP 威胁情报（原有接口保留）────────────────────────────────────────────────

/**
 * 威胁情报列表
 *
 * 注意：该组接口直接返回业务 dict，不带 `{ code, message, data }` 信封，
 * 且分页参数为蛇形 `page_size`，与其他列表接口不同。
 */
export function fetchGetThreatIntelList(params?: Api.Fangyu.ThreatIntelListParams) {
  return request.get<Api.Fangyu.ThreatIntelList>({
    url: '/api/v2/threat-intel',
    params
  })
}

/** 新增威胁情报 */
export function fetchAddThreatIntel(data: {
  ip: string
  category: string
  severity: string
  confidence: number
  description?: string
  expires_at?: string | null
}) {
  return request.post<Api.Fangyu.ThreatIntel>({
    url: '/api/v2/threat-intel',
    data
  })
}

/** 停用某个 IP 的情报（按 IP 而非 ID 删除） */
export function fetchRemoveThreatIntel(ip: string) {
  return request.del<{ ok: boolean; ip: string }>({
    url: `/api/v2/threat-intel/${ip}`
  })
}

/** 批量导入 */
export function fetchBulkImportThreatIntel(records: unknown[]) {
  return request.post<{ imported: number }>({
    url: '/api/v2/threat-intel/bulk-import',
    data: records
  })
}

/** 同步到 Redis */
export function fetchSyncThreatIntelRedis() {
  return request.post<Record<string, unknown>>({
    url: '/api/v2/threat-intel/sync-redis'
  })
}

/** Redis 统计 */
export function fetchGetThreatIntelRedisStats() {
  return request.get<Record<string, unknown>>({
    url: '/api/v2/threat-intel/stats/redis'
  })
}

// ── 多类型情报通用 CRUD ───────────────────────────────────────────────────────

const INTEL_BASE = '/api/v2/intelligence'

/** 外部情报源配置状态 */
export interface ExternalSourceStatus {
  id: string
  name: string
  url: string
  enabled: boolean
  requiresApiKey: boolean
  configured?: boolean
  /** 该来源当前贡献的活跃条目数 */
  entry_count?: number
  description: string
}

/** 内置预设数据源（ASN / 爬虫），name 由后端产出，前端不再自带一份 */
export interface IntelPresetSource {
  name: string
  label: string
  description: string
  /** 预设自带条数，非已入库条数 */
  entry_count: number
}

/** 查询某情报类型可用的内置预设 */
export function fetchGetIntelPresets(type: string) {
  return request.get<{ sources: IntelPresetSource[] }>({
    url: `${INTEL_BASE}/${type}/presets`
  })
}

/** 查询外部情报源配置状态 */
export function fetchGetExternalSources() {
  return request.get<{ sources: ExternalSourceStatus[] }>({
    url: '/api/v2/threat-intel/external-sources'
  })
}

/**
 * 外部源同步耗时远超普通接口（拉取 + 批量入库 + 推 Redis），
 * 用默认 15s 超时会让浏览器先断开，后端随即报 No response returned。
 */
const SYNC_TIMEOUT = 180000

/** 手动触发外部情报源拉取（Tor/URLhaus/AbuseIPDB） */
export function fetchSyncExternalIntel() {
  return request.post<{ imported: number; skipped: number; sources: string[] }>({
    url: '/api/v2/threat-intel/sync-external',
    timeout: SYNC_TIMEOUT
  })
}

/** 查询某情报类型的外部情报源状态（目前仅 IP 画像有，其余返回空列表） */
export function fetchGetIntelExternalSources(type: string) {
  return request.get<{ sources: ExternalSourceStatus[] }>({
    url: `${INTEL_BASE}/${type}/external-sources`
  })
}

/** 手动触发某情报类型的外部源拉取 */
export function fetchSyncIntelExternal(type: string) {
  return request.post<{ imported: number; skipped: number; sources: string[] }>({
    url: `${INTEL_BASE}/${type}/sync-external`,
    timeout: SYNC_TIMEOUT
  })
}

/** 通用情报列表 */
export function fetchGetIntelList<T = Record<string, unknown>>(
  type: string,
  params?: IntelListParams
) {
  return request.get<IntelPageResponse<T>>({
    url: `${INTEL_BASE}/${type}`,
    params
  })
}

/** 通用情报新增 */
export function fetchAddIntel<T = Record<string, unknown>>(type: string, data: unknown) {
  return request.post<T>({
    url: `${INTEL_BASE}/${type}`,
    data
  })
}

/** 通用情报更新 */
export function fetchUpdateIntel<T = Record<string, unknown>>(
  type: string,
  id: number | string,
  data: unknown
) {
  return request.put<T>({
    url: `${INTEL_BASE}/${type}/${id}`,
    data
  })
}

/** 通用情报删除 */
export function fetchDeleteIntel(type: string, id: number | string) {
  return request.del<{ ok: boolean }>({
    url: `${INTEL_BASE}/${type}/${id}`
  })
}

/** 通用 CSV 导入 */
export function fetchImportIntelCsv(type: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return request.post<{ imported: number; errors?: string[] }>({
    url: `${INTEL_BASE}/${type}/import`,
    data: form
  })
}

/** 通用全量导出（返回 Blob） */
export function fetchExportIntel(type: string) {
  return request.get<Blob>({
    url: `${INTEL_BASE}/${type}/export`,
    responseType: 'blob'
  } as any)
}

/** 载入预设模板 */
export function fetchLoadIntelPreset(type: string, presetName: string) {
  return request.post<{ imported: number }>({
    url: `${INTEL_BASE}/${type}/preset/${presetName}`
  })
}

/** 情报总览统计 */
export function fetchGetIntelOverview() {
  return request.get<IntelOverviewStats>({
    url: `${INTEL_BASE}/overview`
  })
}

// ── MMDB (GeoIP 数据库) 管理 ───────────────────────────────────────────────

export interface MmdbFileStatus {
  file_type:   string
  exists:      boolean
  size_bytes:  number | null
  modified_at: string | null
}

/** MMDB 文件状态 */
export function fetchMmdbStatus() {
  return request.get<{ storage_dir: string; files: MmdbFileStatus[] }>({
    url: '/api/v1/intelligence/mmdb/status',
  })
}

/** 上传 MMDB 文件（.mmdb，multipart/form-data；可选 onProgress 回调报告进度 0-100） */
export function fetchUploadMmdb(
  fileType: 'country' | 'asn',
  file: File,
  onProgress?: (pct: number) => void
) {
  const form = new FormData()
  form.append('file', file)
  return request.post<MmdbFileStatus>({
    url: `/api/v1/intelligence/mmdb/upload?file_type=${fileType}`,
    data: form,
    ...(onProgress && {
      onUploadProgress: (e: { loaded: number; total?: number }) => {
        if (e.total) onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }),
  })
}

/** 删除 MMDB 文件 */
export function fetchDeleteMmdb(fileType: 'country' | 'asn') {
  return request.del<MmdbFileStatus>({
    url: `/api/v1/intelligence/mmdb/${fileType}`,
  })
}

/** MMDB 对某个 CIDR 的原始判定，用于与修正值对比 */
export interface MmdbCidrLookup {
  country: string | null
  continent: string | null
}

/** 批量查询 CIDR 在 MMDB 中的原始归属（key 为传入的 cidr 原串） */
export function fetchCompareCidrs(cidrs: string[]) {
  return request.post<{ results: Record<string, MmdbCidrLookup>; available?: boolean }>({
    url: '/api/v1/intelligence/mmdb/compare-cidrs',
    data: cidrs
  })
}

/** 测试指定 IP 的 MMDB 画像（留空时用请求来源 IP） */
export function fetchTestMmdbIp(ip?: string) {
  return request.get<Record<string, unknown>>({
    url: '/api/v1/intelligence/mmdb/test',
    params: ip ? { ip } : undefined,
  })
}
