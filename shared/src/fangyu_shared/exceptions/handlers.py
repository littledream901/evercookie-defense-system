"""FastAPI 统一异常处理器."""

from __future__ import annotations

import json
import traceback
from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .base import BusinessException

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = structlog.get_logger(__name__)


def _make_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    details: dict | None = None,
) -> JSONResponse:
    """构造统一错误响应格式."""
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id,
        },
    )


def _safe_errors(exc: RequestValidationError) -> list[dict]:
    """把 Pydantic 校验错误清洗成可 JSON 序列化的结构。

    自定义校验器（``field_validator`` / ``model_validator``）抛 ``ValueError``
    时，``exc.errors()`` 会在 ``ctx.error`` 里塞入**原始异常对象**。该对象
    不可 JSON 序列化，会让 JSONResponse 在序列化阶段抛 TypeError——
    结果是本该干净返回的 422 变成 500，且真正的校验原因完全丢失。

    ``input`` 也可能是任意对象（如 bytes、自定义类型），同样需要兜底。
    """
    cleaned: list[dict] = []
    for err in exc.errors():
        item = {
            "type": err.get("type"),
            "loc": [str(x) for x in err.get("loc", ())],
            "msg": err.get("msg"),
        }
        ctx = err.get("ctx")
        if isinstance(ctx, dict):
            # ctx 里除 error 外还可能有 limit_value 等标量，保留可序列化的部分
            safe_ctx = {k: str(v) for k, v in ctx.items()}
            if safe_ctx:
                item["ctx"] = safe_ctx
        try:
            json.dumps(err.get("input"))
            item["input"] = err.get("input")
        except (TypeError, ValueError):
            item["input"] = repr(err.get("input"))
        cleaned.append(item)
    return cleaned


def register_exception_handlers(app: FastAPI) -> None:
    """注册全部异常处理器."""

    @app.exception_handler(BusinessException)
    async def _business_handler(request: Request, exc: BusinessException) -> JSONResponse:
        logger.info(
            "business_exception",
            extra={
                "error_code": exc.code,
                "error_message": exc.message,
                "details": exc.details,
            },
        )
        return _make_response(
            request,
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _make_response(
            request,
            code="VALID_FAILED",
            message="请求参数不合法",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"errors": _safe_errors(exc)},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _make_response(
            request,
            code=f"HTTP_{exc.status_code}",
            message=str(exc.detail),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            extra={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        return _make_response(
            request,
            code="INTERNAL_UNKNOWN",
            message="服务内部错误",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
