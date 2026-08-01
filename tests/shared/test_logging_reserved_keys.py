"""logging extra 保留键回归测试。

覆盖本轮发现的 Bug：
handlers.py 在处理 BusinessException 时用了
logger.info("business_exception", extra={"message": ...})
Python logging 的 LogRecord 内建 `message` 属性，extra 里出现同名键
会抛 KeyError: "Attempt to overwrite 'message' in LogRecord"，
导致所有业务异常（如 401 登录失败）变成 500。
"""
from __future__ import annotations

import logging
from io import StringIO


LOGGING_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
}


def _emit_with_extra(extra: dict) -> None:
    """向标准 logging 发射一条带 extra 的 INFO 日志，如果 extra 含保留键会抛异常。"""
    handler = logging.StreamHandler(StringIO())
    logger = logging.getLogger(f"test.reserved.{id(extra)}")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.info("test_event", extra=extra)
    logger.removeHandler(handler)


def test_safe_extra_keys_do_not_raise():
    """安全的 extra 键名不应引发任何异常。"""
    _emit_with_extra({"error_code": "AUTH_FAILED", "error_message": "invalid creds"})


def test_reserved_key_message_raises():
    """回归文档：使用 'message' 这个保留键会抛 KeyError，用于证明问题存在。"""
    try:
        _emit_with_extra({"message": "this is problematic"})
        raise AssertionError("预期应抛 ValueError/KeyError，但没有抛出")
    except (ValueError, KeyError):
        pass


def test_handlers_extra_uses_safe_keys():
    """扫描 handlers.py 中的 extra 字典，确认没有保留键。"""
    import ast
    import pathlib

    handlers_path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "shared" / "src" / "fangyu_shared" / "exceptions" / "handlers.py"
    )
    assert handlers_path.exists(), f"找不到 handlers.py: {handlers_path}"

    tree = ast.parse(handlers_path.read_text(encoding="utf-8"))
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "extra" or not isinstance(kw.value, ast.Dict):
                continue
            for k in kw.value.keys:
                if isinstance(k, ast.Constant) and k.value in LOGGING_RESERVED:
                    violations.append((node.lineno, k.value))

    assert not violations, (
        f"handlers.py 在 extra 中使用了保留键（会导致 500）: {violations}"
    )
