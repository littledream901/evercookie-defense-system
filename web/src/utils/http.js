import axios from 'axios'
import { getAccessToken, getRefreshToken, setTokens, clearTokens } from './token'

const BASE = import.meta.env.VITE_API_BASE || '/api'

const http = axios.create({
  baseURL: BASE,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

let refreshing = false
let waiters = []

function notifyWaiters(token) {
  waiters.forEach((cb) => cb(token))
  waiters = []
}

async function tryRefresh() {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return null
  try {
    // 裸 axios 不走响应拦截器，需自行剥掉 HTTP 层的 resp.data，
    // 再取业务包装层 { code, data: { tokens: {...} } } 里的 tokens。
    const resp = await axios.post(`${BASE}/v2/auth/refresh`, { refresh_token: refreshToken })
    const tokens = resp.data?.data?.tokens ?? resp.data?.tokens ?? {}
    if (!tokens.access_token) {
      clearTokens()
      return null
    }
    setTokens(tokens.access_token, tokens.refresh_token || refreshToken)
    return tokens.access_token
  } catch (e) {
    clearTokens()
    return null
  }
}

http.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token && !config.noAuth) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (resp) => resp.data,
  async (error) => {
    const { response, config } = error
    if (!response) return Promise.reject({ message: '网络错误', raw: error })

    if (response.status === 401 && !config._retry) {
      config._retry = true
      if (refreshing) {
        return new Promise((resolve) => {
          waiters.push((token) => {
            if (!token) return resolve(Promise.reject({ message: '登录已失效' }))
            config.headers.Authorization = `Bearer ${token}`
            resolve(http(config))
          })
        })
      }
      refreshing = true
      const token = await tryRefresh()
      refreshing = false
      notifyWaiters(token)
      if (!token) {
        window.location.href = '/login'
        return Promise.reject({ message: '登录已失效' })
      }
      config.headers.Authorization = `Bearer ${token}`
      return http(config)
    }

    const detail = response.data?.detail || response.data?.message || response.statusText
    return Promise.reject({ status: response.status, message: detail, raw: response.data })
  }
)

export default http
