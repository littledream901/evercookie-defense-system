# Phase 4 测试页面

手动测试台，无需运行 pytest，直接在浏览器中打开。

## 文件列表

| 文件 | 用途 |
|---|---|
| `adapter_test.html` | Gateway `/v2/decide` 接入测试：场景模拟、签名验证、三层处置展示、压力测试 |
| `sdk_test.html` | SDK 6 通道存储写/读/投票、selfHeal、浏览器指纹、`/sdk/init`、`/sdk/heartbeat` |
| `prelanding_test.html` | AB 页测试：`serve_alt` 落地/安全页、`redirect` 单 URL + 池、`not_found`、`page_resource` 内容注入断言 |

## 快速启动

1. 启动 Gateway（`docker compose up gateway-api` 或 `uvicorn` 直接运行）。
2. 用浏览器直接打开对应 HTML 文件（`file://` 协议或通过本地 HTTP server）。
3. 填入 **Gateway URL / App ID / API Key / App Secret**，然后点击场景按钮。

> 注意：`indexedDB` 和 `cacheStorage` 在 `file://` 协议下可能受浏览器限制，建议用本地 HTTP server：
> ```
> python -m http.server 9000
> ```
> 然后访问 `http://localhost:9000/tests/pages/adapter_test.html`。

## 签名说明

所有测试页面的 HMAC-SHA256 签名逻辑与 Python 侧 `build_sign_payload` 完全一致：

- 字段按 key 字典序排序
- `None / null / ""` 跳过；`0 / false` 保留
- `bool` → `"true"` / `"false"`
- 嵌套 object → 递归按 key 排序后 compact JSON
- percent-encode 使用 `encodeURIComponent`（`!*'()` **不**编码）

## 预期断言说明

测试台中的断言基于网关实际返回值进行校验。如果某个场景未在规则引擎中配置对应规则（如 `serve_alt` 或 `redirect` 池），相关断言会显示为 `⏭ Skip` 而不是 `✗ Fail`，不影响其他断言。

## 关联

- 自动化集成测试：`tests/integration/test_decide_e2e.py`
- 签名源码：`shared/src/fangyu_shared/utils/crypto.py`
- 决策接口：`gateway-api/src/interfaces/http/v2/decide.py`
- SDK 端点：`gateway-api/src/interfaces/http/v2/sdk.py`
