"""MAC 协议字段位图编解码。

提供 FieldBit 定义、预定义字段集合（PresetField）、字段选择器（FieldSelection），
以及 20 字节请求位图的构建与响应位图解析。
"""

from collections.abc import Iterable, Iterator
from enum import Enum, IntEnum
from typing import TypeAlias

# ── 统一的字段选择类型 ──
Fields: TypeAlias = "FieldBit | PresetField | FieldSelection | Iterable[FieldBit]"


class FieldBit(IntEnum):
    """字段位定义，自带格式和描述，单一数据源。"""

    fmt: str  # 由 __new__ 设置
    desc: str  # 由 __new__ 设置

    def __new__(cls, value: int, fmt: str = "<f", desc: str = "") -> "FieldBit":
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.fmt = fmt
        obj.desc = desc
        return obj

    @property
    def field_name(self) -> str:
        """返回英文字段名，用于 DataFrame 列名等。"""
        return self.name.lower()

    # ── 基础字段 (0x00-0x05) ──
    PRE_CLOSE = 0x00, "<f", "昨收"
    OPEN = 0x01, "<f", "开盘价"
    HIGH = 0x02, "<f", "最高价"
    LOW = 0x03, "<f", "最低价"
    CLOSE = 0x04, "<f", "收盘价"
    VOL = 0x05, "<I", "成交量"
    VOL_RATIO = 0x06, "<f", "量比"
    AMOUNT = 0x07, "<f", "总金额(元)"

    # ── 扩展字段 (0x08-0x0F) ──
    INSIDE_VOLUME = 0x08, "<I", "内盘"
    OUTSIDE_VOLUME = 0x09, "<I", "外盘"
    TOTAL_SHARES = 0x0A, "<f", "总股数(单位万)"
    FLOAT_SHARES = 0x0B, "<f", "流通股(单位万)"
    EPS = 0x0C, "<f", "每股收益"
    NET_ASSETS = 0x0D, "<f", "净资产"
    SECURITY_TYPE_PRICE = 0x0E, "<f", "证券类型价"
    TOTAL_MARKET_CAP_AB = 0x0F, "<f", "AB股总市值"

    # ── 0x10-0x1F ──
    PE_DYNAMIC = 0x10, "<f", "市盈率(动)"
    BID_PRICE = 0x11, "<f", "买一价"
    ASK_PRICE = 0x12, "<f", "卖一价"
    SERVER_UPDATE_DATE = 0x13, "<I", "服务器更新日期 YYYYMMDD"
    SERVER_UPDATE_TIME = 0x14, "<I", "服务器更新时间 HHMMSS"
    LOT_SIZE_INFO = 0x15, "<I", "未确定"
    BOARD_STRENGTH = 0x16, "<f", "板块强度(涨跌家数差)"
    DIVIDEND_YIELD = 0x17, "<f", "每股股息(元)"
    BID_VOLUME = 0x18, "<I", "买量"
    ASK_VOLUME = 0x19, "<I", "卖量"
    LAST_VOLUME = 0x1A, "<I", "现量"
    TURNOVER = 0x1B, "<f", "换手"
    INDUSTRY = 0x1C, "<I", "行业分类代码"
    INDUSTRY_CHANGE_UP = 0x1D, "<f", "行业涨跌幅"
    STOCK_TAG_FLAGS = 0x1E, "<I", "股票标签位图"
    DECIMAL_POINT = 0x1F, "<I", "数据精度"

    # ── 0x20-0x2F ──
    BUY_PRICE_LIMIT = 0x20, "<f", "涨停价"
    SELL_PRICE_LIMIT = 0x21, "<f", "跌停价"
    PRICE_DECIMAL_INFO = 0x22, "<I", "价格精度标志"
    LOT_SIZE = 0x23, "<I", "所属地区板块/每手股数"
    PRE_IOPV = 0x24, "<f", "昨IOPV"
    SPEED_PCT = 0x25, "<f", "涨速"
    AVG_PRICE = 0x26, "<f", "均价"
    IOPV = 0x27, "<f", "IOPV"
    PE_TTM_VOL_RELATED = 0x28, "<f", "前参考价(美股适用)"
    EX_PRICE_PLACEHOLDER = 0x29, "<f", "前金额参考"
    OPERATING_REVENUE = 0x2A, "<f", "营业收入(万)"
    FLAG_KCB = 0x2B, "<I", "科创板标志"
    FLAG_BJ = 0x2C, "<I", "北交所标志"
    CIRCULATING_CAPITAL_Z = 0x2D, "<f", "流通股本Z（单位：万股）"
    AFTER_HOURS_VOLUME = 0x2E, "<i", "盘后量"

    # ── 0x30-0x3F ──
    PE_TTM = 0x30, "<f", "市盈率TTM"
    PE_STATIC = 0x31, "<f", "市盈率静"
    INDEX_METRIC = 0x37, "<f", "指数指标"
    MAIN_NET_AMOUNT = 0x38, "<f", "今日主力净流入"
    BID_ASK_RATIO = 0x39, "<f", "委比"
    NON_INDEX_FLAG = 0x3A, "<I", "非指数标志"
    CHANGE_20D_PCT = 0x3B, "<f", "20日涨幅%"
    YTD_PCT = 0x3C, "<f", "年初至今%"
    STOCK_CLASS_CODE = 0x3E, "<I", "证券子分类码"
    PERCENT_BASE = 0x3F, "<I", "百分比基底"

    # ── 0x40-0x4F ──
    MTD_PCT = 0x40, "<f", "月初至今%"
    CHANGE_1Y_PCT = 0x41, "<f", "一年涨幅%"
    PREV_CHANGE_PCT = 0x42, "<f", "昨涨幅%"
    CHANGE_3D_PCT = 0x43, "<f", "3日涨幅%"
    CHANGE_60D_PCT = 0x44, "<f", "60日涨幅%"
    CHANGE_5D_PCT = 0x45, "<f", "5日涨幅%"
    CHANGE_10D_PCT = 0x46, "<f", "10日涨幅%"
    PREV2_CHANGE_PCT = 0x47, "<f", "前日涨幅%"
    BID2_PRICE = 0x48, "<f", "买二价"
    ASK2_PRICE = 0x49, "<f", "卖二价"
    AH_CODE = 0x4A, "<I", "对应A/H股code"
    UNKNOWN_CODE = 0x4B, "<I", "少部分有数据"

    # ── 0x50-0x6F ──
    OPEN_AMOUNT = 0x57, "<f", "开盘金额(元)"
    ANNUAL_LIMIT_UP_DAYS = 0x58, "<i", "年涨停天数"
    ACTIVITY = 0x59, "<I", "活跃度"
    DIVIDEND_YIELD_RATE = 0x5B, "<f", "股息率%"
    CONSECUTIVE_UP_DAYS = 0x5C, "<i", "连涨天"
    LIMIT_UP_COUNT = 0x5D, "<I", "涨停数(板块) / 买二量(个股)"
    BID2_VOLUME = 0x5D, "<I", "买二量(个股)"
    LIMIT_DOWN_COUNT = 0x5E, "<I", "跌停数(板块) / 卖二量(个股)"
    ASK2_VOLUME = 0x5E, "<I", "卖二量(个股)"
    INDUSTRY_SUB = 0x5F, "<I", "行业二级分类"
    AUCTION_BUY_LIMIT = 0x66, "<f", "连续竞价买入上限"
    AUCTION_SELL_LIMIT = 0x67, "<f", "连续竞价卖出下限"
    VOL_SPEED_PCT = 0x68, "<f", "量涨速%"
    SHORT_TURNOVER_PCT = 0x69, "<f", "短换手%"
    AMOUNT_2M = 0x6A, "<f", "2分钟金额(元)"
    MAIN_NET_AMOUNT_COPY = 0x6B, "<f", "今日主力净流入(副本)"
    MAIN_NET_RATIO = 0x6C, "<f", "主力净比%"
    RETAIL_NET_AMOUNT = 0x6D, "<f", "散户单增比"
    MAIN_NET_5M_AMOUNT = 0x6E, "<f", "5分钟主力净额"
    MAIN_NET_3D_AMOUNT = 0x6F, "<f", "近三日主力净额"

    # ── 0x70-0x7F ──
    MAIN_NET_5D_AMOUNT = 0x70, "<f", "近五日主力净额"
    MAIN_NET_10D_AMOUNT = 0x71, "<f", "近十日主买金额(待确定)"
    MAIN_BUY_NET_AMOUNT = 0x72, "<f", "今日主买净额"
    DDX = 0x73, "<f", "DDX"
    DDY = 0x74, "<f", "DDY"
    DDZ = 0x75, "<f", "DDZ"
    DDF = 0x76, "<f", "DDF"
    STOCK_FLAG_A = 0x77, "<f", "个股标志位A"
    STOCK_FLAG_B = 0x78, "<f", "个股标志位B(副本)"
    AUCTION_VOL_RATIO = 0x7A, "<f", "竞价昨比"
    PREV_AMOUNT = 0x7B, "<f", "昨成交额(元)"
    RECENT_INDICATOR = 0x7D, "<f", "近日指标提示"

    # ── 0x80-0x8F ──
    BID3_PRICE = 0x80, "<f", "买三价"
    BID4_PRICE = 0x81, "<f", "买四价"
    BID5_PRICE = 0x82, "<f", "买五价"
    ASK3_PRICE = 0x83, "<f", "卖三价"
    ASK4_PRICE = 0x84, "<f", "卖四价"
    ASK5_PRICE = 0x85, "<f", "卖五价"
    BID3_VOLUME = 0x86, "<I", "买三量"
    BID4_VOLUME = 0x87, "<I", "买四量"
    UP_COUNT = 0x88, "<I", "上涨家数(板块) / 买五量(个股)"
    BID5_VOLUME = 0x88, "<I", "买五量(个股)"
    ASK3_VOLUME = 0x89, "<I", "卖三量"
    ASK4_VOLUME = 0x8A, "<I", "卖四量"
    DOWN_COUNT = 0x8B, "<I", "下跌家数(板块) / 卖五量(个股)"
    ASK5_VOLUME = 0x8B, "<I", "卖五量(个股)"
    BID_ASK_DIFF = 0x8C, "<i", "委差"
    CHANGE_UP_TYPE = 0x8D, "<i", "封板状态"
    SAFETY_SCORE = 0x8E, "<f", "安全分"
    HIGHLIGHT_COUNT = 0x8F, "<f", "亮点数"

    # ── 0x90-0x96: 日内时间涨幅(从昨收算) ──
    CHANGE_AT_1000 = 0x90, "<f", "日内涨幅% 10:00"
    CHANGE_AT_1030 = 0x91, "<f", "日内涨幅% 10:30"
    CHANGE_AT_1100 = 0x92, "<f", "日内涨幅% 11:00"
    CHANGE_AT_1130 = 0x93, "<f", "日内涨幅% 11:30"
    CHANGE_AT_1330 = 0x94, "<f", "日内涨幅% 13:30"
    CHANGE_AT_1400 = 0x95, "<f", "日内涨幅% 14:00"
    CHANGE_AT_1430 = 0x96, "<f", "日内涨幅% 14:30"


