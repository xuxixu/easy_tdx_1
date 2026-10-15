"""同步客户端锁纪律测试（handoff 遗留④验证）。

- 四个同步客户端的 _execute_lock 必须是 threading.RLock（_reconnect 内部
  自加锁 + _execute 嵌套调用，换成普通 Lock 即死锁）。
- _reconnect 无需外层持锁即可调用；嵌套调用不死锁。
- failover 测速在锁外：用“测速期间同伴已切换”的探针验证复用分支。
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from easy_tdx.client import TdxClient
from easy_tdx.commands.security_count import GetSecurityCountCmd
from easy_tdx.ex.client import ExTdxClient
from easy_tdx.ex.mac_client import MacExClient
from easy_tdx.exceptions import TdxConnectionError
from easy_tdx.mac.client import MacClient
from easy_tdx.models.enums import Market


def _make(cls_name: str):
    """按客户端构造实例（连接类全部 mock，不触网）。"""
    if cls_name == "tdx":
        with patch("easy_tdx.client.TdxConnection"):
            return TdxClient("1.1.1.1", 7709, 1.0, heartbeat_interval=0)
    if cls_name == "mac":
        with patch("easy_tdx.mac.client.TdxConnection"):
            return MacClient("1.1.1.1", 7709, 1.0, heartbeat_interval=0)
    if cls_name == "ex":
        with patch("easy_tdx.ex.client.ExTdxConnection"):
            return ExTdxClient("1.1.1.1")
    with patch("easy_tdx.ex.mac_client.ExTdxConnection"):
        return MacExClient("1.1.1.1")


class TestSyncLockDiscipline:
    @pytest.mark.parametrize("cls_name", ["tdx", "mac", "ex", "macex"])
    def test_execute_lock_is_rlock(self, cls_name: str) -> None:
        """四个同步客户端的锁必须是可重入 RLock（_reconnect 嵌套依赖）。"""
        client = _make(cls_name)
        assert isinstance(client._execute_lock, type(threading.RLock())), cls_name

    def test_reconnect_without_outer_lock(self) -> None:
        """_reconnect 可直接调用（内部自加锁），不依赖调用方持锁。"""
        with patch("easy_tdx.client.TdxConnection") as mock_conn_cls:
            mock_conn = MagicMock()
            mock_conn_cls.return_value = mock_conn
            client = TdxClient("1.1.1.1", 7709, 1.0, auto_reconnect=True, heartbeat_interval=0)
            client._reconnect("2.2.2.2")  # 未持锁调用，不应死锁/抛错
            assert client._host == "2.2.2.2"
            mock_conn.connect.assert_called()

    def test_nested_reconnect_no_deadlock(self) -> None:
        """锁内嵌套 _reconnect 不死锁（RLock 可重入的直接证明）。"""
        with patch("easy_tdx.client.TdxConnection") as mock_conn_cls:
            mock_conn_cls.return_value = MagicMock()
            client = TdxClient("1.1.1.1", 7709, 1.0, auto_reconnect=True, heartbeat_interval=0)
            with client._execute_lock:
                client._reconnect()  # 普通 Lock 到此即死锁，测试会超时失败

    def test_failover_reuses_peer_switched_host(self) -> None:
        """测速期间同伴已切换：复用新连接重试，不再调 _reconnect(new_host)。"""
        with patch("easy_tdx.client.TdxConnection") as mock_conn_cls:
            mock_conn = MagicMock()
            # 首次 + 4 次同主机重试全部失败，之后成功 1 次
            mock_conn.execute.side_effect = [TdxConnectionError("down")] * 5 + [777]
            mock_conn_cls.return_value = mock_conn
            client = TdxClient("bad-host", 7709, 1.0, auto_reconnect=True, heartbeat_interval=0)

            def _fake_ping(*args):
                # 模拟并发同伴在测速期间完成了切换
                client._host = "peer-host"
                return "other-host"

            with (
                patch("easy_tdx.client.time.sleep"),
                patch("easy_tdx.client.select_best_host_sync", side_effect=_fake_ping),
            ):
                with patch.object(client, "_reconnect", wraps=client._reconnect) as mock_reconnect:
                    result = client._execute(GetSecurityCountCmd(Market.SH))
            assert result == 777
            # 4 次同主机重试各调 1 次 _reconnect；failover 阶段因 host 已变，
            # 只复用连接重试，不得再调 _reconnect("other-host")
            assert mock_reconnect.call_count == 4
