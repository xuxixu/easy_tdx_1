"""港美股个股快照源（us_hk_snapshot）单测：mock urllib，不出网。

回归载体均为 2026-10-14 实测报文（新浪 / 东财 push2），断言含自洽检查。
"""

from __future__ import annotations

import json
import urllib.request


def _fake_urlopen_factory(payload: bytes):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return payload

    def _fake(req, timeout=None):
        return _Resp()

    return _fake


def test_sina_us_quote(monkeypatch):
    from easy_tdx.sources import us_hk_snapshot as M

    # gb_aapl 36 字段实测报文（含扩展时段 [21]=342.74/[22]=0.43/[23]=1.47）
    body = (
        'var hq_str_gb_aapl="苹果,341.2700,0.09,2026-10-14 19:10:00,'
        "0.3000,344.6650,348.1499,340.7400,345.3400,242.8900,38983814,"
        "35666905,4980555808941,8.30,41.120000,0.00,0.00,0.00,0.00,"
        "14594180001,63,342.7400,0.43,1.47,Oct 14 07:10AM EDT,"
        "Oct 13 04:00PM EDT,340.9700,119689,1,2026,13395654408.7413,"
        '343.7000,341.2687,41017789.3555,342.5927,341.2700";'
    ).encode("gbk")
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_factory(body))
    q = M.fetch_quote("US", "AAPL")
    assert q["source"] == "sina"
    assert q["price"] == 341.27
    assert q["open"] == 344.665
    # 昨收 = 现价 - 涨跌额
    assert abs(q["pre_close"] - 340.97) < 1e-6
    assert q["high"] >= q["price"] >= q["low"]
    # 扩展时段：342.74-341.27=1.47（额），1.47/341.27=0.43%（幅）
    assert q["ext_price"] == 342.74
    assert q["ext_change"] == 1.47
    assert q["ext_pct"] == 0.43
    # 扩展量额：[27]=119689（量）、[33]=41017789.3555（额）
    assert q["ext_vol"] == 119689.0
    assert q["ext_amount"] == 41017789.3555


def test_sina_us_short_payload_keeps_row(monkeypatch):
    from easy_tdx.sources import us_hk_snapshot as M

    # 短报文（无扩展字段）：常规报价照常返回，ext_* 为 None
    body = (
        'var hq_str_gb_aapl="苹果,341.2700,0.09,2026-10-14 19:02:51,'
        '0.3000,344.6650,348.1499,340.7400,345.3400";'
    ).encode("gbk")
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_factory(body))
    q = M.fetch_quote("US", "AAPL")
    assert q["price"] == 341.27
    assert q["ext_price"] is None
    assert q["ext_change"] is None
    assert q["ext_pct"] is None
    assert q["ext_vol"] is None
    assert q["ext_amount"] is None


def test_sina_hk_quote(monkeypatch):
    from easy_tdx.sources import us_hk_snapshot as M

    body = (
        'var hq_str_rt_hk00700="TENCENT,腾讯控股,421.400,425.200,430.400,'
        '416.400,423.400,-1.800,-0.423,423.400,423.600";'
    ).encode("gbk")
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_factory(body))
    q = M.fetch_quote("HK", "00700")
    assert q["source"] == "sina"
    assert q["price"] == 423.4
    assert q["pre_close"] == 425.2
    assert q["open"] == 421.4


def test_em_fallback_when_sina_fails(monkeypatch):
    from easy_tdx.sources import us_hk_snapshot as M

    # 新浪失败 → 回落东财 105.AAPL 实测报文
    calls = {"n": 0}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            if calls["n"] == 0:
                return "var hq_str_gb_aapl=;".encode("gbk")
            return json.dumps(
                {
                    "rc": 0,
                    "data": {
                        "f43": 341270,
                        "f44": 348150,
                        "f45": 340740,
                        "f46": 344665,
                        "f47": 38983839,
                        "f48": 13395660544.0,
                        "f57": "AAPL",
                        "f58": "苹果",
                    },
                }
            ).encode()

    def _fake(req, timeout=None):
        calls["n"] += 1
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", _fake)
    q = M.fetch_quote("US", "AAPL")
    assert q["source"] == "em"
    assert q["price"] == 341.27
    assert q["high"] == 348.15
    assert q["low"] == 340.74
    # 东财行无扩展字段，ext_* 置 None（与新浪行对齐列，混批不偏列）
    assert q["ext_price"] is None
    assert q["ext_vol"] is None


def test_code_mapping():
    from easy_tdx.sources import us_hk_snapshot as M

    # 美股小写归一，东财按 105/106/107 依次试
    assert M._sina_symbol("US", "aapl") == "gb_aapl"
    assert M._em_secid("US", "AAPL") == ["105.AAPL", "106.AAPL", "107.AAPL"]
    # 港股补零到 5 位（700.HK ↔ 00700 双向实测）
    assert M._sina_symbol("HK", "700") == "rt_hk00700"
    assert M._em_secid("HK", "00700") == ["116.00700"]
    # 非港美股无映射（调用方转 RuntimeError，不静默错取）
    assert M._sina_symbol("SH", "600000") == ""
    assert M._em_secid("SH", "600000") == []


def test_disabled_raises(monkeypatch):
    from easy_tdx.sources import us_hk_snapshot as M

    monkeypatch.setenv("EASY_TDX_US_HK_SNAPSHOT", "0")
    assert not M.is_enabled()
    try:
        M.fetch_quote("US", "AAPL")
    except RuntimeError:
        pass
    else:
        raise AssertionError("关闭后应抛 RuntimeError")


def test_batch_skips_failed(monkeypatch):
    from easy_tdx.sources import us_hk_snapshot as M

    monkeypatch.setattr(M, "_sina_quote", lambda market, code: None)
    monkeypatch.setattr(M, "_em_quote", lambda market, code: None)
    df = M.fetch_quotes([("AAPL", "US"), ("00700", "HK")])
    assert df.empty