# 从 FieldBit 自动生成
FIELD_BITMAP_MAP: dict[int, tuple[str, str, str]] = {
    bit.value: (bit.name.lower(), bit.fmt, bit.desc) for bit in FieldBit
}


# ── 字段后处理钩子 ──
def _post_ah_code(value: int, market: int = 0) -> str:
    """A/H股代码补齐位数。"""
    if not value:
        return ""
    # 沪深北 5 位，其他 6 位
    width = 5 if market in (0, 1) else 6
    return str(value).zfill(width)


FIELD_POSTPROCESS: dict[int, object] = {
    0x4A: _post_ah_code,  # AH_CODE: 补齐0
}


# ── 控制区(位128-159, 4字节) ──
# 前16字节(位0-127)是字段位图, 后4字节(位128-159)是控制区。
# 注意两条 MAC 命令的线格式不同（均经抓包/实测反推，见下）：
#
# - ``0x122B``（个股批量报价）：请求体 = 完整 20 字节位图（高位字段直接置位，
#   见 :func:`build_bitmap`），响应 20 字节位图回显有效字段。
# - ``0x122C``（板块成分报价）：请求体 = 16 字节位图 + 4 字节控制区，其中
#   字节17 固定为排除/限流位（:class:`FilterType` 位掩码 1/2/4/.../128），与
#   字段位 0x88-0x8F（同处字节17）在物理上冲突——因此 0x88-0x8F 字段在此命令
#   上无法表达（见 :func:`split_control_bytes` 的警告逻辑）。
#
# 字节含义（两命令响应通用）：
#   字节16(位128-135): 盘口深度(bid3_price~bid4_volume，即 0x80-0x87，恰占满一字节)
#   字节17(位136-143): 0x122B=字段位(0x88-0x8F)；0x122C=排除/限流位（回显排除标志）
#   字节18(位144-151): 日内涨幅(change_at_1000~1430，即 0x90-0x96)
#   字节19(位152-159): 控制字节(CTRL_EXTENDED等；当前无 152+ 字段位，恒为纯控制)
#
# 解析规则（见 :func:`resolve_response_fields`）：
#   0x122B 用整 20 字节解析（长度精确拟合校验）；0x122C 只用低 16 字节，
#   高字节非零且映射到已知字段时打警告（行错位比丢字段更危险）。

