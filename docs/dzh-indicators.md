# 大智慧指标转换对照表

> 由 `scripts/convert_dzh_indicators.py` 自动生成（2026-10-12）。源目录：桌面「大智慧指标」（62 个，文华 WH6 转大智慧/通达信语法）。转换目标为本项目公式引擎方言（`easy_tdx.formula`），验证口径：编译通过 + 600 根合成 K 线试算有有限输出。

- 成功：**52** 个（见下表，Web「系统 → 自定义指标」页经「从文件恢复」批量导入）
- 跳过：**10** 个（原因见末表，多为跨市场/Level2/流通股本等引擎无数据源）

## 成功列表

| 显示名 | 位置 | 输出列 | 转换说明 |
|---|---|---|---|
| ANGLE | 副图 | OUTPUT_1、OUTPUT_3、OUTPUT_4、OUTPUT_2 | 注入参数 N=10 |
| ATS | 副图 | RCA、HR | 直转 |
| BBIANDMA60 | 主图 | BBI、MA60、上穿条件、下穿条件 | 剔除绘图 DRAWICON；剔除绘图 DRAWICON |
| BDL | 副图 | ROYAL_KING、OUTPUT_1、OUTPUT_3、OUTPUT_4、OUTPUT_2 | 直转 |
| BIGMONEY | 主图 | KL、KT、OUTPUT_1 | 直转 |
| BLB | 副图 | BDL、BDNL、BDNL1 | 剔除绘图 STICKLINE |
| C-EMA200 | 副图 | 差值线、零轴 | 剔除绘图 STICKLINE；剔除绘图 STICKLINE |
| CTA | 副图 | CTAT、OUTPUT_1 | 直转 |
| DJIEV | 主图 | A1、A2、A3、A4、A5、A6、A9、A10、A11、A12 | 剔除不可复刻 ZIGZAG |
| DKZJL | 副图 | OUTPUT_1、OUTPUT_2 | 直转 |
| DROP | 副图 | 强弱识别、OUTPUT_1、OUTPUT_2 | 直转 |
| DTR | 副图 | FHC、FLC、信号1、信号2 | 动态REF→VALUEWHEN(信号当根值)；预替换近似；剔除绘图 STICKLINE；剔除绘图 DRAWTEXT；剔除绘图 STICKLINE；剔除绘图 DRAWTEXT；剔除绘图 STICKLINE；剔除绘图 DRAWTEXT；剔除绘图 STICKLINE；剔除绘图 DRAWTEXT；动态窗口→30近似；动态窗口→30近似；DRAWTEXT条件→信号1；DRAWTEXT条件→信号2 |
| FILL | 副图 | OUTPUT_1、OUTPUT_3、OUTPUT_4、OUTPUT_2 | 剔除绘图 STICKLINE；剔除绘图 STICKLINE |
| FVG | 副图 | SIGNAL、SIGNAL1 | 剔除绘图 DRAWICON；剔除绘图 DRAWICON；提升输出 SIGNAL,SIGNAL1 |
| H52 | 主图 | OUTPUT_1 | 直转 |
| HPS | 主图 | OUTPUT_1、OUTPUT_2、OUTPUT_3 | 直转 |
| JCJY | 主图 | C10、H10、L10、OUTPUT_1、OUTPUT_2 | 剔除不可复刻 REFX；剔除绘图 FILLRGN；剔除绘图 FILLRGN |
| KAGI | 副图 | A、B | 剔除绘图 DRAWLINE；剔除绘图 DRAWLINE；提升输出 A,B |
| LCS | 副图 | LCS、关键位置 | 直转 |
| Rking | 副图 | EE、DD、FF、GG | 剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；提升输出 EE,DD,FF,GG |
| RVC001 | 主图 | UP、DOWN、UP1、DOWN1、KO、KH、KL、KC、信号1、信号2 | 剔除绘图 DRAWICON；剔除绘图 DRAWICON；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；DRAWICON条件→信号1；DRAWICON条件→信号2；平均K线列→叠加K线(KO/KH/KL/KC… |
| RVC002 | 副图 | ATR | 剔除不可复刻 跨市场引用；剔除不可复刻 PERIOD；剔除不可复刻 PERIOD；剔除不可复刻 PERIOD；剔除绘图 DRAWNUMBER1；剔除绘图 DRAWNUMBER1；剔除绘图 DRAWNUMBER1；剔除绘图 DRAWCOLORKLINE；剔除绘图 DRAWCOLORKLINE；剔除绘图 DRAWCOLORKLINE；剔除绘图 DRAWTEXT；剔除绘图 DRAWTEXT；提升输出 ATR |
| RVC004 | 副图 | ROYAL_INDEX、OUTPUT_1、OUTPUT_2、OUTPUT_3、OUTPUT_4、OUTPUT_5 | 核心线提升为输出；DRAWNULL→空值；DRAWNULL→空值；DRAWNULL→空值；DRAWNULL→空值；DRAWNULL→空值 |
| RVC005 | 副图 | OUTPUT_1、OUTPUT_3、OUTPUT_4、OUTPUT_2 | 剔除不可复刻 跨市场引用；剔除不可复刻 WINNER；级联剔除 匿名；注入参数 M=10 |
| RVC006 | 副图 | DH、DL、DI、OUTPUT_1 | 直转 |
| RVC009 | 主图 | FTI | 剔除绘图 PARTLINE |
| RVC010 | 副图 | OUTPUT_1、OUTPUT_2、OUTPUT_3 | 直转 |
| RVC011 | 副图 | OUTPUT_1、OUTPUT_2 | 直转 |
| RVC012 | 副图 | CML、OUTPUT_1、OUTPUT_3、OUTPUT_2 | 剔除绘图 DRAWCOLORLINE |
| RVC013 | 主图 | OUTPUT_1、OUTPUT_2 | 直转 |
| RVC018 | 副图 | 主力、散户、总合、OUTPUT_1 | 直转 |
| RVOL | 副图 | MV20、D20、M20、信号1 | 剔除不可复刻 CJLVOL；剔除绘图 DRAWICON；注入参数 N=10；DRAWICON条件→信号1 |
| SD | 副图 | XSD、OUTPUT_1、OUTPUT_2、信号1、信号2 | 剔除绘图 VERTLINE；剔除绘图 DRAWICON；剔除绘图 DRAWICON；DRAWICON条件→信号1；DRAWICON条件→信号2 |
| SDC | 副图 | SD | 直转 |
| SEV-RVC | 主图 | A7、A8 | 剔除不可复刻 PERIOD；DRAWNULL→空值；DRAWNULL→空值；DRAWNULL→空值；DRAWNULL→空值；DRAWNULL→空值；DRAWNULL→空值；DRAWNULL→空值；DRAWNULL→空值；DRAWNULL→空值；DRAWNULL→空值；DRAWNULL→空值；DRAWNULL→空值；级联剔除 A2；级联剔除 A21；级联剔除 A3；级联剔除 A4；级联剔除 A5；级联剔除 A6；级联剔除 A9；级联剔除 A10；级联剔除 A11；级联剔除 A12；级联剔除 匿名；级联剔除 匿名；提升… |
| SIGMA | 副图 | OUTPUT_1、OUTPUT_2 | 注入参数 N=10 |
| SPIR | 副图 | TR、ATR、SPIR、OUTPUT_2、OUTPUT_1 | 直转；恒为空列(SPIR，原公式该路恒除零/恒假)仅作占位 |
| TC | 副图 | PR、VWAP、OUTPUT_1、OUTPUT_2、OUTPUT_3、OUTPUT_4、OUTPUT_5、OUTPUT_6 | 按月复位窗口→MC=20近似；按年复位窗口→YC=240近似；剔除绘图 VERTLINE；剔除绘图 VERTLINE |
| TCY | 副图 | PR、VWAPY、OUTPUT_1、OUTPUT_2、OUTPUT_3、OUTPUT_4、OUTPUT_5、OUTPUT_6 | 按月复位窗口→MC=20近似；按年复位窗口→YC=240近似；剔除绘图 VERTLINE |
| TT | 副图 | TYT | 直转 |
| VOL20 | 副图 | OUTPUT_1 | 剔除不可复刻 CJLVOL |
| VWAP | 副图 | VWAPY、U1、D1、U2、D2、U3、D3、OUTPUT_1 | 按日复位窗口→DC=20近似；预替换近似；剔除绘图 VERTLINE；注入参数 N=10 |
| WUYANYUAN1964 | 主图 | UP1、DOWN1、VAR1、VAR2、KO、KH、KL、KC | 剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；注入参数 F=8,M=10；提升输出 UP1,DOWN1,VAR1,VAR2；平均K线列→叠加K线(KO/KH/KL/KC) |
| WWW | 副图 | OUTPUT_1、OUTPUT_2、OUTPUT_3、OUTPUT_4 | 直转 |
| ZSCORE | 副图 | ZSCORE、强势线、风险线、异常线、零轴 | 直转 |
| 主宰V1 | 主图 | OUTPUT_1、OUTPUT_2、OUTPUT_3、OUTPUT_4、OUTPUT_5、OUTPUT_6、OUTPUT_7、OUTPUT_8、OUTPUT_9、OUTPUT_10 | 直转 |
| 全换手 | 主图 | CC | 剔除不可复刻 CAPITAL；剔除不可复刻 SUMBARS；级联剔除 HS；级联剔除 HSM；提升输出 CC |
| 基准点趋势分析指标 | 主图 | RISING_BP、FALLING_BP、CLOSE_PRICE | 剔除绘图 DRAWLINE；剔除绘图 DRAWLINE；剔除绘图 DRAWTEXT；剔除绘图 DRAWTEXT |
| 知行趋势线 | 主图 | 知行短期趋势线、知行多空线 | 注入参数 M1=5,M2=10,M3=20,M4=60 |
| 箱体 | 主图 | OUTPUT_1、OUTPUT_2、OUTPUT_3 | 直转 |
| 趋势识别 | 主图 | 收盘价、BBI、长周期BBI、信号1、信号2、信号3、信号4、信号5 | 剔除绘图 DRAWTEXT；剔除绘图 DRAWTEXT；剔除绘图 DRAWTEXT；剔除绘图 DRAWTEXT；剔除绘图 DRAWTEXT；DRAWTEXT条件→信号1；DRAWTEXT条件→信号2；DRAWTEXT条件→信号3；DRAWTEXT条件→信号4；DRAWTEXT条件→信号5 |
| 通道组合 | 主图 | EMA8、EMA13、EMA21、EMA55、EMA144、EMA169、EMA288、EMA338、信号1、信号2 | 剔除绘图 DRAWICON；剔除绘图 DRAWICON；DRAWICON条件→信号1；DRAWICON条件→信号2 |

## 跳过列表

| 显示名 | 原因 |
|---|---|
| BP-V2 | 仅剩裸行情引用，无指标信息 |
| BPM | 剔除不可复刻 SCALE；剔除不可复刻 SCALE；剔除绘图 DRAWNUMBER；剔除绘图 DRAWNUMBER；剔除绘图 DRAWNUMBER；剔除绘图 DRAWICON；级联剔除 DD；级联剔除后无剩余语句 |
| BPV3 | 剔除不可复刻 SCALE；剔除不可复刻 SCALE；剔除绘图 STICKLINE；剔除绘图 STICKLINE；剔除绘图 DRAWNUMBER；剔除绘图 DRAWNUMBER；级联剔除 买卖净额；级联剔除 X5日净额；级联剔除后无剩余语句 |
| BPV4 | 剔除不可复刻 SCALE；级联剔除 匿名；级联剔除后无剩余语句 |
| HLP | 仅剩常数参考线，无指标信息 |
| HZ | 剔除不可复刻 跨市场引用；级联剔除 RS；级联剔除 RSM；级联剔除 BZC；级联剔除 上轨；级联剔除 下轨；级联剔除后无剩余语句 |
| NRTR | 引擎验证失败：函数 REF 求值失败：REF 的周期参数必须是整数，得到 array([ 1., 2., 3., 4., 5., 6., 7., 8., 9., 10., 11., 12., 13., 14., 15., 0., 1., 0., 1., 2., 3., 0., 1., 2., 0., 1., 2., 3., 4., 5., 6., 7., 0., 0., 1., 2., 0., 0., 0., 1., 2., 0., 0… |
| RVC003 | 仅剩裸行情引用，无指标信息 |
| SM5 | 剔除不可复刻 跨市场引用；剔除绘图 PARTLINE；级联剔除 匿名；级联剔除后无剩余语句 |
| SV5 | 剔除不可复刻 跨市场引用；剔除绘图 PARTLINE；级联剔除 匿名；级联剔除后无剩余语句 |

## 口径说明

- 绘图语句（DRAWICON/DRAWTEXT/STICKLINE/VERTLINE 等）只管画图，
  不产出数值，转换时剔除，信号本身保留为输出列。
- `DRAWNULL` → 空值（不断线）；`STDP` 与 `STD` 同总体口径；
  `REVERSE(X)` 取负；`<>` 按 `!=` 求值；`ATAN` 由引擎补齐。
- `HHV/LLV(X,0)`（全历史最值）按 250 根近似；动态窗口按 30 根近似；
  VWAP/TC/TCY 的按日/月复位窗口按 20/240 近似。
- 原公式未给默认值的参数（N/M/F 等）注入默认值，明细见各条“转换说明”。
- DTR 的信号 Bar 动态 REF 改写为 `VALUEWHEN`
  （信号当根值前向延续，语义等价且无未来数据）。
