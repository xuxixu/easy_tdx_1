"""自定义策略类型装配：校验定义 → 动态生成策略类 → 注册进全局注册表。

自定义类型 = 基于一个**内置**策略的命名预设包（新 label + 说明 + 默认参数
+ 可选预设网格）。装配后与内置类型同等可用：回测 / 组合 / 参数寻优表单 /
信号扫描全部零改动（都走 ``registry.get(name).build(params)``）。

约束（与注册表语义对齐）：
- 注册表键固定 ``custom_<8位hex>``；只有该前缀的条目可注销，
  内置策略类型不可编辑/删除（它们是 Python 代码）。
- 自定义类型不能再基于自定义类型（只允许一层派生，参数语义可追溯）。
- 默认参数必须通过基准参数的合法性校验（含快慢线倒挂等跨参数约束）。
- 预设网格键必须是参数名，笛卡尔积 ≤ 200（与寻优器上限一致）。
"""

from __future__ import annotations

import dataclasses
import logging
import math
import uuid
from typing import Any

logger = logging.getLogger(__name__)

#: 自定义类型注册表键前缀。只有该前缀的条目允许注销。
CUSTOM_PREFIX = "custom_"

#: 预设网格笛卡尔积上限（与 ParamGridOptimizer.MAX_GRID_POINTS 一致）。
MAX_GRID_POINTS = 200


def new_custom_id() -> str:
    """生成 8 位 hex 短 id（注册表键 = ``custom_<id>``）。"""
    return uuid.uuid4().hex[:8]


def is_custom_name(name: str) -> bool:
    return name.startswith(CUSTOM_PREFIX)


def _validate_defaults(base_entry: Any, default_params: dict[str, Any]) -> list[Any]:
    """校验默认参数并返回带新默认值的 Param 列表（含跨参数约束检查）。"""
    declared = {p.name: p for p in base_entry.params}
    unknown = set(default_params) - set(declared)
    if unknown:
        raise ValueError(f"未知参数: {sorted(unknown)}（基准策略无此参数）")
    out = []
    resolved: dict[str, Any] = {}
    for p in base_entry.params:
        if p.name in default_params:
            validated = p.validate(default_params[p.name])
            out.append(dataclasses.replace(p, default=validated))
            resolved[p.name] = validated
        else:
            out.append(p)
            resolved[p.name] = p.default
    # 跨参数语义约束（如 fast < slow）对新默认值同样生效
    labels = {p.name: p.label or p.name for p in base_entry.params}
    for smaller, larger in base_entry.strategy_cls.param_constraints:
        a, b = resolved[smaller], resolved[larger]
        try:
            ok = bool(a < b)
        except TypeError:
            ok = False
        if not ok:
            raise ValueError(
                f"默认参数 '{labels[smaller]}'({smaller})={a} 必须小于 "
                f"'{labels[larger]}'({larger})={b}，周期/阈值倒挂在语义上无效"
            )
    return out


def _validate_grid(preset_grid: dict[str, Any], param_names: set[str]) -> dict[str, list[Any]]:
    """校验预设网格：键须为参数名、值为非空标量列表、笛卡尔积 ≤ 200。"""
    if not preset_grid:
        return {}
    if not isinstance(preset_grid, dict):
        raise ValueError("preset_grid 须为对象（参数名 → 取值列表）")
    cleaned: dict[str, list[Any]] = {}
    for key, values in preset_grid.items():
        if key not in param_names:
            raise ValueError(f"预设网格含未知参数 '{key}'")
        if not isinstance(values, list) or not values:
            raise ValueError(f"预设网格 '{key}' 须为非空列表")
        for v in values:
            if not isinstance(v, (int, float, str, bool)) or (
                isinstance(v, float) and not math.isfinite(v)
            ):
                raise ValueError(f"预设网格 '{key}' 含非法取值 {v!r}")
        # 去重保序
        seen: list[Any] = []
        for v in values:
            if v not in seen:
                seen.append(v)
        cleaned[key] = seen
    total = 1
    for values in cleaned.values():
        total *= len(values)
    if total > MAX_GRID_POINTS:
        raise ValueError(f"预设网格笛卡尔积 {total} 超过上限 {MAX_GRID_POINTS}，请缩小")
    return cleaned