CTRL_BYTE = 0  # 控制字节起始位(152)
CTRL_EXTENDED = 1  # 非0=扩展模式(含北交所等)，0=标准模式(仅A股)

# 0x122C 控制区中专属于排除标志的字节下标（相对 4 字节控制区）。
_EXCLUDE_BYTE_INDEX = 1  # 整体第 17 字节
# 落在该字节范围内的字段位（0x88-0x8F），在 0x122C 上无法与排除标志共存。
_EXCLUDE_CONFLICT_RANGE = range(0x88, 0x90)


# ── 预定义字段集合 ──
class PresetField(Enum):
    """预定义字段集合，支持 + / | 链式组合。

    Usage:
        PresetField.BASIC + PresetField.VOLUME          # 两个预设合并
        PresetField.OHLC + FieldBit.AH_CODE             # 预设 + 单字段
        FieldBit.OPEN + FieldBit.HIGH + FieldBit.LOW    # 纯字段组合
    """

    NONE = ()
    OHLC = (FieldBit.OPEN, FieldBit.HIGH, FieldBit.LOW, FieldBit.CLOSE)
    BASIC = (
        FieldBit.OPEN,
        FieldBit.HIGH,
        FieldBit.LOW,
        FieldBit.CLOSE,
        FieldBit.PRE_CLOSE,
        FieldBit.VOL,
    )
    QUOTE = (
        FieldBit.BID_PRICE,
        FieldBit.ASK_PRICE,
        FieldBit.BID_VOLUME,
        FieldBit.ASK_VOLUME,
        FieldBit.LAST_VOLUME,
    )
    VOLUME = (FieldBit.VOL, FieldBit.AMOUNT, FieldBit.TURNOVER, FieldBit.VOL_RATIO)
    FUNDAMENTAL = (
        FieldBit.TOTAL_SHARES,
        FieldBit.FLOAT_SHARES,
        FieldBit.EPS,
        FieldBit.NET_ASSETS,
    )
    ENHANCED = (
        FieldBit.OPEN,
        FieldBit.HIGH,
        FieldBit.LOW,
        FieldBit.CLOSE,
        FieldBit.VOL,
        FieldBit.FLOAT_SHARES,
        FieldBit.ACTIVITY,
    )
    AH_CODE_FIELDS = (
        FieldBit.OPEN,
        FieldBit.HIGH,
        FieldBit.LOW,
        FieldBit.CLOSE,
        FieldBit.VOL,
        FieldBit.AH_CODE,
        FieldBit.LOT_SIZE,
        FieldBit.INDUSTRY,
    )
    BOARD_STATS = (
        FieldBit.LIMIT_UP_COUNT,
        FieldBit.LIMIT_DOWN_COUNT,
        FieldBit.UP_COUNT,
        FieldBit.DOWN_COUNT,
    )
    HANDICAP = (
        FieldBit.BID_PRICE,
        FieldBit.BID2_PRICE,
        FieldBit.BID3_PRICE,
        FieldBit.BID4_PRICE,
        FieldBit.BID5_PRICE,
        FieldBit.ASK_PRICE,
        FieldBit.ASK2_PRICE,
        FieldBit.ASK3_PRICE,
        FieldBit.ASK4_PRICE,
        FieldBit.ASK5_PRICE,
        FieldBit.BID_VOLUME,
        FieldBit.BID2_VOLUME,
        FieldBit.BID3_VOLUME,
        FieldBit.BID4_VOLUME,
        FieldBit.BID5_VOLUME,
        FieldBit.ASK_VOLUME,
        FieldBit.ASK2_VOLUME,
        FieldBit.ASK3_VOLUME,
        FieldBit.ASK4_VOLUME,
        FieldBit.ASK5_VOLUME,
    )
    COMMON = (
        FieldBit.PRE_CLOSE,
        FieldBit.OPEN,
        FieldBit.HIGH,
        FieldBit.LOW,
        FieldBit.CLOSE,
        FieldBit.VOL,
        FieldBit.VOL_RATIO,
        FieldBit.AMOUNT,
        FieldBit.TOTAL_SHARES,
        FieldBit.FLOAT_SHARES,
        FieldBit.EPS,
        FieldBit.NET_ASSETS,
        FieldBit.SECURITY_TYPE_PRICE,
        FieldBit.TOTAL_MARKET_CAP_AB,
        FieldBit.PE_DYNAMIC,
        FieldBit.LOT_SIZE_INFO,
        FieldBit.DIVIDEND_YIELD,
        FieldBit.LAST_VOLUME,
        FieldBit.TURNOVER,
        FieldBit.STOCK_TAG_FLAGS,
        FieldBit.DECIMAL_POINT,
        FieldBit.BUY_PRICE_LIMIT,
        FieldBit.SELL_PRICE_LIMIT,
        FieldBit.PRICE_DECIMAL_INFO,
        FieldBit.LOT_SIZE,
        FieldBit.PRE_IOPV,
        FieldBit.SPEED_PCT,
        FieldBit.FLAG_KCB,
        FieldBit.PE_TTM,
        FieldBit.PE_STATIC,
        FieldBit.MAIN_NET_AMOUNT,
        FieldBit.VOL_SPEED_PCT,
        FieldBit.SHORT_TURNOVER_PCT,
        FieldBit.CIRCULATING_CAPITAL_Z,
    )
    DEBUG = (-1, "", "调试用全字段")
    ALL = tuple(FieldBit)

    def __add__(self, other: object) -> "FieldSelection":
        if isinstance(other, FieldBit | PresetField | FieldSelection):
            return FieldSelection(self, other)
        return NotImplemented

    def __or__(self, other: object) -> "FieldSelection":
        return self.__add__(other)

    def __radd__(self, other: object) -> "FieldSelection":
        if isinstance(other, FieldBit | FieldSelection):
            return FieldSelection(other, self)
        return NotImplemented

    def __ror__(self, other: object) -> "FieldSelection":
        return self.__radd__(other)


