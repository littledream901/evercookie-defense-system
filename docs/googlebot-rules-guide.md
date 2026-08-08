# Googlebot 专属规则使用指南

## 概述

本文档介绍如何使用系统中新增的 Googlebot 专属规则模板，以及如何验证这些规则是否正确工作。

## 新增的规则模板

系统已添加 4 个专门针对 Google 爬虫的规则模板：

### 1. 放行 Googlebot（核心搜索）
- **ID**: `allow-googlebot`
- **优先级**: 紧急（Critical）
- **用途**: 确保 Google 核心搜索爬虫能正常访问网站，保障 SEO 排名
- **匹配条件**:
  - `ua.crawler_vendor` 等于 `google`
  - `ua.crawler_name` 等于 `googlebot`
- **处置**: 放行，缓存 2 小时

### 2. 放行 Google AdsBot（广告质量）
- **ID**: `allow-google-adsbot`
- **优先级**: 高（High）
- **用途**: 允许 Google Ads 广告质量检查爬虫访问，用于评估广告着陆页质量
- **匹配条件**:
  - `ua.crawler_vendor` 等于 `google`
  - `ua.crawler_name` 在列表中 `['adsbot-google', 'adsbot-google-mobile']`
- **处置**: 放行，缓存 2 小时

### 3. 放行 Google 图片爬虫
- **ID**: `allow-google-image-crawler`
- **优先级**: 高（High）
- **用途**: 允许 Google 图片搜索爬虫索引网站图片资源
- **匹配条件**:
  - `ua.crawler_vendor` 等于 `google`
  - `ua.crawler_name` 等于 `googlebot-image`
- **处置**: 放行，缓存 2 小时

### 4. 放行 Google 移动端爬虫
- **ID**: `allow-google-mobile-crawler`
- **优先级**: 紧急（Critical）
- **用途**: 允许 Google 移动优先索引爬虫访问，评估移动端页面体验
- **匹配条件**:
  - `ua.crawler_vendor` 等于 `google`
  - `ua.crawler_name` 在列表中 `['googlebot-mobile', 'googlebot-smartphone']`
- **处置**: 放行，缓存 2 小时

## 使用方法

### 在规则页面应用模板

1. 进入 **防御 → 规则管理** 页面
2. 点击 **从模板创建** 按钮
3. 在弹出的对话框中，选择 **爬虫管理** 分类
4. 选择需要的 Googlebot 规则模板
5. 点击 **应用模板** 按钮
6. 根据需要调整规则的优先级和条件
7. 保存规则

### 手动创建规则

如果需要自定义条件，可以手动创建规则：

1. 进入 **防御 → 规则管理** 页面
2. 点击 **新增规则** 按钮
3. 设置规则名称，如 "放行 Googlebot"
4. 添加条件：
   - 条件 1: `ua.crawler_vendor` 等于 `google`
   - 条件 2: `ua.crawler_name` 等于 `googlebot`
5. 设置匹配模式为 **全部匹配**（AND 逻辑）
6. 设置命中处置为 **放行**，缓存时间 7200 秒
7. 设置未命中处置为 **放行**，缓存时间 0 秒
8. 保存规则

## 验证方法

### 方法 1: 查看访问日志

1. 进入 **防御 → 访问日志** 页面
2. 在筛选条件中，选择 **是否爬虫** = **是**
3. 查看日志中的 **爬虫信息** 列
4. 确认 Google 爬虫的访问记录中：
   - **爬虫厂商** 显示为 `Google`
   - **爬虫名称** 显示具体的爬虫类型（如 `Googlebot`、`AdsBot-Google`）
   - **裁决** 显示为 **放行**

### 方法 2: 使用测试脚本

运行项目提供的测试脚本：

```bash
python test/test_googlebot_detection.py
```

该脚本会测试：
- 核心 Googlebot 的识别
- AdsBot-Google 的识别
- Googlebot-Image 的识别
- Googlebot Mobile 的识别
- 普通用户不被误识别

所有测试应显示 ✅ 通过。

### 方法 3: 模拟 Googlebot 请求

使用 curl 或 Postman 模拟 Googlebot 的请求：

```bash
# 模拟核心 Googlebot
curl -H "User-Agent: Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" \
  https://your-domain.com

# 模拟 AdsBot-Google
curl -H "User-Agent: AdsBot-Google (+http://www.google.com/adsbot.html)" \
  https://your-domain.com

# 模拟 Googlebot-Image
curl -H "User-Agent: Googlebot-Image/1.0" \
  https://your-domain.com
```

然后在访问日志中查看这些请求是否被正确识别和处理。

## 常见 Google 爬虫 User-Agent 示例

### Googlebot（核心搜索）
```
Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)
Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/W.X.Y.Z Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)
```

