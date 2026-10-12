"""自定义策略类型持久化（WebUI「策略类型」页的新增/编辑/删除）。

自定义类型 = 基于一个内置策略的命名预设包（新 label + 说明 + 默认参数
+ 可选预设网格），注册进全局策略注册表后与内置类型同等可用（回测 /
组合 / 寻优表单 / 信号扫描零改动）。

- 单文件 SQLite，落在统一配置目录（``~/.easy_tdx/custom_strategies.db``，
  随 ``EASY_TDX_CONFIG_DIR`` 环境变量走），短连接 + 写锁串行。
- 本模块只做存取；合法性校验（base 存在、默认参数合法）与注册表装配
  见 :mod:`easy_tdx.backtest.custom_strategies`。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import _sqlite

__all__ = ["CustomStrategyType", "CustomStrategyStore", "get_custom_strategy_store"]

_write_lock = threading.Lock()


def _config_dir() -> Path:
    return Path(os.environ.get("EASY_TDX_CONFIG_DIR", str(Path.home() / ".easy_tdx")))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class CustomStrategyType:
    """一条自定义策略类型。``name`` 为注册表键（``custom_`` 前缀 + 短 id）。"""

    id: str
    name: str
    label: str
    base: str
    description: str = ""
    default_params: dict[str, Any] = field(default_factory=dict)
    preset_grid: dict[str, list[Any]] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "label": self.label,
            "base": self.base,
            "description": self.description,
            "default_params": self.default_params,
            "preset_grid": self.preset_grid,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class CustomStrategyStore:
    """自定义策略类型 SQLite 存储。单例由 :func:`get_custom_strategy_store` 提供。"""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS custom_strategy_types (
        id             TEXT PRIMARY KEY,
        name           TEXT NOT NULL UNIQUE,
        label          TEXT NOT NULL DEFAULT '',
        base           TEXT NOT NULL DEFAULT '',
        description    TEXT NOT NULL DEFAULT '',
        default_params TEXT NOT NULL DEFAULT '{}',
        preset_grid    TEXT NOT NULL DEFAULT '{}',
        created_at     TEXT NOT NULL DEFAULT '',
        updated_at     TEXT NOT NULL DEFAULT ''
    );
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (_config_dir() / "custom_strategies.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(self._SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # 退出 with 时真正 close（裸 sqlite3.connect 只 commit 不 close → fd 泄漏）
        return _sqlite.connect(self.db_path)

    def list_all(self) -> list[CustomStrategyType]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM custom_strategy_types ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get(self, custom_id: str) -> CustomStrategyType | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM custom_strategy_types WHERE id = ?", (custom_id,)
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def get_by_name(self, name: str) -> CustomStrategyType | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM custom_strategy_types WHERE name = ?", (name,)
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def add(self, rec: CustomStrategyType) -> CustomStrategyType:
        now = _now_iso()
        rec.created_at = rec.created_at or now
        rec.updated_at = now
        with _write_lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO custom_strategy_types (id, name, label, base, description,"
                " default_params, preset_grid, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rec.id,
                    rec.name,
                    rec.label,
                    rec.base,
                    rec.description,
                    json.dumps(rec.default_params, ensure_ascii=False),
                    json.dumps(rec.preset_grid, ensure_ascii=False),
                    rec.created_at,
                    rec.updated_at,
                ),
            )
        return rec

    def update(self, rec: CustomStrategyType) -> CustomStrategyType:
        rec.updated_at = _now_iso()
        with _write_lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE custom_strategy_types SET label = ?, base = ?, description = ?,"
                " default_params = ?, preset_grid = ?, updated_at = ? WHERE id = ?",
                (
                    rec.label,
                    rec.base,
                    rec.description,
                    json.dumps(rec.default_params, ensure_ascii=False),
                    json.dumps(rec.preset_grid, ensure_ascii=False),
                    rec.updated_at,
                    rec.id,
                ),
            )
            if cur.rowcount == 0:
                raise KeyError(f"未知自定义类型 '{rec.id}'")
        return rec

    def delete(self, custom_id: str) -> bool:
        with _write_lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM custom_strategy_types WHERE id = ?", (custom_id,))
            return cur.rowcount > 0

    @staticmethod
    def _row_to_record(r: sqlite3.Row) -> CustomStrategyType:
        try:
            default_params = json.loads(r["default_params"] or "{}")
        except json.JSONDecodeError:
            default_params = {}
        try:
            preset_grid = json.loads(r["preset_grid"] or "{}")
        except json.JSONDecodeError:
            preset_grid = {}
        return CustomStrategyType(
            id=r["id"],
            name=r["name"],
            label=r["label"],
            base=r["base"],
            description=r["description"],
            default_params=default_params if isinstance(default_params, dict) else {},
            preset_grid=preset_grid if isinstance(preset_grid, dict) else {},
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )


_store: CustomStrategyStore | None = None
_store_lock = threading.Lock()


def get_custom_strategy_store() -> CustomStrategyStore:
    """全局单例（首次调用惰性建库）。"""
    global _store  # noqa: PLW0603 — 模块级单例
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = CustomStrategyStore()
    return _store
