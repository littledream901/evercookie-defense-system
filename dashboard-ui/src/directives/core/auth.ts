/**
 * v-auth 权限指令
 *
 * 基于权限标识控制 DOM 元素的显示和隐藏。
 * 需同时满足两个条件元素才可见：当前页面声明了该操作，且用户持有对应权限码。
 *
 * ## 主要功能
 *
 * - 页面声明校验 - 检查路由 meta.authList 是否包含该操作标识
 * - 用户权限校验 - 通过 userStore.hasPermission 匹配权限码，支持通配
 * - 响应式更新 - 权限变化时自动更新元素状态
 *
 * ## 使用示例
 *
 * ```vue
 * <!-- 只有拥有 'add' 权限的用户才能看到新增按钮 -->
 * <el-button v-auth="'add'">新增</el-button>
 *
 * <!-- 只有拥有 'edit' 权限的用户才能看到编辑按钮 -->
 * <el-button v-auth="'edit'">编辑</el-button>
 *
 * <!-- 只有拥有 'delete' 权限的用户才能看到删除按钮 -->
 * <el-button v-auth="'delete'">删除</el-button>
 * ```
 *
 * ## 注意事项
 *
 * - 通过 display 样式隐藏元素，不移除 DOM 节点：KeepAlive 缓存的页面复用时
 *   不会重新触发 mounted，移除节点将无法恢复
 * - 页面可用操作清单来自当前路由的 meta.authList，用户权限来自 userStore
 *
 * @module directives/auth
 * @author EverCookie Team
 */

import { router } from '@/router'
import { useUserStore } from '@/store/modules/user'
import { App, Directive, DirectiveBinding } from 'vue'

export type AuthDirective = Directive<HTMLElement, string>

function checkAuthPermission(el: HTMLElement, binding: DirectiveBinding<string>): void {
  const userStore = useUserStore()

  // 页面是否声明了该按钮：路由 meta.authList 描述当前页可用的操作
  const authList = (router.currentRoute.value.meta.authList as Array<{ authMark: string }>) || []
  const declared = authList.some((item) => item.authMark === binding.value)

  // 用户是否实际持有该权限码（支持 `resource.*` 与 `*` 通配）
  const granted = userStore.hasPermission(binding.value)

  // 用 display 控制而非移除节点：KeepAlive 缓存的页面不会重走 mounted，
  // removeChild 造成的隐藏无法恢复
  el.style.display = declared && granted ? '' : 'none'
}

const authDirective: AuthDirective = {
  mounted: checkAuthPermission,
  updated: checkAuthPermission
}

export function setupAuthDirective(app: App): void {
  app.directive('auth', authDirective)
}
