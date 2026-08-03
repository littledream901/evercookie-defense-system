/**
 * API 接口类型定义模块
 *
 * 提供所有后端接口的类型定义
 *
 * ## 主要功能
 *
 * - 通用类型（分页参数、响应结构等）
 * - 认证类型（登录、用户信息等）
 * - 系统管理类型（用户、角色等）
 * - 全局命名空间声明
 *
 * ## 使用场景
 *
 * - API 请求参数类型约束
 * - API 响应数据类型定义
 * - 接口文档类型同步
 *
 * ## 注意事项
 *
 * - 在 .vue 文件使用需要在 eslint.config.mjs 中配置 globals: { Api: 'readonly' }
 * - 使用全局命名空间，无需导入即可使用
 *
 * ## 使用方式
 *
 * ```typescript
 * const params: Api.Auth.LoginParams = { userName: 'admin', password: '123456' }
 * const response: Api.Auth.UserInfo = await fetchUserInfo()
 * ```
 *
 * @module types/api/api
 * @author EverCookie Team
 */

declare namespace Api {
  /** 通用类型 */
  namespace Common {
    /** 分页参数 */
    interface PaginationParams {
      /** 当前页码 */
      current: number
      /** 每页条数 */
      size: number
      /** 总条数 */
      total: number
    }

    /** 通用搜索参数 */
    type CommonSearchParams = Pick<PaginationParams, 'current' | 'size'>

    /** 分页响应基础结构 */
    interface PaginatedResponse<T = any> {
      records: T[]
      current: number
      size: number
      total: number
    }

    /** admin-api 分页响应结构（PageResponse） */
    interface PageResponse<T = any> {
      items: T[]
      total: number
      page: number
      pageSize: number
    }

    /** admin-api 分页请求参数 */
    interface PageParams {
      page?: number
      pageSize?: number
    }

    /** 启用状态 */
    type EnableStatus = '1' | '2'
  }

  /** 认证类型 */
  namespace Auth {
    /** 登录参数 */
    interface LoginParams {
      username: string
      password: string
    }

    /** 令牌对 */
    interface TokenPair {
      access_token: string
      refresh_token: string
      expires_in: number
    }

    /** 后端用户简要信息 */
    interface UserBrief {
      id: number
      username: string
      email: string
      display_name: string | null
      status: string
      role_ids: number[]
      last_login_at: string | null
      created_at: string | null
      updated_at: string | null
    }

    /** 登录响应（admin-api /v2/auth/login） */
    interface LoginResponse {
      user: UserBrief
      tokens: TokenPair
      role_names: string[]
      permissions: string[]
      password_change_required: boolean
    }

    /** 当前用户响应（admin-api /v2/auth/me） */
    interface CurrentUserResponse {
      user: UserBrief
      role_names: string[]
      permissions: string[]
    }

    /** 用户信息（前端归一化后的形态） */
    interface UserInfo {
      buttons: string[]
      roles: string[]
      /** 权限码列表，形如 `app.read`，支持 `app.*` 与 `*` 通配 */
      permissions: string[]
      userId: number
      userName: string
      email: string
      avatar?: string
      /** 显示名 */
      displayName?: string
      /** 账号状态 */
      status?: string
    }

    /** 修改密码参数 */
    interface ChangePasswordParams {
      old_password: string
      new_password: string
    }
  }

  /** 系统管理类型 */
  namespace SystemManage {
    /** 用户列表 */
    type UserList = Api.Common.PaginatedResponse<UserListItem>

    /** 用户列表项 */
    interface UserListItem {
      id: number
      avatar: string
      status: string
      userName: string
      userGender: string
      nickName: string
      userPhone: string
      userEmail: string
      userRoles: string[]
      createBy: string
      createTime: string
      updateBy: string
      updateTime: string
    }

