"""页面资源模板目录。

与 :mod:`rule_templates` 同构：模板是**静态内置清单**而非数据库记录。
理由一致——模板是产品预置的最佳实践，随后端版本演进，不该被运维改坏；
运维「载入」后得到的是一条独立的页面资源，改它不影响模板本身。

模板内容一律是**完整 HTML 文档**（含 doctype / head / 内联样式），因为
``serve_alt`` 在客户端走 ``document.write`` 整体替换文档，片段式 HTML 会
丢失 head 且脚本不执行。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from fangyu_shared.schemas.common import BaseSchema, SuccessResponse

from src.domain.page_resource.entities import PageResourceKind
from src.interfaces.http.dependencies import require_permission

router = APIRouter(prefix="/page-resources/templates", tags=["page-resources"])


class PageResourceTemplateSchema(BaseSchema):
    """页面资源模板。

    ``suggested_name`` 是载入时预填的资源名建议值，运维可改；它同时也是规则
    处置里 ``target.url`` 要填的资源名，因此命名保持简短且无空格。
    """

    id: str
    name: str
    description: str
    kind: PageResourceKind
    suggested_name: str
    content_type: str = "text/html; charset=utf-8"
    content: str


_MAINTENANCE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>系统维护中</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#f7f8fa;color:#303133}
  .box{max-width:420px;padding:32px;text-align:center}
  h1{margin:0 0 12px;font-size:20px;font-weight:600}
  p{margin:0;font-size:14px;line-height:1.7;color:#606266}
</style>
</head>
<body>
  <div class="box">
    <h1>系统维护中</h1>
    <p>我们正在进行例行维护，请稍后再访问。感谢您的耐心等待。</p>
  </div>
</body>
</html>
"""

_NOT_FOUND_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>404 - 页面不存在</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#fff;color:#303133}
  .box{max-width:420px;padding:32px;text-align:center}
  .code{font-size:64px;font-weight:700;color:#dcdfe6;line-height:1}
  h1{margin:8px 0 12px;font-size:18px;font-weight:600}
  p{margin:0;font-size:14px;line-height:1.7;color:#909399}
</style>
</head>
<body>
  <div class="box">
    <div class="code">404</div>
    <h1>页面不存在</h1>
    <p>您访问的页面已被移除、重命名，或暂时不可用。</p>
  </div>
</body>
</html>
"""

_RATE_LIMIT_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>访问过于频繁</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#fffbf5;color:#303133}
  .box{max-width:420px;padding:32px;text-align:center}
  h1{margin:0 0 12px;font-size:20px;font-weight:600;color:#e6a23c}
  p{margin:0;font-size:14px;line-height:1.7;color:#606266}
</style>
</head>
<body>
  <div class="box">
    <h1>访问过于频繁</h1>
    <p>您的请求频率超出正常范围，请稍后再试。若为正常使用，请放慢操作节奏。</p>
  </div>
</body>
</html>
"""

_EMPTY_RESULT_JSON = """{"code": 0, "message": "ok", "data": {"items": [], "total": 0}}
"""

_SAFE_PLACEHOLDER_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>内容加载中</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#fff;color:#606266}
  .box{text-align:center;padding:32px}
  .dot{display:inline-block;width:8px;height:8px;margin:0 3px;border-radius:50%;
       background:#409eff;animation:b 1.4s infinite ease-in-out both}
  .dot:nth-child(1){animation-delay:-.32s}
  .dot:nth-child(2){animation-delay:-.16s}
  @keyframes b{0%,80%,100%{transform:scale(.6);opacity:.5}40%{transform:scale(1);opacity:1}}
  p{margin:16px 0 0;font-size:14px}
</style>
</head>
<body>
  <div class="box">
    <span class="dot"></span><span class="dot"></span><span class="dot"></span>
    <p>内容加载中，请稍候</p>
  </div>
</body>
</html>
"""

_PAGE_RESOURCE_TEMPLATES: list[PageResourceTemplateSchema] = [
    PageResourceTemplateSchema(
        id="maintenance",
        name="维护页",
        description=(
            "中性的维护提示，不暴露访客已被识别。"
            "适合对可疑流量降级投放——访客看到的是业务状态说明，而非拦截告知。"
        ),
        kind=PageResourceKind.LANDING,
        suggested_name="maintenance",
        content=_MAINTENANCE_HTML,
    ),
    PageResourceTemplateSchema(
        id="not-found",
        name="404 伪装页",
        description=(
            "以 404 外观静默阻断。相比 403，它不告知访客「存在但被拒」，"
            "可降低对方针对性调整的动机。注意 serve_alt 下发时状态码仍是 200，"
            "需要真 404 状态码请改用 not_found 机制。"
        ),
        kind=PageResourceKind.LANDING,
        suggested_name="fake_404",
        content=_NOT_FOUND_HTML,
    ),
    PageResourceTemplateSchema(
        id="rate-limited",
        name="限流提示页",
        description=(
            "明示频率超限，给正常用户自我纠正的机会。"
            "适合搭配频控类规则——对误伤的真人访客比静默阻断友好。"
        ),
        kind=PageResourceKind.LANDING,
        suggested_name="rate_limited",
        content=_RATE_LIMIT_HTML,
    ),
    PageResourceTemplateSchema(
        id="empty-json",
        name="空 JSON 响应",
        description=(
            "面向接口路径的投放：返回结构合法但数据为空的响应。"
            "爬虫拿到的是可解析的空结果而非错误码，不会触发其重试或换 IP 逻辑。"
            "载入后请按自身接口契约调整字段结构。"
        ),
        kind=PageResourceKind.LANDING,
        suggested_name="empty_api_result",
        content_type="application/json",
        content=_EMPTY_RESULT_JSON,
    ),
    PageResourceTemplateSchema(
        id="safe-placeholder",
        name="加载占位页（正常分支）",
        description=(
            "kind=safe 的占位内容，投给可信访客。"
            "用途是把「识别耗时」包装成正常的加载态，避免白屏引起怀疑；"
            "实际业务页应由源站返回，此模板仅作过渡兜底。"
        ),
        kind=PageResourceKind.SAFE,
        suggested_name="safe_placeholder",
        content=_SAFE_PLACEHOLDER_HTML,
    ),
]


@router.get(
    "",
    response_model=SuccessResponse[list[PageResourceTemplateSchema]],
    dependencies=[Depends(require_permission("app.read"))],
)
async def list_page_resource_templates():
    """内置页面资源模板清单。"""
    return SuccessResponse(data=_PAGE_RESOURCE_TEMPLATES)
