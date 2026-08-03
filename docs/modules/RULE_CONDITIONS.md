# 风控规则条件参考

规则条件的完整字段表、操作符语义与配置约束。

- 字段注册表（唯一真相源）：`shared/src/fangyu_shared/rules/fields.py`
- 操作符实现：`shared/src/fangyu_shared/rules/operators.py`
- 契约测试：`tests/gateway/test_rule_field_contract.py`、`tests/admin/test_rule_template_contract.py`

## 1. 条件模型

一条规则由若干条件构成，每个条件是扁平三元组：

```json
{ "field": "ip.country", "op": "in_ci", "value": ["RU", "KP"] }
```

- **不支持嵌套 AND/OR 组**。整条规则只有一个 `matchAll` 布尔开关：`true` 为全部满足（AND），`false` 为任一满足（OR）。需要 `(A AND B) OR C` 这类表达式时，拆成多条规则用优先级串联。
- **条件至少一条**。空条件在 schema 层就被拒绝（`min_length=1`），求值器也会对空条件返回 `false`。风控侧 fail-closed，空条件不会命中全站。
- **只有 `published` 状态的规则参与决策**。`shadow` 仅做影子评估不影响结果，`draft`/`disabled`/`archived` 完全不参与。
- **规则需绑定站点才生效**。未绑定站点的已发布规则影响零流量。

## 2. 求值顺序

```
critical → high → normal → low        同级按规则 ID 升序
```

决策规则命中即终止流水线并施加处置；打分规则贡献权重，永不终止，最终由评分阈值决定处置。两类规则字段互斥：决策规则有 `disposition` 无 `weight`，打分规则反之。

## 3. 字段表

命名风格按命名空间不同，**这是最容易踩的坑**：

| 命名空间 | 风格 | 来源 |
|---|---|---|
| `device.*` `ip.*` | camelCase | Pydantic `model_dump(by_alias=True)` |
| `ua.*` `request.*` `intel.*` | snake_case | dataclass / 手工构造 |

写 `ip.is_proxy` 不会报错，规则能存能发布，但**永远取不到值**。正确写法是 `ip.isProxy`。

### 3.1 `ip.*` 网络层

| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| `ip.ip` | string | | 访客 IP |
| `ip.ipType` | enum | | `ipv4` / `ipv6` |
| `ip.continent` | enum | ✓ | `AS` `EU` `NA` `SA` `AF` `OC` `AN` |
| `ip.country` | enum | ✓ | ISO 3166-1 alpha-2 |
| `ip.region` | string | ✓ | 需 MMDB City 库 |
| `ip.city` | string | ✓ | 需 MMDB City 库 |
| `ip.asn` | asn | ✓ | 只用 `asn_in` / `asn_not_in` |
| `ip.asnOrg` | string | ✓ | ASN 组织名 |
| `ip.isp` | string | ✓ | 运营商 |
| `ip.connectionType` | enum | | `datacenter` `mobile` `residential` `education` `government` `unknown` |
| `ip.isProxy` | bool | | |
| `ip.isVpn` | bool | | |
| `ip.isTor` | bool | | 来自 Tor 出口节点情报，非 MMDB |
| `ip.isDatacenter` | bool | | |
| `ip.isMobileNetwork` | bool | | |
| `ip.reputationScore` | number | | 0-100，越低越可疑 |
| `ip.reputationSamples` | number | | **为 0 时信誉分是默认占位值 50，不是真实结论** |
| `ip.totalRequests` | number | | |
| `ip.lastSeenAt` | datetime | | ISO 8601 字符串 |

`ip.*` 的地理与网络属性有两层来源：MMDB 解析为基础层，后台人工维护的情报为覆盖层，情报优先。

### 3.2 `ua.*` 客户端

| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| `ua.device_type` | enum | | `desktop` `mobile` `tablet` `bot` `tv` `console` `wearable` `unknown` |
| `ua.os` | enum | | `windows` `macos` `linux` `android` `ios` `harmonyos` … |
| `ua.os_version` | string | ✓ | Windows 已归一为 `10` `8.1` `7` `Vista` `XP` |
| `ua.browser` | enum | | `chrome` `firefox` `safari` `edge` `ie` … |
| `ua.browser_version` | string | ✓ | |
| `ua.engine` | enum | | `blink` `gecko` `webkit` `trident` `presto` `unknown` |
| `ua.brand` | enum | | 设备品牌 |
| `ua.model` | string | ✓ | 设备型号 |
| `ua.client_type` | enum | | `browser` `app` `library` `bot` `unknown` |
| `ua.client_name` | string | | |
| `ua.is_bot` | bool | | |
| `ua.is_mobile` | bool | | |
| `ua.is_empty` | bool | | 空 UA |
| `ua.crawler_category` | enum | ✓ | `search_engine` `social` `ai_crawler` `seo` `monitoring` `security` `library` `feed` `archive` `other`。**非爬虫为空** |
| `ua.crawler_vendor` | string | ✓ | 如 `google` `baidu` `sqlmap`。非爬虫为空 |
| `ua.crawler_verifiable` | bool | | 是否可通过反向 DNS 验证 |

### 3.3 `request.*` 本次请求

| 字段 | 类型 | 可空 |
|---|---|---|
| `request.path` | string | |
| `request.method` | enum | |
| `request.user_agent` | string | |
| `request.referer` | string | ✓ |
| `request.session_id` | string | ✓ |
| `request.has_referer` | bool | |

这些键由网关按真实请求写入，客户端提交的 `extra` 无法覆盖。

### 3.4 `device.*` 设备画像

| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| `device.fingerprint` | string | | |
| `device.deviceId` | string | ✓ | |
| `device.totalRequests` | number | | **为 0 即新设备** |
| `device.blockedRequests` | number | | |
| `device.reputationScore` | number | | 0-100 |
| `device.reputationSamples` | number | | 为 0 时信誉分是占位值 |
| `device.tags` | list | | 用 `contains` 判断 |
| `device.firstSeenAt` | datetime | | ISO 8601 字符串 |
| `device.lastSeenAt` | datetime | | ISO 8601 字符串 |

没有 `device.isNew` 字段。判断新设备用 `device.totalRequests eq 0`。

### 3.5 `intel.*` 威胁情报命中

| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| `intel.matched` | bool | | 是否命中任一情报 |
| `intel.risk_score` | number | | 累计风险分，未命中为 0 |
| `intel.reasons` | list | | 命中原因，用 `contains` 判断 |
| `intel.crawler_category` | enum | ✓ | 后台录入的爬虫特征命中结果 |
| `intel.crawler_name` | string | ✓ | |
| `intel.is_legitimate_crawler` | bool | | 搜索引擎与社交媒体爬虫 |

没有 `ip.category` 字段。要按恶意 IP 分类拦截，用 `intel.reasons contains ...` 或 `intel.risk_score gte ...`。

## 4. 操作符

| 操作符 | 适用类型 | 语义 |
|---|---|---|
| `eq` `neq` | 全部 | 严格相等，**不做类型转换** |
| `gt` `gte` `lt` `lte` | number | 转 float 比较，不可比时不命中；布尔值排除在外 |
| `in` `not_in` | 全部 | 集合成员，严格相等 |
| `in_ci` `not_in_ci` | string / enum | 大小写无关，两侧转字符串后 strip + lower |
| `contains` `not_contains` | string / list | 字符串子串或列表成员，大小写敏感 |
| `startswith` `endswith` | string | 大小写敏感 |
| `regex` | string | Python `re.search`，模式上限 512 字符 |
| `cidr_in` | string | IP 落在单个 CIDR 段内 |
| `cidr_list_in` `cidr_list_not_in` | string | IP 落在任一 CIDR 段内，非法段逐条跳过 |
| `asn_in` `asn_not_in` | asn | 归一化后比较，兼容 `4134` `"4134"` `"AS4134"` |

### 4.1 类型转换不统一，需按字段选对操作符

```
eq(4134, "4134")       → false     严格相等，不转换
in(4134, ["4134"])     → false     同上
in_ci(4134, ["4134"])  → true      两侧转字符串
gt("80", 50)           → true      转 float
asn_in(4134, ["AS4134"]) → true    归一化 ASN
```

ASN 字段只提供 `asn_in` / `asn_not_in`，因为只有它们做归一化。用 `eq` 填 `"AS4134"` 不会命中。