    /** 用户搜索参数 */
    type UserSearchParams = Partial<
      Pick<UserListItem, 'id' | 'userName' | 'userGender' | 'userPhone' | 'userEmail' | 'status'> &
        Api.Common.CommonSearchParams
    >

    /** 角色列表 */
    type RoleList = Api.Common.PaginatedResponse<RoleListItem>

    /** 角色列表项 */
    interface RoleListItem {
      roleId: number
      roleName: string
      roleCode: string
      description: string
      enabled: boolean
      createTime: string
    }

    /** 角色搜索参数 */
    type RoleSearchParams = Partial<
      Pick<RoleListItem, 'roleId' | 'roleName' | 'roleCode' | 'description' | 'enabled'> &
        Api.Common.CommonSearchParams & {
          startTime: string | null
          endTime: string | null
        }
    >
  }

  /** 防御系统业务类型 */
  namespace Fangyu {
    /** 站点（主体对象，api_secret 仅在创建/轮换响应中出现）
     *
     * site_id 同时作为 X-App-Key 请求头的值，无独立 app_id 字段。
     */
    interface Site {
      id: number
      /**
       * 站点标识，格式 site_<hex8>，同时用作 X-App-Key 请求头。
       * 适配器中对应的配置变量为 FANGYU_SITE_ID。
       */
      site_id: string
      /** HMAC 验签密钥，明文回显，可随时查看 */
      app_secret: string
      name: string
      domain: string
      alt_domains: string[]
      /** adapter: Nginx-Lua / WordPress / CF Worker / 直连 API；sdk: 浏览器 SDK (embed.js) */
      access_mode: 'adapter' | 'sdk'
      status: string
      is_active: boolean
      sdk_version: string | null
      gateway_url: string | null
      clock_stats_enabled: boolean
      log_retention_days: number
      remark: string | null
      owner_user_id: number | null
      created_at: string | null
      updated_at: string | null
      /** 绑定的规则名称（列表接口附带，可选） */
      rule_name?: string | null
      /** 绑定的规则状态（列表接口附带，可选） */
      rule_status?: string | null
    }

    /** 创建 / 轮换站点响应（结构与 Site 一致，app_secret 已在 Site 中） */
    interface SiteCreateResponse extends Site {}

    /** 批量操作结果；逐条执行，失败项不影响其他项 */
    interface SiteBatchResult {
      succeeded: number[]
      failed: Array<{ id: string; reason: string }>
    }

    /** 批量修改站点配置载荷；未传字段保持原值 */
    interface SiteBatchUpdatePayload {
      ids: number[]
      access_mode?: 'adapter' | 'sdk'
      clock_stats_enabled?: boolean
      log_retention_days?: number
    }

    /** 站点列表查询参数 */
    interface SiteListParams extends Api.Common.PageParams {
      keyword?: string
      status?: string
      access_mode?: string
      owner_id?: number
    }

    /** 站点创建载荷 */
    interface SiteCreatePayload {
      name: string
      domain: string
      alt_domains?: string[]
      access_mode: 'adapter' | 'sdk'
      sdk_version?: string | null
      gateway_url?: string | null
      clock_stats_enabled?: boolean
      log_retention_days?: number
      remark?: string | null
    }

    /** 站点更新载荷（不含 domain，主域名不可修改） */
    interface SiteUpdatePayload {
      name?: string
      alt_domains?: string[]
      access_mode?: 'adapter' | 'sdk'
      sdk_version?: string | null
      gateway_url?: string | null
      is_active?: boolean
      clock_stats_enabled?: boolean
      log_retention_days?: number
      remark?: string | null
      status?: string
    }

    /** @deprecated 旧版 App 类型，待迁移完成后移除 */
    interface App extends Site {
      api_key: string
      description: string | null
      domains: string[]
    }

    /** @deprecated 旧版 AppPayload */
    interface AppPayload {
      name?: string
      description?: string | null
      domains?: string[]
      status?: string
    }

