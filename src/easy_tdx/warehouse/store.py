"""K 线本地数据仓库（DuckDB，v1.26 新增）。

此前 easy-tdx 的缓存是碎片化的（股票列表缓存 / best_host / 进程内 XDXR
字典 / 扫描 JSON），没有统一的 K 线磁盘层——下游项目（indicator-lab 的
DuckDB 仓库、backtest-system 的 cache/ 目录）都在自建数据层。本模块把
「拉过的行情」沉淀为本地列存仓库：

- **单文件 DuckDB**（默认 ``~/.easy_tdx/warehouse.duckdb``，随
  ``EASY_TDX_CONFIG_DIR`` 走）：零服务、列存、SQL 友好、压缩率高
  （万只标的十年日线约几百 MB）；
- **增量同步**：每标的只补最后若干根（首同步全量拉取），同日 bar 用新值
  覆盖（收盘修正），历史数据不动；
- **provisional / completed 状态机**（借鉴 indicator-lab）：15:05 前落盘
  的当日 bar 标记 ``provisional``（未收盘的临时值），查询/回测**默认忽略**，
  只在显式 ``include_provisional=True`` 时可见；次日增量同步自动把过期
  临时行转正/覆盖。

DuckDB 为可选依赖（``pip install easy-tdx[warehouse]``），惰性导入——
未安装时本模块给出明确报错，不影响核心三通道。
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any

import pandas as pd

from easy_tdx.realtime.session import SHANGHAI_TZ

logger = logging.getLogger(__name__)

__all__ = ["KlineWarehouse", "default_warehouse_path", "MARKET_TO_TDX"]

# 未收盘 cutoff：15:05（A股 15:00 收盘 + 5 分钟数据落定余量）
_MARKET_CLOSE_CUTOFF = dt_time(15, 5)

_VALID_ADJUST = ("NONE", "QFQ", "HFQ")


def _shanghai_now() -> datetime:
    """沪市墙钟（naive）：provisional 判定与主机时区无关。

    非 UTC+8 主机（海外服务器）的系统本地时间会把「当日 / 15:05 前」判错
    （UTC 主机上沪市 18:00 收盘后本地才 10:00，当日 bar 被误标 provisional
    而被默认查询隐藏），故统一按 A 股时区取墙钟。中国无夏令时，固定 UTC+8。
    """
    return datetime.now(SHANGHAI_TZ).replace(tzinfo=None)


MARKET_TO_TDX: dict[str, int] = {"SZ": 0, "SH": 1, "BJ": 2}
_TDX_TO_MARKET: dict[int, str] = {v: k for k, v in MARKET_TO_TDX.items()}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS klines (
    market     TEXT NOT NULL,
    code       TEXT NOT NULL,
    period     TEXT NOT NULL,
    datetime   TIMESTAMP NOT NULL,
    open       DOUBLE,
    high       DOUBLE,
    low        DOUBLE,
    close      DOUBLE,
    vol        DOUBLE,
    amount     DOUBLE,
    adjust     TEXT NOT NULL DEFAULT 'QFQ',
    status     TEXT NOT NULL DEFAULT 'completed',
    updated_at TIMESTAMP,
    PRIMARY KEY (market, code, period, adjust, datetime)
);
CREATE INDEX IF NOT EXISTS idx_klines_symbol ON klines (market, code, period, adjust, datetime);
"""


def _normalize_adjust(adjust: str | None) -> str:
    """归一化复权口径；None/空 → 默认 QFQ（与 WarehouseSyncer 一致）。"""
    if not adjust:
        return "QFQ"
    a = str(adjust).upper()
    if a not in _VALID_ADJUST:
        raise ValueError(f"adjust 须为 {_VALID_ADJUST} 之一，收到 {adjust!r}")
    return a


