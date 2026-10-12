"""市场抽象层：把「港股 / 美股（外盘）」提升为一等公民市场。

背景
----
通达信协议里，A股市场是单字节 ``Market``（SZ=0 / SH=1 / BJ=2），而港美股
走的是**扩展市场**（MAC 协议 0x122B/0x122E，端口 7727）的 ``ExMarket``，
两者分属不同协议栈：标准 ``TdxClient``/``MacClient`` 发不出外盘请求，
只有 ``MacExClient``/``AsyncMacExClient`` 能取。

于是同一个概念（"某只票的日K"）在上层要分流到两条完全不同的连接上。
本模块提供唯一的市场归一化入口，让上层只认"市场令牌"（字符串），
由 :func:`ex_market_value` 决定该走哪条协议栈。

市场令牌
--------
接受以下写法，全部归一化为 :data:`MARKET_US` / :data:`MARKET_SH` 等规范值：

===============  ==========================================
令牌              含义
===============  ==========================================
``SH`` / ``1``    上海 A 股
``SZ`` / ``0``    深圳 A 股
``BJ`` / ``2``    北京 A 股
``HK`` / ``31``   **香港股票（主板）**，另见 :data:`HK_EX_MARKETS`
``US`` / ``74``   **美国股票（外盘）**
===============  ==========================================

未知令牌一律抛 :class:`ValueError`，并把全部可选值列进错误信息——
宁可早点炸，也不要静默拿错市场的数据。

港股是一族市场而非一个
----------------------
通达信把港股拆成多个 ``ExMarket`` 子市场：主板 31、创业板 48、基金 49、
指数 27、暗盘 98（实测共约 3600 个标的，全量拉取约 2 秒）。

上层不该感知这个拆分——:func:`ex_market_values` 返回该市场的**全部**
子市场值（用于列表/搜索），而具体某只票落在哪个子市场，由
:func:`resolve_ex_market` 配合 ``web/symbol_index.py`` 的代码索引判定。
"""

from __future__ import annotations

import re
from typing import Final

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

MARKET_SZ: Final = "SZ"
MARKET_SH: Final = "SH"
MARKET_BJ: Final = "BJ"
MARKET_HK: Final = "HK"
MARKET_US: Final = "US"

#: 通达信扩展市场里"美国股票"的市场代码（``ExMarket.US_STOCK``）。
#: 这是美股全部请求在线路上的实际取值，勿硬编码 74。
US_STOCK_EX_MARKET: Final = 74

#: 港股子市场集合（``ExMarket`` 值 → 含义）：
#: 31 主板 / 48 创业板 / 49 基金 / 27 指数 / 98 暗盘。
HK_EX_MARKETS: Final[tuple[int, ...]] = (31, 48, 49, 27, 98)

#: 港股默认子市场（主板）。绝大多数港股代码落在 31，
#: 且它是 :data:`HK_EX_MARKETS` 里标的最多的一类。
HK_DEFAULT_EX_MARKET: Final = 31

#: 子市场 → 中文名（榜单/搜索结果的分组标签）。
HK_EX_MARKET_NAMES: Final[dict[int, str]] = {
    31: "主板",
    48: "创业板",
    49: "ETF/基金",
    27: "指数",
    98: "暗盘",
}

#: 全部规范市场令牌。
ALL_MARKETS: Final = (MARKET_SZ, MARKET_SH, MARKET_BJ, MARKET_HK, MARKET_US)

#: 全部走扩展市场协议栈（端口 7727）的市场令牌。
EX_MARKETS: Final = (MARKET_HK, MARKET_US)

#: 全部 A 股市场令牌（走 7709 标准/MAC 协议栈）。
A_SHARE_MARKETS: Final = (MARKET_SZ, MARKET_SH, MARKET_BJ)

#: 默认市场。未显式指定 market 时的兜底。
DEFAULT_MARKET: Final = MARKET_SH

# 归一化别名表：用户/CI/前端传入的写法 → 规范令牌。
# 键一律大写；值要么是 Market 枚举名，要么是十进制数字字符串。
_ALIASES: Final[dict[str, str]] = {
    "SZ": MARKET_SZ,
    "0": MARKET_SZ,
    "SH": MARKET_SH,
    "1": MARKET_SH,
    "BJ": MARKET_BJ,
    "2": MARKET_BJ,
    "US": MARKET_US,
    "USA": MARKET_US,
    "US_STOCK": MARKET_US,
    "OVERSEAS": MARKET_US,
    "74": MARKET_US,
    "HK": MARKET_HK,
    "HKG": MARKET_HK,
    "HKEX": MARKET_HK,
    "HK_STOCK": MARKET_HK,
    "HONGKONG": MARKET_HK,
    "HONG_KONG": MARKET_HK,
    # 港股子市场代码直接写出来时，按所属子市场归一到 HK 族
    "HK_MAIN_BOARD": MARKET_HK,
    "HK_GEM": MARKET_HK,
    "HK_FUND": MARKET_HK,
    "HK_INDEX": MARKET_HK,
    "HK_DARK_POOL": MARKET_HK,
    "31": MARKET_HK,
    "48": MARKET_HK,
    "49": MARKET_HK,
    "27": MARKET_HK,
    "98": MARKET_HK,
}

