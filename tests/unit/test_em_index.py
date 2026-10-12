"""东财现货三备源（em_index）单测：mock akshare 模块，不出网。

覆盖：开关（未安装静默关闭 / 环境变量禁用）、港股同名代码命中、
美股 DJI→DJIA 映射、IXIC 缺失时宁可抛异常不可错给、全表 TTL 缓存
（多 code 一轮只调一次底层接口）、报价链三级回落（新浪→腾讯→东财）。
"""

from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from easy_tdx.sources import em_index


def _hk_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "代码": ["HSI", "HSCEI", "HSTECH"],
            "名称": ["恒生指数", "恒生中国企业指数", "恒生科技指数"],
            "最新价": [24255.889, 8151.24, 4174.21],
            "涨跌额": [44.539, 3.369, -23.63],
            "涨跌幅": [0.18, 0.04, -0.56],
            "今开": [24434.93, 8229.32, 4241.07],
            "最高": [24455.95, 8235.69, 4241.07],
            "最低": [24234.19, 8143.11, 4172.06],
            "昨收": [24211.35, 8147.871, 4197.84],
            "成交量": [1.0, 2.0, 3.0],
            "成交额": [5.5e9, 7.9e8, 4.6e8],
        }
    )


def _global_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "代码": ["DJIA", "SPX", "NDX"],
            "名称": ["道琼斯", "标普500", "纳斯达克"],
            "最新价": [51654.95, 7811.54, 30883.15],
            "涨跌额": [423.31, 46.18, 157.34],
            "涨跌幅": [0.83, 0.59, 0.51],
            "开盘价": [51258.95, 7786.36, 30900.06],
            "最高价": [51765.11, 7820.57, 30946.74],
            "最低价": [51258.95, 7779.34, 30770.06],
            "昨收价": [51231.64, 7765.36, 30725.81],
        }
    )


def _install_fake_akshare(monkeypatch) -> dict[str, int]:
    """装假 akshare，记录各现货接口被调用次数。"""
    calls = {"hk": 0, "global": 0}

    def stock_hk_index_spot_em() -> pd.DataFrame:
        calls["hk"] += 1
        return _hk_table().copy()

    def index_global_spot_em() -> pd.DataFrame:
        calls["global"] += 1
        return _global_table().copy()

    mod = types.ModuleType("akshare")
    mod.stock_hk_index_spot_em = stock_hk_index_spot_em  # type: ignore[attr-defined]
    mod.index_global_spot_em = index_global_spot_em  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "akshare", mod)
    em_index.clear_cache()
    return calls


@pytest.fixture(autouse=True)
def _clear_cache():
    em_index.clear_cache()
    yield
    em_index.clear_cache()


def test_is_enabled_true_when_installed(monkeypatch):
    _install_fake_akshare(monkeypatch)
    assert em_index.is_enabled() is True


def test_is_enabled_false_when_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "akshare", None)
    assert em_index.is_enabled() is False


def test_disabled_by_env(monkeypatch):
    _install_fake_akshare(monkeypatch)
    monkeypatch.setenv(em_index._DISABLE_ENV, "0")
    assert em_index.is_enabled() is False


def test_hk_quote_by_same_code(monkeypatch):
    _install_fake_akshare(monkeypatch)
    q = em_index.fetch_quote("HK", "HSI")
    assert q["price"] == pytest.approx(24255.889)
    assert q["pre_close"] == pytest.approx(24211.35)
    assert q["open"] == pytest.approx(24434.93)
    assert q["code"] == "HSI" and q["market"] == "HK"


def test_us_dji_maps_to_djia(monkeypatch):
    _install_fake_akshare(monkeypatch)
    q = em_index.fetch_quote("US", "DJI")
    assert q["price"] == pytest.approx(51654.95)
    assert q["pre_close"] == pytest.approx(51231.64)


def test_us_ixic_missing_raises_not_wrong(monkeypatch):
    """全球表无 IXIC/COMP 时抛异常——宁可缺，不可错给 NDX 的数。"""
    _install_fake_akshare(monkeypatch)
    with pytest.raises(RuntimeError, match="无此指数"):
        em_index.fetch_quote("US", "IXIC")


def test_bulk_cache_single_fetch_per_round(monkeypatch):
    """同表 TTL 内多 code 只调一次底层接口（SSE 一轮 3 个指数）。"""
    calls = _install_fake_akshare(monkeypatch)
    df = em_index.fetch_quotes("HK", ["HSI", "HSCEI", "HSTECH"])
    assert len(df) == 3
    assert calls["hk"] == 1


def test_quote_chain_falls_to_em(monkeypatch):
    """新浪腾讯双失败 → 东财三备接住；三源全挂 → 抛异常。"""
    from easy_tdx.sources import qq_index as Q

    _install_fake_akshare(monkeypatch)
    monkeypatch.setattr(Q, "_sina_quote", lambda key: (_ for _ in ()).throw(OSError("sina down")))
    monkeypatch.setattr(Q, "_qq_quote", lambda key: (_ for _ in ()).throw(OSError("qq down")))
    q = Q.fetch_quote("HK", "HSI")
    assert q["price"] == pytest.approx(24255.889)

    monkeypatch.setitem(sys.modules, "akshare", None)
    em_index.clear_cache()
    with pytest.raises(RuntimeError):
        Q.fetch_quote("HK", "HSI")
