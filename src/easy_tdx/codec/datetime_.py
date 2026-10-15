"""日期时间解码（通达信 TCP 两种格式）。

分钟级（category < 4 或 == 7/8）：4 字节 = 2 字节压缩日期 + 2 字节分钟数
  zipday: year=(>>11)+2004, month=(% 2048)//100, day=(% 2048)%100
  tminutes: hour=//60, minute=%60

日线及以上（其余 category）：4 字节 YYYYMMDD 整数

错误契约（与传输层/客户端联动，勿单独改动一处）：
  非法日期/时间抛 ``TdxDecodeError``（非法即脏包，不静默产出 1970 年之类
  的"合法"脏数据）。该异常在 ``transport/sync.py`` 与 ``transport/async_.py``
  的 ``execute()`` 中发生在 ``parse_response`` 阶段——IO try 块之外，因此
  不会作废 socket（不断线），也不会触发客户端重连/故障转移（只捕
  ``TdxConnectionError``）；K 线类命令（``security_bars`` 等，变长 varint
  无法重同步）按条捕获后返回已解析前缀（截断容错），调用方拿到短页而非整页
  500。中间坏条会截断该页剩余部分（varint 失步后无法定位下一条起点，只能
  break 保前缀正确），属已知取舍。
"""

from .._binary import unpack_from
from ..exceptions import TdxDecodeError


def _check_ymd(year: int, month: int, day: int, *, ctx: str) -> None:
    if not (1990 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        raise TdxDecodeError(f"非法日期 {year:04d}-{month:02d}-{day:02d}（{ctx}）")


def _check_hm(hour: int, minute: int, *, ctx: str) -> None:
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise TdxDecodeError(f"非法时间 {hour:02d}:{minute:02d}（{ctx}）")


def get_datetime_minute(data: bytes | bytearray, pos: int) -> tuple[int, int, int, int, int, int]:
    """解析分钟级时间戳（4 字节）。

    Returns:
        (year, month, day, hour, minute, new_pos)
    """
    zipday, tminutes = unpack_from("<HH", data, pos, "minute datetime")
    year = (zipday >> 11) + 2004
    month = (zipday % 2048) // 100
    day = (zipday % 2048) % 100
    hour = tminutes // 60
    minute = tminutes % 60
    _check_ymd(year, month, day, ctx="minute datetime")
    _check_hm(hour, minute, ctx="minute datetime")
    return year, month, day, hour, minute, pos + 4


def get_datetime_day(data: bytes | bytearray, pos: int) -> tuple[int, int, int, int]:
    """解析日期（4 字节 YYYYMMDD）。

    Returns:
        (year, month, day, new_pos)
    """
    (zipday,) = unpack_from("<I", data, pos, "day datetime")
    year = zipday // 10000
    month = (zipday % 10000) // 100
    day = zipday % 100
    _check_ymd(year, month, day, ctx="day datetime")
    return year, month, day, pos + 4


def get_datetime(
    category: int, data: bytes | bytearray, pos: int
) -> tuple[int, int, int, int, int, int]:
    """根据 KlineCategory 选择解析格式。

    Returns:
        (year, month, day, hour, minute, new_pos)
        日线及以上时 hour=15, minute=0（收盘时间，与 pytdx 保持一致）
    """
    if category < 4 or category in (7, 8):
        return get_datetime_minute(data, pos)
    else:
        year, month, day, new_pos = get_datetime_day(data, pos)
        return year, month, day, 15, 0, new_pos


def get_time(data: bytes | bytearray, pos: int) -> tuple[int, int, int]:
    """解析 2 字节时间（分钟数）。

    Returns:
        (hour, minute, new_pos)
    """
    (tminutes,) = unpack_from("<H", data, pos, "trade time")
    hour, minute = tminutes // 60, tminutes % 60
    _check_hm(hour, minute, ctx="trade time")
    return hour, minute, pos + 2