### 4.2 数据缺失时的行为

字段取不到值（`None`）时：

| 操作符 | 结果 |
|---|---|
| `eq` `gt` `gte` `lt` `lte` `in` `in_ci` `contains` `startswith` `endswith` `regex` `cidr_in` `cidr_list_in` `asn_in` | **不命中** |
| `neq` `not_in` `not_in_ci` `cidr_list_not_in` `asn_not_in` | **命中** |
| `not_contains` | **不命中**（唯一例外） |

否定类操作符在数据缺失时命中，是刻意保留的语义——「非白名单国家一律拦截」需要它才能表达。但这带来一类高危配置：

```jsonc
// 危险：MMDB 未加载或内网地址时 ip.country 为空，此规则拦下全部流量
[{ "field": "ip.country", "op": "not_in_ci", "value": ["CN", "HK"] }]

// 正确：先排除数据缺失
[{ "field": "ip.country", "op": "neq", "value": null },
 { "field": "ip.country", "op": "not_in_ci", "value": ["CN", "HK"] }]
```

规则编辑器对「可空字段 + 否定操作符」的组合会给出黄色风险提示。内置模板已按此加固。

`not_contains` 之所以例外：它在前端被归入字符串操作符组，容易被用到数值或布尔字段上。若也 fail-open，条件会恒成立——配上 `deny` 就是对全部流量放开阻断。

### 4.3 其他边界

- `eq(null, null)` 命中。对可空字段配 `eq` + 空值可用于「该字段无数据」的判断。
- `eq(true, 1)` 命中（Python `bool` 是 `int` 子类），但 `gt(true, 0)` 不命中（有序比较显式排除布尔）。
- 未知操作符、求值抛异常一律判为不命中，不会中断决策。
- 时间字段是 ISO 8601 字符串，可用 `startswith` / `regex` 做日期前缀匹配，也可用有序比较做字典序比较。

## 5. 内置模板

`GET /api/v2/rules/templates`，26 条，覆盖地理、网络类型、ASN、IP 名单、爬虫分类、UA 特征、路径、设备画像等场景。规则编辑器「从模板套用」可直接载入条件与处置。

模板由契约测试保证：字段必须真实可取值、操作符必须已实现、用了否定操作符的可空字段必须自带空值排除、普通浏览器请求不得命中任何阻断类模板。

## 6. 新增字段的步骤

1. 在 `shared/src/fangyu_shared/schemas/profile.py`（或对应 schema）加字段；
2. 同步 `shared/src/fangyu_shared/rules/fields.py` 的 `CONTEXT_FIELDS`，可空字段一并加入 `NULLABLE_FIELDS`；
3. 在 `dashboard-ui/src/constants/ruleFields.ts` 加字段定义，注意命名风格与可空标注；枚举字段还要在 `OPTION_LABELS` 补每个选项的中文文案；
4. 分别跑 `pytest tests/gateway/test_rule_field_contract.py` 与 `pytest tests/admin/test_rule_template_contract.py`（两个服务的顶层包都叫 `src`，不能同一次运行）。

契约测试会断言注册表与真实评估上下文完全一致、前端字段表无幽灵字段、可空标注无遗漏、枚举选项无缺失文案。漏改任一处都会失败。

## 7. 界面文案约定

枚举选项在下拉里显示为「中文 (原始值)」，例如 `机房/云主机 (datacenter)`、`AI 语料抓取 (ai_crawler)`。保留原始值是为了让运营看规则详情、对照访问日志或排查接口返回时能与后端数据对上。

国家码、设备品牌、HTTP 方法直接显示原始值——ISO 3166 码、厂商名与 HTTP 动词本身就是通用标识。

文案维护在 `ruleFields.ts` 的 `OPTION_LABELS`，键为 `字段路径.选项值`。按字段路径而非全局值索引，因为同一字符串在不同字段含义不同：`mobile` 在 `ip.connectionType` 里是移动蜂窝网络，在 `ua.device_type` 里是手机；`security` 在爬虫类别里指扫描器。`ua.crawler_category` 与 `intel.crawler_category` 取值相同，共用 `crawler_category` 前缀。