class FieldSelection:
    """字段选择器，支持 PresetField + FieldBit 组合。

    Usage:
        PresetField.BASIC + FieldBit.AH_CODE
        PresetField.BASIC | FieldBit.INDUSTRY
        FieldBit.OPEN + FieldBit.HIGH + FieldBit.LOW
    """

    __slots__ = ("_fields",)

    def __init__(self, *parts: "FieldBit | PresetField | FieldSelection") -> None:
        seen: set[FieldBit] = set()
        result: list[FieldBit] = []
        for part in parts:
            if isinstance(part, PresetField):
                source: Iterable[FieldBit] = part.value
            elif isinstance(part, FieldBit):
                source = (part,)
            else:
                source = part._fields
            for bit in source:
                if bit not in seen:
                    seen.add(bit)
                    result.append(bit)
        self._fields: tuple[FieldBit, ...] = tuple(result)

    def __add__(self, other: object) -> "FieldSelection":
        if isinstance(other, FieldBit | PresetField | FieldSelection):
            return FieldSelection(self, other)
        return NotImplemented

    def __or__(self, other: object) -> "FieldSelection":
        return self.__add__(other)

    def __radd__(self, other: object) -> "FieldSelection":
        if isinstance(other, FieldBit | PresetField):
            return FieldSelection(other, self)
        return NotImplemented

    def __ror__(self, other: object) -> "FieldSelection":
        return self.__radd__(other)

    def __iter__(self) -> Iterator[FieldBit]:
        return iter(self._fields)

    def __len__(self) -> int:
        return len(self._fields)

    def __bool__(self) -> bool:
        return bool(self._fields)

    def __contains__(self, item: object) -> bool:
        return item in self._fields

    def __repr__(self) -> str:
        names = [bit.name for bit in self._fields]
        return f"FieldSelection([{', '.join(names)}])"


