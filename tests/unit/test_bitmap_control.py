"""位图控制区拆分与响应口径选择测试（handoff 遗留①验证）。

覆盖：
- split_control_bytes：HANDICAP 高位落盘口/日内字节，0x88-0x8F 报不可表达；
  COMMON 无高位时与旧硬编码 (0, b1, 0, 1) 逐字节一致（零回归）。
- resolve_response_fields：整 20 字节精确拟合用全口径，否则回落低 16 字节。
- 0x122B HANDICAP 端到端：合成响应体解析出全部 20 个字段（回归行错位）。
- 0x122C：请求控制字节正确；响应高字节守卫对已知字段位告警、对纯控制静默。
"""

from __future__ import annotations

import logging
import struct

from easy_tdx.codec.bitmap import (
    FieldBit,
    PresetField,
    build_bitmap,
    check_board_response_control,
    get_active_fields,
    resolve_response_fields,
    split_control_bytes,
)
from easy_tdx.mac.commands.board_members_quotes import BoardMembersQuotesCmd
from easy_tdx.mac.commands.symbol_quotes import SymbolQuotesCmd
from easy_tdx.mac.enums import SortOrder, SortType


class TestSplitControlBytes:
    def test_common_has_no_high_bits(self) -> None:
        control, unexpressible = split_control_bytes(PresetField.COMMON)
        assert control == b"\x00\x00\x00\x00"
        assert unexpressible == []

    def test_handicap_splits_depth_and_intraday(self) -> None:
        control, unexpressible = split_control_bytes(PresetField.HANDICAP)
        # byte16 = 0x80-0x87（买三~卖五价 + 买三/四量）全置位；
        # HANDICAP 无 0x90+ 日内字段，byte18 为 0
        assert control[0] == 0xFF
        assert control[1] == 0x00  # 排除字节恒 0，由调用方填 FilterType
        assert control[2] == 0x00
        assert control[3] == 0x00
        # 0x88-0x8F 四个别名对（UP_COUNT/BID5_VOLUME 等）无法表达
        assert sorted(unexpressible) == sorted(
            ["UP_COUNT", "ASK3_VOLUME", "ASK4_VOLUME", "DOWN_COUNT"]
        )

    def test_intraday_field_maps_to_byte18(self) -> None:
        control, unexpressible = split_control_bytes(FieldBit.CHANGE_AT_1000)
        assert control == bytes((0x00, 0x00, 0x01, 0x00))
        assert unexpressible == []

    def test_single_high_field(self) -> None:
        control, unexpressible = split_control_bytes(FieldBit.BID3_PRICE)
        assert control == bytes((0x01, 0x00, 0x00, 0x00))
        assert unexpressible == []

    def test_conflict_field_warns(self, caplog) -> None:
        with caplog.at_level(logging.WARNING, logger="easy_tdx.codec.bitmap"):
            _, unexpressible = split_control_bytes(FieldBit.UP_COUNT)
        assert unexpressible == ["UP_COUNT"]
        assert "0x88-0x8F" in caplog.text


def _row_122b(market: int = 1, code: str = "600519", n_fields: int = 0) -> bytes:
    return struct.pack(
        "<H22s44s", market, code.encode("gbk"), "浦发银行".encode("gbk")
    ) + b"\x00" * (4 * n_fields)


class TestResolveResponseFields:
    def test_exact_full_fit_uses_full(self) -> None:
        ba = build_bitmap(PresetField.HANDICAP)
        # HANDICAP 去重后 20 个唯一位
        assert len(get_active_fields(bytes(ba))) == 20
        body = bytes(ba) + struct.pack("<IH", 1, 1) + _row_122b(n_fields=20)
        active = resolve_response_fields(bytes(ba), body_len=len(body), header_len=26, row_count=1)
        assert len(active) == 20

    def test_exact_low_fit_uses_low(self) -> None:
        ba = build_bitmap(PresetField.OHLC)
        body = bytes(ba) + struct.pack("<IH", 1, 1) + _row_122b(n_fields=4)
        active = resolve_response_fields(bytes(ba), body_len=len(body), header_len=26, row_count=1)
        assert {f.name for f, _ in active} == {"OPEN", "HIGH", "LOW", "CLOSE"}

    def test_mismatch_falls_back_with_warning(self, caplog) -> None:
        # 高位有已知字段但长度不拟合：回落低口径 + 警告（不静默错位）
        ba = bytearray(build_bitmap(PresetField.OHLC))
        ba[16] = 0x01  # 伪造 BID3_PRICE 位
        body = bytes(ba) + struct.pack("<IH", 1, 1) + _row_122b(n_fields=4)
        with caplog.at_level(logging.WARNING, logger="easy_tdx.codec.bitmap"):
            active = resolve_response_fields(
                bytes(ba), body_len=len(body), header_len=26, row_count=1
            )
        assert {f.name for f, _ in active} == {"OPEN", "HIGH", "LOW", "CLOSE"}
        assert "BID3_PRICE" in caplog.text


class TestSymbolQuotesHighBits:
    def test_handicap_response_parses_all_fields(self) -> None:
        """0x122B 请求 HANDICAP 时响应回显高位：必须解析 20 字段，行不错位。"""
        cmd = SymbolQuotesCmd([(1, "600519")], PresetField.HANDICAP)
        req_bitmap = cmd._bitmap
        assert len(req_bitmap) == 20
        body = req_bitmap + struct.pack("<IH", 1, 1) + _row_122b(n_fields=20)
        quotes = cmd.parse_response(body)
        assert len(quotes) == 1
        assert len(quotes[0].fields) == 20
        assert quotes[0].code == "600519"


class TestBoardMembersControl:
    def test_common_control_bytes_unchanged(self) -> None:
        """无高位字段时控制区与旧硬编码 (0,b1,0,1) 完全一致（零回归）。"""
        cmd = BoardMembersQuotesCmd(
            board_code=881001,
            sort_type=SortType.CHANGE_PCT,
            start=0,
            page_size=80,
            sort_order=SortOrder.DESC,
            fields=PresetField.COMMON,
        )
        req = cmd.build_request()
        assert req[-4:] == b"\x00\x00\x00\x01"

    def test_handicap_control_bytes_carry_high_bits(self) -> None:
        cmd = BoardMembersQuotesCmd(
            board_code=881001,
            sort_type=SortType.CHANGE_PCT,
            start=0,
            page_size=80,
            sort_order=SortOrder.DESC,
            fields=PresetField.HANDICAP,
        )
        req = cmd.build_request()
        # byte16=盘口 0xFF，byte17=排除 0，byte18=日内 0（HANDICAP 无 0x90+），byte19=控制 1
        assert req[-4:] == bytes((0xFF, 0x00, 0x00, 0x01))

    def test_board_response_guard_silent_on_pure_control(self, caplog) -> None:
        with caplog.at_level(logging.WARNING, logger="easy_tdx.codec.bitmap"):
            check_board_response_control(b"\x00" * 19 + b"\x01")
        assert caplog.text == ""

    def test_board_response_guard_warns_on_field_bits(self, caplog) -> None:
        with caplog.at_level(logging.WARNING, logger="easy_tdx.codec.bitmap"):
            check_board_response_control(b"\x00" * 16 + b"\x01\x00\x00\x00")
        assert "BID3_PRICE" in caplog.text