def _affected_rows(cur: Any) -> int:
    """稳健取 UPDATE/DELETE 影响行数（DuckDB 版本间 fetchone/description 语义不一）。"""
    try:
        rowcount = getattr(cur, "rowcount", None)
        if isinstance(rowcount, int) and rowcount >= 0:
            return rowcount
    except Exception:
        pass
    try:
        if cur.description:
            row = cur.fetchone()
            if row is not None and len(row) > 0 and isinstance(row[0], (int, float)):
                return int(row[0])
    except Exception:
        pass
    try:
        rows = cur.fetchall()
        if rows and isinstance(rows[0], (list, tuple)) and isinstance(rows[0][0], (int, float)):
            return int(rows[0][0])
    except Exception:
        pass
    return 0


def default_warehouse_path() -> Path:
    """默认仓库文件路径（随 ``EASY_TDX_CONFIG_DIR``）。"""
    import os

    base = Path(os.environ.get("EASY_TDX_CONFIG_DIR", str(Path.home() / ".easy_tdx")))
    return base / "warehouse.duckdb"


def _require_duckdb() -> Any:
    try:
        import duckdb  # noqa: PLC0415 — 惰性导入，可选依赖
    except ImportError as exc:
        raise ImportError(
            "warehouse 功能需要 DuckDB：pip install easy-tdx[warehouse]（或 pip install duckdb）"
        ) from exc
    return duckdb


