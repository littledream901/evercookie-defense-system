/**
 * API 响应类型定义模块
 *
 * 提供统一的 API 响应结构类型定义
 *
 * ## 主要功能
 *
 * - 基础响应结构定义
 * - 泛型支持（适配不同数据类型）
 * - 统一的响应格式约束
 *
 * ## 使用场景
 *
 * - API 请求响应类型约束
 * - 接口数据类型定义
 * - 响应数据解析
 *
 * @module types/common/response
 * @author EverCookie Team
 */

/**
 * 基础 API 响应结构
 *
 * admin-api 的成功响应为 `{ code: 0, message, data, request_id }`，
 * 失败响应的 code 为业务错误字符串（如 `PERM_DENIED`），因此 code 为联合类型。
 * `msg` 保留用于兼容模板既有代码。
 */
export interface BaseResponse<T = unknown> {
  /** 状态码：成功为 0，失败为业务错误码字符串 */
  code: number | string
  /** 消息（admin-api 字段名） */
  message?: string
  /** 消息（模板兼容字段） */
  msg?: string
  /** 数据 */
  data: T
  /** 链路追踪 ID */
  request_id?: string | null
}
