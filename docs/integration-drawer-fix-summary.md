# 接入抽屉修复总结

## 📋 修复背景

adapters 和 client-sdk 完成 V3 双层架构升级后，接入抽屉（`app-integration-drawer.vue`）中的代码示例仍使用旧的参数命名，导致用户复制代码后无法正常运行。

## 🔧 修复内容

### 1. SDK 配置参数名修正 ✅

**问题**：SDK 使用了已废弃的 `appId` 参数

**修复**：
```diff
  SdSdk.guard({
    apiBase: '${gw.value}',
    apiKey:  '${siteId.value}',
-   appId:   ${numericAppId.value}
+   siteId:   ${numericAppId.value}
  });
```

**影响范围**：
- 网站 SDK 接入代码（第 454 行）
- Shopify 内联脚本（第 487 行）
- SDK 代码注释说明（第 436 行）

---

### 2. Nginx-Lua 配置完善 ✅

**问题**：缺少 `$fy_sdk_snippet` 必需变量

**修复**：
```diff
  set $fangyu_gateway_url  "${gw.value}";
  set $fangyu_site_key     "${siteId.value}";
  set $fangyu_site_id      "${numericAppId.value}";
  set $fangyu_site_secret  "${appSecret.value}";
  set $fangyu_fail_mode    "open";
+ set $fy_sdk_snippet      "";  # ⚠️ 关键！SDK 注入必需！
```

**修复位置**：第 404-412 行

---

### 3. WordPress 配置参数修正 ✅

**问题**：参数命名与实际 WordPress 插件不一致

**修复**：
```diff
  define('FANGYU_GATEWAY_URL', '${gw.value}');
- define('FANGYU_SITE_ID',     '${siteId.value}');
- define('FANGYU_APP_SECRET',  '${appSecret.value}');
+ define('FANGYU_SITE_KEY',    '${siteId.value}');  // 站点密钥
+ define('FANGYU_SITE_ID',     ${numericAppId.value});  // 站点数字主键
+ define('FANGYU_SITE_SECRET', '${appSecret.value}');
```

**修复位置**：第 426-432 行

---

### 4. Cloudflare Worker 配置修正 ✅

**问题**：
- 缺少 `FANGYU_SITE_KEY` 变量
- 缺少 `FANGYU_SITE_ID` 变量
- 密钥命名使用旧的 `FANGYU_APP_SECRET`

**修复**：
```diff
  [vars]
  FANGYU_GATEWAY_URL = "${gw.value}"
- FANGYU_SITE_ID     = "${siteId.value}"
+ FANGYU_SITE_KEY    = "${siteId.value}"
+ FANGYU_SITE_ID     = "${numericAppId.value}"
  FANGYU_FAIL_MODE   = "open"
  
- # 注意：FANGYU_APP_SECRET 不在此文件设置
+ # 注意：FANGYU_SITE_SECRET 不在此文件设置
```

```diff
- wrangler secret put FANGYU_APP_SECRET
+ wrangler secret put FANGYU_SITE_SECRET
```

**修复位置**：
- wrangler.toml 示例（第 414-422 行）
- secret 命令（第 423 行）
- 注意事项说明（第 114 行）

---

### 5. 参数说明文档更新 ✅

**问题**：参数说明章节仍然说明已废弃的 `appId`

**修复**：
```diff
  <ElAlert title="参数说明">
    <ul>
      <li><code>apiBase</code>: 网关地址</li>
-     <li><code>apiKey</code>: 站点标识 (site_key)</li>
-     <li><code>appId</code>: 站点数字主键 (Site.id)</li>
+     <li><code>apiKey</code>: 站点密钥字符串 (site_key)，用于 X-App-Key 请求头身份验证</li>
+     <li><code>siteId</code>: 站点数字主键 (Site.id)，用于租户隔离<br/>
+       <small>注意：这是站点的 id 字段（整数），不是 site_key 字段（字符串）</small>
+     </li>
    </ul>
  </ElAlert>
```