def normalize_fields(fields: "Fields") -> FieldSelection:
    """将任意字段选择形式归一化为 FieldSelection。"""
    if fields is None:
        return FieldSelection()
    if isinstance(fields, FieldSelection):
        return fields
    if isinstance(fields, PresetField):
        return FieldSelection(*fields.value)
    if isinstance(fields, FieldBit):
        return FieldSelection(fields)
    return FieldSelection(*fields)


def build_bitmap(
    fields: "Fields",
    exclude_flags: int = 0,
) -> bytearray:
    """将字段选择转换为 20 字节请求位图。

    Parameters
    ----------
    fields : Fields
        字段选择，可以是 PresetField、FieldBit、FieldSelection 或可迭代对象。
    exclude_flags : int
        控制区 4 字节（位 128-159）的值，默认 0。

    Returns
    -------
    bytearray
        20 字节位图。
    """
    if isinstance(fields, PresetField) and fields is PresetField.DEBUG:
        return bytearray(b"\xff" * 20)
    selection = normalize_fields(fields)
    low_int = 0
    high_int = 0
    for bit in selection:
        v = int(bit.value)
        if v < 0:
            raise ValueError(f"非法字段位 {v}")
        if v < 128:
            low_int |= 1 << v
        elif v < 160:
            high_int |= 1 << (v - 128)
        else:
            raise ValueError(f"字段位超出20字节位图范围: {v:#x}")
    control = int(high_int) | int(exclude_flags)
    if control >= 1 << 32:
        raise ValueError(f"控制区超出4字节范围: {control:#x}")
    ba = bytearray(low_int.to_bytes(16, "little"))
    ba.extend(control.to_bytes(4, "little"))
    return ba