class KlineWarehouse:
    """K 线 DuckDB 仓库：upsert / 查询 / provisional 状态机 / 健康自检。

    Example::
        wh = KlineWarehouse()               # 或 KlineWarehouse(path)
        wh.upsert_bars("SH", "600519", df)  # 增量写入
        df = wh.query("SH", "600519", count=250)  # 默认忽略 provisional
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._duckdb = _require_duckdb()
        self._path = Path(db_path) if db_path is not None else default_warehouse_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        try:
            self._conn = self._duckdb.connect(str(self._path))
        except Exception as exc:
            raise RuntimeError(
                f"无法打开 K 线仓库 {self._path}：{exc}"
                "（DuckDB 为单写者——请检查是否另有 easy-tdx 进程/CLI 正占用该文件）"
            ) from exc
        with self._lock:
            # 先迁移后建表： legacy 表无 adjust 列时 _SCHEMA 中的索引
            # （含 adjust）会直接 Binder 失败，故迁移必须在 _SCHEMA 之前
            self._migrate_adjust_column()
            self._conn.execute(_SCHEMA)

    # 迁移时每事务拷贝的标的数量上限：大库单语句 INSERT...SELECT 会长时间
    # 持有 DuckDB 写锁并堆积内存，分块提交让其他进程可穿插读写。
    _MIGRATE_CHUNK_SYMBOLS = 500

    def _migrate_adjust_column(self) -> None:
        """老库迁移：无 adjust 列时重建表并按 QFQ 回填（历史同步器默认 QFQ）。

        旧主键 (market,code,period,datetime) 会让 QFQ/NONE 互相覆盖；新主键含
        adjust，必须重建表才能分离口径。空库/新库直接跳过。

        分块与可恢复：按标的分块拷贝（每块独立事务），全部拷贝成功并经
        行数校验后才 DROP 旧表；中断后残留 ``klines_legacy``，下次打开自动
        续拷（幂等 anti-join），校验通过才删表，不会静默 serving 半截数据。

        注意：回填统一标 ``'QFQ'``——旧同步器无口径列，若老库实际是 NONE
        口径，迁移后需用 ``--adjust NONE`` 重拉该口径（见警告日志）。
        """
        try:
            cols = [r[1] for r in self._conn.execute("PRAGMA table_info('klines')").fetchall()]
        except Exception:
            return
        if not cols:
            return
        if "adjust" in cols:
            self._resume_legacy_copy()
            return
        if self._legacy_table_exists():
            raise RuntimeError(
                "仓库迁移进行中（klines_legacy 已存在）：可能另有进程正在迁移，"
                "请稍后重试；若确认无并发进程，备份后手动处理残留表"
            )
        logger.warning("仓库迁移：检测到无 adjust 列的老表，按 QFQ 回填并重建主键（含 adjust）")
        logger.warning("若老库实际为 NONE 口径，迁移后请用 --adjust NONE 重拉该口径")
        try:
            legacy_count = self._conn.execute("SELECT count(*) FROM klines").fetchone()[0]
        except Exception:
            legacy_count = None
        try:
            self._conn.execute("ALTER TABLE klines RENAME TO klines_legacy")
            self._conn.execute(_SCHEMA)
            self._copy_legacy_chunked()
            self._verify_and_drop_legacy(legacy_count)
        except Exception as exc:
            raise RuntimeError(
                f"仓库迁移失败（klines_legacy 已保留，可备份后重试）：{exc}"
            ) from exc

    def _legacy_table_exists(self) -> bool:
        """残留 klines_legacy 是否存在（sqlite_master 兼容视图，DuckDB 支持）。"""
        try:
            row = self._conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='klines_legacy'"
            ).fetchone()
            return bool(row and row[0])
        except Exception:
            return False

    def _legacy_row_count(self) -> int | None:
        try:
            return int(self._conn.execute("SELECT count(*) FROM klines_legacy").fetchone()[0])
        except Exception:
            return None

    def _new_row_count(self) -> int | None:
        try:
            return int(self._conn.execute("SELECT count(*) FROM klines").fetchone()[0])
        except Exception:
            return None

    def _copy_legacy_chunked(self) -> int:
        """分块把 klines_legacy 按 QFQ 拷入新表（幂等，可重入续拷），返回标的数。"""
        try:
            symbols = self._conn.execute(
                "SELECT DISTINCT market, code FROM klines_legacy ORDER BY market, code"
            ).fetchall()
        except Exception as exc:
            raise RuntimeError(f"读取 legacy 标的列表失败：{exc}") from exc
        if not symbols:
            return 0
        chunk: list[tuple[Any, Any]] = []
        done = 0

        def _flush() -> None:
            nonlocal done
            if not chunk:
                return
            # anti-join 保证幂等：已拷过的标的不重复插入
            cond = " OR ".join(["(market = ? AND code = ?)"] * len(chunk))
            params: list[Any] = [p for m, c in chunk for p in (m, c)]
            self._conn.execute("BEGIN TRANSACTION")
            try:
                self._conn.execute(
                    f"""
                    INSERT INTO klines
                        (market, code, period, datetime, open, high, low, close,
                         vol, amount, adjust, status, updated_at)
                    SELECT market, code, period, datetime, open, high, low, close,
                           vol, amount, 'QFQ', status, updated_at
                    FROM klines_legacy AS L
                    WHERE ({cond})
                      AND NOT EXISTS (
                          SELECT 1 FROM klines AS K
                          WHERE K.market = L.market AND K.code = L.code
                            AND K.period = L.period AND K.datetime = L.datetime
                      )
                    """,
                    params,
                )
                self._conn.execute("COMMIT")
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
            done += len(chunk)
            if done % (self._MIGRATE_CHUNK_SYMBOLS * 10) == 0:
                logger.info("仓库迁移拷贝中：%d/%d 标的", done, len(symbols))

        try:
            for mkt, code in symbols:
                chunk.append((mkt, code))
                if len(chunk) >= self._MIGRATE_CHUNK_SYMBOLS:
                    _flush()
                    chunk = []
            _flush()
        except Exception as exc:
            raise RuntimeError(f"分块拷贝失败（已拷 {done} 标的，可重开续拷）：{exc}") from exc
        logger.info("仓库迁移拷贝完成：%d 标的", len(symbols))
        return len(symbols)

    def _verify_and_drop_legacy(self, legacy_count: int | None) -> None:
        """行数校验通过后删除 legacy；不一致则保留并抛错（不删表）。"""
        if legacy_count is not None:
            new_count = self._new_row_count()
            if new_count is None or int(new_count) != int(legacy_count):
                raise RuntimeError(
                    f"仓库迁移行数不一致（旧 {legacy_count} → 新 {new_count}），"
                    "已保留 klines_legacy 未删表"
                )
        self._conn.execute("DROP TABLE klines_legacy")

    def _resume_legacy_copy(self) -> None:
        """新表已含 adjust 列但残留 legacy（上次中断）：续拷→校验→删表。

        全部成功则完成清理；续拷/校验失败则抛错（legacy 保留），避免静默
        serving 半截数据——此前仅警告返回，是数据缺口风险。
        """
        if not self._legacy_table_exists():
            return
        logger.warning("仓库迁移残留 klines_legacy（上次迁移中断），自动续拷")
        try:
            legacy_count = self._legacy_row_count()
            self._copy_legacy_chunked()
            self._verify_and_drop_legacy(legacy_count)
        except Exception as exc:
            raise RuntimeError(f"仓库迁移续拷失败（klines_legacy 已保留）：{exc}") from exc
        logger.info("仓库迁移续拷完成，残留表已清理")

    # ── 基本属性 ─────────────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        """关闭连接。"""
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001 — 幂等关闭
            pass

    def __enter__(self) -> KlineWarehouse:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ── 写入 ─────────────────────────────────────────────────────────────────

    def upsert_bars(
        self,
        market: str,
        code: str,
        df: pd.DataFrame,
        period: str = "DAILY",
        status: str | None = None,
        adjust: str = "QFQ",
    ) -> tuple[int, int]:
        """Upsert 一批 K 线，返回 ``(新增数, 更新数)``。

        Args:
            market: ``"SH"`` / ``"SZ"`` / ``"BJ"``。
            code: 6 位代码。
            df: 含 ``datetime``（或 ``date``）与 OHLCV 列的 K 线。
            period: 周期名（默认 ``"DAILY"``，与 Period 名对齐）。
            status: 显式状态；None = 自动（当日 bar 且未过 15:05 →
                ``provisional``，其余 ``completed``）。
            adjust: 复权口径（``NONE/QFQ/HFQ``，默认 ``QFQ``）。主键含 adjust，
                不同口径互不覆盖；混用同一文件需显式传参，CLI `--adjust` 透传。
        """
        if df is None or len(df) == 0:
            return (0, 0)
        adj = _normalize_adjust(adjust)
        mkt = market.upper()
        src = df.copy()
        dt_col = "datetime" if "datetime" in src.columns else "date"
        src["_dt"] = pd.to_datetime(src[dt_col], errors="coerce")
        src = src.dropna(subset=["_dt"])
        if len(src) == 0:
            return (0, 0)
        # 时区归一：DuckDB TIMESTAMP 为 naive，按上海墙钟去 tz，避免混时区比较抛错
        try:
            tz_series = src["_dt"].dt.tz
            if tz_series is not None:
                src["_dt"] = src["_dt"].dt.tz_convert(SHANGHAI_TZ).dt.tz_localize(None)
        except Exception:
            pass
        # 秒级对齐：毫秒级抖动不产生新键
        try:
            src["_dt"] = src["_dt"].dt.floor("s")
        except Exception:
            pass
        cols = ["open", "high", "low", "close", "vol", "amount"]
        for c in cols:
            if c not in src.columns:
                src[c] = float("nan")

        now = _shanghai_now()
        today = now.date()
        before_close = now.time() < _MARKET_CLOSE_CUTOFF

        def _row_status(ts: pd.Timestamp) -> str:
            """逐行判定：当日 bar 且未过 15:05 → provisional，否则 completed。"""
            if status is not None:
                return status
            try:
                return "provisional" if (ts.date() == today and before_close) else "completed"
            except Exception:
                return "completed"

        with self._lock:
            # 统计新增/更新（按已有键，限定同 adjust）
            try:
                min_dt = src["_dt"].min()
                min_py = min_dt.to_pydatetime() if hasattr(min_dt, "to_pydatetime") else min_dt
            except Exception:
                return (0, 0)
            existing = self._conn.execute(
                """
                SELECT datetime FROM klines
                WHERE market = ? AND code = ? AND period = ? AND adjust = ?
                  AND datetime >= ?
                """,
                [mkt, code, period, adj, min_py],
            ).fetchall()
            existing_keys = {row[0] for row in existing}

            rows = []
            for _, r in src.iterrows():
                ts = r["_dt"]
                try:
                    ts_py = ts.to_pydatetime()
                except Exception:
                    continue
                rows.append(
                    (
                        mkt,
                        code,
                        period,
                        ts_py,
                        float(r["open"]),
                        float(r["high"]),
                        float(r["low"]),
                        float(r["close"]),
                        float(r["vol"]),
                        float(r["amount"]),
                        adj,
                        _row_status(ts),
                        now,
                    )
                )
            if not rows:
                return (0, 0)
            self._conn.executemany(
                """
                INSERT INTO klines (market, code, period, datetime, open, high, low,
                                    close, vol, amount, adjust, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (market, code, period, adjust, datetime) DO UPDATE SET
                    open = excluded.open, high = excluded.high, low = excluded.low,
                    close = excluded.close, vol = excluded.vol, amount = excluded.amount,
                    status = excluded.status, updated_at = excluded.updated_at
                """,
                rows,
            )

            # DuckDB timestamp 精度：统一到秒级比较
            def _sec(ts: Any) -> Any:
                try:
                    return ts.replace(microsecond=0)
                except Exception:
                    return ts

            existing_sec = {_sec(ts) for ts in existing_keys}
            inserted = sum(1 for r in rows if _sec(r[3]) not in existing_sec)
            updated = len(rows) - inserted
            return (inserted, updated)

    def promote_provisional(
        self,
        market: str | None = None,
        code: str | None = None,
        before: datetime | pd.Timestamp | None = None,
        adjust: str | None = None,
    ) -> int:
        """把 provisional 行转正为 completed，返回转正行数。

        两种用法：

        - **同步流程（推荐）**：``promote_provisional(market, code,
          before=max_dt)``——在拉取成功并 upsert 之后调用，只转正「本次成功
          拉到的数据已覆盖」（datetime <= before）的行；拉取失败/为空时不
          调用，盘中临时值不会被洗成 completed。
        - **无参维护**：仅转正日期早于沪市今日的行（历史遗留清理）。

        Args:
            market: 限定市场（None = 全仓库）。
            code: 限定标的（None = 全市场）。
            before: 只转正 datetime <= 该时刻的行；None = 日期早于沪市今日。
            adjust: 限定复权口径（None = 全部口径，默认；同步流程建议透传）。
        """
        conds = ["status = 'provisional'"]
        params: list[Any] = []
        if before is not None:
            conds.append("datetime <= ?")
            params.append(pd.Timestamp(before).to_pydatetime())
        else:
            conds.append("CAST(datetime AS DATE) < ?")
            params.append(_shanghai_now().date())
        if market is not None:
            conds.append("market = ?")
            params.append(market.upper())
        if code is not None:
            conds.append("code = ?")
            params.append(code)
        if adjust is not None:
            conds.append("adjust = ?")
            params.append(_normalize_adjust(adjust))
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE klines SET status = 'completed' WHERE {' AND '.join(conds)}",
                params,
            )
            return _affected_rows(cur)

    # ── 查询 ─────────────────────────────────────────────────────────────────

    def query(
        self,
        market: str,
        code: str,
        period: str = "DAILY",
        start: str | None = None,
        end: str | None = None,
        count: int | None = None,
        include_provisional: bool = False,
        adjust: str | None = None,
    ) -> pd.DataFrame:
        """查询 K 线（时间升序），返回 pandas DataFrame。

        Args:
            start / end: 日期范围（``YYYY-MM-DD``，闭区间，可选）。
            count: 只取最近 N 根（在过滤后应用）。
            include_provisional: False（默认）时忽略未收盘的临时 bar——
                筛选/回测默认口径，杜绝拿盘中价当收盘价。
            adjust: 复权口径过滤（``NONE/QFQ/HFQ``；None = 全部口径，默认，
                保持老调用兼容；新代码建议显式透传，避免混口径）。
        """
        mkt = market.upper()
        conds = ["market = ?", "code = ?", "period = ?"]
        params: list[Any] = [mkt, code, period]
        if adjust is not None:
            conds.append("adjust = ?")
            params.append(_normalize_adjust(adjust))
        if not include_provisional:
            conds.append("status = 'completed'")
        if start:
            conds.append("CAST(datetime AS DATE) >= ?")
            params.append(start)
        if end:
            conds.append("CAST(datetime AS DATE) <= ?")
            params.append(end)
        where = " AND ".join(conds)
        with self._lock:
            if count is not None:
                df = self._conn.execute(
                    f"""
                    SELECT * FROM (
                        SELECT * FROM klines WHERE {where}
                        ORDER BY datetime DESC LIMIT ?
                    ) ORDER BY datetime ASC
                    """,
                    [*params, int(count)],
                ).df()
            else:
                df = self._conn.execute(
                    f"SELECT * FROM klines WHERE {where} ORDER BY datetime ASC", params
                ).df()
            return df

    def last_datetime(
        self,
        market: str,
        code: str,
        period: str = "DAILY",
        include_provisional: bool = True,
        adjust: str | None = None,
    ) -> pd.Timestamp | None:
        """该标的最新 bar 时间（无数据返回 None）。"""
        mkt = market.upper()
        cond = "" if include_provisional else "AND status = 'completed'"
        params: list[Any] = [mkt, code, period]
        if adjust is not None:
            cond += " AND adjust = ?"
            params.append(_normalize_adjust(adjust))
        with self._lock:
            row = self._conn.execute(
                f"""
                SELECT max(datetime) FROM klines
                WHERE market = ? AND code = ? AND period = ? {cond}
                """,
                params,
            ).fetchone()
        val = row[0] if row else None
        return pd.Timestamp(val) if val is not None else None

    def symbols(
        self, period: str = "DAILY", adjust: str | None = None, per_adjust: bool = True
    ) -> pd.DataFrame:
        """列出仓库内全部标的及其数据范围/行数。

        Args:
            period: 周期键。
            adjust: 限定复权口径（None = 全部口径）。
            per_adjust: True（默认）按 ``(market, code, adjust)`` 分组，一标的
                多口径时返回多行（含 ``adjust`` 列）；False 按 ``(market, code)``
                合并（历史形状，无 ``adjust`` 列，兼容老调用方）。
        """
        if per_adjust:
            cond = "period = ?"
            params: list[Any] = [period]
            if adjust is not None:
                cond += " AND adjust = ?"
                params.append(_normalize_adjust(adjust))
            with self._lock:
                return self._conn.execute(
                    f"""
                    SELECT market, code, adjust, count(*) AS bars,
                           min(datetime) AS first, max(datetime) AS last,
                           sum(CASE WHEN status = 'provisional' THEN 1 ELSE 0 END)
                               AS provisional
                    FROM klines WHERE {cond}
                    GROUP BY market, code, adjust ORDER BY market, code, adjust
                    """,
                    params,
                ).df()
        cond = "period = ?"
        params = [period]
        if adjust is not None:
            cond += " AND adjust = ?"
            params.append(_normalize_adjust(adjust))
        with self._lock:
            return self._conn.execute(
                f"""
                SELECT market, code, count(*) AS bars,
                       min(datetime) AS first, max(datetime) AS last,
                       sum(CASE WHEN status = 'provisional' THEN 1 ELSE 0 END) AS provisional
                FROM klines WHERE {cond}
                GROUP BY market, code ORDER BY market, code
                """,
                params,
            ).df()

    # ── 删除 ─────────────────────────────────────────────────────────────────

    def delete_symbol(
        self, market: str, code: str, period: str = "DAILY", adjust: str | None = None
    ) -> int:
        """删除某标的全部数据，返回删除行数。"""
        cond = "market = ? AND code = ? AND period = ?"
        params: list[Any] = [market.upper(), code, period]
        if adjust is not None:
            cond += " AND adjust = ?"
            params.append(_normalize_adjust(adjust))
        with self._lock:
            cur = self._conn.execute(f"DELETE FROM klines WHERE {cond}", params)
            return _affected_rows(cur)

    # ── 健康自检（P2-3）──────────────────────────────────────────────────────

    def health_check(
        self,
        market: str | None = None,
        code: str | None = None,
        max_gap_weekdays: int = 5,
        adjust: str | None = None,
    ) -> dict[str, Any]:
        """仓库健康自检：缺口 / 异常跳变 / 最新度 / 临时行统计。

        Args:
            market / code: 只检查指定标的（None = 全仓库）。
            max_gap_weekdays: 相邻 bar 间缺失「交易日数」超过该值报疑似缺口
                （节假日会造成少量误报，报告口径为「待人工核查」）。
            adjust: 限定复权口径（None = 按口径分别检查，默认；QFQ/NONE 混存
                时不再混算，避免把跨口径价差误报为 price_jump）。

        Returns:
            ``{"symbols_checked", "issues": [...], "summary": {...}}``。
            ``symbols_checked`` 按 ``(market, code, adjust)`` 口径计数；
            issue/stale 条目带 ``adjust`` 字段，``symbol`` 保持 ``"MKT:CODE"``
            兼容老调用。
        """
        from easy_tdx.mac.qfq_check import detect_ex_dividend_gaps

        conds = ["period = 'DAILY'"]
        params: list[Any] = []
        if market is not None:
            conds.append("market = ?")
            params.append(market.upper())
        if code is not None:
            conds.append("code = ?")
            params.append(code)
        if adjust is not None:
            conds.append("adjust = ?")
            params.append(_normalize_adjust(adjust))
        where = " AND ".join(conds)

        sym_df = self._conn.execute(
            f"""
            SELECT market, code, adjust, count(*) AS bars,
                   min(datetime) AS first, max(datetime) AS last,
                   sum(CASE WHEN status = 'provisional' THEN 1 ELSE 0 END) AS provisional
            FROM klines WHERE {where}
            GROUP BY market, code, adjust
            """,
            params,
        ).df()

        issues: list[dict[str, Any]] = []
        today = _shanghai_now().date()
        stale: list[dict[str, Any]] = []
        total_provisional = 0

        for _, s in sym_df.iterrows():
            mkt, cde, adj = str(s["market"]), str(s["code"]), str(s["adjust"])
            total_provisional += int(s["provisional"])

            # 最新度
            last = pd.Timestamp(s["last"])
            stale_days = (today - last.date()).days
            if stale_days > 7:
                stale.append(
                    {
                        "symbol": f"{mkt}:{cde}",
                        "adjust": adj,
                        "last": str(last.date()),
                        "days": stale_days,
                    }
                )

            # 缺口：相邻 bar 的「工作日差」（同口径内计算，不跨口径混算）
            df = self.query(mkt, cde, include_provisional=True, adjust=adj)
            if len(df) < 2:
                continue
            dts = pd.to_datetime(df["datetime"]).dt.date
            gaps = []
            for prev, cur_d in zip(dts.iloc[:-1], dts.iloc[1:], strict=False):
                weekdays = np_busdays(prev, cur_d)
                if weekdays > max_gap_weekdays:
                    gaps.append(
                        {"after": str(prev), "before": str(cur_d), "weekdays": int(weekdays)}
                    )
            if gaps:
                issues.append(
                    {
                        "symbol": f"{mkt}:{cde}",
                        "adjust": adj,
                        "kind": "gap",
                        "detail": (
                            f"{len(gaps)} 处疑似缺口（缺失工作日>{max_gap_weekdays}，含节假日误报）"
                        ),
                        "gaps": gaps[:10],
                    }
                )

            # 异常跳变（板块感知阈值，复用 QFQ 对拍的跳空检测）
            jump_dates = detect_ex_dividend_gaps(df, cde, MARKET_TO_TDX.get(mkt))
            if jump_dates:
                issues.append(
                    {
                        "symbol": f"{mkt}:{cde}",
                        "adjust": adj,
                        "kind": "price_jump",
                        "detail": (
                            f"{len(jump_dates)} 处超出跌停幅度的向下跳空"
                            "（多为除权，未复权数据需人工核查）"
                        ),
                        "dates": jump_dates[:10],
                    }
                )

        return {
            "symbols_checked": int(len(sym_df)),
            "issues": issues,
            "summary": {
                "symbols_with_issues": len({i["symbol"] for i in issues}),
                "stale_symbols": stale[:20],
                "provisional_rows": total_provisional,
                "checked_at": _shanghai_now().isoformat(timespec="seconds"),
            },
        }


def np_busdays(d1: date, d2: date) -> int:
    """两个日期之间的工作日数（不含首日，含规则近似：周一~周五）。"""
    import numpy as _np

    if d2 <= d1:
        return 0
    return int(_np.busday_count(d1, d2))