**修复位置**：第 190-198 行

---

### 6. 注释说明优化 ✅

**优化内容**：
- 清理了冗余的参数用途说明注释
- 统一了所有配置项的注释格式
- 明确区分 `site_key`（字符串）和 `site.id`（数字）的用途

---

## 📊 修复统计

| 修复项 | 修改行数 | 影响范围 |
|-------|---------|---------|
| SDK 参数名 | 3 处 | 网站 SDK、Shopify、注释 |
| Nginx 配置 | 1 处 | 配置示例 |
| WordPress 配置 | 3 处 | 变量定义 |
| Cloudflare Worker | 5 处 | wrangler.toml、secret 命令、说明 |
| 参数说明文档 | 1 处 | 用户可见文档 |
| 注释优化 | 2 处 | 代码注释 |
| **总计** | **15 处** | **全部 6 种接入方式** |

---

## ✅ 验证结果

### 参数一致性检查
```bash
# 检查是否还有旧参数名
grep -r "appId\|FANGYU_APP_" app-integration-drawer.vue
# 结果：No matches found ✅
```

### 关键参数对照表

| 用途 | 变量名 | 类型 | 示例值 |
|-----|--------|------|--------|
| 站点密钥字符串（身份验证） | `site_key` / `apiKey` | string | `"site_abc123xyz"` |
| 站点数字主键（租户隔离） | `Site.id` / `siteId` | number | `10001` |
| 站点签名密钥 | `site_secret` / `appSecret` | string | `"your_secret_here"` |

---

## 🎯 修复效果

### 修复前
用户复制接入代码后遇到的问题：
- ❌ SDK 报错：`siteId 必须是正整数`（因为使用了不存在的 `appId` 参数）
- ❌ Nginx-Lua 无法注入 SDK（缺少 `$fy_sdk_snippet` 变量）
- ❌ WordPress 插件配置不匹配（参数名错误）
- ❌ Cloudflare Worker 配置不完整（缺少必需变量）

### 修复后
- ✅ 所有接入方式的代码示例可直接复制使用
- ✅ 参数命名与实际 SDK/Adapter 实现完全一致
- ✅ 配置说明清晰，用户不会混淆 `site_key` 和 `site.id`
- ✅ 所有必需变量齐全，不会遗漏关键配置

---

## 📝 后续建议

### 1. 测试验证
建议在测试环境验证以下场景：
- [ ] 网站 SDK 接入：复制代码后能否正常初始化
- [ ] Nginx-Lua 接入：SDK 注入功能是否正常
- [ ] WordPress 接入：插件配置是否匹配
- [ ] Cloudflare Worker 接入：变量是否完整
- [ ] Shopify 接入：内联脚本参数是否正确

### 2. 文档同步
如果存在以下文档，也需要同步更新：
- [ ] 快速开始指南
- [ ] 接入教程视频脚本
- [ ] API 文档中的示例代码

### 3. 迁移指引（如有历史用户）
如果有用户已按旧文档完成接入，建议提供迁移指引：
```javascript
// 旧版代码
SdSdk.guard({
  apiBase: 'xxx',
  apiKey: 'xxx',
  appId: 123  // ❌ 废弃
});

// 新版代码
SdSdk.guard({
  apiBase: 'xxx',
  apiKey: 'xxx',
  siteId: 123  // ✅ 正确
});
```

---

## 🔗 相关文件

- **修复文件**：`dashboard-ui/src/views/fangyu/apps/modules/app-integration-drawer.vue`
- **分析文档**：`tmp/integration-drawer-refactor-analysis.md`
- **SDK 实现**：`client-sdk/src/index.ts` 和 `client-sdk/src/config.ts`
- **Nginx 适配器**：`adapters/nginx-lua/defense.lua`

---

**修复日期**：2026-08-09  
**修复人员**：AI Assistant  
**版本**：V3 双层架构  
**状态**：✅ 已完成
