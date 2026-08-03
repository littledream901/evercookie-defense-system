<!-- 审计日志页面：追踪管理端的操作记录 -->
<template>
  <div class="art-full-height">
    <div class="mb-3">
      <h2 class="text-lg font-medium text-g-900">审计日志</h2>
      <p class="mt-1 text-sm text-g-600">管理端操作记录，追踪配置变更与安全事件</p>
    </div>

    <AuditLogSearch
      v-show="showSearchBar"
      v-model="searchForm"
      @search="handleSearch"
      @reset="handleReset"
    ></AuditLogSearch>

    <ElCard class="art-table-card" :style="{ 'margin-top': showSearchBar ? '12px' : '0' }">
      <ArtTableHeader
        v-model:columns="columnChecks"
        v-model:showSearchBar="showSearchBar"
        :loading="loading"
        @refresh="refreshData"
      >
      </ArtTableHeader>

      <ArtTable
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      >
      </ArtTable>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { ElTag, ElTooltip } from 'element-plus'
  import { useTable } from '@/hooks/core/useTable'
  import { fetchGetAuditLogList } from '@/api/logs'
  import AuditLogSearch from './modules/audit-log-search.vue'
  import { httpStatusTag, pruneParams } from '@/constants/fangyu'

  defineOptions({ name: 'AuditLogs' })

  type AuditLog = Api.Fangyu.AuditLog

  type AuditLogSearchFormParams = {
    keyword?: string
    resource?: string
    action?: string
    daterange?: string[]
  }

  const showSearchBar = ref(false)

  const searchForm = ref<AuditLogSearchFormParams>({
    keyword: undefined,
    resource: undefined,
    action: undefined,
    daterange: undefined
  })

  /** 空值占位 */
  const dash = () => h('span', { class: 'text-g-400' }, '-')

  const {
    columns,
    columnChecks,
    data,
    loading,
    pagination,
    getData,
    replaceSearchParams,
    handleSizeChange,
    handleCurrentChange,
    refreshData
  } = useTable({
    core: {
      apiFn: fetchGetAuditLogList,
      apiParams: {
        page: 1,
        pageSize: 20
      },
      columnsFactory: () => [
        {
          prop: 'occurredAt',
          label: '时间',
          width: 170,
          formatter: (row: AuditLog) => row.occurredAt || '-'
        },
        {
          prop: 'username',
          label: '操作人',
          width: 120,
          formatter: (row: AuditLog) => row.username || (row.userId ? `#${row.userId}` : '-')
        },
        {
          prop: 'method',
          label: '方法',
          width: 90,
          formatter: (row: AuditLog) =>
            row.method ? h(ElTag, { size: 'small' }, () => row.method) : dash()
        },
        {
          prop: 'resource',
          label: '资源',
          width: 120,
          formatter: (row: AuditLog) => row.resource || '-'
        },
        {
          prop: 'action',
          label: '动作',
          width: 100,
          formatter: (row: AuditLog) => row.action || '-'
        },
        {
          prop: 'resourceId',
          label: '对象 ID',
          width: 110,
          showOverflowTooltip: true,
          formatter: (row: AuditLog) => row.resourceId || '-'
        },
        {
          prop: 'statusCode',
          label: '状态',
          width: 80,
          formatter: (row: AuditLog) =>
            row.statusCode
              ? h(ElTag, { type: httpStatusTag(row.statusCode), size: 'small' }, () =>
                  String(row.statusCode)
                )
              : dash()
        },
        {
          prop: 'ip',
          label: 'IP',
          width: 130,
          showOverflowTooltip: true,
          formatter: (row: AuditLog) => row.ip || '-'
        },
        {
          prop: 'path',
          label: '路径',
          minWidth: 220,
          showOverflowTooltip: true,
          formatter: (row: AuditLog) =>
            h(
              ElTooltip,
              {
                content: `请求 ID：${row.requestId || '-'}｜UA：${row.userAgent || '-'}`,
                placement: 'top',
                showAfter: 200
              },
              () => h('code', { class: 'text-xs' }, row.path || '-')
            )
        }
      ]
    }
  })

  /**
   * 组装请求参数，daterange 拆成 startAt / endAt
   */
  const buildParams = (form: AuditLogSearchFormParams) => {
    const { daterange, ...rest } = form
    return pruneParams({
      ...rest,
      startAt: daterange?.[0],
      endAt: daterange?.[1]
    }) as Partial<Api.Fangyu.AuditLogListParams>
  }

  /**
   * 查询
   */
  const handleSearch = (form: AuditLogSearchFormParams) => {
    replaceSearchParams(buildParams(form))
    getData()
  }

  /**
   * 重置
   */
  const handleReset = () => {
    searchForm.value = {
      keyword: undefined,
      resource: undefined,
      action: undefined,
      daterange: undefined
    }
    handleSearch(searchForm.value)
  }
</script>