def build_exclude_flags(exclude_flags: int = 0) -> bytes:
    """构建 4 字节控制区。

    Parameters
    ----------
    exclude_flags : int
        控制区原始值，默认 0。

    Returns
    -------
    bytes
        4 字节控制区。
    """
    return exclude_flags.to_bytes(4, "little")


def split_control_bytes(fields: "Fields") -> tuple[bytes, list[str]]:
    """把字段选择拆成 0x122C 风格的控制区 4 字节。

    0x122C 请求 = 16 字节位图 + ``(盘口, 排除, 日内, 控制)``，其中字节17
    专属于排除标志：落在 0x88-0x8F 的字段位无法表达，随 ``unexpressible``
    返回，由调用方打警告（静默丢字段比报错更危险，故只警告不断链）。

    Returns:
        ``(control_4bytes, unexpressible_names)``。
    """
    import logging

    selection = normalize_fields(fields)
    b16 = b18 = b19 = 0
    unexpressible: list[str] = []
    for bit in selection:
        v = int(bit.value)
        if v < 128:
            continue  # 低 128 位走 16 字节位图，与本函数无关
        if v >= 160:
            raise ValueError(f"字段位超出20字节位图范围: {v:#x}")
        if v in _EXCLUDE_CONFLICT_RANGE:
            unexpressible.append(bit.name)
        elif v < 0x88:
            b16 |= 1 << (v - 128)
        elif v < 0x98:
            b18 |= 1 << (v - 144)
        else:
            b19 |= 1 << (v - 152)
    if unexpressible:
        logging.getLogger(__name__).warning(
            "0x122C 请求丢弃 %d 个无法表达的字段（与排除字节冲突 0x88-0x8F）：%s",
            len(unexpressible),
            ",".join(unexpressible),
        )
    return bytes((b16, 0, b18, b19)), unexpressible