    /** 站点列表查询参数（旧版别名） */
    interface AppListParams extends SiteListParams {}

    /** 平台用户 */
    interface User {
      id: number
      username: string
      email: string
      display_name: string | null
      status: string
      role_ids: number[]
      roles?: Role[]
      last_login_at: string | null
      created_at: string | null
      updated_at: string | null
    }

    /** 用户列表查询参数 */
    interface UserListParams extends Api.Common.PageParams {
      keyword?: string
      status?: string
    }

    /** 角色 */
    interface Role {
      id: number
      name: string
      description: string | null
      is_system: boolean
      permissions: string[]
      created_at: string | null
      updated_at: string | null
    }

    /** 权限元数据 */
    interface Permission {
      code: string
      description: string | null
      created_at: string | null
    }

    /** 处置目标 */
    /** 地址池命中分布项 */
    interface PoolDistributionItem {
      target_url: string
      hit_count: number
      error_count: number
      first_hit_at: string
      last_hit_at: string
    }

    /** 地址池条目 */
    interface PoolEntry {
      url: string
      weight: number
      enabled: boolean
      /** 每日配额上限，null 表示不限 */
      dailyQuota: number | null
      /** 每小时配额上限，null 表示不限 */
      hourlyQuota: number | null
    }

    /** 轮询策略配置 */
    interface Rotation {
      strategy: 'hash' | 'weighted' | 'sticky' | 'round_robin' | 'failover'
      entries: PoolEntry[]
    }

    interface DispositionTarget {
      kind: string
      url: string | null
      urls: string[] | null
      rotation: Rotation | null
      httpStatus: number | null
    }

    /** 处置动作 */
    interface Disposition {
      verdict: string
      mechanism: string
      target: DispositionTarget
      challengeKind: string | null
      ttlSeconds: number
    }

    /** 规则处置动作（决策规则专用，无 verdict） */
    interface DecisionDisposition {
      mechanism: string
      target: DispositionTarget
      challengeKind: string | null
      ttlSeconds: number
    }

    /** 规则条件 */
    interface RuleCondition {
      field: string
      op: string
      value: unknown
    }

    /** 风控规则 */
    interface Rule {
      id: number
      /** 绑定的站点 ID 列表（many-to-many） */
      siteIds: number[]
      name: string
      description: string | null
      status: string
      priority: string
      group: string | null
      disposition_match: DecisionDisposition
      disposition_miss: DecisionDisposition
      /** @deprecated 旧版单路处置，编辑回填时兼容用 */
      disposition?: Disposition | null
      conditions: RuleCondition[]
      version: number
      created_at: string | null
      updated_at: string | null
    }

    /** 规则列表查询参数 */
    interface RuleListParams extends Api.Common.PageParams {
      keyword?: string
      status?: string
    }

    /** 规则创建/更新载荷 */
    interface RulePayload {
      name: string
      description?: string | null
      priority: string
      group?: string | null
      conditions: RuleCondition[]
      matchAll: boolean
      disposition_match: DecisionDisposition
      disposition_miss: DecisionDisposition
    }

    /**
     * 规则模板
     *
     * 后端 `_TEMPLATES` 的投影。决策模板带 disposition（含 verdict），
     * 打分模板带 weight，两者互斥，由 kind 区分。
     */
    interface RuleTemplate {
      id: string
      name: string
      description?: string | null
      priority?: string
      kind?: 'decision' | 'scoring'
      conditions?: RuleCondition[]
      disposition?: {
        verdict?: string
        mechanism: string
        challengeKind?: string | null
        ttlSeconds?: number | null
        target?: {
          kind?: string
          url?: string | null
          urls?: string[] | null
          rotation?: Rotation | null
          httpStatus?: number | null
        } | null
      } | null
      weight?: number | null
    }