#: 规范令牌 → 该市场在线路上的 int 取值。
#: A股取 ``Market`` 枚举值（标准协议口径），外盘取扩展市场 ``ExMarket`` 值。
_MARKET_VALUES: Final[dict[str, int]] = {
    MARKET_SZ: 0,
    MARKET_SH: 1,
    MARKET_BJ: 2,
    MARKET_HK: HK_DEFAULT_EX_MARKET,
    MARKET_US: US_STOCK_EX_MARKET,
}


# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------


def normalize_market(market: str | int) -> str:
    """把任意市场写法归一化为规范令牌。

    Args:
        market: 市场令牌，如 ``"SH"`` / ``"us"`` / ``74`` / ``1`` / ``"HK"``。

    Returns:
        规范令牌：``"SZ"`` / ``"SH"`` / ``"BJ"`` / ``"HK"`` / ``"US"``。

    Raises:
        ValueError: 令牌无法识别。

    >>> normalize_market("sh")
    'SH'
    >>> normalize_market(74)
    'US'
    >>> normalize_market("HK_GEM")
    'HK'
    """
    key = str(market).strip().upper()
    try:
        return _ALIASES[key]
    except KeyError:
        valid = ", ".join(f"{m}({_MARKET_VALUES[m]})" for m in ALL_MARKETS)
        raise ValueError(f"无效市场代码 '{market}'，可选值: {valid}") from None


def is_us(market: str | int) -> bool:
    """判断该市场是否为美股。

    Args:
        market: 任意市场写法，非法值同样抛 :class:`ValueError`。

    >>> is_us("US"), is_us("SH")
    (True, False)
    """
    return normalize_market(market) == MARKET_US


def is_hk(market: str | int) -> bool:
    """判断该市场是否为港股（含主板/创业板/基金/指数/暗盘全部子市场）。

    >>> is_hk("HK"), is_hk(31), is_hk("US")
    (True, True, False)
    """
    return normalize_market(market) == MARKET_HK


def is_ex(market: str | int) -> bool:
    """判断该市场是否走扩展市场协议栈（端口 7727）。

    >>> is_ex("HK"), is_ex("US"), is_ex("SH")
    (True, True, False)
    """
    return normalize_market(market) in EX_MARKETS


def is_a_share(market: str | int) -> bool:
    """判断该市场是否为 A 股（沪/深/北）。

    >>> is_a_share("SH"), is_a_share("HK")
    (True, False)
    """
    return normalize_market(market) in A_SHARE_MARKETS


def needs_symbol_resolution(market: str | int) -> bool:
    """判断该市场是否为"一族多子市场"（港股），需要按代码定位具体子市场。

    A 股与美股的市场码本身就是单字节的，不需要额外解析；
    港股有 5 个子市场，仅凭 ``HK`` 令牌无法确定该走哪个。

    >>> needs_symbol_resolution("HK"), needs_symbol_resolution("US")
    (True, False)
    """
    return normalize_market(market) == MARKET_HK


def ex_market_value(market: str | int) -> int:
    """取该市场在线路上的 int 取值（MAC 协议口径）。

    A 股返回 ``Market`` 枚举值，美股返回 :data:`US_STOCK_EX_MARKET`（74），
    港股返回**默认子市场** :data:`HK_DEFAULT_EX_MARKET`（31，主板）。

    .. warning::
       港股有 5 个子市场，精确取数请用 :func:`resolve_ex_market`；
       本函数对港股只在"确定是主板/只是兜底"时才正确。

    >>> ex_market_value("US")
    74
    >>> ex_market_value("SH")
    1
    >>> ex_market_value("HK")
    31
    """
    return _MARKET_VALUES[normalize_market(market)]


def ex_market_values(market: str | int) -> tuple[int, ...]:
    """取该市场在线路上的**全部** int 取值（用于列表/搜索遍历）。

    港股返回 :data:`HK_EX_MARKETS` 五个子市场；其余市场是单值元组。

    >>> ex_market_values("US")
    (74,)
    >>> ex_market_values("HK")
    (31, 48, 49, 27, 98)
    """
    token = normalize_market(market)
    if token == MARKET_HK:
        return HK_EX_MARKETS
    return (_MARKET_VALUES[token],)


