# 爬虫名称字段使用指南

## 概述

本文档说明如何在规则编辑器中使用新增的"爬虫名称"字段来精确匹配特定的爬虫程序。

## 问题背景

之前的规则编辑器只提供了以下爬虫相关字段：
- `ua.is_bot` - 是否为爬虫（布尔值）
- `ua.crawler_category` - 爬虫类别（如：search_engine、ai_crawler）
- `ua.crawler_vendor` - 爬虫厂商（如：google、bing）

**缺少了精确到具体爬虫程序的字段**，例如：
- 无法区分 `googlebot`（核心搜索）和 `adsbot-google`（广告检查）
- 无法单独针对 `googlebot-image`（图片爬虫）设置规则

## 解决方案

新增了 **`ua.crawler_name`** 和 **`intel.crawler_name`** 两个字段，支持精确匹配具体的爬虫程序名称。

### 新增字段说明

#### ua.crawler_name
- **标签**: 爬虫名称
- **类型**: 枚举（enum）
- **可空**: 是（非爬虫请求该字段为空）
- **支持的操作符**: 等于、不等于、在列表中、不在列表中、为空、不为空
- **用途**: 从 User-Agent 解析出的具体爬虫程序名称

**注意**: `intel.crawler_name` 保持原有的字符串类型，支持模糊匹配，不做修改。

### 支持的爬虫名称列表

#### Google 系列（15 种）
- `googlebot` - Google 核心搜索爬虫
- `googlebot-image` - Google 图片搜索
- `googlebot-news` - Google 新闻搜索
- `googlebot-video` - Google 视频搜索
- `googlebot-mobile` - Google 移动端爬虫
- `googlebot-smartphone` - Google 智能手机爬虫
- `adsbot-google` - Google Ads 广告质量检查（桌面）
- `adsbot-google-mobile` - Google Ads 广告质量检查（移动）
- `mediapartners-google` - Google AdSense 爬虫
- `feedfetcher-google` - Google RSS/Feed 抓取
- `storebot-google` - Google 购物爬虫
- `google-inspectiontool` - Search Console 检查工具
- `googleother` - 其他 Google 服务

#### Bing 系列（4 种）
- `bingbot` - Bing 搜索爬虫
- `adidxbot` - Bing 广告索引爬虫
- `bingpreview` - Bing 页面预览
- `msnbot` - MSN 搜索爬虫

#### 百度系列（3 种）
- `baiduspider` - 百度搜索爬虫
- `baiduspider-render` - 百度渲染爬虫
- `baiduspider-image` - 百度图片爬虫

#### AI 爬虫（5 种）
- `gptbot` - OpenAI ChatGPT 爬虫
- `claudebot` - Anthropic Claude 爬虫
- `ccbot` - Common Crawl 爬虫
- `google-extended` - Google AI 训练数据爬虫
- `perplexitybot` - Perplexity AI 爬虫
- `bytespider` - 字节跳动爬虫

#### 其他常见爬虫（13 种）
- `yandexbot` - Yandex 搜索爬虫
- `applebot` - Apple 搜索爬虫
- `facebookexternalhit` - Facebook 预览爬虫
- `twitterbot` - Twitter 卡片爬虫
- `linkedinbot` - LinkedIn 爬虫
- `slackbot` - Slack 链接预览
- `discordbot` - Discord 预览爬虫
- `ahrefsbot` - Ahrefs SEO 爬虫
- `semrushbot` - Semrush SEO 爬虫
- `mj12bot` - Majestic SEO 爬虫
- `uptimerobot` - UptimeRobot 监控
- `pingdom` - Pingdom 监控

**合计**: 40 种常见爬虫

## 使用示例

### 示例 1: 放行 Google 核心搜索爬虫

**场景**: 只允许 Google 核心搜索爬虫访问，阻止其他 Google 爬虫

**规则配置**:
```
规则名称: 放行 Googlebot 核心搜索
优先级: 紧急
匹配模式: 全部匹配（AND）

条件:
- ua.crawler_vendor 等于 google
- ua.crawler_name 等于 googlebot

命中处置: 放行，缓存 7200 秒
未命中处置: 放行，缓存 0 秒
```

### 示例 2: 阻止所有 AI 训练爬虫

**场景**: 阻止 GPTBot、ClaudeBot、CCBot 等 AI 训练爬虫

**规则配置**:
```
规则名称: 阻断 AI 训练爬虫
优先级: 高
匹配模式: 任一匹配（OR）

条件:
- ua.crawler_name 在列表中 [gptbot, claudebot, ccbot, google-extended, perplexitybot]

命中处置: 阻断，返回 403，缓存 86400 秒
未命中处置: 放行，缓存 0 秒
```

### 示例 3: Google Ads 广告爬虫单独放行

