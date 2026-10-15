"""美股交易时段：盘前 / 盘中 / 盘后 / 夜盘四态判断 + 分钟线盘中过滤。

为什么需要这个模块
------------------
美股一天 24 小时里只有 6.5 小时是连续竞价（盘中），其余时间分属盘前、
盘后、夜盘三个不同流动性 regime。前端顶栏要显示当前处在哪个时段，
回测分钟线要剔除盘前盘后（流动性差、跳空多，会污染信号）。

时段划分（美东时间）
-------------------
夏令时（EDT，UTC-4）/ 冬令时（EST，UTC-5）差 1 小时，下表以夏令为准，
冬令整体 +1 小时：

================  ============  ============
时段               美东           北京时间
================  ============  ============
盘前               04:00–09:30   16:00–21:30
盘中               09:30–16:00   21:30–04:00
盘后               16:00–20:00   04:00–08:00
夜盘               20:00–04:00   08:00–16:00
================  ============  ============

周末全天归为夜盘（无交易）。节假日不判断——误判为盘中只会多一次取数，
无副作用（与 A 股 session.py 同口径）。

夏令时规则：3 月第 2 个周日 02:00 起，至 11 月第 1 个周日 02:00 止。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Final, Literal

USSession = Literal["pre", "open", "after", "night"]

#: 四态中文名（前端顶栏直接展示）。
SESSION_LABELS: Final[dict[str, str]] = {
    "pre": "盘前",
    "open": "盘中",
    "after": "盘后",
    "night": "夜盘",
}

_ET = timezone(timedelta(hours=-5))  # 美东标准时基线，夏令 +1
_BEIJING = timezone(timedelta(hours=8))


def _dst_start(year: int) -> date:
    """3 月第 2 个周日（夏令开始日）。"""
    d = date(year, 3, 1)
    count = 0
    while count < 2:
        if d.weekday() == 6:
            count += 1
        if count < 2:
            d += timedelta(days=1)
    return d


def _dst_end(year: int) -> date:
    """11 月第 1 个周日（夏令结束日）。"""
    d = date(year, 11, 1)
    while d.weekday() != 6:
        d += timedelta(days=1)
    return d


def _dst_transitions_utc(year: int) -> tuple[datetime, datetime]:
    """当年夏令切换的 UTC 精确时刻（02:00 美东墙钟）。

    开始：3月第2个周日 02:00 EST（UTC-5）= 07:00 UTC；
    结束：11月第1个周日 02:00 EDT（UTC-4）= 06:00 UTC。
    日级判定在切换日会错1h，此处精确到分钟。
    """
    start_day = _dst_start(year)
    end_day = _dst_end(year)
    start_utc = datetime(start_day.year, start_day.month, start_day.day, 7, 0, tzinfo=timezone.utc)
    end_utc = datetime(end_day.year, end_day.month, end_day.day, 6, 0, tzinfo=timezone.utc)
    return start_utc, end_utc


def _is_dst_at_utc(utc: datetime) -> bool:
    """按 UTC 瞬时判定夏令（精确到切换时刻，而非整日）。"""
    utc = utc.astimezone(timezone.utc)
    start_utc, end_utc = _dst_transitions_utc(utc.year)
    return start_utc <= utc < end_utc


def is_dst(day: date | None = None) -> bool:
    """判断某天是否为夏令时（默认今天，美东口径）。

    兼容口径：取该日中午 12:00 美东（UTC-5 基线 17:00 UTC）判定，避免切换日
    00:00-02:00 的边界歧义；精确到分钟的判定请用 ``_is_dst_at_utc``。
    """
    day = day or datetime.now(_ET).date()
    noon_utc = datetime(day.year, day.month, day.day, 17, 0, tzinfo=timezone.utc)
    return _is_dst_at_utc(noon_utc)


def us_session(now: datetime | None = None) -> USSession:
    """判断当前美股四态（美东时间口径）。

    夏令美东 = UTC-4，冬令 = UTC-5。这里先按 UTC-5 基线定日期、
    判定夏令，再换算真实美东钟面比较——不能直接 astimezone 到固定
    时区（夏令会差 1 小时）。

    Args:
        now: 任意时区的时间，None 表示现在。

    Returns:
        ``pre`` / ``open`` / ``after`` / ``night``。
    """
    utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    summer = _is_dst_at_utc(utc)
    et = utc - timedelta(hours=4 if summer else 5)
    if et.weekday() >= 5:
        return "night"  # 周末全天夜盘（按美东星期判定，避免 UTC 日期错位）
    mins = et.hour * 60 + et.minute
    if 4 * 60 <= mins < 9 * 60 + 30:
        return "pre"
    if 9 * 60 + 30 <= mins < 16 * 60:
        return "open"
    if 16 * 60 <= mins < 20 * 60:
        return "after"
    return "night"


def us_session_info(now: datetime | None = None) -> dict[str, object]:
    """四态详情（供前端顶栏展示）。"""
    utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    session = us_session(now)
    dst = _is_dst_at_utc(utc)
    return {
        "session": session,
        "label": SESSION_LABELS[session],
        "is_dst": dst,
        # 展示用：北京时间口径的盘中窗口
        "open_window_bj": "21:30–04:00" if dst else "22:30–05:00",
    }


def is_us_trading_minutes(dt: datetime, *, dst: bool | None = None) -> bool:
    """判断一根分钟 bar 是否落在盘中（美东 09:30–16:00）。

    Args:
        dt: bar 时间（naive 视为北京时间，aware 按其时区换算）。
        dst: 强制夏令/冬令，None 按该日期自动判断。
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_BEIJING)
    utc = dt.astimezone(timezone.utc)
    summer = _is_dst_at_utc(utc) if dst is None else dst
    # 美东时钟 = UTC - 4h（夏令）/ -5h（冬令）
    et = utc - timedelta(hours=4 if summer else 5)
    if et.weekday() >= 5:
        return False
    return (et.hour, et.minute) >= (9, 30) and (et.hour, et.minute) < (16, 0)


def filter_us_regular_hours(df: object) -> object:
    """过滤 DataFrame 只留盘中分钟 bar（日线及以上周期原样返回）。

    要求 df 有 ``datetime`` 列。盘前盘后 bar 的流动性与盘中完全不同，
    混入分钟线回测会污染信号（缺口/零成交段拉偏指标）。
    """
    import pandas as pd

    assert isinstance(df, pd.DataFrame)
    if df.empty or "datetime" not in df.columns:
        return df
    ts = pd.to_datetime(df["datetime"], errors="coerce")
    # 日线及以上（时间为 00:00:00 整点）不过滤
    if ((ts.dt.hour == 0) & (ts.dt.minute == 0)).all():
        return df
    mask = [is_us_trading_minutes(t) if not pd.isna(t) else False for t in ts]
    return df.loc[mask].reset_index(drop=True)


__all__ = [
    "USSession",
    "SESSION_LABELS",
    "is_dst",
    "us_session",
    "us_session_info",
    "is_us_trading_minutes",
    "filter_us_regular_hours",
]
