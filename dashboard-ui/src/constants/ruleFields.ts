/**
 * 规则条件字段元数据
 *
 * 字段的 `type` 决定值输入控件，`ops` 决定可用操作符。
 * 新增字段时必须与网关侧的取值路径保持一致，否则条件永远不会命中。
 */

/** 操作符中文字典 */
export const OPERATOR_LABELS: Record<string, string> = {
  eq: '等于',
  neq: '不等于',
  gt: '大于',
  gte: '大于等于',
  lt: '小于',
  lte: '小于等于',
  in: '在列表中',
  not_in: '不在列表中',
  in_ci: '在列表中(忽略大小写)',
  not_in_ci: '不在列表中(忽略大小写)',
  contains: '包含',
  not_contains: '不包含',
  startswith: '开头是',
  endswith: '结尾是',
  regex: '正则匹配',
  cidr_in: '在CIDR段内',
  cidr_list_in: '在CIDR列表中',
  cidr_list_not_in: '不在CIDR列表中',
  asn_in: 'ASN在列表中',
  asn_not_in: 'ASN不在列表中'
}

/** 字段值类型 */
export type FieldType = 'string' | 'enum' | 'bool' | 'number' | 'asn' | 'datetime'

/** 字段定义 */
export interface FieldDef {
  label: string
  value: string
  type: FieldType
  ops: string[]
  options?: string[]
  hint?: string
  /**
   * 该字段在运行时可能为空。
   *
   * 为空时否定类操作符（not_in / not_in_ci / neq / asn_not_in /
   * cidr_list_not_in）会**命中**。「非白名单国家一律拦截」这类规则若不额外
   * 排除空值，在 MMDB 未加载或内网地址场景下会退化为拦截全部流量。
   */
  nullable?: boolean
}

/**
 * 枚举选项的中文文案
 *
 * 键为 `字段路径.选项值`，缺失时回退到原始值。
 *
 * 为什么按字段路径而非全局值索引：同一个字符串在不同字段里含义不同。
 * `mobile` 在 ip.connectionType 里是「移动蜂窝网络」，在 ua.device_type
 * 里是「手机」；`security` 在爬虫类别里指扫描器而非「安全」。
 *
 * 国家码与品牌名不在此表：ISO 3166 码与厂商名本身就是通用标识，
 * 加中文只会让下拉变长。
 */
const OPTION_LABELS: Record<string, string> = {
  // ip.continent
  'ip.continent.AS': '亚洲',
  'ip.continent.EU': '欧洲',
  'ip.continent.NA': '北美洲',
  'ip.continent.SA': '南美洲',
  'ip.continent.AF': '非洲',
  'ip.continent.OC': '大洋洲',
  'ip.continent.AN': '南极洲',
  // ip.ipType
  'ip.ipType.ipv4': 'IPv4',
  'ip.ipType.ipv6': 'IPv6',
  // ip.connectionType —— 直接决定误杀率，必须说清
  'ip.connectionType.datacenter': '机房/云主机',
  'ip.connectionType.mobile': '移动蜂窝网络',
  'ip.connectionType.residential': '家庭宽带',
  'ip.connectionType.education': '教育网',
  'ip.connectionType.government': '政府机构',
  'ip.connectionType.unknown': '未识别',
  // ua.device_type
  'ua.device_type.desktop': '桌面电脑',
  'ua.device_type.mobile': '手机',
  'ua.device_type.tablet': '平板',
  'ua.device_type.bot': '机器人',
  'ua.device_type.tv': '智能电视',
  'ua.device_type.console': '游戏主机',
  'ua.device_type.wearable': '可穿戴设备',
  'ua.device_type.unknown': '未识别',
  // ua.os
  'ua.os.windows': 'Windows',
  'ua.os.macos': 'macOS',
  'ua.os.linux': 'Linux',
  'ua.os.android': 'Android',
  'ua.os.ios': 'iOS',
  'ua.os.harmonyos': '鸿蒙',
  'ua.os.chromeos': 'ChromeOS',
  'ua.os.ubuntu': 'Ubuntu',
  'ua.os.debian': 'Debian',
  'ua.os.centos': 'CentOS',
  'ua.os.fedora': 'Fedora',
  'ua.os.freebsd': 'FreeBSD',
  'ua.os.windows_phone': 'Windows Phone',
  'ua.os.unknown': '未识别',
  // ua.browser
  'ua.browser.chrome': 'Chrome',
  'ua.browser.firefox': 'Firefox',
  'ua.browser.safari': 'Safari',
  'ua.browser.edge': 'Edge',
  'ua.browser.ie': 'IE',
  'ua.browser.opera': 'Opera',
  'ua.browser.vivaldi': 'Vivaldi',
  'ua.browser.brave': 'Brave',
  'ua.browser.yandexbrowser': 'Yandex 浏览器',
  'ua.browser.samsungbrowser': '三星浏览器',
  'ua.browser.ucbrowser': 'UC 浏览器',
  'ua.browser.qqbrowser': 'QQ 浏览器',
  'ua.browser.miuibrowser': '小米浏览器',
  'ua.browser.huaweibrowser': '华为浏览器',
  'ua.browser.micromessenger': '微信内置浏览器',
  'ua.browser.unknown': '未识别',
  // ua.engine
  'ua.engine.blink': 'Blink（Chrome 系）',
  'ua.engine.gecko': 'Gecko（Firefox）',
  'ua.engine.webkit': 'WebKit（Safari）',
  'ua.engine.trident': 'Trident（IE）',
  'ua.engine.presto': 'Presto（旧 Opera）',
  'ua.engine.unknown': '未识别',
  // ua.client_type
  'ua.client_type.browser': '浏览器',
  'ua.client_type.app': '移动 App',
  'ua.client_type.library': '脚本库（curl / requests 等）',
  'ua.client_type.bot': '机器人',
  'ua.client_type.unknown': '未识别',
  // 爬虫类别，ua.crawler_category 与 intel.crawler_category 共用同一套取值
  'crawler_category.search_engine': '搜索引擎（Google / 百度）',
  'crawler_category.social': '社交媒体（微信 / Twitter）',
  'crawler_category.ai_crawler': 'AI 语料抓取（GPTBot / ClaudeBot）',
  'crawler_category.seo': 'SEO 工具（Ahrefs / Semrush）',
  'crawler_category.monitoring': '监控探测（UptimeRobot）',
  'crawler_category.security': '安全扫描器（sqlmap / nuclei）',
  'crawler_category.library': '脚本库（curl / requests）',
  'crawler_category.feed': 'RSS 订阅抓取',
  'crawler_category.archive': '网页存档（Wayback）',
  'crawler_category.other': '其他爬虫'
}

