import request from '@/utils/http'

/** 获取全局流水线配置 */
export function fetchGetGlobalPipelineConfig() {
  return request.get<Api.Fangyu.PipelineConfig>({
    url: '/api/v2/pipeline-config/global'
  })
}

/** 保存全局流水线配置 */
export function fetchPutGlobalPipelineConfig(data: Api.Fangyu.PipelineConfigPayload) {
  return request.put<Api.Fangyu.PipelineConfig>({
    url: '/api/v2/pipeline-config/global',
    data
  })
}

/** 获取站点流水线配置 */
export function fetchGetPipelineConfig(siteId: number) {
  return request.get<Api.Fangyu.PipelineConfig>({
    url: `/api/v2/sites/${siteId}/pipeline-config`
  })
}

/** 保存站点流水线配置 */
export function fetchPutPipelineConfig(siteId: number, data: Api.Fangyu.PipelineConfigPayload) {
  return request.put<Api.Fangyu.PipelineConfig>({
    url: `/api/v2/sites/${siteId}/pipeline-config`,
    data
  })
}