    /** 规则试跑请求 */
    interface RulePreviewParams {
      rule: {
        appId: number
        name: string
        conditions: RuleCondition[]
        matchAll: boolean
        disposition_match: DecisionDisposition
        disposition_miss: DecisionDisposition
      }
      ip: string
      userAgent: string
    }

    /** 规则试跑的单条条件结果 */
    interface RulePreviewCondition {
      field: string
      op: string
      expected: unknown
      actual: unknown
      matched: boolean
    }

    /** 规则试跑响应 */
    interface RulePreviewResult {
      matched: boolean
      durationMs: number
      verdict?: string
      mechanism?: string
      httpStatus?: number
      targetUrl?: string | null
      conditions: RulePreviewCondition[]
      context: {
        ip: Record<string, unknown>
        ua: Record<string, unknown>
      }
    }

    /** 威胁情报记录 */
    interface ThreatIntel {
      ip: string
      category: string
      severity: string
      source: string
      confidence: number
      description: string | null
      expires_at: string | null
      created_at: string | null
    }

    /** 威胁情报列表查询参数 */
    interface ThreatIntelListParams {
      page?: number
      /** 该接口分页参数为蛇形 page_size，与其他列表接口不同 */
      page_size?: number
      category?: string
      source?: string
      severity?: string
    }

    /** 威胁情报列表响应（裸分页，不带 code 信封） */
    interface ThreatIntelList {
      items: ThreatIntel[]
      total: number
      page: number
      page_size: number
    }

    /** 访问日志 */
    interface AccessLog {
      request_id: string
      ip: string
      ip_type: string | null
      country: string | null
      asn: number | null
      connection_type: string | null
      is_vpn: boolean | null
      is_proxy: boolean | null
      device_type: string | null
      device_id: string | null
      os: string | null
      browser: string | null
      user_agent: string | null
      fingerprint: string | null
      is_bot: boolean
      crawler_vendor: string | null
      crawler_category: string | null
      verdict: string | null
      mechanism: string | null
      http_status: number | null
      decided_by: string | null
      stage: string | null
      rule_id: number | null
      reason: string | null
      score: number | null
      evercookie_restore: boolean
      shadow_rule_ids: number[] | null
      decision_cost_ms: number | null
      path: string | null
      referer: string | null
      repeat_key: string | null
      repeat_value: string | null
      accept_language: string | null
      occurred_at: string | null
      mouse_events: Array<{ type: string; x: number | null; y: number | null; ts: number | null }> | null
    }

    /** 访问日志查询参数 */
    interface AccessLogListParams {
      siteId: number
      page?: number
      pageSize?: number
      start?: string
      end?: string
      requestId?: string
      ip?: string
      fingerprint?: string
      verdict?: string
      mechanism?: string
      decidedBy?: string
      country?: string
      deviceType?: string
      crawlerCategory?: string
      connectionType?: string
      path?: string
      isBot?: boolean
    }

    /** 审计日志 */
    interface AuditLog {
      id: number
      userId: number | null
      username: string | null
      method: string
      path: string
      resource: string | null
      action: string | null
      resourceId: string | null
      statusCode: number
      ip: string | null
      userAgent: string | null
      requestId: string | null
      occurredAt: string | null
    }

    /** 审计日志查询参数 */
    interface AuditLogListParams extends Api.Common.PageParams {
      userId?: number
      resource?: string
      action?: string
      startAt?: string
      endAt?: string
      keyword?: string
    }

    /** 分析查询基础参数 */
    interface AnalyticsParams {
      site_id?: number | null
      start: string
      end: string
      filters?: Record<string, string>
    }

    /** 时间线查询参数 */
    interface TimelineParams extends AnalyticsParams {
      granularity?: 'minute' | 'hour' | 'day'
    }

    /** Top 实体查询参数 */
    interface TopEntitiesParams extends AnalyticsParams {
      dimension?: 'ip' | 'device' | 'country' | 'decided_by' | 'mechanism' | 'verdict'
      limit?: number
    }