def resolve_ex_market(market: str | int, code: str | None = None) -> int:
    """把「市场令牌 + 可选代码」解析为线上唯一的市场 int 取值。

    仅港股需要 ``code``：主板/创业板/基金/指数/暗盘共用 ``HK`` 令牌，
    必须靠代码索引定位到具体子市场。索引未加载或查不到时退回
    :data:`HK_DEFAULT_EX_MARKET`（主板），宁可近似也不要整体失败。

    A 股与美股忽略 ``code``，直接返回单值。

    Args:
        market: 市场令牌。
        code: 证券代码，仅港股使用。

    Returns:
        发给服务器的市场代码。

    >>> resolve_ex_market("US", "AAPL")
    74
    """
    token = normalize_market(market)
    if token != MARKET_HK or not code:
        return _MARKET_VALUES[token]

    from easy_tdx.web.symbol_index import lookup_ex_market

    resolved = lookup_ex_market(code)
    if resolved is None:
        return HK_DEFAULT_EX_MARKET
    return resolved


def market_label(market: str | int) -> str:
    """取市场的中文展示名（前端标题栏 / 报错信息用）。

    >>> market_label("US")
    '美股'
    >>> market_label("HK")
    '港股'
    """
    return {
        MARKET_SZ: "深证",
        MARKET_SH: "上证",
        MARKET_BJ: "北证",
        MARKET_HK: "港股",
        MARKET_US: "美股",
    }[normalize_market(market)]


def currency_label(market: str | int) -> str:
    """取市场的计价货币展示名。

    >>> currency_label("HK")
    '港元'
    """
    return {
        MARKET_SZ: "元",
        MARKET_SH: "元",
        MARKET_BJ: "元",
        MARKET_HK: "港元",
        MARKET_US: "美元",
    }[normalize_market(market)]


def market_currency(market: str | int) -> str:
    """取市场的 ISO 4217 货币代码。

    >>> market_currency("US")
    'USD'
    """
    return {
        MARKET_SZ: "CNY",
        MARKET_SH: "CNY",
        MARKET_BJ: "CNY",
        MARKET_HK: "HKD",
        MARKET_US: "USD",
    }[normalize_market(market)]


def ex_market_label(ex_market: int) -> str:
    """取港股子市场的中文名；非港股子市场返回空串。

    >>> ex_market_label(48)
    '创业板'
    >>> ex_market_label(74)
    ''
    """
    return HK_EX_MARKET_NAMES.get(int(ex_market), "")


# ---------------------------------------------------------------------------
# 标的令牌：``MARKET:CODE``
# ---------------------------------------------------------------------------
#
# 三类市场的代码格式无法互相推断（港股指数 CES100 与美股 AAPL 同形），
# 所以标的必须自带市场前缀，而不是靠代码长相猜。这也是前端
# 「每个标的自带市场标识」约定的服务端表达。
#
# 三类格式：
#
# * A 股 ``SH:600519`` / ``SZ:000001`` / ``BJ:430047`` —— 6 位数字
# * 港股 ``HK:00700`` —— 4-5 位数字
# * 美股 ``US:AAPL`` / ``US:BRK.B`` —— 字母 ticker，可含 ``.`` 与 ``-``

#: ``MARKET:CODE`` 正则（供 pydantic ``pattern=`` 直接引用）。
SYMBOL_PATTERN: Final = r"^(?:SZ|SH|BJ):\d{6}$|^HK:\d{4,5}$|^US:[A-Z0-9][A-Z0-9.\-]{0,11}$"

#: 同上的预编译版本，供 Python 侧的 ``if not SYMBOL_REGEX.match(s)`` 判断
#: （pydantic 的 ``pattern=`` 要字符串，两者别混用）。
SYMBOL_REGEX: Final = re.compile(SYMBOL_PATTERN)


def make_symbol(market: str | int, code: str) -> str:
    """拼标的令牌（``MARKET:CODE``），两侧去空白、市场转大写。

    >>> make_symbol("hk", "00700")
    'HK:00700'
    >>> make_symbol(74, "aapl")
    'US:AAPL'
    """
    token = normalize_market(market)
    return f"{token}:{(code or '').strip().upper()}"


def parse_symbol(symbol: str) -> tuple[str, str]:
    """拆标的令牌为 ``(市场令牌, 代码)``。

    Args:
        symbol: ``MARKET:CODE`` 形式的字符串。

    Returns:
        ``(market, code)``，市场已归一化，代码已去空白转大写。

    Raises:
        ValueError: 格式不对或市场无法识别。

    >>> parse_symbol("HK:00700")
    ('HK', '00700')
    """
    text = (symbol or "").strip().upper()
    if ":" not in text:
        raise ValueError(f"标的令牌格式应为 'MARKET:CODE'，收到: {symbol!r}")
    raw_market, _, code = text.partition(":")
    code = code.strip()
    if not code:
        raise ValueError(f"标的令牌缺少代码: {symbol!r}")
    return normalize_market(raw_market), code
