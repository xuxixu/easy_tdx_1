"""统一取数网关：按市场把请求分流到正确的协议栈。

为什么需要这一层
----------------
同一个"取某只票日 K"的调用，在不同市场下要打到**完全不同的连接**上：

===========  =======================================  =====================
市场          协议栈                                    客户端
===========  =======================================  =====================
A 股(SH/SZ/BJ)  MAC 协议（0x0465 等）                 ``AsyncMacClient``
美股(US)        MAC **扩展市场**协议（0x122F）         ``AsyncMacExClient``
===========  =======================================  =====================

两条栈连的是不同主机、不同端口（7709 vs 7727）、走不同命令号，
互相发不了对方的请求。把这个分流逻辑藏在路由层里重复写，迟早会漏；
这里收成唯一出口，路由只管调 :class:`MarketGateway`。

契约
----
四个取数方法（``bars`` / ``minute`` / ``quotes`` / ``transactions``）返回的
DataFrame **列结构一致**，调用方无需关心走了哪条栈：

* 时间列：日线及以上是 ``date``，分钟线是 ``datetime``（对齐 ``/bars`` 旧契约）
* 行情列：``open`` / ``close`` / ``high`` / ``low`` / ``vol`` / ``amount``
* ``amount`` 缺失时按 ``close × vol`` 补齐（外盘接口未必给成交额）
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from easy_tdx.markets import (
    MARKET_US,
    ex_market_value,
    ex_market_values,
    is_ex,
    is_hk,
    is_us,
    normalize_market,
    resolve_ex_market,
)

logger = logging.getLogger(__name__)

# 规整后保持的列顺序（与 /bars 既有契约一致）
_NORMAL_COLS = ["open", "close", "high", "low", "vol", "amount"]

#: 美国股票代码长度上限（美股 ticker 最长 5 字符，如 ``BRK.B`` 类更长写法）。
#: A股是固定 6 位数字，这里放宽以便两类代码共用同一套校验。
_MAX_CODE_LEN = 12


class MarketGateway:
    """按市场分流取数的统一网关。

    构造时注入各协议栈客户端；缺失的客户端对应市场在调用时抛
    :class:`~easy_tdx.exceptions.TdxConnectionError`，而不是启动即崩——
    这样美股连接失败不会连累 A 股功能。

    Args:
        mac_client: ``AsyncMacClient``，A 股 MAC 协议栈。
        tdx_client: ``AsyncTdxClient``，标准协议栈（A 股兜底）。
        mac_ex_client: ``AsyncMacExClient``，美股 / 期货扩展市场栈。
    """

    def __init__(
        self,
        mac_client: Any = None,
        tdx_client: Any = None,
        mac_ex_client: Any = None,
    ) -> None:
        self.mac_client = mac_client
        self.tdx_client = tdx_client
        self.mac_ex_client = mac_ex_client

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #

    @property
    def us_available(self) -> bool:
        """美股协议栈是否已连接。"""
        return self.mac_ex_client is not None

    @property
    def hk_available(self) -> bool:
        """港股协议栈是否已连接（与美股共用同一条扩展栈）。"""
        return self.mac_ex_client is not None

    @property
    def ex_available(self) -> bool:
        """扩展市场协议栈（港股 + 美股）是否已连接。"""
        return self.mac_ex_client is not None

    def _require_ex_client(self, token: str) -> Any:
        """取扩展市场客户端，缺失时给一条指明市场与端口的报错。"""
        if self.mac_ex_client is None:
            from easy_tdx.exceptions import TdxConnectionError
            from easy_tdx.markets import market_label

            raise TdxConnectionError(
                f"{market_label(token)}数据需要 MAC 扩展市场协议栈（端口 7727），当前未连接。"
                "请检查网络或服务器设置。"
            )
        return self.mac_ex_client

    # 兼容旧调用点：内部已统一走 _require_ex_client
    _require_us_client = _require_ex_client

    @staticmethod
    def _normalize_columns(df: pd.DataFrame, daily_plus: bool) -> pd.DataFrame:
        """把客户端原始输出规整到统一列契约。

        Args:
            df: 客户端返回的 DataFrame。
            daily_plus: True=日线及以上（时间列归一为 ``date``）。
        """
        if df is None or df.empty:
            return pd.DataFrame() if df is None else df

        out = df.copy()
        # 外盘 K 线带 float_shares（流通股本），对回测无用，统一丢弃
        out = out.drop(columns=[c for c in ("float_shares", "desc") if c in out.columns])

        time_col = "date" if daily_plus else "datetime"
        if "datetime" in out.columns:
            parsed = pd.to_datetime(out["datetime"], errors="coerce")
            if daily_plus:
                out["datetime"] = parsed.dt.normalize()
            out = out.rename(columns={"datetime": time_col})

        cols = [c for c in [time_col, *_NORMAL_COLS] if c in out.columns]
        cols += [c for c in out.columns if c not in cols]
        out = out[cols]

        # 成交额缺失时按 close×vol 补齐，保证下游收益类计算不会拿到 NaN
        if "amount" in out.columns and "close" in out.columns and "vol" in out.columns:
            if out["amount"].isna().all():
                out["amount"] = (out["close"] * out["vol"]).round(2)
        return out

    @staticmethod
    def _is_daily_plus(category: Any) -> bool:
        """日线及以上周期判定（枚举值无序，必须查表）。"""
        from easy_tdx._df import _category_to_minutes

        return _category_to_minutes(int(category)) is None

    # ------------------------------------------------------------------ #
    # 对外接口
    # ------------------------------------------------------------------ #

    async def bars(
        self,
        market: str,
        code: str,
        category: Any,
        start: int = 0,
        count: int = 800,
        adjust: Any = None,
    ) -> pd.DataFrame:
        """取 K 线，按市场自动分流。

        Args:
            market: 市场令牌，如 ``"US"`` / ``"HK"`` / ``"SH"``。
            code: 证券代码（美股为字母代码如 ``AAPL``，港股 5 位如 ``00700``）。
            category: ``KlineCategory`` 枚举。
            start/count: 偏移与根数。
            adjust: ``Adjust`` 枚举，None 表示不复权。

        Returns:
            统一列契约的 DataFrame；无数据时为空表。
        """
        from easy_tdx.web.convert import period_times_from_category

        token = normalize_market(market)

        if is_ex(token):
            # 真指数（HSCEI/HSTECH/DJI/IXIC/SPX）：TDX 无，走 HTTP 源
            if _is_http_index(token, code):
                return await _run_blocking(_http_bars, token, code, category, start, count, adjust)
            client = self._require_ex_client(token)
            period, times = period_times_from_category(category)
            # 外盘扩展市场没有"多分钟周期"概念，times>1 时降级为单周期
            df = await client.goods_kline(
                _resolve_ex_or_board(token, code),
                code,
                period,
                start,
                count,
                adjust if adjust is not None else 0,
            )
            return _with_source(
                self._normalize_columns(df, daily_plus=self._is_daily_plus(category)),
                "tdx",
            )

        # A 股：MAC 优先（支持复权）→ 标准协议兜底
        if self.mac_client is not None:
            try:
                period, times = period_times_from_category(category)
                df = await self.mac_client.get_stock_kline(
                    ex_market_value(token), code, period, start, count, times
                )
                return _with_source(
                    self._normalize_columns(df, daily_plus=self._is_daily_plus(category)),
                    "tdx",
                )
            except Exception as exc:  # noqa: BLE001 — 降级不中断
                logger.warning("MAC 取 K 线失败，降级标准协议 (%s%s): %s", token, code, exc)

        if self.tdx_client is None:
            from easy_tdx.exceptions import TdxConnectionError

            raise TdxConnectionError("行情客户端未连接")
        df = await self.tdx_client.get_security_bars(
            _market_enum(token), code, category, start, count
        )
        return _with_source(
            self._normalize_columns(df, daily_plus=self._is_daily_plus(category)), "tdx"
        )

    async def minute(self, market: str, code: str) -> pd.DataFrame:
        """取分时数据（分钟级），按市场自动分流。"""
        token = normalize_market(market)

        if is_ex(token):
            if _is_http_index(token, code):
                return await _run_blocking(_http_minute, token, code)
            client = self._require_ex_client(token)
            df = await client.goods_tick_chart(_resolve_ex_or_board(token, code), code)
            return _with_source(self._expand_ex_chart(df), "tdx")

        if self.tdx_client is None:
            from easy_tdx.exceptions import TdxConnectionError

            raise TdxConnectionError("行情客户端未连接")
        df = await self.tdx_client.get_minute_time_data(_market_enum(token), code)
        return _with_source(self._normalize_columns(df, daily_plus=False), "tdx")

    async def quotes(self, market: str, codes: list[str]) -> pd.DataFrame:
        """取批量报价，按市场自动分流。"""
        token = normalize_market(market)

        if is_ex(token):
            http_codes = [c for c in codes if _is_http_index(token, c)]
            tdx_codes = [c for c in codes if not _is_http_index(token, c)]
            frames: list[pd.DataFrame] = []
            if http_codes:
                frames.append(await _run_blocking(_http_quotes, token, http_codes))
            if tdx_codes:
                client = self._require_ex_client(token)
                stocks = [(_resolve_ex_or_board(token, c), c) for c in tdx_codes]
                frames.append(_with_source(await client.goods_quotes(stocks), "tdx"))
            if not frames:
                return pd.DataFrame()
            return frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)

        if self.tdx_client is None:
            from easy_tdx.exceptions import TdxConnectionError

            raise TdxConnectionError("行情客户端未连接")
        return _with_source(
            await self.tdx_client.get_security_quotes([(_market_enum(token), c) for c in codes]),
            "tdx",
        )

    async def transactions(self, market: str, code: str, start: int = 0, count: int = 800) -> Any:
        """取当日逐笔成交，按市场自动分流。"""
        token = normalize_market(market)

        if is_ex(token):
            if _is_http_index(token, code):
                # 指数无逐笔：返回空表（上层显示"指数无逐笔成交"而不是 503）
                return pd.DataFrame()
            client = self._require_ex_client(token)
            return _with_source(
                await client.goods_transaction(
                    _resolve_ex_or_board(token, code), code, None, start, count
                ),
                "tdx",
            )

        if self.tdx_client is None:
            from easy_tdx.exceptions import TdxConnectionError

            raise TdxConnectionError("行情客户端未连接")
        return _with_source(
            await self.tdx_client.get_transaction_data(_market_enum(token), code, start, count),
            "tdx",
        )

    # ------------------------------------------------------------------ #
    # 外盘专有
    # ------------------------------------------------------------------ #

    @staticmethod
    def _expand_ex_chart(df: pd.DataFrame) -> pd.DataFrame:
        """把外盘分时的 ``charts`` 内嵌字段展开成逐分钟行。

        扩展市场分时接口把整条分钟序列塞在一个 ``charts`` 列里（``[{'time',
        'price', 'avg', 'vol'}, ...]``），而 A 股分时是一行一分钟的平表。
        这里统一展开成平表，上层图表组件无需两套渲染逻辑。
        """
        if df is None or df.empty or "charts" not in df.columns:
            return _normalize_flat(df)

        rows: list[dict[str, Any]] = []
        for _, quote in df.iterrows():
            charts = quote.get("charts") or []
            base = {
                "market": quote.get("market"),
                "code": quote.get("code"),
                "name": quote.get("name"),
                "pre_close": quote.get("pre_close"),
            }
            for pt in charts:
                rows.append(
                    {
                        **base,
                        "datetime": pt.get("time"),
                        "price": pt.get("price"),
                        "avg_price": pt.get("avg"),
                        "vol": pt.get("vol"),
                    }
                )
        return pd.DataFrame(rows)

    async def us_symbol_list(self, start: int = 0, count: int = 5000) -> pd.DataFrame:
        """取美股标的列表（代码 / 中文名）。"""
        client = self._require_ex_client(MARKET_US)
        return await client.goods_list(ex_market_value(MARKET_US), start=start, count=count)

    async def us_symbol_count(self) -> int:
        """美股标的总数。"""
        client = self._require_ex_client(MARKET_US)
        count: Any = await client.goods_count(ex_market_value(MARKET_US))
        return int(count)

    async def ex_symbol_list(self, market: str, start: int = 0, count: int = 3000) -> pd.DataFrame:
        """取外盘（港股/美股）标的列表。

        港股会遍历 5 个子市场并合并，返回值每行带 ``ex_market`` 标明来源子市场。

        Args:
            market: ``HK`` / ``US``。
            start/count: 分页参数（按每个子市场分别生效）。
        """
        token = normalize_market(market)
        client = self._require_ex_client(token)
        frames: list[pd.DataFrame] = []
        for ex_market in ex_market_values(token):
            try:
                df = await client.goods_list(ex_market, start=start, count=count)
            except Exception as exc:  # noqa: BLE001 — 单个子市场失败不阻断其余
                logger.warning("拉取 %s 子市场 %s 失败: %s", token, ex_market, exc)
                continue
            if df is None or df.empty:
                continue
            df = df.copy()
            df["ex_market"] = ex_market
            frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    async def ex_symbol_count(self, market: str) -> int:
        """外盘（港股/美股）标的总数（各子市场求和）。"""
        token = normalize_market(market)
        client = self._require_ex_client(token)
        total = 0
        for ex_market in ex_market_values(token):
            try:
                total += int(await client.goods_count(ex_market) or 0)
            except Exception as exc:  # noqa: BLE001
                logger.warning("取 %s 子市场 %s 总数失败: %s", token, ex_market, exc)
        return total


def _normalize_flat(df: pd.DataFrame | None) -> pd.DataFrame:
    """分时平表兜底规整（无内嵌 charts 字段时原样返回）。"""
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    out = df.drop(columns=[c for c in ("float_shares", "charts") if c in df.columns])
    return out


def _market_enum(token: str) -> Any:
    """规范令牌 → A 股 ``Market`` 枚举（仅 SH/SZ/BJ 可用）。

    港股/美股不会走到这里——它们在 :meth:`MarketGateway` 的四个取数方法里
    就被 :func:`is_ex` 分流到扩展市场栈了。
    """
    from easy_tdx.models.enums import Market

    return Market[token]


def _is_http_index(token: str, code: str) -> bool:
    """是否为 HTTP 源真指数（TDX 取不到，走新浪/腾讯）。"""
    from easy_tdx.sources.qq_index import is_http_index

    try:
        return is_http_index(token, code)
    except Exception:  # noqa: BLE001 — 判断失败按 TDX 路径走，不阻断
        return False


async def _run_blocking(func: Any, *args: Any) -> Any:
    """同步 HTTP 取数丢线程池（不阻塞事件循环）。"""
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args))


def _http_bars(
    token: str, code: str, category: Any, start: int, count: int, adjust: Any
) -> pd.DataFrame:
    """真指数 K 线（同步，调用方丢线程池）。

    数据源优先级：AkShare 全历史（已安装时，日/周/月）→ 腾讯快照。
    返回帧带 ``source`` 列（ak/qq），上层据此标注数据来源与延时。
    """
    from easy_tdx.sources import ak_index

    cat_name = getattr(category, "name", str(category)).upper()
    source = "qq"
    try:
        if cat_name in ("DAY", "WEEK", "MONTH") and ak_index.is_enabled():
            df = ak_index.fetch_bars(token, code, cat_name, start, count)
            source = "ak"
        else:
            raise RuntimeError("akshare 不可用或非日线周期，走腾讯快照")
    except Exception as exc:  # noqa: BLE001 — ak 失败回落腾讯快照，不整体失败
        logger.warning("akshare 指数K线失败 %s:%s，回落腾讯: %s", token, code, exc)
        from easy_tdx.sources.qq_index import fetch_bars

        df = fetch_bars(token, code, cat_name, start, count)
    df = MarketGateway._normalize_columns(df, daily_plus=MarketGateway._is_daily_plus(category))
    return _with_source(df, source)


def _with_source(df: Any, source: str) -> Any:
    """给返回帧打数据源标记列（``source``：tdx / sina / qq / ak）。

    前端据此展示"实时/延时/快照"徽标；无数据（空表）直接返回。
    缺列的调用方（回测引擎取 close 列）不受影响——多一列无害。
    """
    if df is None:
        return df
    try:
        if len(df) == 0:
            return df
        out = df.copy()
        out["source"] = source
        return out
    except Exception:  # noqa: BLE001 — 标记失败不阻断数据本身
        return df


def _http_minute(token: str, code: str) -> pd.DataFrame:
    """真指数分时（腾讯 minute/query），展开为平表（同步，调用方丢线程池）。"""
    from easy_tdx.sources.qq_index import fetch_minute

    df = fetch_minute(token, code)
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    out = df.copy()
    out["market"] = token
    out["code"] = code.upper()
    out["source"] = "qq"
    return out


def _http_quotes(token: str, codes: list[str]) -> pd.DataFrame:
    """真指数批量报价（新浪主、腾讯备；同步，调用方丢线程池）。"""
    from easy_tdx.sources.qq_index import fetch_quotes

    return _with_source(fetch_quotes(token, codes), "sina")


#: 港美股板块代码正则（HK0285 / US0467）：板块指数挂在 market=70 分区，
#: 不在任何子市场里，符号索引查不到，必须短路直传 70。
_BOARD_CODE_RE: Any = None


def _board_code_re() -> Any:
    """延迟编译的板块代码正则（避免模块 import 时就拉 re 开销，可忽略）。"""
    import re

    global _BOARD_CODE_RE
    if _BOARD_CODE_RE is None:
        _BOARD_CODE_RE = re.compile(r"^(HK|US)\d{4}$")
    return _BOARD_CODE_RE


def _resolve_ex_or_board(token: str, code: str) -> int:
    """港美股取数用的市场 int：板块代码短路 70，其余查符号索引。"""
    if _board_code_re().match((code or "").strip().upper()):
        return 70
    return resolve_ex_market(token, code)


def validate_code(code: str, market: str | None = None) -> str:
    """校验证券代码（A 股 6 位 / 港股 5 位 / 美股字母 ticker）。

    Args:
        code: 原始代码字符串。
        market: 可选市场令牌。给了就按该市场的代码长度做更严的校验；
            不给则只做通用字符校验（字母/数字/点/连字符，≤12 字符）。

    Returns:
        大写、去空白的代码。

    Raises:
        ValueError: 代码为空、过长或含非法字符。
    """
    cleaned = (code or "").strip().upper()
    if not cleaned:
        raise ValueError("证券代码不能为空")
    if len(cleaned) > _MAX_CODE_LEN:
        raise ValueError(f"证券代码过长（最多 {_MAX_CODE_LEN} 字符）: {code}")
    if not cleaned.replace(".", "").replace("-", "").isalnum():
        raise ValueError(f"证券代码含非法字符: {code}")

    if market is not None:
        token = normalize_market(market)
        if token in ("SH", "SZ", "BJ") and not (cleaned.isdigit() and len(cleaned) == 6):
            raise ValueError(f"A 股代码应为 6 位数字，收到: {code}")
        if (
            token == "HK"
            and not (
                (cleaned.isdigit() and len(cleaned) in (4, 5))
                # 港股板块指数（如 HK0285）：2 字母前缀 + 4 位数字
                or (len(cleaned) == 6 and cleaned[:2] == "HK" and cleaned[2:].isdigit())
                # 港股指数（如 HSI/CES100/HZ5014）：字母开头
                or (
                    cleaned[0].isalpha()
                    and cleaned.replace(".", "").isalnum()
                    and len(cleaned) <= 8
                )
            )
        ):
            raise ValueError(f"港股代码应为 4-5 位数字（板块 HKxxxx / 指数如 HSI），收到: {code}")
        if (
            token == "US"
            and not (
                (cleaned[0].isalpha() and cleaned.replace(".", "").replace("-", "").isalnum())
                # 美股板块指数（如 US0467）
                or (len(cleaned) == 6 and cleaned[:2] == "US" and cleaned[2:].isdigit())
            )
        ):
            raise ValueError(f"美股代码应为字母（板块 USxxxx），收到: {code}")
    return cleaned


__all__ = [
    "MarketGateway",
    "validate_code",
    "is_us",
    "is_hk",
    "is_ex",
    "resolve_ex_market",
]
