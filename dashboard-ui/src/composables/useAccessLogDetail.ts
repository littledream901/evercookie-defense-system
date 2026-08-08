import { ref, watch } from 'vue'
import { fetchGetAccessLog, fetchGetAccessLogTraces } from '@/api/logs'
import { ElMessage } from 'element-plus'

interface UseAccessLogDetailProps {
  visible: boolean
  requestId: string
  siteId?: number
}

/**
 * 访问日志详情 Composable
 * 
 * 用于管理详情抽屉的数据加载和状态
 */
export function useAccessLogDetail(props: UseAccessLogDetailProps) {
  // 基础详情
  const loading = ref(false)
  const detail = ref<Api.Fangyu.AccessLog | null>(null)
  
  // 规则命中明细
  const traces = ref<Api.Fangyu.DecisionTrace[]>([])
  const tracesLoading = ref(false)
  const tracesLoaded = ref(false)

  // 请求序号：防止快速切换记录时先发后至的响应覆盖当前记录
  let loadSeq = 0

  /**
   * 加载访问日志详情
   */
  async function loadDetail() {
    if (!props.requestId) return
    
    const seq = ++loadSeq
    loading.value = true
    detail.value = null
    
    try {
      const res = await fetchGetAccessLog(props.requestId, 
        props.siteId ? { siteId: props.siteId } : undefined
      )
      
      // 只有当前请求序号匹配时才更新数据（防止先发后至）
      if (seq === loadSeq) {
        detail.value = res || null
      }
    } catch (err: any) {
      console.error('加载日志详情失败:', err)
      if (seq === loadSeq) {
        detail.value = null
        ElMessage.error(err?.message || '加载日志详情失败，请稍后重试')
      }
    } finally {
      if (seq === loadSeq) {
        loading.value = false
      }
    }
  }

  /**
   * 加载规则条件命中明细
   */
  async function loadTraces() {
    if (!props.requestId) return
    
    // 如果已经加载过，不重复加载
    if (tracesLoaded.value) return
    
    tracesLoading.value = true
    traces.value = []
    
    try {
      const res = await fetchGetAccessLogTraces(props.requestId, 
        props.siteId ? { siteId: props.siteId } : undefined
      )
      traces.value = res || []
      tracesLoaded.value = true
    } catch (err: any) {
      console.error('加载规则明细失败:', err)
      tracesLoaded.value = true
      // 不显示错误提示，因为数据可能已过期（7天TTL）
    } finally {
      tracesLoading.value = false
    }
  }

  /**
   * 重置所有状态
   */
  function reset() {
    detail.value = null
    traces.value = []
    tracesLoaded.value = false
    loading.value = false
    tracesLoading.value = false
  }

  // 监听 visible 和 requestId 变化
  watch(
    () => [props.visible, props.requestId] as const,
    ([visible, id]) => {
      if (visible && id) {
        // 打开抽屉时加载基础详情
        loadDetail()
      } else {
        // 关闭抽屉时重置状态
        reset()
      }
    },
    { immediate: true }
  )

  return {
    // 状态
    loading,
    detail,
    traces,
    tracesLoading,
    tracesLoaded,
    
    // 方法
    loadDetail,
    loadTraces,
    reset
  }
}