/** 共用同一套爬虫类别取值的字段，文案走 crawler_category 前缀 */
const CRAWLER_CATEGORY_FIELDS = new Set(['ua.crawler_category', 'intel.crawler_category'])

/**
 * 取枚举选项的展示文案
 *
 * 返回「中文 (原始值)」。保留原始值是为了让运营在看规则详情、对照访问日志
 * 或排查接口返回时能与后端数据对上，否则中文标签反而成了排查障碍。
 * 无中文文案的（国家码、品牌名）直接返回原始值。
 */
export function optionLabel(fieldValue: string, option: string): string {
  const prefix = CRAWLER_CATEGORY_FIELDS.has(fieldValue) ? 'crawler_category' : fieldValue
  const text = OPTION_LABELS[`${prefix}.${option}`]
  return text ? `${text} (${option})` : option
}

/** 空值时会命中的否定类操作符，用于给 nullable 字段出风险提示 */
export const NEGATIVE_OPS = new Set([
  'neq',
  'not_in',
  'not_in_ci',
  'not_contains',
  'asn_not_in',
  'cidr_list_not_in'
])

/** 字段分组 */
export interface FieldGroup {
  label: string
  fields: FieldDef[]
}

/* 按类型预设的操作符集合 */
const STR_OPS = [
  'eq',
  'neq',
  'contains',
  'not_contains',
  'startswith',
  'endswith',
  'regex',
  'in',
  'not_in'
]
const ENUM_OPS = ['eq', 'neq', 'in_ci', 'not_in_ci']
const BOOL_OPS = ['eq', 'neq']
const NUM_OPS = ['eq', 'neq', 'gt', 'gte', 'lt', 'lte']
const CIDR_OPS = ['cidr_in', 'cidr_list_in', 'cidr_list_not_in']
/**
 * ASN 专用操作符。
 *
 * 只给 asn_in / asn_not_in，不给 NUM_OPS：只有 ASN 族操作符做 coerce_asn
 * 归一，能同时匹配 4134 / "4134" / "AS4134"。用 eq 填 "AS4134" 不会命中。
 */
const ASN_OPS = ['asn_in', 'asn_not_in']
/** 时间字段：上下文里是 ISO 8601 字符串，只放字符串前缀/正则类比较 */
const DATETIME_OPS = ['startswith', 'contains', 'regex', 'gt', 'gte', 'lt', 'lte']

