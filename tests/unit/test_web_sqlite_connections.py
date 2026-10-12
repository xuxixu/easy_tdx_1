"""回归测试：web 层 SQLite 短连接必须真正关闭。

``sqlite3.Connection`` 的 ``__enter__/__exit__`` 只做事务管理（commit/rollback），
**不关闭连接**。此前各 store 用 ``with self._connect() as conn:`` 写法，
每次都泄漏一个 fd（只能等 CPython 引用计数回收）。本测试用可观测的
``_ClosingConnection`` 断言退出 with 后连接已关闭。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from easy_tdx.web import _sqlite
from easy_tdx.web.watchlist_store import WatchlistStore


class TestClosingConnection:
    def test_closes_on_context_exit(self, tmp_path: Path) -> None:
        conn = _sqlite.connect(tmp_path / "t.db")
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
        # 已关闭的连接再次使用会抛 ProgrammingError
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_closes_even_on_exception(self, tmp_path: Path) -> None:
        conn = _sqlite.connect(tmp_path / "t.db")
        with pytest.raises(RuntimeError):
            with conn:
                raise RuntimeError("boom")
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_rolls_back_on_exception(self, tmp_path: Path) -> None:
        # 每次 with 都会关闭连接，所以各步骤必须用新连接
        with _sqlite.connect(tmp_path / "t.db") as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
        with pytest.raises(RuntimeError):
            with _sqlite.connect(tmp_path / "t.db") as conn:
                conn.execute("INSERT INTO t VALUES (1)")
                raise RuntimeError("boom")
        with _sqlite.connect(tmp_path / "t.db") as conn2:
            n = conn2.execute("SELECT COUNT(*) FROM t").fetchone()[0]
        assert n == 0


class TestStoreConnectionsClose:
    def test_store_connect_is_self_closing(self, tmp_path: Path) -> None:
        store = WatchlistStore(tmp_path / "w.db")
        conn = store._connect()
        with conn:
            conn.execute("SELECT 1")
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")