def get_active_fields(bitmap_bytes: bytes) -> list[tuple[FieldBit, str]]:
    """从响应位图解析活跃字段。

    Parameters
    ----------
    bitmap_bytes : bytes
        响应中的位图字节（通常 16 或 20 字节）。

    Returns
    -------
    list[tuple[FieldBit, str]]
        活跃字段及其格式说明符，按位序升序。
    """
    bitmap_int = int.from_bytes(bitmap_bytes, "little")
    active: list[tuple[FieldBit, str]] = []
    while bitmap_int:
        lowbit = bitmap_int & -bitmap_int
        bit_pos = lowbit.bit_length() - 1
        bitmap_int ^= lowbit
        field = FieldBit._value2member_map_.get(bit_pos)
        if field is not None and isinstance(field, FieldBit):
            active.append((field, field.fmt))
    return active


def resolve_response_fields(
    bitmap20: bytes,
    *,
    body_len: int,
    header_len: int,
    row_count: int,
    base_row_len: int = 68,
    field_len: int = 4,
    command: str = "0x122B",
) -> list[tuple[FieldBit, str]]:
    """选择响应位图解析口径（整 20 字节 vs 低 16 字节）。

    背景：行宽 = ``base_row_len + 4 × 字段数``，选错口径整表错位。决策规则：

    - 整 20 字节解析恰好精确消费整个 body（``header + rows == body_len``）
      → 用全口径（服务器回显了高位字段）。
    - 否则回落低 16 字节（历史行为，零回归风险）；若高字节含已知字段位，
      打警告（说明请求的高位字段被服务端忽略或线格式假设有误）。

    0x122C 调用方不应调本函数（其字节17 为排除标志回显，直接用低 16 字节
    并用 :func:`check_board_response_control` 做高字节守卫）。
    """
    import logging

    full = get_active_fields(bytes(bitmap20[:20]))
    low = get_active_fields(bytes(bitmap20[:16]))
    if len(full) != len(low):
        expected_full = header_len + row_count * (base_row_len + field_len * len(full))
        if expected_full == body_len:
            return full
        high_names = sorted({f.name for f, _ in full} - {f.name for f, _ in low})
        logging.getLogger(__name__).warning(
            "%s 响应高字节含已知字段位但长度不拟合（回落低16字节）：%s",
            command,
            ",".join(high_names),
        )
    return low


def check_board_response_control(bitmap20: bytes, *, command: str = "0x122C") -> None:
    """0x122C 响应高字节守卫：高字节出现已知字段位即打警告。

    该命令字节17 为排除标志回显，只能用低 16 字节解析；若服务端某天开始在
    高字节回显字段，本函数是第一道哨兵（行错位前先告警）。
    """
    import logging

    high = bytes(bitmap20[16:20])
    if not any(high):
        return
    full = {f.name for f, _ in get_active_fields(bytes(bitmap20[:20]))}
    low = {f.name for f, _ in get_active_fields(bytes(bitmap20[:16]))}
    extra = sorted(full - low)
    if extra:
        logging.getLogger(__name__).warning(
            "%s 响应高字节出现已知字段位（仍按低16字节解析，行可能错位）：%s",
            command,
            ",".join(extra),
        )
