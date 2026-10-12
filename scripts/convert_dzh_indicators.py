"""大智慧/文华指标批量转换为 easy-tdx 公式引擎可识别的自定义指标。

读取 --src 目录下全部 ``*.txt``（文华 WH6 转大智慧/通达信语法），清洗为
本项目公式方言（见 :mod:`easy_tdx.formula`），逐条用
``compile_formula`` + 合成 K 线试算验证，通过的写入前端自定义指标包：

- ``web-ui/public/dzh-custom-indicators.json``（前端「自定义指标」页一键导入）
- ``docs/dzh-indicators.md``（转换对照表：通过 / 跳过及原因）

转换规则（保持原指标语义，逐条可审计）：

- 去 ``//`` 行注释与 ``{...}`` 块注释外的绘图语句（DRAWICON/DRAWTEXT/
  STICKLINE/VERTLINE/FILLRGN/DRAWCOLOR*/PARTLINE/DRAWLINE 等只管画图，
  不参与数值，一律剔除；其中 DRAWICON/DRAWTEXT 的第一个参数是触发条件，
  抢救为 ``信号N`` 输出列）；
- 语句末尾的显示后缀（``,COLORRED``/``,LINETHICK1``/``,NODRAW``/``,DOT``…
  逗号在顶层括号深度为 0 处切分，只保留第一段）同步剔除；
- 含跨市场引用（``"..."``/``$``）、Level2 逐笔（``SCALE``）、流通股本
  （``CAPITAL``）、胜率（``WINNER``）、未来函数（``ZIG``/``REFX``/周期
  ``PERIOD``/日期 ``MONTH``/``YEAR`` 等）的语句无法复刻，直接剔除，
  被污染变量的下游语句级联剔除（fixpoint），全程记录；
- ``DRAWNULL`` → ``(0/0)``（NaN，不断线）；``STDP`` → ``STD``（同总体口径）；
  ``REVERSE(X)`` → ``-X`` 由引擎原生支持；``<>`` → ``!=``；
- ``HHV/LLV(X,0)``（全历史最值）→ 窗口 250 近似；``SUM(X,0)`` 保持累计和
  （与引擎语义一致）；动态窗口（序列型 ``COUNT(X,动态)``）→ 30 近似；
- 未定义参数注入默认值（``N=10 M=10 F=8 M1=5 M2=10 M3=20 M4=60``，其余 10），
  ``AMOUNT`` → ``(C*V)``（作图链路无 amount 列，保证两条链路同口径）；
- 无命名输出时把汇点中间变量（不被其他语句引用的 ``:=``）提升为输出，
  如 KAGI 的 A/B、FVG 的 SIGNAL/SIGNAL1。

用法::

    python scripts/convert_dzh_indicators.py [--src DIR] [--check-only]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = Path("C:/Users/xuxin/Desktop/大智慧指标")
DEFAULT_JSON = REPO_ROOT / "web-ui" / "public" / "dzh-custom-indicators.json"
DEFAULT_MD = REPO_ROOT / "docs" / "dzh-indicators.md"

# ── 规则表 ────────────────────────────────────────────────────────────────

#: 纯绘图函数：整条语句剔除（只管画图，不产出数值）
DRAW_HEADS = {
    "DRAWICON", "DRAWTEXT", "DRAWNUMBER", "DRAWNUMBER1", "STICKLINE",
    "STICKLINE1", "VERTLINE", "FILLRGN", "DRAWCOLORKLINE", "DRAWCOLORLINE",
    "DRAWLINE", "PARTLINE", "DRAWBAND", "DRAWMONEY",
}

#: 绘图函数中第一个参数为触发条件的，条件抢救为信号列（图标/文字本身画不出，
#: 但条件是真实信号）。STICKLINE 系 shade 区间语义，非事件信号，不抢救。
SIGNAL_HEADS = {"DRAWICON", "DRAWTEXT"}

#: 无法复刻的语义标记：含这些记号的语句剔除（大小写不敏感，子串匹配）
POISON_MARKS = {
    "WINNER", "ZIGZAG", "SUMBARS", "CJLVOL", "ISCONTRACT", "SCALE",
    "CAPITAL", "PERIOD", "MONTH", "YEAR", "DAYBARPOS", "BARPOS",
    "DATACOUNT", "ISLASTBAR", "ISUP", "ISDOWN", "ISEQUAL", "REFX",
    "COST", "HYBLOCK", "DYNAINFO", "FINANCE", "WINNER",
}

#: 未定义参数的注入默认值
PARAM_DEFAULTS = {
    "N": 10, "M": 10, "F": 8, "M1": 5, "M2": 10, "M3": 20, "M4": 60,
    "P": 14, "P1": 14, "P2": 26, "P3": 52,
}
FALLBACK_PARAM = 10

#: 需要动态窗口→固定近似的函数（窗口位索引，从 0 起；LONGCROSS 的 N 在第 3 位）
WINDOW_FUNCS = {
    "MA": [1], "EMA": [1], "SMA": [1], "WMA": [1], "HHV": [1], "LLV": [1],
    "HHVBARS": [1], "LLVBARS": [1], "STD": [1], "STDP": [1], "SUM": [1],
    "COUNT": [1], "EXIST": [1], "EVERY": [1], "FILTER": [1], "AVEDEV": [1],
    "SLOPE": [1], "FORCAST": [1], "BARSSINCEN": [1], "LONGCROSS": [2],
    "REF": [1], "DIFF": [1],
}
DYNAMIC_WINDOW_FALLBACK = 30
FULL_HISTORY_WINDOW = 250  # HHV/LLV(X,0) 全历史最值 → 250 根近似

#: 文件级预替换（pattern, repl, 说明），多为动态口径→固定近似
FILE_PREREPLACE: dict[str, list[tuple[str, str, str]]] = {
    # VWAP/TC/TCY：按日/月/年复位的动态窗口 → 固定窗口近似（原语义需日内复位，
    # 日线引擎无复位信息，取 20/240 近似，报告中注明）
    "VWAP.txt": [
        (r"N\s*:=\s*IF\s*\(PERIOD.*?;\s*", "", "按日复位窗口→DC=20近似"),
        (r"DC\s*:=\s*BARSLAST\s*\(N\)\s*\+\s*1\s*;", "DC:=20;", ""),
    ],
    "TC.txt": [
        (r"MC\s*:=\s*BARSLAST\s*\(MONTH.*?;\s*", "MC:=20;", "按月复位窗口→MC=20近似"),
        (r"YC\s*:=\s*BARSLAST\s*\(YEAR.*?;\s*", "YC:=240;", "按年复位窗口→YC=240近似"),
    ],
    "TCY.txt": [
        (r"MC\s*:=\s*BARSLAST\s*\(MONTH.*?;\s*", "MC:=20;", "按月复位窗口→MC=20近似"),
        (r"YC\s*:=\s*BARSLAST\s*\(YEAR.*?;\s*", "YC:=240;", "按年复位窗口→YC=240近似"),
    ],
    # DTR：信号 Bar 的动态 REF → VALUEWHEN（信号成立当根的值，语义等价）
    "DTR.txt": [
        (r"JCH\s*:=\s*IF\s*\(JT\s*=\s*1\s*,\s*REF\s*\(HIGH\s*,\s*JP\s*\)\s*,\s*0\s*\)\s*;",
         "JCH:=VALUEWHEN(JC,HIGH);", "动态REF→VALUEWHEN(信号当根值)"),
        (r"JCL\s*:=\s*IF\s*\(JT\s*=\s*2\s*,\s*REF\s*\(LOW\s*,\s*JP\s*\)\s*,\s*0\s*\)\s*;",
         "JCL:=VALUEWHEN(SC,LOW);", ""),
    ],
    # RVC004：核心数值线原为中间变量，提升为输出
    "RVC004.txt": [
        (r"ROYAL_INDEX\s*:=\s*SUM\s*\(", "ROYAL_INDEX:SUM(", "核心线提升为输出"),
    ],
}

SERIES_ALIASES = {
    "C", "CLOSE", "O", "OPEN", "H", "HIGH", "L", "LOW", "V", "VOL",
    "VOLUME", "AMOUNT", "AMT",
}
LOGIC_WORDS = {"AND", "OR", "NOT"}

_NAME_RE = r"[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*"


@dataclass
class Converted:
    name: str
    kind: str
    formula: str
    note: str
    outputs: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    source_file: str = ""
    candle: list[str] = field(default_factory=list)


@dataclass
class Skipped:
    name: str
    reason: str
    source_file: str = ""


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "gbk", "utf-16"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def _strip_line_comments(text: str) -> str:
    return re.sub(r"//[^\n]*", "", text)


def _split_top_level(stmt: str) -> str:
    """取语句顶层第一个逗号之前的部分（去显示后缀，括号感知）。"""
    depth = 0
    in_str = False
    for i, ch in enumerate(stmt):
        if ch == "'":
            in_str = not in_str
        elif in_str:
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            return stmt[:i]
    return stmt


def _head_func(expr: str) -> str | None:
    """表达式头函数名（`NAME :=? head(`），无则 None。"""
    m = re.match(r"\s*(?:" + _NAME_RE + r"\s*:={0,1}\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(", expr)
    # 上式对 `NAME: IF(...)` 会把 NAME 当前缀吞掉；绘图调用都是裸调用，
    # 为避免误判，只在无赋值号时取头函数
    if ":=" in expr.split("(", 1)[0] or re.match(r"\s*" + _NAME_RE + r"\s*:\s*[A-Za-z_]", expr):
        inner = expr.split(":", 1)[1]
        m2 = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", inner)
        return m2.group(1).upper() if m2 else None
    return m.group(1).upper() if m else None


def _head_call_args(raw: str, head: str) -> list[str] | None:
    """取裸调用 `HEAD(...)` 的顶层参数表；括号不平衡返回 None。"""
    i = raw.upper().find(head)
    j = raw.find("(", i)
    if i < 0 or j < 0:
        return None
    args: list[str] = []
    depth, cur, in_str = 0, "", False
    k = j
    while k < len(raw):
        ch = raw[k]
        if ch == "'":
            in_str = not in_str
            cur += ch
        elif in_str:
            cur += ch
        elif ch == "(":
            depth += 1
            if depth > 1:
                cur += ch
        elif ch == ")":
            depth -= 1
            if depth == 0:
                args.append(cur.strip())
                tail = raw[k + 1 :].strip()
                return args if not tail else None
            cur += ch
        elif ch == "," and depth == 1:
            args.append(cur.strip())
            cur = ""
        else:
            cur += ch
        k += 1
    return None


def _norm_expr(expr: str) -> str:
    return re.sub(r"\s+", "", expr).upper()


def _parse_statement(stmt: str) -> tuple[str | None, str, bool] | None:
    """解析单条语句 → (name, expr, is_output)。裸表达式 name=None。"""
    s = stmt.strip()
    if not s:
        return None
    m = re.match(r"(" + _NAME_RE + r")\s*(:=|:)\s*(.*)$", s, re.DOTALL)
    if m:
        name, assign, expr = m.group(1), m.group(2), m.group(3).strip()
        if not expr:
            return None
        return (name, expr, assign == ":")
    return (None, s, True)


@dataclass
class _Stmt:
    name: str | None
    expr: str
    is_output: bool
    raw: str


def _signal_cond(raw: str, head: str) -> str | None:
    """DRAWICON/DRAWTEXT 第一个参数即触发条件；取不出返回 None。"""
    args = _head_call_args(raw, head)
    if not args:
        return None
    cond = args[0].strip()
    return cond or None


def _is_poisoned(text: str) -> bool:
    upper = text.upper()
    return '"' in text or "$" in text or any(m in upper for m in POISON_MARKS)


def convert_text(filename: str, text: str) -> tuple[str | None, list[str], list[str]]:
    """转换单个指标文本 → (formula | None, notes, candle)。None 表示不可转换。"""
    notes: list[str] = []
    t = _strip_line_comments(text)
    # {块注释}（含 {/*...*/} 头）整体去掉
    t = re.sub(r"\{[^}]*\}", " ", t)
    for pat, repl, label in FILE_PREREPLACE.get(filename, []):
        t, n = re.subn(pat, repl, t, flags=re.DOTALL)
        if n:
            notes.append(label or "预替换近似")
    # 归一化
    t = re.sub(r":\s*=", ":=", t)  # `TR : =` → `TR:=`
    t = t.replace("<>", "!=")  # TDX 不等价 → 引擎 !=
    # 前导数字变量名（`5F`/`30F`）→ X 前缀（引擎标识符不能以数字开头）
    t = re.sub(r"\b(\d+)([A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*)", r"X\1\2", t)
    t = re.sub(r"\bSTDP\s*\(", "STD(", t)
    t = re.sub(r"\bSTICKLINE1\b", "STICKLINE", t)  # 大智慧变体拼写归一化（仍按绘图剔除）
    t = re.sub(r"\bAMOUNT\b(?!\s*:=)", "(C*V)", t)
    t = re.sub(r"\bAMT\b(?!\s*:=)", "(C*V)", t)
    t = re.sub(r"\bAVPRICE\b", "C", t)
    # HHV/LLV(X,0) 全历史最值 → 250 根近似（SUM(X,0) 累计和引擎原生支持，保持）
    t = re.sub(r"\b(HHV|LLV)\s*\(\s*([^,;]+?)\s*,\s*0\s*\)", r"\1(\2,250)", t)

    stmts: list[_Stmt] = []
    for chunk in t.split(";"):
        seg = _split_top_level(chunk).strip()
        if not seg or seg == "{" or seg == "}":
            continue
        parsed = _parse_statement(seg)
        if parsed is None:
            continue
        name, expr, is_output = parsed
        stmts.append(_Stmt(name=name, expr=expr, is_output=is_output, raw=seg))

    # 1) 剔除纯绘图语句 / 含毒标记语句（含跨市场引号）
    kept: list[_Stmt] = []
    dropped: list[str] = []
    pending_signals: list[tuple[str, str]] = []
    for st in stmts:
        head = _head_func(st.raw)
        if head in DRAW_HEADS:
            dropped.append(st.raw[:40])
            notes.append(f"剔除绘图 {head}")
            if head in SIGNAL_HEADS and st.name is None:
                pending_signals.append((st.raw, head))
            continue
        upper = st.raw.upper()
        if '"' in st.raw or "$" in st.raw or any(m in upper for m in POISON_MARKS):
            if '"' in st.raw or "$" in st.raw:
                hit = "跨市场引用"
            else:
                hit = next(m for m in POISON_MARKS if m in upper)
            dropped.append(st.raw[:40])
            notes.append(f"剔除不可复刻 {hit}")
            continue
        if re.search(r"\bDRAWNULL\b", st.expr, re.IGNORECASE):
            st.expr = re.sub(r"\bDRAWNULL\b", "(0/0)", st.expr, flags=re.IGNORECASE)
            notes.append("DRAWNULL→空值")
        kept.append(st)

    if not kept:
        return None, notes + ["全部语句被剔除"], []

    # 2) 毒变量级联剔除（fixpoint）：被剔语句定义的变量，下游一并剔除
    defined = {s.name.upper() for s in kept if s.name}
    dropped_names = {s.name.upper() for s in stmts if s.name} - defined
    changed = True
    while changed:
        changed = False
        survivors: list[_Stmt] = []
        for st in kept:
            refs = {w.upper() for w in re.findall(_NAME_RE, st.expr)}
            refs -= LOGIC_WORDS
            if refs & dropped_names:
                dropped.append(st.raw[:40])
                if st.name:
                    dropped_names.add(st.name.upper())
                notes.append(f"级联剔除 {(st.name or '匿名')}")
                changed = True
            else:
                survivors.append(st)
        kept = survivors
    if not kept:
        return None, notes + ["级联剔除后无剩余语句"], []

    # 3) 标量名集合：字面量定义 + 待注入参数（动态窗口判定用）
    scalar_names: set[str] = set()
    for st in kept:
        if st.name and re.fullmatch(r"\d+(\.\d+)?", st.expr.strip()):
            scalar_names.add(st.name.upper())

    # 收集引用名（函数名大写，需扣掉白名单——在验证阶段由引擎裁决，此处只做参数注入）
    from easy_tdx.formula import _functions  # noqa: PLC2701 — 复用引擎白名单

    whitelist = set(_functions().keys()) | {"IF"}
    used: set[str] = set()
    for st in kept:
        for w in re.findall(_NAME_RE, st.expr):
            if w.upper() not in LOGIC_WORDS:
                used.add(w)
    defined_now = {s.name.upper() for s in kept if s.name}
    series = SERIES_ALIASES | {"DRAWNULL"}

    def _is_known(w: str) -> bool:
        u = w.upper()
        return u in defined_now or u in whitelist or u in series

    missing = sorted({w for w in used if not _is_known(w)}, key=str.upper)
    # 中文/英文未定义变量 → 注入参数默认值；疑似函数拼写一律保留给引擎报错
    injected: dict[str, int] = {}
    for w in missing:
        key = w.upper()
        injected[key] = PARAM_DEFAULTS.get(key, FALLBACK_PARAM)
        scalar_names.add(key)
    if injected:
        notes.append("注入参数 " + ",".join(f"{k}={v}" for k, v in sorted(injected.items())))

    # 4) 动态窗口 → 固定近似（窗口位为标识符/表达式且非常量时）
    def _fix_windows(expr: str) -> tuple[str, bool]:
        hit = False

        def _sub(m: re.Match[str]) -> str:
            nonlocal hit
            fname = m.group(1).upper()
            args = m.group(2)
            parts = _split_args(args)
            idxs = WINDOW_FUNCS.get(fname, [])
            for i in idxs:
                if i < len(parts):
                    w = parts[i].strip()
                    if re.fullmatch(r"-?\d+(\.\d+)?", w):
                        if float(w) == 0 and fname in ("HHV", "LLV"):
                            parts[i] = str(FULL_HISTORY_WINDOW)
                            hit = True
                        continue
                    if re.fullmatch(_NAME_RE, w) and w.upper() in scalar_names:
                        continue
                    parts[i] = str(DYNAMIC_WINDOW_FALLBACK)
                    hit = True
            return m.group(1) + "(" + ",".join(parts) + ")"

        return re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*)\)", _sub, expr), hit

    for st in kept:
        new_expr, hit = _fix_windows(st.expr)
        if hit:
            st.expr = new_expr
            notes.append(f"动态窗口→{DYNAMIC_WINDOW_FALLBACK}近似")

    # 5) 无任何输出（连匿名都没有）→ 汇点变量提升为输出
    if not any(s.is_output for s in kept):
        referenced: set[str] = set()
        for st in kept:
            for w in re.findall(_NAME_RE, st.expr):
                referenced.add(w.upper())
        sinks = [s for s in kept if s.name and not s.is_output and s.name.upper() not in referenced]
        targets = sinks or [s for s in kept if s.name and not s.is_output]
        for s in targets:
            s.is_output = True
        if targets:
            notes.append("提升输出 " + ",".join(s.name or "?" for s in targets))

    # 6) 绘图触发条件抢救为信号列（提升之后：只跟输出列去重）
    if pending_signals:
        defined_all = {s.name.upper() for s in kept if s.name} | scalar_names
        known_exprs = {_norm_expr(s.expr) for s in kept}
        out_names = {s.name.upper() for s in kept if s.name and s.is_output}
        sig_idx = sum(1 for s in kept if s.name and re.fullmatch(r"信号\d+", s.name or ""))
        for raw, head in pending_signals:
            cond = _signal_cond(raw, head)
            if cond is None or _is_poisoned(cond):
                continue
            refs = {w.upper() for w in re.findall(_NAME_RE, cond)} - LOGIC_WORDS
            if not refs <= (defined_all | whitelist | series):
                notes.append(f"{head}条件引用缺失被跳过")
                continue
            if _norm_expr(cond) in known_exprs or cond.strip().upper() in out_names:
                continue
            cond, w_hit = _fix_windows(cond)
            if w_hit:
                notes.append(f"动态窗口→{DYNAMIC_WINDOW_FALLBACK}近似")
            sig_idx += 1
            kept.append(
                _Stmt(name=f"信号{sig_idx}", expr=cond, is_output=True, raw=f"信号{sig_idx}:{cond}")
            )
            known_exprs.add(_norm_expr(cond))
            out_names.add(f"信号{sig_idx}")
            defined_all.add(f"信号{sig_idx}")
            notes.append(f"{head}条件→信号{sig_idx}")

    # 7) 平均K线类（XOPEN/XCLOSE/XHIGH/XLOW 中间变量齐备）：追加 KO/KH/KL/KC
    # 输出别名并绑定叠加K线，导入即在主图显示蜡烛
    candle: list[str] = []
    defined_names = {s.name.upper() for s in kept if s.name}
    if {"XOPEN", "XCLOSE", "XHIGH", "XLOW"} <= defined_names:
        aliases = [("KO", "XOPEN"), ("KH", "XHIGH"), ("KL", "XLOW"), ("KC", "XCLOSE")]
        if all(a.upper() not in defined_names for a, _ in aliases):
            for a, src in aliases:
                kept.append(_Stmt(name=a, expr=src, is_output=True, raw=f"{a}:{src}"))
            candle = [a for a, _ in aliases]
            notes.append("平均K线列→叠加K线(KO/KH/KL/KC)")

    # 组装
    lines: list[str] = []
    if injected:
        lines.append("{参数为原公式未给默认值的占位，转换时注入}")
        for k in sorted(injected):
            lines.append(f"{k}:={injected[k]};")
    for st in kept:
        if st.name:
            lines.append(f"{st.name}{':' if st.is_output else ':='}{st.expr};")
        else:
            lines.append(f"{st.expr};")
    return "\n".join(lines), notes, candle


def _split_args(args: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in args:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def _guess_kind(name: str, formula: str) -> str:
    """主图叠加 vs 副图：allowlist 明确指定的放主图，其余一律副图。"""
    return "overlay" if name in KIND_OVERLAY else "sub"


def _synthetic_df(n: int = 600):  # noqa: ANN202 — 脚本内部工具
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0, 0.01, n))
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2023-01-01", periods=n, freq="B"),
            "open": close * (1 + rng.normal(0, 0.002, n)),
            "high": close * (1 + rng.uniform(0, 0.015, n)),
            "low": close * (1 - rng.uniform(0, 0.015, n)),
            "close": close,
            "vol": rng.uniform(1e6, 8e6, n),
        }
    )


KIND_OVERLAY = {
    # 主图叠加：输出与价格同量纲的跟踪线/带/箱体（其余一律副图，避免量纲压住 K 线）
    "BIGMONEY", "HPS", "RVC001", "WUYANYUAN1964", "通道组合", "BBIANDMA60",
    "JCJY", "主宰V1", "箱体", "基准点趋势分析指标", "趋势识别", "H52",
    "RVC009", "RVC013", "知行趋势线", "DJIEV", "SEV-RVC", "全换手",
}


def process(src: Path) -> tuple[list[Converted], list[Skipped]]:
    import numpy as np

    from easy_tdx.formula import FormulaError, compile_formula

    df = _synthetic_df()
    ok: list[Converted] = []
    bad: list[Skipped] = []
    files = sorted(src.glob("*.txt"))
    for path in files:
        name = path.stem
        formula, notes, candle = convert_text(path.name, _read_text(path))
        if formula is None:
            bad.append(
                Skipped(name=name, reason="；".join(notes) or "不可转换", source_file=path.name)
            )
            continue
        try:
            compiled = compile_formula(formula)
            res = compiled.compute(df)
        except (FormulaError, ValueError, RuntimeError) as exc:
            bad.append(Skipped(name=name, reason=f"引擎验证失败：{exc}", source_file=path.name))
            continue
        cols = list(res.columns.keys())
        if not cols:
            bad.append(Skipped(name=name, reason="无输出列", source_file=path.name))
            continue
        # 质量门：至少一列在尾部 100 根有 ≥5 个有限值
        frame = res.to_frame()
        tail = frame.iloc[-100:]
        finite_counts = {
            c: int(np.isfinite(tail[c].to_numpy(dtype=float)).sum())
            for c in frame.columns
        }
        if not any(v >= 5 for v in finite_counts.values()):
            bad.append(
                Skipped(
                    name=name,
                    reason="输出全为 NaN（原公式除零/条件恒假）",
                    source_file=path.name,
                )
            )
            continue
        # 全常数列（如仅剩 5/50/95 参考线）视为无信息
        try:
            varying = sum(1 for c in frame.columns if frame[c].nunique(dropna=True) > 1)
        except TypeError:
            varying = 1
        if varying == 0:
            bad.append(
                Skipped(name=name, reason="仅剩常数参考线，无指标信息", source_file=path.name)
            )
            continue
        dead_cols = sorted(c for c, v in finite_counts.items() if v == 0)
        # 单一裸 OHLCV 别名输出视为无信息
        if len(cols) == 1 and re.fullmatch(r"OUTPUT_\d+", cols[0]):
            sole = formula.strip().splitlines()[-1].strip().rstrip(";").upper()
            if sole in SERIES_ALIASES:
                bad.append(
                    Skipped(name=name, reason="仅剩裸行情引用，无指标信息", source_file=path.name)
                )
                continue
        kind = _guess_kind(name, formula)
        note = "；".join(notes) if notes else "直转"
        if dead_cols:
            note += f"；恒为空列({','.join(dead_cols)}，原公式该路恒除零/恒假)仅作占位"
        ok.append(
            Converted(
                name=name, kind=kind, formula=formula,
                note=note,
                outputs=[c for c in res.values], signals=list(res.signals),
                source_file=path.name, candle=candle,
            )
        )
    return ok, bad


def _cell(text: str, limit: int = 220) -> str:
    """md 表格单元格清洗：去换行、截断（引擎报错常带多行数组）。"""
    one = re.sub(r"\s+", " ", text).strip()
    return one if len(one) <= limit else one[:limit] + "…"


def write_outputs(ok: list[Converted], bad: list[Skipped], json_path: Path, md_path: Path) -> None:
    payload = {
        "version": 1,
        "source": "桌面「大智慧指标」目录（文华WH6转通达信语法）批量转换",
        "generated": _dt.date.today().isoformat(),
        "count": len(ok),
        "indicators": [
            {
                "name": c.name, "kind": c.kind, "formula": c.formula,
                "note": c.note, "outputs": c.outputs, "signals": c.signals,
                "source_file": c.source_file, "candle": c.candle,
            }
            for c in ok
        ],
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = [
        "# 大智慧指标转换对照表",
        "",
        f"> 由 `scripts/convert_dzh_indicators.py` 自动生成（{_dt.date.today().isoformat()}）。"
        "源目录：桌面「大智慧指标」（62 个，文华 WH6 转大智慧/通达信语法）。"
        "转换目标为本项目公式引擎方言（`easy_tdx.formula`），"
        "验证口径：编译通过 + 600 根合成 K 线试算有有限输出。",
        "",
        f"- 成功：**{len(ok)}** 个（见下表，Web「系统 → 自定义指标」页经「从文件恢复」批量导入）",
        f"- 跳过：**{len(bad)}** 个（原因见末表，多为跨市场/Level2/流通股本等引擎无数据源）",
        "",
        "## 成功列表",
        "",
        "| 显示名 | 位置 | 输出列 | 转换说明 |",
        "|---|---|---|---|",
    ]
    for c in ok:
        outs = "、".join(c.outputs + [s for s in c.signals if s not in c.outputs]) or "—"
        pos = "主图" if c.kind == "overlay" else "副图"
        lines.append(f"| {c.name} | {pos} | {_cell(outs)} | {_cell(c.note, 260)} |")
    lines += ["", "## 跳过列表", "", "| 显示名 | 原因 |", "|---|---|"]
    for s in bad:
        lines.append(f"| {s.name} | {_cell(s.reason)} |")
    lines += [
        "",
        "## 口径说明",
        "",
        "- 绘图语句（DRAWICON/DRAWTEXT/STICKLINE/VERTLINE 等）只管画图，",
        "  不产出数值，转换时剔除，信号本身保留为输出列。",
        "- `DRAWNULL` → 空值（不断线）；`STDP` 与 `STD` 同总体口径；",
        "  `REVERSE(X)` 取负；`<>` 按 `!=` 求值；`ATAN` 由引擎补齐。",
        "- `HHV/LLV(X,0)`（全历史最值）按 250 根近似；动态窗口按 30 根近似；",
        "  VWAP/TC/TCY 的按日/月复位窗口按 20/240 近似。",
        "- 原公式未给默认值的参数（N/M/F 等）注入默认值，明细见各条“转换说明”。",
        "- DTR 的信号 Bar 动态 REF 改写为 `VALUEWHEN`",
        "  （信号当根值前向延续，语义等价且无未来数据）。",
    ]
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="大智慧指标批量转换为自定义指标包")
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_MD)
    ap.add_argument("--check-only", action="store_true", help="只验证并打印报告，不写文件")
    args = ap.parse_args()

    ok, bad = process(args.src)
    print(f"成功 {len(ok)} / 跳过 {len(bad)}")
    for c in ok:
        print(f"  OK   {c.name} [{c.kind}] 输出={c.outputs + c.signals}")
    for s in bad:
        print(f"  SKIP {s.name} :: {s.reason[:120]}")
    if not args.check_only:
        write_outputs(ok, bad, args.out_json, args.out_md)
        print(f"写出 {args.out_json} / {args.out_md}")


if __name__ == "__main__":
    main()