/** 取值为列表的操作符，决定值控件是否为多值输入 */
export const LIST_OPS = new Set([
  'in',
  'not_in',
  'in_ci',
  'not_in_ci',
  'asn_in',
  'asn_not_in',
  'cidr_list_in',
  'cidr_list_not_in'
])

/** 网络层（IP）字段 */
const IP_FIELDS: FieldDef[] = [
  { label: 'IP 地址', value: 'ip.ip', type: 'string', ops: [...STR_OPS, ...CIDR_OPS] },
  {
    label: '国家/地区',
    value: 'ip.country',
    type: 'enum',
    ops: ENUM_OPS,
    nullable: true,
    options: [
      'CN', 'US', 'HK', 'TW', 'MO', 'JP', 'KR', 'SG', 'DE', 'GB',
      'FR', 'RU', 'KP', 'IN', 'BR', 'AU', 'CA', 'NL', 'SE', 'NO'
    ]
  },
  {
    label: '洲际',
    value: 'ip.continent',
    type: 'enum',
    ops: ENUM_OPS,
    nullable: true,
    options: ['AS', 'EU', 'NA', 'SA', 'AF', 'OC', 'AN']
  },
  {
    label: 'ASN 号',
    value: 'ip.asn',
    type: 'asn',
    ops: ASN_OPS,
    nullable: true,
    hint: '支持 4134 / AS4134 两种写法'
  },
  { label: 'ASN 组织', value: 'ip.asnOrg', type: 'string', ops: STR_OPS, nullable: true },
  { label: '运营商(ISP)', value: 'ip.isp', type: 'string', ops: STR_OPS, nullable: true },
  {
    label: '省/州',
    value: 'ip.region',
    type: 'string',
    ops: STR_OPS,
    nullable: true,
    hint: 'MMDB City 库才有，Country 库为空'
  },
  {
    label: '城市',
    value: 'ip.city',
    type: 'string',
    ops: STR_OPS,
    nullable: true,
    hint: 'MMDB City 库才有，Country 库为空'
  },
  {
    label: 'IP 版本',
    value: 'ip.ipType',
    type: 'enum',
    ops: ENUM_OPS,
    options: ['ipv4', 'ipv6']
  },
  {
    label: '网络类型',
    value: 'ip.connectionType',
    type: 'enum',
    ops: ENUM_OPS,
    options: ['datacenter', 'mobile', 'residential', 'education', 'government', 'unknown']
  },
  { label: '是否代理', value: 'ip.isProxy', type: 'bool', ops: BOOL_OPS },
  { label: '是否 VPN', value: 'ip.isVpn', type: 'bool', ops: BOOL_OPS },
  { label: '是否 Tor', value: 'ip.isTor', type: 'bool', ops: BOOL_OPS },
  { label: '是否数据中心', value: 'ip.isDatacenter', type: 'bool', ops: BOOL_OPS },
  { label: '是否移动网络', value: 'ip.isMobileNetwork', type: 'bool', ops: BOOL_OPS },
  {
    label: 'IP 信誉分',
    value: 'ip.reputationScore',
    type: 'number',
    ops: NUM_OPS,
    hint: '0-100，越低越可疑。需配合信誉样本数判断有效性'
  },
  {
    label: 'IP 信誉样本数',
    value: 'ip.reputationSamples',
    type: 'number',
    ops: NUM_OPS,
    hint: '为 0 表示尚未评估，此时信誉分 50 是默认占位值而非真实结论'
  },
  { label: 'IP 累计请求数', value: 'ip.totalRequests', type: 'number', ops: NUM_OPS },
  { label: 'IP 最后出现时间', value: 'ip.lastSeenAt', type: 'datetime', ops: DATETIME_OPS }
]

/**
 * 威胁情报命中字段
 *
 * 由网关在决策前查询后台维护的六类情报得出，是「情报库」与「规则」之间的
 * 唯一桥梁。要按恶意 IP 分类拦截请用 intel.reasons / intel.risk_score，
 * IP 画像里没有 category 字段。
 */
