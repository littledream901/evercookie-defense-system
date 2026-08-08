<template>
  <ArtSearchBar
    ref="searchBarRef"
    v-model="formData"
    :items="formItems"
    :rules="rules"
    @reset="handleReset"
    @search="handleSearch"
  >
  </ArtSearchBar>
</template>

<script setup lang="ts">
  import { DECIDED_BY_LABELS, MECHANISM_OPTIONS, VERDICT_OPTIONS } from '@/constants/disposition'
  import { DEVICE_TYPE_OPTIONS } from '@/constants/fangyu'

  type AccessLogSearchFormParams = {
    requestId?: string
    ip?: string
    verdict?: string
    mechanism?: string
    decidedBy?: string
    deviceType?: string
    isBot?: boolean
    isCrawler?: boolean
    crawlerCategory?: string
    crawlerVendor?: string
    ipType?: string
    riskTags?: string[]
    accessSource?: string
    country?: string
    asn?: number
    path?: string
    visitorId?: string
    daterange?: string[]
  }

  interface Props {
    modelValue: AccessLogSearchFormParams
  }

  interface Emits {
    (e: 'update:modelValue', value: AccessLogSearchFormParams): void
    (e: 'search', params: AccessLogSearchFormParams): void
    (e: 'reset'): void
  }

  const props = defineProps<Props>()
  const emit = defineEmits<Emits>()

  const searchBarRef = ref()

  /**
   * 表单数据双向绑定
   */
  const formData = computed({
    get: () => props.modelValue,
    set: (val) => emit('update:modelValue', val)
  })

  /**
   * 表单校验规则
   */
  const rules = {}

  /** 裁决选项，剔除 desc 避免透传到 ElOption */
  const verdictOptions = VERDICT_OPTIONS.map((o) => ({ label: o.label, value: o.value }))

  /** 机制选项 */
  const mechanismOptions = MECHANISM_OPTIONS.map((o) => ({ label: o.label, value: o.value }))

  /** 处置来源选项，由中文映射表反推 */
  const decidedByOptions = Object.entries(DECIDED_BY_LABELS).map(([value, label]) => ({
    label,
    value
  }))

  /** 是否爬虫 */
  const botOptions = [
    { label: '仅爬虫', value: true },
    { label: '仅真人', value: false }
  ]

  /** 爬虫分类选项 */
  const crawlerCategoryOptions = [
    { label: '搜索引擎', value: 'search_engine' },
    { label: '社交平台', value: 'social' },
    { label: 'AI 爬虫', value: 'ai_crawler' },
    { label: 'SEO 工具', value: 'seo' },
    { label: '监控服务', value: 'monitoring' },
    { label: '安全扫描', value: 'security' },
    { label: 'HTTP 库', value: 'library' },
    { label: '订阅抓取', value: 'feed' },
    { label: '归档服务', value: 'archive' },
    { label: '其他爬虫', value: 'other' }
  ]

  /** 爬虫厂商选项 */
  const crawlerVendorOptions = [
    { label: 'Google', value: 'google' },
    { label: 'Bing', value: 'bing' },
    { label: 'Baidu', value: 'baidu' },
    { label: 'Yandex', value: 'yandex' },
    { label: 'Facebook', value: 'facebook' },
    { label: 'LinkedIn', value: 'linkedin' },
    { label: 'Twitter', value: 'twitter' },
    { label: 'OpenAI', value: 'openai' },
    { label: 'Anthropic', value: 'anthropic' },
    { label: 'Bytedance', value: 'bytedance' },
    { label: 'Apple', value: 'apple' },
    { label: 'Amazon', value: 'amazon' },
    { label: 'Semrush', value: 'semrush' },
    { label: 'Ahrefs', value: 'ahrefs' },
    { label: 'Moz', value: 'moz' },
    { label: 'Screaming Frog', value: 'screamingfrog' },
    { label: 'DataDog', value: 'datadog' },
    { label: 'Pingdom', value: 'pingdom' },
    { label: 'UptimeRobot', value: 'uptimerobot' },
    { label: 'Internet Archive', value: 'internetarchive' },
    { label: 'Common Crawl', value: 'commoncrawl' },
    { label: '其他', value: 'unknown' }
  ]

  const ipTypeOptions = [
    { label: '数据中心/IDC', value: 'datacenter' },
    { label: '住宅宽带',     value: 'residential' },
    { label: '移动网络',     value: 'mobile' },
    { label: 'VPN',          value: 'vpn' },
    { label: '代理',         value: 'proxy' },
    { label: 'Tor',          value: 'tor' },
  ]

  const accessSourceOptions = [
    { label: 'Nginx-Lua', value: 'nginx' },
    { label: 'SDK',       value: 'sdk' },
    { label: 'CF Worker', value: 'cloudflare' },
    { label: '直接 API',  value: 'api' },
  ]

  /**
   * 搜索表单配置项
   */
  const formItems = computed(() => [
    {
      label: '请求 ID',
      key: 'requestId',
      type: 'input',
      props: { placeholder: '请输入请求 ID', clearable: true }
    },
    {
      label: 'IP',
      key: 'ip',
      type: 'input',
      props: { placeholder: '请输入 IP', clearable: true }
    },
    {
      label: '裁决',
      key: 'verdict',
      type: 'select',
      props: { placeholder: '请选择裁决', options: verdictOptions, clearable: true }
    },
    {
      label: '机制',
      key: 'mechanism',
      type: 'select',
      props: { placeholder: '请选择机制', options: mechanismOptions, clearable: true }
    },
    {
      label: '处置来源',
      key: 'decidedBy',
      type: 'select',
      props: { placeholder: '请选择处置来源', options: decidedByOptions, clearable: true }
    },
    {
      label: '设备类型',
      key: 'deviceType',
      type: 'select',
      props: { placeholder: '请选择设备类型', options: DEVICE_TYPE_OPTIONS, clearable: true }
    },
    {
      label: '是否爬虫',
      key: 'isBot',
      type: 'select',
      props: { placeholder: '请选择', options: botOptions, clearable: true }
    },
    {
      label: '是否识别爬虫',
      key: 'isCrawler',
      type: 'select',
      props: { placeholder: '请选择', options: botOptions, clearable: true }
    },
    {
      label: '爬虫分类',
      key: 'crawlerCategory',
      type: 'select',
      props: { placeholder: '请选择爬虫分类', options: crawlerCategoryOptions, clearable: true }
    },
    {
      label: '爬虫厂商',
      key: 'crawlerVendor',
      type: 'select',
      props: { placeholder: '请选择爬虫厂商', options: crawlerVendorOptions, clearable: true, filterable: true }
    },
    {
      label: 'IP 类型',
      key: 'ipType',
      type: 'select',
      props: { placeholder: '请选择 IP 类型', options: ipTypeOptions, clearable: true }
    },
    {
      label: '接入来源',
      key: 'accessSource',
      type: 'select',
      props: { placeholder: '请选择接入方式', options: accessSourceOptions, clearable: true }
    },
    {
      label: '国家',
      key: 'country',
      type: 'input',
      props: { placeholder: '国家代码，如 CN', clearable: true, maxlength: 2 }
    },
    {
      label: 'ASN',
      key: 'asn',
      type: 'input-number',
      props: { placeholder: 'ASN 编号', min: 1, controlsPosition: 'right', style: { width: '100%' } }
    },
    {
      label: '请求路径',
      key: 'path',
      type: 'input',
      props: { placeholder: '如 /api/login', clearable: true }
    },
    {
      label: '访客 ID',
      key: 'visitorId',
      type: 'input',
      props: { placeholder: '指纹 / visitor ID', clearable: true }
    },
    {
      label: '时间范围',
      key: 'daterange',
      type: 'datetime',
      props: {
        type: 'datetimerange',
        valueFormat: 'YYYY-MM-DDTHH:mm:ss',
        rangeSeparator: '至',
        startPlaceholder: '开始',
        endPlaceholder: '结束',
        style: { width: '100%' }
      }
    }
  ])

  /**
   * 处理重置事件
   */
  const handleReset = () => {
    emit('reset')
  }

  /**
   * 处理搜索事件
   */
  const handleSearch = async (params: AccessLogSearchFormParams) => {
    await searchBarRef.value.validate()
    emit('search', params)
  }
</script>
