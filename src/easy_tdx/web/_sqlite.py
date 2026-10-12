"""SQLite 短连接辅助。

``sqlite3.Connection`` 的上下文管理器语义**只负责事务**（退出时 commit / rollback），
**不关闭连接**。因此 ``with sqlite3.connect(...) as conn:`` 这种写法会随每次调用
泄漏一个文件描述符，只能寄希望于 CPython 的引用计数及时回收——而异常 traceback
持有帧会显著延长对象生存期，于是 fd 可能长时间不释放。

本模块提供 :func:`connect`：返回一个在 ``with`` 退出时**真正 close()** 的
:class:`sqlite3.Connection` 子类，让各 store 保持 ``with self._connect() as conn:``
写法不变即可修复泄漏。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType


class _ClosingConnection(sqlite3.Connection):
    """退出 ``with`` 块时关闭自身（保留父类的 commit/rollback 语义）。"""

    def __exit__(  # type: ignore[override]
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_val, exc_tb))
        finally:
            self.close()


def connect(db_path: str | Path) -> sqlite3.Connection:
    """打开一个短连接：``check_same_thread=False`` + ``Row`` 工厂 + 退出即关闭。

    ``check_same_thread=False`` 是必需的：FastAPI 后台任务会在 ThreadPool 线程里
    访问同一个 store。
    """
    conn = sqlite3.connect(db_path, check_same_thread=False, factory=_ClosingConnection)
    conn.row_factory = sqlite3.Row
    return conn