const INTEL_FIELDS: FieldDef[] = [
  { label: '情报是否命中', value: 'intel.matched', type: 'bool', ops: BOOL_OPS },
  {
    label: '情报风险分',
    value: 'intel.risk_score',
    type: 'number',
    ops: NUM_OPS,
    hint: '命中情报累计风险分，未命中为 0'
  },
  {
    label: '命中原因',
    value: 'intel.reasons',
    type: 'string',
    ops: ['contains', 'not_contains'],
    hint: '字符串列表，用「包含」判断是否含某条原因'
  },
  {
    label: '情报爬虫类别',
    value: 'intel.crawler_category',
    type: 'enum',
    ops: ENUM_OPS,
    nullable: true,
    options: [
      'search_engine', 'social', 'ai_crawler', 'seo', 'monitoring',
      'security', 'library', 'feed', 'archive', 'other'
    ],
    hint: '后台录入的爬虫特征命中结果，优先于内置签名表'
  },
  {
    label: '情报爬虫名称',
    value: 'intel.crawler_name',
    type: 'string',
    ops: STR_OPS,
    nullable: true
  },
  {
    label: '是否合法爬虫',
    value: 'intel.is_legitimate_crawler',
    type: 'bool',
    ops: BOOL_OPS,
    hint: '搜索引擎与社交媒体爬虫，通常应放行以免影响 SEO'
  }
]

/** 设备 / UA 字段 */
const UA_FIELDS: FieldDef[] = [
  {
    label: '设备类型',
    value: 'ua.device_type',
    type: 'enum',
    ops: ENUM_OPS,
    options: ['desktop', 'mobile', 'tablet', 'bot', 'tv', 'console', 'wearable', 'unknown']
  },
  {
    label: '操作系统',
    value: 'ua.os',
    type: 'enum',
    ops: ENUM_OPS,
    options: [
      'windows', 'macos', 'linux', 'android', 'ios', 'harmonyos', 'chromeos',
      'ubuntu', 'debian', 'centos', 'fedora', 'freebsd', 'windows_phone', 'unknown'
    ]
  },
  { label: 'OS 版本', value: 'ua.os_version', type: 'string', ops: STR_OPS, nullable: true },
  {
    label: '浏览器',
    value: 'ua.browser',
    type: 'enum',
    ops: ENUM_OPS,
    options: [
      'chrome', 'firefox', 'safari', 'edge', 'ie', 'opera', 'vivaldi', 'brave',
      'yandexbrowser', 'samsungbrowser', 'ucbrowser', 'qqbrowser', 'miuibrowser',
      'huaweibrowser', 'micromessenger', 'unknown'
    ]
  },
  { label: '浏览器版本', value: 'ua.browser_version', type: 'string', ops: STR_OPS, nullable: true },
  {
    label: '渲染引擎',
    value: 'ua.engine',
    type: 'enum',
    ops: ENUM_OPS,
    options: ['blink', 'gecko', 'webkit', 'trident', 'presto', 'unknown']
  },
  {
    label: '设备品牌',
    value: 'ua.brand',
    type: 'enum',
    ops: ENUM_OPS,
    options: [
      'apple', 'samsung', 'huawei', 'xiaomi', 'oppo', 'vivo', 'oneplus', 'google',
      'motorola', 'nokia', 'sony', 'lg', 'htc', 'zte', 'lenovo', 'asus',
      'amazon', 'microsoft', 'unknown'
    ]
  },
  { label: '设备型号', value: 'ua.model', type: 'string', ops: STR_OPS, nullable: true },
  {
    label: '客户端类型',
    value: 'ua.client_type',
    type: 'enum',
    ops: ENUM_OPS,
    options: ['browser', 'app', 'library', 'bot', 'unknown']
  },
  { label: '客户端名称', value: 'ua.client_name', type: 'string', ops: STR_OPS },
  { label: '是否机器人', value: 'ua.is_bot', type: 'bool', ops: BOOL_OPS },
  { label: '是否移动端', value: 'ua.is_mobile', type: 'bool', ops: BOOL_OPS },
  { label: '是否空 UA', value: 'ua.is_empty', type: 'bool', ops: BOOL_OPS },
  {
    label: '爬虫类别',
    value: 'ua.crawler_category',
    type: 'enum',
    ops: ENUM_OPS,
    nullable: true,
    options: [
      'search_engine', 'social', 'ai_crawler', 'seo', 'monitoring',
      'security', 'library', 'feed', 'archive', 'other'
    ],
    hint: '非爬虫请求该字段为空'
  },
  {
    label: '爬虫厂商',
    value: 'ua.crawler_vendor',
    type: 'string',
    ops: ENUM_OPS,
    nullable: true,
    hint: '如 google / baidu / sqlmap / curl。非爬虫请求为空'
  },
  { label: '可验证爬虫', value: 'ua.crawler_verifiable', type: 'bool', ops: BOOL_OPS }
]

