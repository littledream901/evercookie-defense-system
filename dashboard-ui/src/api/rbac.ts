import request from '@/utils/http'

/* ------------------------------ 用户 ------------------------------ */

/** 用户列表 */
export function fetchGetUserList(params?: Api.Fangyu.UserListParams) {
  return request.get<Api.Common.PageResponse<Api.Fangyu.User>>({
    url: '/api/v2/users',
    params
  })
}

/** 用户详情（含已分配角色） */
export function fetchGetUserDetail(id: number) {
  return request.get<Api.Fangyu.User>({
    url: `/api/v2/users/${id}`
  })
}

/** 新建用户 */
export function fetchCreateUser(data: {
  username: string
  email: string
  display_name?: string
  password: string
}) {
  return request.post<Api.Fangyu.User>({
    url: '/api/v2/users',
    data
  })
}

/** 更新用户（后端为 PATCH，用户名不可改） */
export function fetchUpdateUser(
  id: number,
  data: { email?: string; display_name?: string; status?: string }
) {
  return request.request<Api.Fangyu.User>({
    url: `/api/v2/users/${id}`,
    method: 'PATCH',
    data
  })
}

/** 删除用户 */
export function fetchDeleteUser(id: number) {
  return request.del<null>({
    url: `/api/v2/users/${id}`
  })
}

/** 重置用户密码 */
export function fetchResetUserPassword(id: number, data: { new_password: string }) {
  return request.post<null>({
    url: `/api/v2/users/${id}/reset-password`,
    data
  })
}

/** 分配角色 */
export function fetchAssignUserRoles(id: number, data: { role_ids: number[] }) {
  return request.post<null>({
    url: `/api/v2/users/${id}/roles`,
    data
  })
}

/* ------------------------------ 角色 ------------------------------ */

/** 角色列表（后端不分页，data 直接为数组） */
export function fetchGetRoleList() {
  return request.get<Api.Fangyu.Role[]>({
    url: '/api/v2/roles'
  })
}

/** 新建角色 */
export function fetchCreateRole(data: {
  name: string
  description?: string
  permissions: string[]
}) {
  return request.post<Api.Fangyu.Role>({
    url: '/api/v2/roles',
    data
  })
}

/** 更新角色（后端为 PATCH，角色名不可改） */
export function fetchUpdateRole(
  id: number,
  data: { description?: string; permissions?: string[] }
) {
  return request.request<Api.Fangyu.Role>({
    url: `/api/v2/roles/${id}`,
    method: 'PATCH',
    data
  })
}

/** 删除角色 */
export function fetchDeleteRole(id: number) {
  return request.del<null>({
    url: `/api/v2/roles/${id}`
  })
}

/* ------------------------------ 权限 ------------------------------ */

/** 权限列表（后端不分页） */
export function fetchGetPermissionList() {
  return request.get<Api.Fangyu.Permission[]>({
    url: '/api/v2/permissions'
  })
}

/** 新增或更新权限元数据 */
export function fetchUpsertPermission(data: { code: string; description?: string }) {
  return request.post<Api.Fangyu.Permission>({
    url: '/api/v2/permissions',
    data
  })
}