    /** 时间线分桶 */
    interface TimelineBucket {
      bucket: string
      count: number
      verdict?: string
      mechanism?: string
      decided_by?: string
    }

    /** 处置分布分桶 */
    interface DispositionBucket {
      disposition: string
      verdict?: string
      mechanism?: string
      count: number
    }

    /** Top 实体条目 */
    interface TopEntity {
      entity: string
      count: number
    }

    /** 频控窗口定义 */
    interface ClockWindow {
      name: string
      seconds: number
    }

    /** 频控阈值配置 */
    interface ClockLimits {
      enabled: boolean
      banEnabled: boolean
      banSeconds: number
      limits: Record<string, number | null>
    }

    /** 封禁记录 */
    interface ClockBan {
      dimension: string
      value: string
      reason: string | null
      ttlSeconds: number
    }

    /** 资源投放目标：safe = 正常分支，landing = 阻断/质疑分支 */
    type PageResourceKind = 'safe' | 'landing'

    /** 页面资源（serve_alt 机制的内容来源） */
    interface PageResource {
      id: number
      appId: number
      name: string
      kind: PageResourceKind
      content: string
      content_type: string
      enabled: boolean
      created_at: string | null
      updated_at: string | null
    }

    /** 页面资源模板（后端内置，只读） */
    interface PageResourceTemplate {
      id: string
      name: string
      description: string
      kind: PageResourceKind
      /** 载入时预填的资源名建议值，也是规则处置 target.url 要填的值 */
      suggested_name: string
      content_type: string
      content: string
    }

    /** 页面资源列表查询参数 */
    interface PageResourceListParams {
      kind?: PageResourceKind
      enabled?: boolean
      page?: number
      pageSize?: number
    }

    /** 页面资源创建/更新载荷 */
    interface PageResourcePayload {
      name: string
      kind?: PageResourceKind
      content?: string
      content_type?: string
      enabled?: boolean
    }

    /** 白名单维度 */
    type WhitelistDimension = 'ip' | 'fingerprint'

    /** 白名单条目（后端按 dimension+value 存储，ip 明文，fingerprint 明文） */
    interface WhitelistEntry {
      dimension: WhitelistDimension
      value: string
      app_id: number
      /** @deprecated 使用 site_id 替代 */
      site_id?: string
      note: string
      created_by: string | null
      created_at: string | null
    }

    /** 白名单条目创建载荷 */
    interface WhitelistPayload {
      dimension: WhitelistDimension
      value: string
      note?: string
    }

    /** 封禁单条记录 */
    interface BanEntry {
      dimension: string
      value: string
      ttlSeconds: number
      reason: string
    }

    /** 封禁列表（游标翻页） */
    interface BanListResponse {
      items: BanEntry[]
      nextCursor: number
      hasMore: boolean
    }

    /** 评分配置 */
    interface ScoringConfig {
      id: number
      app_id: number
      name: string
      /** suspect 阈值：score ≥ 此值触发 suspect 处置 */
      threshold_suspect: number
      /** hostile 阈值：score ≥ 此值触发 hostile 处置 */
      threshold_hostile: number
      /** 各维度权重，键为 scorer 名，值为 0-100（网关侧除以 10 换算为浮点量纲） */
      weights: Record<string, number>
      /** 自定义处置。无 verdict——由 mechanism 推导，与规则侧一致 */
      disposition_suspect: DecisionDisposition | null
      disposition_hostile: DecisionDisposition | null
      enabled: boolean
      created_at: string | null
      updated_at: string | null
    }

    /** 评分配置更新载荷（全部可选，支持 PATCH 语义） */
    interface ScoringConfigPayload {
      name?: string
      threshold_suspect?: number
      threshold_hostile?: number
      weights?: Record<string, number>
      disposition_suspect?: DecisionDisposition | null
      disposition_hostile?: DecisionDisposition | null
      enabled?: boolean
    }
  }
}
