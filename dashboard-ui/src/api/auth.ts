import request from '@/utils/http'

/**
 * 登录
 *
 * 该接口无需鉴权，且失败提示由登录页自行处理。
 */
export function fetchLogin(params: Api.Auth.LoginParams) {
  return request.post<Api.Auth.LoginResponse>({
    url: '/api/v2/auth/login',
    data: params,
    noAuth: true,
    showErrorMessage: false
  })
}

/** 获取当前登录用户的原始信息 */
export function fetchCurrentUser() {
  return request.get<Api.Auth.CurrentUserResponse>({
    url: '/api/v2/auth/me'
  })
}

/**
 * 把后端的 `{ user, role_names, permissions }` 归一化为模板使用的 UserInfo
 *
 * 模板的菜单过滤、按钮权限与用户展示都依赖这个扁平结构。
 */
export function normalizeUserInfo(
  payload: Api.Auth.CurrentUserResponse | Api.Auth.LoginResponse
): Api.Auth.UserInfo {
  const { user, role_names, permissions } = payload

  return {
    userId: user.id,
    userName: user.username,
    email: user.email,
    displayName: user.display_name ?? user.username,
    status: user.status,
    roles: role_names ?? [],
    permissions: permissions ?? [],
    // 模板的 useAuth 在前端模式下读 buttons 做按钮级权限，这里与权限码共用一套数据
    buttons: permissions ?? []
  }
}

/** 获取用户信息（模板守卫调用入口） */
export async function fetchGetUserInfo(): Promise<Api.Auth.UserInfo> {
  const data = await fetchCurrentUser()
  return normalizeUserInfo(data)
}

/** 修改密码 */
export function fetchChangePassword(params: Api.Auth.ChangePasswordParams) {
  return request.post<null>({
    url: '/api/v2/auth/change-password',
    data: params
  })
}

/** 刷新 access token（http 层内置调用，此处导出供显式使用） */
export function fetchRefreshToken(refreshToken: string) {
  return request.post<Api.Auth.TokenPair>({
    url: '/api/v2/auth/refresh',
    data: { refresh_token: refreshToken },
    noAuth: true,
    showErrorMessage: false
  })
}

/** 登出 */
export function fetchLogout() {
  return request.post<null>({
    url: '/api/v2/auth/logout',
    showErrorMessage: false
  })
}
