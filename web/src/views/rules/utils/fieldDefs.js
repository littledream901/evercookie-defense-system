export const OPERATOR_LABELS = {
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
  asn_not_in: 'ASN不在列表中',
}

const STR_OPS = ['eq', 'neq', 'contains', 'not_contains', 'startswith', 'endswith', 'regex', 'in', 'not_in']
const ENUM_OPS = ['eq', 'neq', 'in_ci', 'not_in_ci']
const BOOL_OPS = ['eq']
const NUM_OPS = ['eq', 'neq', 'gt', 'gte', 'lt', 'lte']
const CIDR_OPS = ['cidr_in', 'cidr_list_in', 'cidr_list_not_in']
const ASN_OPS = ['asn_in', 'asn_not_in']

export const FIELD_GROUPS = [
  {
    label: '网络层（IP）',
    fields: [
      { label: 'IP 地址', value: 'ip.ip', type: 'string', ops: [...STR_OPS, ...CIDR_OPS] },
      { label: '国家/地区', value: 'ip.country', type: 'enum', ops: ENUM_OPS,
        options: ['CN','US','HK','TW','MO','JP','KR','SG','DE','GB','FR','RU','KP','IN','BR','AU','CA','NL','SE','NO'] },
      { label: '洲际', value: 'ip.continent', type: 'enum', ops: ENUM_OPS,
        options: ['AS','EU','NA','SA','AF','OC','AN'] },
      { label: 'ASN 号', value: 'ip.asn', type: 'asn', ops: [...NUM_OPS, ...ASN_OPS] },
      { label: 'ASN 组织', value: 'ip.asnOrg', type: 'string', ops: STR_OPS },
      { label: '运营商(ISP)', value: 'ip.isp', type: 'string', ops: STR_OPS },
      { label: '网络类型', value: 'ip.connectionType', type: 'enum', ops: ENUM_OPS,
        options: ['datacenter','mobile','residential','education','government','unknown'] },
      { label: '是否代理', value: 'ip.isProxy', type: 'bool', ops: BOOL_OPS },
      { label: '是否 VPN', value: 'ip.isVpn', type: 'bool', ops: BOOL_OPS },
      { label: '是否 Tor', value: 'ip.isTor', type: 'bool', ops: BOOL_OPS },
      { label: '是否数据中心', value: 'ip.isDatacenter', type: 'bool', ops: BOOL_OPS },
      { label: '是否移动网络', value: 'ip.isMobileNetwork', type: 'bool', ops: BOOL_OPS },
    ],
  },
  {
    label: '设备/UA',
    fields: [
      { label: '设备类型', value: 'ua.device_type', type: 'enum', ops: ENUM_OPS,
        options: ['desktop','mobile','tablet','bot','tv','console','wearable','unknown'] },
      { label: '操作系统', value: 'ua.os', type: 'enum', ops: ENUM_OPS,
        options: ['windows','macos','linux','android','ios','harmonyos','chromeos','ubuntu','debian','centos','fedora','freebsd','windows_phone','unknown'] },
      { label: 'OS 版本', value: 'ua.os_version', type: 'string', ops: STR_OPS },
      { label: '浏览器', value: 'ua.browser', type: 'enum', ops: ENUM_OPS,
        options: ['chrome','firefox','safari','edge','ie','opera','vivaldi','brave','yandexbrowser','samsungbrowser','ucbrowser','qqbrowser','miuibrowser','huaweibrowser','micromessenger','unknown'] },
      { label: '浏览器版本', value: 'ua.browser_version', type: 'string', ops: STR_OPS },
      { label: '渲染引擎', value: 'ua.engine', type: 'enum', ops: ENUM_OPS,
        options: ['blink','gecko','webkit','trident','presto','unknown'] },
      { label: '设备品牌', value: 'ua.brand', type: 'enum', ops: ENUM_OPS,
        options: ['apple','samsung','huawei','xiaomi','oppo','vivo','oneplus','google','motorola','nokia','sony','lg','htc','zte','lenovo','asus','amazon','microsoft','unknown'] },
      { label: '设备型号', value: 'ua.model', type: 'string', ops: STR_OPS },
      { label: '客户端类型', value: 'ua.client_type', type: 'enum', ops: ENUM_OPS,
        options: ['browser','app','library','bot','unknown'] },
      { label: '客户端名称', value: 'ua.client_name', type: 'string', ops: STR_OPS },
      { label: '是否机器人', value: 'ua.is_bot', type: 'bool', ops: BOOL_OPS },
      { label: '是否移动端', value: 'ua.is_mobile', type: 'bool', ops: BOOL_OPS },
      { label: '是否空 UA', value: 'ua.is_empty', type: 'bool', ops: BOOL_OPS },
      { label: '爬虫类别', value: 'ua.crawler_category', type: 'enum', ops: ENUM_OPS,
        options: ['search_engine','social','ai_crawler','seo','monitoring','security','library','feed','archive','other'] },
      { label: '爬虫厂商', value: 'ua.crawler_vendor', type: 'string', ops: [...ENUM_OPS, 'in_ci', 'not_in_ci'],
        hint: '如 google / baidu / sqlmap / curl' },
      { label: '可验证爬虫', value: 'ua.crawler_verifiable', type: 'bool', ops: BOOL_OPS },
    ],
  },
  {
    label: '请求',
    fields: [
      { label: '请求路径', value: 'request.path', type: 'string', ops: STR_OPS },
      { label: '请求方法', value: 'request.method', type: 'enum', ops: ENUM_OPS,
        options: ['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'] },
      { label: 'User-Agent', value: 'request.user_agent', type: 'string', ops: STR_OPS },
      { label: 'Referer', value: 'request.referer', type: 'string', ops: STR_OPS },
      { label: '有 Referer', value: 'request.has_referer', type: 'bool', ops: BOOL_OPS },
      { label: 'Session ID', value: 'request.session_id', type: 'string', ops: STR_OPS },
    ],
  },
  {
    label: '设备画像',
    fields: [
      { label: '新设备', value: 'device.isNew', type: 'bool', ops: BOOL_OPS },
      { label: '设备信誉分', value: 'device.reputationScore', type: 'number', ops: NUM_OPS },
      { label: '设备指纹', value: 'device.fingerprint', type: 'string', ops: STR_OPS },
    ],
  },
]

export const ALL_FIELDS = FIELD_GROUPS.flatMap((g) => g.fields)

export const FIELD_MAP = Object.fromEntries(ALL_FIELDS.map((f) => [f.value, f]))

export function getOperatorOptions(fieldValue) {
  const def = FIELD_MAP[fieldValue]
  if (!def) return Object.keys(OPERATOR_LABELS).map((v) => ({ label: OPERATOR_LABELS[v], value: v }))
  return def.ops.map((v) => ({ label: OPERATOR_LABELS[v] ?? v, value: v }))
}
