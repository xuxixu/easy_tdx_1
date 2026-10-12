"""响应帧头解析与解压单元测试。"""

import struct
import zlib

import pytest

from easy_tdx.codec.frame import HEADER_SIZE, FrameHeader, decompress_body, parse_header
from easy_tdx.exceptions import TdxConnectionError

# 协议魔数，恒为 7654321（真实响应帧头里必须有它）
MAGIC = 7654321


def _make_header(zipsize: int, unzipsize: int, magic: int = MAGIC) -> bytes:
    return struct.pack("<IIIHH", magic, 0, 0, zipsize, unzipsize)


class TestParseHeader:
    def test_uncompressed(self):
        h = parse_header(_make_header(100, 100))
        assert h.zipsize == 100
        assert h.unzipsize == 100

    def test_compressed(self):
        h = parse_header(_make_header(50, 200))
        assert h.zipsize == 50
        assert h.unzipsize == 200

    def test_header_size(self):
        assert HEADER_SIZE == 16

    def test_magic_preserved(self):
        h = parse_header(_make_header(10, 10))
        assert h.magic == MAGIC

    def test_bad_magic_raises_connection_error(self):
        """magic 不符说明响应流已错位，必须抛 TdxConnectionError 触发重连，
        而不是产出垃圾数据（TdxDecodeError 不会被上层重连逻辑捕获）。"""
        with pytest.raises(TdxConnectionError):
            parse_header(_make_header(10, 10, magic=0))

    def test_frame_header_is_frozen_dataclass(self):
        h = FrameHeader(MAGIC, 0, 0, 1, 1)
        with pytest.raises(Exception):
            h.magic = 1  # type: ignore[misc]


class TestDecompressBody:
    def test_no_compression(self):
        h = parse_header(_make_header(5, 5))
        body = b"hello"
        assert decompress_body(h, body) == b"hello"

    def test_zlib_decompression(self):
        original = b"hello world" * 10
        compressed = zlib.compress(original)
        h = parse_header(_make_header(len(compressed), len(original)))
        result = decompress_body(h, compressed)
        assert result == original