/** 请求字段 */
const REQUEST_FIELDS: FieldDef[] = [
  { label: '请求路径', value: 'request.path', type: 'string', ops: STR_OPS },
  {
    label: '请求方法',
    value: 'request.method',
    type: 'enum',
    ops: ENUM_OPS,
    options: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
  },
  { label: 'User-Agent', value: 'request.user_agent', type: 'string', ops: STR_OPS },
  { label: 'Referer', value: 'request.referer', type: 'string', ops: STR_OPS, nullable: true },
  { label: '有 Referer', value: 'request.has_referer', type: 'bool', ops: BOOL_OPS },
  { label: 'Session ID', value: 'request.session_id', type: 'string', ops: STR_OPS, nullable: true }
]

/** 设备画像字段 */
const DEVICE_FIELDS: FieldDef[] = [
  { label: '设备指纹', value: 'device.fingerprint', type: 'string', ops: STR_OPS },
  { label: '设备 ID', value: 'device.deviceId', type: 'string', ops: STR_OPS, nullable: true },
  {
    label: '累计请求数',
    value: 'device.totalRequests',
    type: 'number',
    ops: NUM_OPS,
    hint: '为 0 即首次出现的新设备，可用于新设备挑战'
  },
  { label: '被拦截次数', value: 'device.blockedRequests', type: 'number', ops: NUM_OPS },
  {
    label: '设备信誉分',
    value: 'device.reputationScore',
    type: 'number',
    ops: NUM_OPS,
    hint: '0-100，越低越可疑。需配合信誉样本数判断有效性'
  },
  {
    label: '设备信誉样本数',
    value: 'device.reputationSamples',
    type: 'number',
    ops: NUM_OPS,
    hint: '为 0 表示尚未评估，此时信誉分 50 是默认占位值而非真实结论'
  },
  {
    label: '设备标签',
    value: 'device.tags',
    type: 'string',
    ops: ['contains', 'not_contains'],
    hint: '字符串列表，用「包含」判断是否含某个标签'
  },
  { label: '首次出现时间', value: 'device.firstSeenAt', type: 'datetime', ops: DATETIME_OPS },
  { label: '最后出现时间', value: 'device.lastSeenAt', type: 'datetime', ops: DATETIME_OPS }
]

/** 全部字段分组 */
export const FIELD_GROUPS: FieldGroup[] = [
  { label: '网络层（IP）', fields: IP_FIELDS },
  { label: '设备/UA', fields: UA_FIELDS },
  { label: '请求', fields: REQUEST_FIELDS },
  { label: '设备画像', fields: DEVICE_FIELDS },
  { label: '威胁情报', fields: INTEL_FIELDS }
]

/** 扁平字段列表 */
export const ALL_FIELDS: FieldDef[] = FIELD_GROUPS.flatMap((g) => g.fields)

/** 字段查找表 */
export const FIELD_MAP: Record<string, FieldDef> = Object.fromEntries(
  ALL_FIELDS.map((f) => [f.value, f])
)

/**
 * 取某字段可用的操作符选项
 *
 * 字段未知时只返回 eq，不再降级返回全部操作符：未知字段说明取值路径写错了，
 * 给出更宽的操作符选择只会掩盖问题。字段是否合法由 isKnownField 单独提示。
 */
export function getOperatorOptions(fieldValue: string): Array<{ label: string; value: string }> {
  const def = FIELD_MAP[fieldValue]
  if (!def) return [{ label: OPERATOR_LABELS.eq, value: 'eq' }]
  return def.ops.map((v) => ({ label: OPERATOR_LABELS[v] ?? v, value: v }))
}

/** 字段是否在已知字段表中。用于给脏字段出告警而非静默放过 */
export function isKnownField(fieldValue: string): boolean {
  return fieldValue in FIELD_MAP
}

/**
 * 检查字段与操作符的组合是否有落空/误杀风险，返回提示文案
 *
 * 两类风险：
 *   1. 字段不在已知表中 → 网关取不到值，条件永不命中；
 *   2. 可空字段配否定类操作符 → 取值为空时条件会命中，可能造成误杀。
 */
export function conditionRiskHint(fieldValue: string, op: string): string | null {
  const def = FIELD_MAP[fieldValue]
  if (!def) {
    return `字段 ${fieldValue} 不在可用字段表中，网关取不到值，此条件永远不会命中`
  }
  if (def.nullable && NEGATIVE_OPS.has(op)) {
    return `${def.label} 可能为空，取值为空时此条件会命中。如需排除空值，请再加一条「${def.label} 不等于 空」`
  }
  return null
}

/**
 * 按字段类型与操作符推导默认值
 *
 * 列表类操作符用空数组，布尔用 true，数值用 null，其余用空串。
 */
export function defaultValueFor(type: FieldType | undefined, op: string): unknown {
  if (LIST_OPS.has(op)) return []
  if (type === 'bool') return true
  if (type === 'number' || type === 'asn') return null
  return ''
}