### AdsBot-Google（广告质量）
```
AdsBot-Google (+http://www.google.com/adsbot.html)
Mozilla/5.0 (iPhone; CPU iPhone OS 9_1 like Mac OS X) AppleWebKit/601.1.46 (KHTML, like Gecko) Version/9.0 Mobile/13B143 Safari/601.1 (compatible; AdsBot-Google-Mobile; +http://www.google.com/mobile/adsbot.html)
```

### Googlebot-Image（图片搜索）
```
Googlebot-Image/1.0
```

### Googlebot-News（新闻搜索）
```
Googlebot-News
```

### Googlebot-Video（视频搜索）
```
Googlebot-Video/1.0
```

## 注意事项

### 1. 规则优先级

建议将 Googlebot 相关规则设置为 **高优先级** 或 **紧急优先级**，确保在其他限制性规则之前执行。

### 2. 爬虫验证

系统已标记 Google 爬虫为 **可验证**（`crawler_verifiable: true`），这意味着可以通过反向 DNS 查询验证爬虫的真实性。建议在生产环境中启用爬虫验证功能，防止伪装的恶意爬虫。

### 3. SEO 影响

错误拦截 Google 爬虫会严重影响网站的 SEO 排名。建议：
- 始终放行 Googlebot 核心搜索爬虫
- 如果网站依赖 Google Ads，也应放行 AdsBot-Google
- 如果网站有大量图片内容，应放行 Googlebot-Image

### 4. 缓存时间

建议为 Google 爬虫设置较长的缓存时间（如 2 小时），减少重复验证的开销。

### 5. 监控和调整

定期查看访问日志中的爬虫访问情况，根据实际需求调整规则：
- 如果发现某个 Google 爬虫被误拦截，及时调整规则
- 如果发现大量伪装的 Google 爬虫，考虑启用 DNS 验证

## 技术实现细节

### 爬虫识别流程

1. **UA 解析**: 系统使用正则表达式从 User-Agent 中提取爬虫特征
2. **厂商匹配**: 识别爬虫所属的厂商（如 `google`、`bing`）
3. **名称提取**: 提取具体的爬虫名称（如 `googlebot`、`adsbot-google`）
4. **分类标记**: 标记爬虫的类别（如 `search_engine`）
5. **可验证标记**: 标记爬虫是否支持 DNS 反向验证

### 字段说明

- `ua.is_bot`: 是否为爬虫（布尔值）
- `ua.crawler_vendor`: 爬虫厂商（字符串，如 `google`）
- `ua.crawler_name`: 爬虫名称（字符串，如 `googlebot`、`adsbot-google`）
- `ua.crawler_category`: 爬虫类别（字符串，如 `search_engine`）
- `ua.crawler_verifiable`: 是否可通过 DNS 验证（布尔值）

### 支持的 Google 爬虫

系统当前支持识别以下 Google 爬虫：
- `googlebot` - 核心搜索爬虫
- `googlebot-image` - 图片搜索爬虫
- `googlebot-news` - 新闻搜索爬虫
- `googlebot-video` - 视频搜索爬虫
- `adsbot-google` - 广告质量检查爬虫（桌面版）
- `adsbot-google-mobile` - 广告质量检查爬虫（移动版）
- `mediapartners-google` - AdSense 广告爬虫
- `feedfetcher-google` - RSS/Feed 抓取爬虫
- `storebot-google` - Google 购物爬虫
- `google-inspectiontool` - Search Console 检查工具
- `googleother` - 其他 Google 服务
- `apis-google` - Google API 客户端

## 故障排查

### 问题 1: Googlebot 仍被拦截

**可能原因**:
- 规则优先级过低，被其他限制性规则先匹配
- 条件配置错误，无法匹配 Googlebot

**解决方法**:
1. 检查规则优先级，确保 Googlebot 规则在前面执行
2. 查看访问日志，确认 `crawler_name` 字段的实际值
3. 调整规则条件，确保能匹配到实际的爬虫名称

### 问题 2: 普通用户被误识别为 Googlebot

**可能原因**:
- 用户伪造了 Googlebot 的 User-Agent

**解决方法**:
1. 启用 DNS 反向验证功能（如果支持）
2. 查看 IP 地址是否属于 Google 的 IP 段
3. 考虑添加额外的验证条件

### 问题 3: 无法区分不同类型的 Google 爬虫

**可能原因**:
- UA 解析器未能正确提取爬虫名称

**解决方法**:
1. 运行测试脚本 `test/test_googlebot_detection.py`
2. 查看实际的 User-Agent 字符串
3. 如果是新的爬虫类型，需要更新爬虫签名库

## 更新日志

- **2026-08-07**: 初始版本，添加 4 个 Googlebot 专属规则模板
- **2026-08-07**: 优化爬虫名称提取逻辑，支持精确识别 Google 各类爬虫
- **2026-08-07**: 添加测试脚本，验证 Googlebot 识别功能

## 相关文档

- [爬虫识别系统设计方案](./crawler-classification-design.md)
- [条件选择优化方案](./condition-selection-optimization.md)
- [字段元数据系统](./field-metadata-system.md)
