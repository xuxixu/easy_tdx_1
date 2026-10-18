"""符号索引（symbol_index）单测：零网络、零真实服务器。"""

from __future__ import annotations

import easy_tdx
from easy_tdx.web import symbol_index as sym_mod


def _isolate(monkeypatch, tmp_path) -> None:
    """隔离配置目录 + 清进程内缓存 + 断网，避免命中真实磁盘索引或走 HTTP。"""
    monkeypatch.setenv("EASY_TDX_CONFIG_DIR", str(tmp_path))
    # 真指数补录（_http_index_rows）走 HTTP，单测一律置空
    monkeypatch.setattr(sym_mod, "_http_index_rows", lambda token: [])
    sym_mod.clear_cache()


def test_connect_failure_still_closes_client(monkeypatch, tmp_path):
    """connect() 抛异常时也必须 close 客户端。

    回归：旧实现在 ``connect()`` **之后**才把 client 赋给 ``client_to_close``，
    一旦 connect（建 socket + 登录）抛错，finally 拿到的仍是 None，每次冷路径
    请求都泄漏一条 socket。扩展行情服务器不可达是常态，这里会持续漏。
    """
    _isolate(monkeypatch, tmp_path)
    closed: list[str] = []

    class FakeClient:
        @classmethod
        def from_best_host(cls) -> FakeClient:
            return cls()

        def connect(self) -> None:
            raise OSError("扩展行情服务器不可达")

        def close(self) -> None:
            closed.append("closed")

    monkeypatch.setattr(easy_tdx, "MacExClient", FakeClient)

    index = sym_mod.get_index("HK", refresh=True)

    assert index.rows == []
    assert closed == ["closed"], "connect() 失败后必须关闭客户端（否则 socket 泄漏）"


def test_success_path_closes_client(monkeypatch, tmp_path):
    """正常回源后同样关闭客户端（一次一条，不多不少）。"""
    _isolate(monkeypatch, tmp_path)
    closed: list[str] = []

    class FakeClient:
        @classmethod
        def from_best_host(cls) -> FakeClient:
            return cls()

        def connect(self) -> None:
            return None

        def close(self) -> None:
            closed.append("closed")

        # _fetch_all 需要的最小协议面（注意方法名是 goods_list）
        def goods_count(self, market: int) -> int:
            return 0

        def goods_list(self, market: int, start: int = 0, count: int = 80):
            import pandas as pd

            if start > 0:
                return pd.DataFrame()
            return pd.DataFrame([{"code": "00700", "name": "腾讯控股", "market": market}])

    monkeypatch.setattr(easy_tdx, "MacExClient", FakeClient)

    index = sym_mod.get_index("HK", refresh=True)

    assert closed == ["closed"]
    assert any(r.get("code") == "00700" for r in index.rows)


def test_from_best_host_failure_closes_nothing(monkeypatch, tmp_path):
    """from_best_host() 自身抛错时没有客户端可关，不应崩溃。"""
    _isolate(monkeypatch, tmp_path)

    class FakeClient:
        @classmethod
        def from_best_host(cls) -> FakeClient:
            raise OSError("全部候选 host 不可达")

    monkeypatch.setattr(easy_tdx, "MacExClient", FakeClient)

    index = sym_mod.get_index("HK", refresh=True)
    assert index.rows == []
