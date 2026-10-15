"""错误脱敏路径擦除测试（handoff 遗留⑤验证）。

契约：detail 保留业务信息（调用方可定位），擦除本地绝对路径。
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from easy_tdx.exceptions import TdxConnectionError
from easy_tdx.web.errors import _safe_detail, register_exception_handlers


class TestSafeDetail:
    def test_keeps_business_text(self) -> None:
        assert "连接失败" in _safe_detail(ValueError("连接失败：服务器无响应"))

    def test_scrubs_windows_path(self) -> None:
        out = _safe_detail(RuntimeError(r"读取失败 D:\data\warehouse.duckdb 被占用"))
        assert "D:" not in out and "warehouse" not in out
        assert "读取失败" in out

    def test_scrubs_unix_home_path(self) -> None:
        out = _safe_detail(RuntimeError("open /home/user/.easy_tdx/warehouse.duckdb failed"))
        assert "/home/user" not in out
        assert "failed" in out

    def test_leaves_normal_slashes_alone(self) -> None:
        # 非路径的普通斜杠文本不动（板块代码/指数对不误伤）
        text = "880005/880001/880006 均返回空"
        assert _safe_detail(ValueError(text)) == text

    def test_truncates_long_message(self) -> None:
        out = _safe_detail(ValueError("x" * 500))
        assert len(out) == 300

    def test_empty_falls_back_to_class_name(self) -> None:
        assert _safe_detail(ValueError("")) == "ValueError"


def _app_with_routes() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom400")
    async def boom400() -> None:
        raise ValueError("参数错误 /home/u/x.json 非法")

    @app.get("/boom503")
    async def boom503() -> None:
        raise TdxConnectionError("连接失败 D:\\host\\1")

    @app.get("/boom500")
    async def boom500() -> None:
        raise RuntimeError("unexpected None at /app/worker.py")

    return app


class TestHandlersScrub:
    def test_400_scrubs_path_keeps_text(self) -> None:
        with TestClient(_app_with_routes(), raise_server_exceptions=False) as c:
            r = c.get("/boom400")
        assert r.status_code == 400
        assert "参数错误" in r.json()["detail"]
        assert "/home/u" not in r.json()["detail"]

    def test_503_scrubs_path_keeps_text(self) -> None:
        with TestClient(_app_with_routes(), raise_server_exceptions=False) as c:
            r = c.get("/boom503")
        assert r.status_code == 503
        assert "连接失败" in r.json()["detail"]
        assert "D:" not in r.json()["detail"]

    def test_500_scrubs_path(self) -> None:
        with TestClient(_app_with_routes(), raise_server_exceptions=False) as c:
            r = c.get("/boom500")
        assert r.status_code == 500
        assert "/app/worker.py" not in r.json()["detail"]