def register_custom_type(rec: Any) -> Any:
    """把一条自定义类型定义装配进全局注册表（幂等：同名自定义条目先注销再注册）。

    Raises:
        ValueError: 基准不存在 / 参数非法 / 网格非法 / 试图覆盖内置类型。
    """
    from easy_tdx.backtest.strategies import get_registry

    registry = get_registry()
    if not is_custom_name(rec.name):
        raise ValueError(f"自定义类型键须以 '{CUSTOM_PREFIX}' 开头，收到 '{rec.name}'")
    if not rec.label or not rec.label.strip():
        raise ValueError("自定义类型名称不能为空")
    if rec.base is None or is_custom_name(str(rec.base)):
        raise ValueError("自定义类型只能基于内置策略类型，不能再基于自定义类型")
    try:
        base_entry = registry.get(rec.base)
    except KeyError as exc:
        raise ValueError(f"基准策略类型 '{rec.base}' 不存在（可能已被删除）") from exc
    if base_entry.custom:
        raise ValueError(f"基准 '{rec.base}' 本身是自定义类型，不允许再派生")

    params = _validate_defaults(base_entry, rec.default_params or {})
    grid = _validate_grid(rec.preset_grid or {}, {p.name for p in base_entry.params})

    cls_name = f"Custom_{rec.id}"
    cls = type(
        cls_name,
        (base_entry.strategy_cls,),
        {
            "params": params,
            "param_constraints": list(base_entry.strategy_cls.param_constraints),
            "__module__": __name__,
            "__doc__": rec.description or f"{rec.label}（自定义类型，基于{base_entry.label}）",
        },
    )
    # 幂等：重载（如进程内重复初始化）时先注销旧的同名自定义条目
    if rec.name in registry.names():
        old = registry.get(rec.name)
        if not old.custom:
            raise ValueError(f"键 '{rec.name}' 已被内置策略占用")
        registry.unregister(rec.name)
    registry.register(
        cls,
        name=rec.name,
        label=rec.label.strip(),
        description=rec.description or "",
        custom=True,
        preset_grid=grid or None,
    )
    return registry.get(rec.name)


def unregister_custom_type(name: str) -> Any:
    """注销自定义类型。非 custom_ 前缀（内置）拒绝，返回被删条目。"""
    from easy_tdx.backtest.strategies import get_registry

    if not is_custom_name(name):
        raise ValueError(f"内置策略类型不可删除：'{name}'")
    registry = get_registry()
    try:
        entry = registry.get(name)
    except KeyError as exc:
        raise ValueError(f"未知策略类型 '{name}'") from exc
    if not entry.custom:
        raise ValueError(f"内置策略类型不可删除：'{name}'")
    return registry.unregister(name)


def load_custom_types() -> int:
    """从 SQLite 读全部自定义类型并装配进注册表（服务启动时调用）。

    单条损坏只记日志跳过，不阻断其余类型与服务启动。返回成功装配数。
    """
    from easy_tdx.web.custom_strategy_store import get_custom_strategy_store

    store = get_custom_strategy_store()
    ok = 0
    for rec in store.list_all():
        try:
            register_custom_type(rec)
            ok += 1
        except Exception:  # noqa: BLE001 — 单条损坏不阻断启动
            logger.warning("自定义策略类型 %s 装配失败，已跳过", rec.name, exc_info=True)
    if ok:
        logger.info("已装配 %d 个自定义策略类型", ok)
    return ok


__all__ = [
    "CUSTOM_PREFIX",
    "MAX_GRID_POINTS",
    "is_custom_name",
    "load_custom_types",
    "new_custom_id",
    "register_custom_type",
    "unregister_custom_type",
]
