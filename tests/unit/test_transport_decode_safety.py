"""解码错误不毒化连接测试（handoff 遗留③验证）。

契约（见 codec/datetime_.py 模块注释）：
- 非法日期/时间抛 TdxDecodeError（不静默产出脏数据）；
- 该异常发生在 parse_response 阶段（IO try 块之外），传输层不断开 socket；
- K 线类 varint 解析按条捕获返回前缀，中间坏条截断本页（无法重同步）。
"""

from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch

import pytest

from easy_tdx.codec.datetime_ import get_datetime_day, get_datetime_minute
from easy_tdx.commands.base import BaseCommand
from easy_tdx.commands.security_bars import GetSecurityBarsCmd
from easy_tdx.exceptions import TdxDecodeError
from easy_tdx.models.enums import KlineCategory, Market
from easy_tdx.transport.sync import HEADER_SIZE, TdxConnection


class TestDatetimeValidation:
    def test_bad_month_raises_decode_error(self) -> None:
        with pytest.raises(TdxDecodeError):
            get_datetime_day(struct.pack("<I", 20240001), 0)

    def test_bad_minute_hour_raises_decode_error(self) -> None:
        # zipday 合法，分钟数 25:00 越界
        body = struct.pack("<HH", (20 << 11) + 1 * 100 + 2, 25 * 60)
        with pytest.raises(TdxDecodeError):
            get_datetime_minute(body, 0)


def _day_record(yyyymmdd: int) -> bytes:
    return struct.pack("<I", yyyymmdd) + b"\x00" * 4 + b"\x00\x00\x00\x00" * 2


class TestMiddleCorruptionTruncates:
    def test_corrupt_middle_bar_returns_prefix(self, caplog) -> None:
        """中间第 2 条日期非法 → 返回第 1 条（break 保前缀），不抛。"""
        import logging

        body = (
            struct.pack("<H", 3)
            + _day_record(20240101)
            + _day_record(20249999)  # 非法日期
            + _day_record(20240103)
        )
        cmd = GetSecurityBarsCmd(Market.SZ, "000001", KlineCategory.DAY, 0, 800)
        with caplog.at_level(logging.WARNING):
            bars = cmd.parse_response(body)
        assert len(bars) == 1
        assert (bars[0].year, bars[0].month, bars[0].day) == (2024, 1, 1)


class _RaisingCmd(BaseCommand[None]):
    def build_request(self) -> bytes:
        return b"\x00"

    def parse_response(self, body: bytes) -> None:
        raise TdxDecodeError("模拟坏日期")


class TestDecodeErrorKeepsSocket:
    def test_sync_socket_survives_decode_error(self) -> None:
        """parse_response 的解码异常向上传播，但 socket 不被作废（可复用）。"""
        conn = TdxConnection("1.2.3.4", 7709, 1.0)
        sock = MagicMock()
        conn._sock = sock
        header = MagicMock()
        header.zipsize = 4
        with (
            patch.object(conn, "_recv_exact", side_effect=[b"H" * HEADER_SIZE, b"body"]),
            patch("easy_tdx.transport.sync.parse_header", return_value=header),
            patch("easy_tdx.transport.sync.decompress_body", return_value=b"body"),
        ):
            with pytest.raises(TdxDecodeError):
                conn.execute(_RaisingCmd())
        assert conn._sock is sock  # 未被置空
        sock.close.assert_not_called()  # 未被关闭

    def test_sync_socket_survives_decode_error_async(self) -> None:
        """异步传输同契约（parse 在 IO try 之外）。"""
        import asyncio
        from unittest.mock import AsyncMock

        from easy_tdx.transport.async_ import AsyncTdxConnection

        async def _run() -> None:
            conn = AsyncTdxConnection("1.2.3.4", 7709, 1.0)
            writer = MagicMock()
            writer.drain = AsyncMock()
            conn._writer = writer
            conn._reader = MagicMock()
            header = MagicMock()
            header.zipsize = 4
            with (
                patch.object(
                    AsyncTdxConnection,
                    "_recv_exact",
                    new=AsyncMock(side_effect=[b"H" * HEADER_SIZE, b"body"]),
                ),
                patch("easy_tdx.transport.async_.parse_header", return_value=header),
                patch("easy_tdx.transport.async_.decompress_body", return_value=b"body"),
            ):
                with pytest.raises(TdxDecodeError):
                    await conn.execute(_RaisingCmd())
            assert conn._writer is writer

        asyncio.run(_run())
