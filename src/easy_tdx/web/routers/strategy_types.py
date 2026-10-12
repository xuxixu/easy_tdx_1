"""策略类型路由：内置浏览（只读）+ 自定义类型增删改。

- 列表/详情复用 ``GET /backtest/strategies``（注册表现状，含已装配的自定义类型）。
- 自定义类型 = 基于内置策略的命名预设包：新增/编辑时先写库再装配进注册表，
  删除时先注销再删库。顺序不可反（先装配成功才写库，保证库里无坏定义）。
- 内置策略类型不可编辑/删除（它们是 Python 代码），请求会 400。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from easy_tdx.web.custom_strategies import (
    CUSTOM_PREFIX,
    is_custom_name,
    new_custom_id,
    register_custom_type,
    unregister_custom_type,
)
from easy_tdx.web.custom_strategy_store import CustomStrategyType, get_custom_strategy_store

router = APIRouter(tags=["strategy-types"])


class CustomTypeCreate(BaseModel):
    """POST /strategy-types 请求体。"""

    label: str = Field(..., min_length=1, max_length=64, description="自定义类型名称")
    base: str = Field(..., min_length=1, max_length=64, description="基准内置策略名")
    description: str = Field("", max_length=2000, description="说明")
    default_params: dict[str, Any] = Field(
        default_factory=dict, description="默认参数（须通过基准参数校验）"
    )
    preset_grid: dict[str, list[Any]] = Field(default_factory=dict, description="预设寻优网格")


class CustomTypeUpdate(BaseModel):
    """PUT /strategy-types/{name} 请求体（全量替换基准之外的可变字段）。"""

    label: str = Field(..., min_length=1, max_length=64)
    base: str = Field(..., min_length=1, max_length=64)
    description: str = Field("", max_length=2000)
    default_params: dict[str, Any] = Field(default_factory=dict)
    preset_grid: dict[str, list[Any]] = Field(default_factory=dict)


def _usage_count(name: str) -> int:
    """引用该类型的已保存策略条数（删除前给前端做二次确认用）。"""
    from easy_tdx.web.strategy_store import get_store

    try:
        return sum(1 for s in get_store().list_all() if s.strategy == name)
    except Exception:  # noqa: BLE001 — 存储故障不阻断主流程
        return 0


def _schema_of(name: str) -> dict[str, Any]:
    from easy_tdx.backtest.strategies import get_registry

    return get_registry().get(name).to_schema()


@router.get("/strategy-types")
async def list_custom_types() -> dict[str, Any]:
    """列出全部自定义类型存储记录（含基准名，供编辑表单用）。"""
    items = [r.to_dict() for r in get_custom_strategy_store().list_all()]
    return {"items": items, "count": len(items)}


@router.post("/strategy-types")
async def create_custom_type(req: CustomTypeCreate) -> dict[str, Any]:
    """新增自定义策略类型（基于内置策略，返回注册表 schema）。"""
    if is_custom_name(req.base):
        raise ValueError("自定义类型只能基于内置策略类型")
    custom_id = new_custom_id()
    rec = CustomStrategyType(
        id=custom_id,
        name=f"{CUSTOM_PREFIX}{custom_id}",
        label=req.label.strip(),
        base=req.base.strip(),
        description=req.description.strip(),
        default_params=req.default_params,
        preset_grid=req.preset_grid,
    )
    # 先装配（参数/网格非法直接 400，库里不留坏定义），再写库
    register_custom_type(rec)
    get_custom_strategy_store().add(rec)
    return {"ok": True, "type": rec.to_dict(), "schema": _schema_of(rec.name)}


@router.put("/strategy-types/{name}")
async def update_custom_type(name: str, req: CustomTypeUpdate) -> dict[str, Any]:
    """编辑自定义策略类型（可改基准，键不变；返回新 schema）。"""
    if not is_custom_name(name):
        raise ValueError(f"内置策略类型不可编辑：'{name}'")
    store = get_custom_strategy_store()
    rec = store.get_by_name(name)
    if rec is None:
        raise ValueError(f"未知自定义类型 '{name}'")
    if is_custom_name(req.base):
        raise ValueError("自定义类型只能基于内置策略类型")
    rec.label = req.label.strip()
    rec.base = req.base.strip()
    rec.description = req.description.strip()
    rec.default_params = req.default_params
    rec.preset_grid = req.preset_grid
    # 先重装配（非法直接 400，库里保留旧定义），再写库
    register_custom_type(rec)
    store.update(rec)
    return {"ok": True, "type": rec.to_dict(), "schema": _schema_of(rec.name)}


@router.delete("/strategy-types/{name}")
async def delete_custom_type(name: str) -> dict[str, Any]:
    """删除自定义策略类型（先注销再删库；返回引用计数供前端提示）。"""
    if not is_custom_name(name):
        raise ValueError(f"内置策略类型不可删除：'{name}'")
    store = get_custom_strategy_store()
    rec = store.get_by_name(name)
    if rec is None:
        raise ValueError(f"未知自定义类型 '{name}'")
    in_use = _usage_count(name)
    unregister_custom_type(name)
    store.delete(rec.id)
    return {"ok": True, "name": name, "in_use": in_use}


__all__ = ["router"]
