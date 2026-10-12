"""真指数 HTTP 源（qq_index）单测：mock urllib，不出网。"""

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


def test_sina_quote_hk(monkeypatch):
    from easy_tdx.sources import qq_index as Q

    # 实盘格式：今开,昨收,最高,最低,今收（今收-昨收==涨跌额）。
    # 之前把 parts[2]/parts[3] 当昨收/今开写反，导致涨跌幅全错。
    body = (
        'var hq_str_rt_hkHSCEI="HSCEI,恒生中国企业指数,8229.320,8147.871,'
        '8235.690,8143.110,8145.609,-2.262,-0.030,0,0,23458646.422,781786623";'
    ).encode("gbk")
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_factory(body))
    q = Q.fetch_quote("HK", "HSCEI")
    assert q["code"] == "HSCEI"
    assert q["price"] == 8145.609
    assert q["pre_close"] == 8147.871
    assert q["open"] == 8229.32
    # 自洽：现价-昨收 ≈ 涨跌额（-2.262）
    assert abs((q["price"] - q["pre_close"]) - (-2.262)) < 0.01


def test_sina_quote_us(monkeypatch):
    from easy_tdx.sources import qq_index as Q

    body = (
        'var hq_str_gb_inx="标普500指数,7811.5400,0.59,2026-10-10,46.1800,'
        '7786.3599,7820.5698,7779.3398";'
    ).encode("gbk")
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_factory(body))
    q = Q.fetch_quote("US", "SPX")
    assert q["price"] == 7811.54
    # 昨收 = 今收 - 涨跌额（7811.54-46.18=7765.36），parts[5] 是今开不是昨收
    assert abs(q["pre_close"] - 7765.36) < 1e-6
    assert q["open"] == 7786.3599


def test_qq_fallback_on_sina_failure(monkeypatch):
    """新浪失败自动切腾讯。"""
    from easy_tdx.sources import qq_index as Q

    calls = []

    def fake(req, timeout=None):
        url = req.full_url
        calls.append(url)
        if "sinajs" in url:
            raise OSError("sina down")

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                # 只保留解析需要的字段（名称/今收/昨收/今开/最高/最低在前 35 个）
                return (
                    'v_r_hkHSI="100~恒生指数~HSI~24211.350~23785.790~23941.260'
                    "~20919924.7143~0~0~24211.350~0~0~0~0~0~0~0~0~0~24211.350"
                    "~0~0~0~0~0~0~0~0~0~0.0~2026/10/09 18:31:07~425.560~1.79"
                    '~24224.050~23941.260~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0";'
                ).encode("gbk")

        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    q = Q.fetch_quote("HK", "HSI")
    assert q["price"] == 24211.35
    assert any("sinajs" in u for u in calls) and any("gtimg" in u for u in calls)


def test_fetch_bars_day(monkeypatch):
    from easy_tdx.sources import qq_index as Q

    payload = json.dumps(
        {
            "code": 0,
            "data": {
                "hkHSI": {
                    "day": [
                        ["2026-10-08", "24031.66", "23785.79", "24146.01", "23737.14", "20726"],
                        ["2026-10-09", "23941.26", "24211.35", "24224.05", "23941.26", "209199247"],
                    ]
                }
            },
        }
    ).encode()
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_factory(payload))
    df = Q.fetch_bars("HK", "HSI", "DAY", 0, 5)
    assert len(df) == 2
    assert list(df.columns[:6]) == ["date", "open", "close", "high", "low", "vol"]
    assert float(df.iloc[-1]["close"]) == 24211.35


def test_is_http_index():
    from easy_tdx.sources.qq_index import is_http_index

    assert is_http_index("HK", "HSCEI") is True
    assert is_http_index("US", "SPX") is True
    assert is_http_index("HK", "HSI") is True
    assert is_http_index("US", "NDX") is True
    assert is_http_index("US", "AAPL") is False
    assert is_http_index("HK", "00700") is False
