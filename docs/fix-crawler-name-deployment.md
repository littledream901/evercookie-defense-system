# 修复爬虫名称字段缺失问题 - 部署指南

## 问题描述

访问日志中爬虫识别字段 `crawler_name` 一直为空，导致前端无法显示具体的爬虫名称（如 "Googlebot"、"Bingbot"）。

## 根本原因

**Gateway API** 在构建 `DecisionEvent` 时遗漏了 `crawlerName` 字段的赋值。

- **文件位置**：`gateway-api/src/application/services/decision_service.py:1445`
- **问题代码**：在构建决策事件时，虽然设置了 `crawlerCategory` 和 `crawlerVendor`，但没有设置 `crawlerName`

## 修复内容

在 `decision_service.py` 第 1445 行添加了缺失的字段：

```python
crawlerName=ua.crawler_name if ua else None,
```

## 部署步骤

### 1. 停止 Gateway 服务

```bash
cd /opt/fangyu-defense-system
docker-compose stop gateway-api
```

### 2. 重新构建 Gateway 镜像

```bash
# 如果使用本地构建
docker-compose build gateway-api

# 或者从代码仓库拉取最新镜像
docker-compose pull gateway-api
```

### 3. 启动 Gateway 服务

```bash
docker-compose up -d gateway-api
```

### 4. 验证服务状态

```bash
# 查看服务日志
docker-compose logs -f gateway-api --tail=100

# 检查服务健康状态
curl http://localhost:8001/health
```

### 5. 验证修复效果

等待新的爬虫访问（建议等待 5-10 分钟），然后执行以下查询：

```bash
docker exec fangyu-clickhouse clickhouse-client --query "
SELECT 
    occurred_at,
    host,
    is_bot,
    crawler_name,
    crawler_category,
    crawler_vendor,
    substring(user_agent, 1, 100) as ua_short
FROM fangyu.decision_events
WHERE is_bot = 1 
  AND toDate(occurred_at) >= today()
ORDER BY occurred_at DESC
LIMIT 10
FORMAT Vertical;
"
```

**预期结果**：`crawler_name` 字段应该显示具体的爬虫名称，例如：
- `Googlebot`
- `bingbot/2.0`
- `Baiduspider`
- `YandexBot`
- 等

### 6. 验证统计数据

```bash
docker exec fangyu-clickhouse clickhouse-client --query "
SELECT 
    countIf(crawler_name != '') as has_crawler_name,
    countIf(crawler_category != '') as has_crawler_category,
    countIf(crawler_vendor != '') as has_crawler_vendor
FROM fangyu.decision_events
WHERE is_bot = 1 
  AND toDate(occurred_at) >= today();
"
```

**预期结果**：`has_crawler_name` 应该 > 0

## 注意事项

### 历史数据

- **已有数据不受影响**：修复前的访问记录 `crawler_name` 仍然为空
- **新数据正常显示**：修复后的新访问记录会正确填充 `crawler_name`
- 如果需要回填历史数据，可以联系技术支持

### 前端显示

修复后，前端访问日志表格应该能够正常显示：
- 爬虫名称标签（如 "Googlebot"）
- 爬虫详细信息工具提示
- 按爬虫名称分类统计

### 相关文件

修改涉及的文件：
- `gateway-api/src/application/services/decision_service.py`

数据流路径：
1. Gateway 解析 UA → `UAResult.crawler_name`
2. Gateway 构建事件 → `DecisionEvent.crawlerName` ✅ **已修复**
3. 发布到 Redis Stream → `crawlerName` 字段
4. Worker 消费转换 → `crawler_name` 字段
5. 写入 ClickHouse → `crawler_name` 列
6. Admin UI 查询显示 → 前端表格

## 回滚方案

如果部署后出现问题，可以快速回滚：

```bash
# 停止服务
docker-compose stop gateway-api

# 恢复到上一个镜像版本
docker-compose up -d gateway-api --force-recreate

# 或者使用 Git 回滚代码后重新构建
git revert <commit-hash>
docker-compose build gateway-api
docker-compose up -d gateway-api
```

## 技术细节

### UA 解析流程

```python
# 1. parser.py:272-273 - 提取爬虫名称
crawler = match_crawler(ua)
crawler_name = extract_crawler_name(ua, crawler)

# 2. parser.py:317 - 填充到 UAResult
crawler_name=crawler_name,

# 3. decision_service.py:1445 - 构建事件（已修复）
crawlerName=ua.crawler_name if ua else None,

# 4. event_transformer.py:193 - Worker 读取
"crawler_name": str(raw.get("crawlerName") or raw.get("crawler_name") or ""),
```

### 爬虫签名库

系统使用内置的爬虫签名库 (`shared/src/fangyu_shared/ua/crawlers.py`)，支持识别：
- 搜索引擎：Google, Bing, Baidu, Yandex 等
- AI 爬虫：OpenAI, Anthropic, Google-Extended 等
- SEO 工具：Ahrefs, Semrush 等
- 社交平台：Facebook, Twitter, LinkedIn 等
- 安全扫描：Censys, Shodan 等

每个签名都配置了 `name_pattern` 正则表达式用于提取具体名称。

## 测试建议

可以使用 curl 模拟爬虫访问进行测试：

```bash
# 模拟 Googlebot
curl -H "User-Agent: Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" \
     https://your-domain.com

# 模拟 Bingbot
curl -H "User-Agent: Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)" \
     https://your-domain.com
```

然后查询 ClickHouse 验证 `crawler_name` 是否正确填充。
