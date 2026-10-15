"""Web API error handling."""

from __future__ import annotations

import logging
import re
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from easy_tdx.exceptions import TdxCommandError, TdxConnectionError, TdxDecodeError, TdxError

logger = logging.getLogger(__name__)

# 需擦除的本地路径模式（只匹配明确像路径的片段，普通业务文本中的 "/" 不动）：
# - Windows 盘符路径：D:/a/b 或 D:\a\b
# - Unix 常见根：/home/ /root/ /tmp/ /var/ /app/ /data/ /Users/ /opt/ /srv/ /etc/
_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:[\\/][^\s\"']*"),
    re.compile(
        r"(?<![\w@.\-])(?:/home|/root|/tmp|/var|/app|/data|/Users|/opt|/srv|/etc)"
        r"(?:/[^\s\"']*)?"
    ),
)


def _scrub_paths(text: str) -> str:
    """擦除文本中的本地绝对路径（保留业务信息，只替换路径片段）。"""
    for pat in _PATH_PATTERNS:
        text = pat.sub("<path>", text)
    return text


def _safe_detail(exc: Exception, *, limit: int = 300) -> str:
    """500/503/400 detail 脱敏：保留业务信息（供调用方定位），擦除本地路径。

    长度截断到 ``limit`` 字；空文本回退异常类名。调用方契约（如
    ``test_baostock_source.py`` 断言 detail 含业务关键词）依赖业务文本保留，
    故不只返回类名——见 tests/unit/test_web_errors_scrub.py。
    """
    text = _scrub_paths(str(exc).replace("\\", "/"))
    text = text[:limit]
    return text if text else type(exc).__name__


class ApiErrorResponse(BaseModel):
    """标准错误响应格式。"""

    error: str
    detail: str = ""
    code: str = ""
    request_id: str = ""


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器到 FastAPI app。"""

    @app.exception_handler(TdxConnectionError)
    async def tdx_connection_error_handler(
        request: Request, exc: TdxConnectionError
    ) -> JSONResponse:
        request_id = uuid.uuid4().hex[:12]
        logger.warning("TDX 503 %s %s [%s]: %s", request.method, request.url.path, request_id, exc)
        return JSONResponse(
            status_code=503,
            content=ApiErrorResponse(
                error="TDX connection error",
                detail=_safe_detail(exc),
                code="TDX_CONNECTION",
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(TdxDecodeError)
    async def tdx_decode_error_handler(request: Request, exc: TdxDecodeError) -> JSONResponse:
        request_id = uuid.uuid4().hex[:12]
        logger.warning("TDX 502 %s %s [%s]: %s", request.method, request.url.path, request_id, exc)
        return JSONResponse(
            status_code=502,
            content=ApiErrorResponse(
                error="TDX decode error",
                detail=_safe_detail(exc),
                code="TDX_DECODE",
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(TdxCommandError)
    async def tdx_command_error_handler(request: Request, exc: TdxCommandError) -> JSONResponse:
        request_id = uuid.uuid4().hex[:12]
        logger.warning("TDX 422 %s %s [%s]: %s", request.method, request.url.path, request_id, exc)
        return JSONResponse(
            status_code=422,
            content=ApiErrorResponse(
                error="TDX command error",
                detail=_safe_detail(exc),
                code="TDX_COMMAND",
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(TdxError)
    async def tdx_error_handler(request: Request, exc: TdxError) -> JSONResponse:
        request_id = uuid.uuid4().hex[:12]
        logger.warning("TDX 503 %s %s [%s]: %s", request.method, request.url.path, request_id, exc)
        return JSONResponse(
            status_code=503,
            content=ApiErrorResponse(
                error="TDX error", detail=_safe_detail(exc), code="TDX_ERROR", request_id=request_id
            ).model_dump(),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        request_id = uuid.uuid4().hex[:12]
        return JSONResponse(
            status_code=400,
            content=ApiErrorResponse(
                error="Bad request",
                detail=_safe_detail(exc),
                code="BAD_REQUEST",
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = uuid.uuid4().hex[:12]
        logger.exception("Unhandled 500 %s %s [%s]", request.method, request.url.path, request_id)
        return JSONResponse(
            status_code=500,
            content=ApiErrorResponse(
                error="Internal server error",
                detail=_safe_detail(exc),
                code="INTERNAL",
                request_id=request_id,
            ).model_dump(),
        )
