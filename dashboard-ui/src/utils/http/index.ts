/**
 * HTTP 请求封装模块
 * 基于 Axios 封装的 HTTP 请求工具，提供统一的请求/响应处理
 *
 * ## 主要功能
 *
 * - 请求/响应拦截器（自动添加 Token、统一错误处理）
 * - 401 未授权自动登出（带防抖机制）
 * - 请求失败自动重试（可配置）
 * - 统一的成功/错误消息提示
 * - 支持 GET/POST/PUT/DELETE 等常用方法
 *
 * @module utils/http
 * @author EverCookie Team
 */

import axios, { AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { useUserStore } from '@/store/modules/user'
import { ApiStatus } from './status'
import { HttpError, handleError, showError, showSuccess } from './error'
import { $t } from '@/locales'
import { BaseResponse } from '@/types'

/** 请求配置常量 */
const REQUEST_TIMEOUT = 15000
const LOGOUT_DELAY = 500
const MAX_RETRIES = 0
const RETRY_DELAY = 1000
const UNAUTHORIZED_DEBOUNCE_TIME = 3000

/** admin-api 成功业务码 */
const BIZ_SUCCESS_CODE = 0

/** 401防抖状态 */
let isUnauthorizedErrorShown = false
let unauthorizedTimer: NodeJS.Timeout | null = null

/** 扩展 AxiosRequestConfig */
interface ExtendedAxiosRequestConfig extends AxiosRequestConfig {
  showErrorMessage?: boolean
  showSuccessMessage?: boolean
  /** 跳过 token 注入与 401 刷新（用于登录、刷新令牌等接口） */
  noAuth?: boolean
  /** 内部标记：该请求已重试过一次，避免刷新令牌死循环 */
  _retry?: boolean
}

const { VITE_API_URL, VITE_WITH_CREDENTIALS } = import.meta.env

/** Axios实例 */
const axiosInstance = axios.create({
  timeout: REQUEST_TIMEOUT,
  baseURL: VITE_API_URL,
  withCredentials: VITE_WITH_CREDENTIALS === 'true',
  validateStatus: (status) => status >= 200 && status < 300,
  transformResponse: [
    (data, headers) => {
      const contentType = headers['content-type']
      if (contentType?.includes('application/json')) {
        try {
          return JSON.parse(data)
        } catch {
          return data
        }
      }
      return data
    }
  ]
})

/** 请求拦截器 */
axiosInstance.interceptors.request.use(
  (request: InternalAxiosRequestConfig) => {
    const { accessToken } = useUserStore()
    const noAuth = (request as ExtendedAxiosRequestConfig).noAuth
    // admin-api 要求 `Authorization: Bearer <token>`
    if (accessToken && !noAuth) request.headers.set('Authorization', `Bearer ${accessToken}`)

    if (request.data && !(request.data instanceof FormData) && !request.headers['Content-Type']) {
      request.headers.set('Content-Type', 'application/json')
      request.data = JSON.stringify(request.data)
    }

    return request
  },
  (error) => {
    showError(createHttpError($t('httpMsg.requestConfigError'), ApiStatus.error))
    return Promise.reject(error)
  }
)

/** 响应拦截器 */
axiosInstance.interceptors.response.use(
  (response: AxiosResponse<BaseResponse>) => {
    const payload = response.data

    // 部分接口（如 /v2/threat-intel）直接返回业务 dict，不带 code/message 信封，原样放行
    if (!payload || typeof payload !== 'object' || !('code' in payload)) return response

    const { code } = payload
    const message = payload.message ?? payload.msg

    // admin-api 成功码为 0，同时兼容模板默认的 200
    if (code === BIZ_SUCCESS_CODE || code === ApiStatus.success) return response
    if (code === ApiStatus.unauthorized) handleUnauthorizedError(message)

    throw createHttpError(message || $t('httpMsg.requestFailed'), ApiStatus.error)
  },
  (error) => {
    return Promise.reject(handleError(error))
  }
)

/** 统一创建HttpError */
function createHttpError(message: string, code: number) {
  return new HttpError(message, code)
}

/** 处理401错误（带防抖） */
function handleUnauthorizedError(message?: string): never {
  const error = createHttpError(message || $t('httpMsg.unauthorized'), ApiStatus.unauthorized)

  if (!isUnauthorizedErrorShown) {
    isUnauthorizedErrorShown = true
    logOut()

    unauthorizedTimer = setTimeout(resetUnauthorizedError, UNAUTHORIZED_DEBOUNCE_TIME)

    showError(error, true)
    throw error
  }

  throw error
}

/** 重置401防抖状态 */
function resetUnauthorizedError() {
  isUnauthorizedErrorShown = false
  if (unauthorizedTimer) clearTimeout(unauthorizedTimer)
  unauthorizedTimer = null
}

/** 退出登录函数 */
function logOut() {
  setTimeout(() => {
    useUserStore().logOut()
  }, LOGOUT_DELAY)
}

/** 是否需要重试 */
function shouldRetry(statusCode: number) {
  return [
    ApiStatus.requestTimeout,
    ApiStatus.internalServerError,
    ApiStatus.badGateway,
    ApiStatus.serviceUnavailable,
    ApiStatus.gatewayTimeout
  ].includes(statusCode)
}

/** 请求重试逻辑 */
async function retryRequest<T>(
  config: ExtendedAxiosRequestConfig,
  retries: number = MAX_RETRIES
): Promise<T> {
  try {
    return await request<T>(config)
  } catch (error) {
    if (retries > 0 && error instanceof HttpError && shouldRetry(error.code)) {
      await delay(RETRY_DELAY)
      return retryRequest<T>(config, retries - 1)
    }
    throw error
  }
}

/** 延迟函数 */
function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** 刷新令牌并发控制 */
let isRefreshing = false
let refreshWaiters: Array<(token: string | null) => void> = []

function notifyRefreshWaiters(token: string | null) {
  refreshWaiters.forEach((resolve) => resolve(token))
  refreshWaiters = []
}

/**
 * 用 refreshToken 换取新的 accessToken
 *
 * 走裸 axios 以绕过拦截器，避免刷新请求自身触发 401 递归。
 */
async function refreshAccessToken(): Promise<string | null> {
  const userStore = useUserStore()
  const refreshToken = userStore.refreshToken
  if (!refreshToken) return null

  try {
    const resp = await axios.post(`${VITE_API_URL}api/v2/auth/refresh`, {
      refresh_token: refreshToken
    })
    const tokens = resp.data?.data ?? {}
    if (!tokens.access_token) return null

    userStore.setToken(tokens.access_token, tokens.refresh_token || refreshToken)
    return tokens.access_token
  } catch {
    return null
  }
}

/** 判断错误是否为 401 未授权 */
function isUnauthorized(error: unknown): boolean {
  return error instanceof HttpError && error.code === ApiStatus.unauthorized
}

/** 请求函数 */
async function request<T = any>(config: ExtendedAxiosRequestConfig): Promise<T> {
  // POST | PUT 参数自动填充
  if (
    ['POST', 'PUT'].includes(config.method?.toUpperCase() || '') &&
    config.params &&
    !config.data
  ) {
    config.data = config.params
    config.params = undefined
  }

  try {
    const res = await axiosInstance.request<BaseResponse<T>>(config)
    const payload = res.data

    // 无信封的裸响应（如 /v2/threat-intel）直接返回整体
    if (!payload || typeof payload !== 'object' || !('code' in payload)) {
      return payload as T
    }

    // 显示成功消息
    const successMsg = payload.message ?? payload.msg
    if (config.showSuccessMessage && successMsg) {
      showSuccess(successMsg)
    }

    return payload.data as T
  } catch (error) {
    // 401 时尝试用 refreshToken 续期后重放一次
    if (isUnauthorized(error) && !config.noAuth && !config._retry) {
      config._retry = true

      if (isRefreshing) {
        // 已有刷新在进行，挂起等待结果
        const token = await new Promise<string | null>((resolve) => refreshWaiters.push(resolve))
        if (token) return request<T>(config)
      } else {
        isRefreshing = true
        const token = await refreshAccessToken()
        isRefreshing = false
        notifyRefreshWaiters(token)
        if (token) return request<T>(config)
      }

      // 刷新失败，走统一登出
      handleUnauthorizedError()
    }

    if (error instanceof HttpError && error.code !== ApiStatus.unauthorized) {
      const showMsg = config.showErrorMessage !== false
      showError(error, showMsg)
    }
    return Promise.reject(error)
  }
}

/** API方法集合 */
const api = {
  get<T>(config: ExtendedAxiosRequestConfig) {
    return retryRequest<T>({ ...config, method: 'GET' })
  },
  post<T>(config: ExtendedAxiosRequestConfig) {
    return retryRequest<T>({ ...config, method: 'POST' })
  },
  put<T>(config: ExtendedAxiosRequestConfig) {
    return retryRequest<T>({ ...config, method: 'PUT' })
  },
  del<T>(config: ExtendedAxiosRequestConfig) {
    return retryRequest<T>({ ...config, method: 'DELETE' })
  },
  request<T>(config: ExtendedAxiosRequestConfig) {
    return retryRequest<T>(config)
  }
}

export default api