**场景**: 为投放 Google Ads 的网站单独放行广告质量检查爬虫

**规则配置**:
```
规则名称: 放行 Google AdsBot
优先级: 高
匹配模式: 任一匹配（OR）

条件:
- ua.crawler_name 在列表中 [adsbot-google, adsbot-google-mobile]

命中处置: 放行，缓存 7200 秒
未命中处置: 放行，缓存 0 秒
```

### 示例 4: 图片网站放行图片搜索爬虫

**场景**: 对于图片分享网站，放行各大搜索引擎的图片爬虫

**规则配置**:
```
规则名称: 放行图片搜索爬虫
优先级: 高
匹配模式: 任一匹配（OR）

条件:
- ua.crawler_name 在列表中 [googlebot-image, baiduspider-image]

命中处置: 放行，缓存 7200 秒
未命中处置: 放行，缓存 0 秒
```

### 示例 5: 限制 SEO 工具访问频率

**场景**: SEO 工具消耗带宽但无业务价值，进行 JS 挑战限流

**规则配置**:
```
规则名称: 限制 SEO 爬虫访问
优先级: 普通
匹配模式: 任一匹配（OR）

条件:
- ua.crawler_name 在列表中 [ahrefsbot, semrushbot, mj12bot]

命中处置: JS 挑战，缓存 1800 秒
未命中处置: 放行，缓存 0 秒
```

## 字段组合使用

### 三层过滤策略

推荐使用三层字段组合实现精细化控制：

#### 第一层：厂商级别（粗粒度）
```
ua.crawler_vendor 等于 google  
→ 适用于"信任所有 Google 爬虫"场景
```

#### 第二层：类别级别（中粒度）
```
ua.crawler_category 等于 search_engine  
→ 适用于"放行所有搜索引擎爬虫"场景
```

#### 第三层：名称级别（细粒度）✨ 新增
```
ua.crawler_name 等于 googlebot  
→ 适用于"只放行 Google 核心搜索，阻止广告爬虫"场景
```

### 组合示例：只放行核心搜索，阻止其他

```
规则 1: 放行核心搜索爬虫（优先级：紧急）
- ua.crawler_name 在列表中 [googlebot, bingbot, baiduspider, yandexbot]
- 处置: 放行

规则 2: 阻断其他爬虫（优先级：普通）
- ua.is_bot 等于 true
- 处置: 阻断
```

## 验证方法

### 1. 在访问日志中查看

进入 **防御 → 访问日志**，筛选条件：
- 是否爬虫 = 是
- 查看"爬虫信息"列中的详细信息

### 2. 测试规则触发

创建测试规则后，使用不同的 User-Agent 发送请求：

```bash
# 测试 Googlebot
curl -A "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" \
  https://your-domain.com/

# 测试 Bingbot
curl -A "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)" \
  https://your-domain.com/

# 测试 GPTBot
curl -A "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.0; +https://openai.com/gptbot)" \
  https://your-domain.com/
```

在访问日志中确认：
- `crawler_name` 字段正确识别
- 规则正确触发
- 处置结果符合预期

## 注意事项

### 1. 优先级设置
- 核心搜索爬虫规则应设为**紧急**或**高**优先级
- 确保在其他限制性规则之前执行

### 2. 爬虫伪装防护
- 恶意爬虫可能伪装成 Googlebot
- 建议启用 DNS 反向验证（`crawler_verifiable` 字段）
- 或配合 `ip.isDatacenter` 等字段综合判断

### 3. SEO 影响
- 错误拦截搜索引擎爬虫会严重影响 SEO 排名
- 建议始终放行核心搜索爬虫：`googlebot`、`bingbot`、`baiduspider`
- 定期查看访问日志，监控爬虫拦截情况

### 4. 缓存时间建议
- 搜索引擎爬虫：7200 秒（2 小时）
- 恶意爬虫：86400 秒（24 小时）
- 挑战类处置：1800 秒（30 分钟）

### 5. 空值处理
- 非爬虫请求的 `crawler_name` 字段为空
- 使用"为空"操作符可以匹配普通用户请求
- 使用"不为空"操作符可以匹配所有爬虫请求

## 相关文档

- [Googlebot 规则使用指南](./googlebot-rules-guide.md)
- [爬虫识别系统设计方案](./crawler-classification-design.md)
- [字段元数据系统](./field-metadata-system.md)
- [规则模板库](./rule-templates-guide.md)

## 更新记录

**2026-08-09**
- 新增 `ua.crawler_name` 字段到规则编辑器
- 新增 `intel.crawler_name` 字段到规则编辑器
- 支持 40 种常见爬虫的精确匹配
- 提供完整的使用示例和最佳实践

---

**文档版本**: v1.0  
**更新日期**: 2026-08-09  
**维护人员**: AI Assistant
