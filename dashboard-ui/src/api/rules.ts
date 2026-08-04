import request from '@/utils/http'

/** 全局规则列表（不限站点；传 siteId 时只返回该站点绑定的规则） */
export function fetchGetAllRules(params?: Api.Fangyu.RuleListParams & { siteId?: number }) {
  return request.get<Api.Common.PageResponse<Api.Fangyu.Rule>>({
    url: '/api/v2/rules',
    params
  })
}

/** 全局创建规则（不绑定站点） */
export function fetchCreateGlobalRule(data: Api.Fangyu.RulePayload) {
  return request.post<Api.Fangyu.Rule>({
    url: '/api/v2/rules',
    data
  })
}

/** 全量覆盖某站点绑定的规则列表，并重建该站点缓存分片 */
export function fetchBindRulesToSite(siteId: number, ruleIds: number[]) {
  return request.post<{ bound: number }>({
    url: `/api/v2/rules/bind-to-site/${siteId}`,
    data: { rule_ids: ruleIds }
  })
}

/** 全量覆盖一条规则绑定的站点列表 */
export function fetchSetRuleSites(ruleId: number, siteIds: number[]) {
  return request.post<Api.Fangyu.Rule>({
    url: `/api/v2/rules/${ruleId}/set-sites`,
    data: { site_ids: siteIds }
  })
}

/** 规则列表（按站点，兼容旧调用） */
export function fetchGetRuleList(siteId: number, params?: Api.Fangyu.RuleListParams) {
  return request.get<Api.Common.PageResponse<Api.Fangyu.Rule>>({
    url: `/api/v2/sites/${siteId}/rules`,
    params
  })
}

/** 规则详情 */
export function fetchGetRule(siteId: number, ruleId: number) {
  return request.get<Api.Fangyu.Rule>({
    url: `/api/v2/sites/${siteId}/rules/${ruleId}`
  })
}

/** 更新规则（后端为 PUT） */
export function fetchUpdateRule(siteId: number, ruleId: number, data: Api.Fangyu.RulePayload) {
  return request.put<Api.Fangyu.Rule>({
    url: `/api/v2/sites/${siteId}/rules/${ruleId}`,
    data
  })
}

/** 删除规则 */
export function fetchDeleteRule(ruleId: number) {
  return request.del<null>({
    url: `/api/v2/sites/0/rules/${ruleId}`
  })
}

/** 发布规则 */
export function fetchPublishRule(ruleId: number, data?: { change_summary?: string }) {
  return request.post<Api.Fangyu.Rule>({
    url: `/api/v2/sites/0/rules/${ruleId}/publish`,
    data
  })
}

/** 置为灰度影子（下发到 gateway 求值，但不参与真实处置） */
export function fetchShadowRule(ruleId: number) {
  return request.post<Api.Fangyu.Rule>({
    url: `/api/v2/sites/0/rules/${ruleId}/shadow`
  })
}

/** 停用规则 */
export function fetchDisableRule(ruleId: number) {
  return request.post<Api.Fangyu.Rule>({
    url: `/api/v2/sites/0/rules/${ruleId}/disable`
  })
}

/** 归档规则 */
export function fetchArchiveRule(ruleId: number) {
  return request.post<Api.Fangyu.Rule>({
    url: `/api/v2/sites/0/rules/${ruleId}/archive`
  })
}

/** 恢复规则（归档 → 草稿） */
export function fetchUnarchiveRule(ruleId: number) {
  return request.post<Api.Fangyu.Rule>({
    url: `/api/v2/sites/0/rules/${ruleId}/unarchive`
  })
}

/** 规则版本列表 */
export function fetchGetRuleVersions(ruleId: number) {
  return request.get<Record<string, unknown>[]>({
    url: `/api/v2/sites/0/rules/${ruleId}/versions`
  })
}

/** 规则试跑（仅支持决策规则） */
export function fetchPreviewRule(data: Api.Fangyu.RulePreviewParams) {
  return request.post<Api.Fangyu.RulePreviewResult>({
    url: '/api/v2/rules/preview',
    data
  })
}

/** 规则模板列表（全局，后端不分页） */
export function fetchGetRuleTemplates() {
  return request.get<Api.Fangyu.RuleTemplate[]>({
    url: '/api/v2/rules/templates'
  })
}
