---
title: A 股日线监控与投资建议 Agent 蓝图
summary: 面向 A 股日线级别多头机会监控、筛选、分析、建议派发与后续交易扩展的业务 agent 蓝图和任务台账。
tags:
  - dev
  - a-share
  - agent
  - investment
  - roadmap
---

# A 股日线监控与投资建议 Agent 蓝图

本文档是 `a-share-monitor` 业务 agent 的唯一追踪入口。目标是在现有 KohakuTerrarium 架构之上，用一个真实复杂业务场景验证：

1. 多源数据采集与质量控制。
2. A 股日线级别做多机会筛选。
3. 基于策略约束的投资建议生成。
4. 可审计、可回测、可 paper trading 的业务闭环。
5. 未来对接投资平台自动挂单与交易的扩展边界。

本项目输出的内容用于研究、回测、模拟与系统验证，不直接构成任何现实投资建议；真实交易扩展必须默认关闭，并经过用户确认、风控限额、审计与合规检查。

## 1. 已确认前提

用户已确认以下方向：

- 股票范围：第一阶段覆盖沪深 A 股，不纳入北交所可交易股票；保留北交所扩展性，北交所数据可作为板块景气度和小盘风险偏好参考。
- 优化目标：以最终收益率为核心目标；最大回撤不作为固定全局目标，而是作为用户可配置风险偏好。
- 数据源：验证阶段优先免费数据源和公开 API；难以免费获取但高价值的权威数据可在后续接入付费源。
- 交易方向：只做多，不做空。
- 交易约束：默认考虑 T+1、涨跌停、停复牌、流动性、滑点和无法成交。
- 市场假设：A 股不按长期价值投资框架建模；政策、资金抱团、题材轮动、估值泡沫和财务质量风险必须进入过滤与风控。

## 2. 项目定位

第一阶段不做自动交易，而是做：

```text
EOD 日线数据采集 -> 数据质量检查 -> 市场环境判断 -> 板块强度筛选 -> 个股候选筛选 -> 风险收益比计算 -> 次日交易计划 -> 纸面验证
```

自动挂单只保留接口，不进入默认执行链。

推荐原因：

- A 股日内数据、集合竞价、涨跌停、T+1、停牌、滑点和交易接口权限都容易让直接实盘复杂度激增。
- 日线 EOD 策略足以验证架构的采集、筛选、分析、建议、审计和扩展能力。
- 先回测和 paper trading，能用最低成本验证策略是否有正期望。

## 3. 策略目标

策略不追求“看起来胜率高”，而是追求在用户风险偏好约束下的最终收益最大化。

核心评估指标：

| 指标 | 用途 |
|---|---|
| 年化收益 / 总收益 | 第一优化目标 |
| 最大回撤 | 用户风险偏好约束 |
| 收益回撤比 | 风险调整后的主评价指标 |
| 单笔期望值 | 判断策略是否有正期望 |
| 胜率 | 辅助指标，不单独优化 |
| 平均盈亏比 | 必须与胜率一起评估 |
| 换手率 | 约束交易成本与滑点 |
| 信号覆盖率 | 防止策略只在少数样本上过拟合 |

基础交易约束：

- 单笔计划盈亏比必须大于 `1.5`。
- 无法定义清晰止损位时不生成买入建议。
- 每个 `buy_watch` / `buy_ready` 建议都必须给出“卖出风险价位”，用于提示用户该交易计划何时失效；系统只提供风险提示，不替用户执行最终卖出决策。
- 不追连续一字板。
- 不使用单一 `risk_on / risk_off` 硬开关；当 `buy_permission` 为 `blocked` 时不新增买入，其余状态按板块强度、流动性、交易拥挤度和个股风险分层放行。
- 默认仓位建议由风险预算反推，而不是由主观置信度直接决定。

## 4. 初版策略：A 股日线强势回踩 / 平台突破组合

初版使用两个主信号和一个低优先级信号。

### 4.1 市场状态过滤

A 股市场状态不能按传统美股式“指数趋势 + 全市场上涨家数”做单一硬过滤。原因是：

- 个股分化长期存在，即使指数处于牛市，也可能有大量股票长期阴跌。
- 板块轮动和板块内部轮动明显，资金经常只集中在少数高景气度赛道，其余板块短暂跟随后继续回落。
- 急跌或跌幅过大时，可能出现权重股、宽基 ETF 或国家队资金托底迹象；这会修复指数和流动性，但不必然代表中小盘和普通个股立即安全。
- T+1、涨跌停和散户交易拥挤会放大次日无法退出风险，因此“今天全市场上涨”不应直接等价为“明天适合买入”。

因此市场层拆成两步：

1. `market_state`：描述市场结构状态。
2. `buy_permission`：给策略层的买入权限，不直接等同于状态名称。

建议状态：

| `market_state` | 含义 | 买入权限 |
|---|---|---|
| `liquidity_crisis` | 跌停扩散、成交塌缩或小盘流动性踩踏 | `blocked` |
| `policy_support_rebound` | 急跌后权重 / 宽基 ETF / 大盘指数被明显托住，跌停压力收敛 | `rebound_watch`，只观察修复最强板块 |
| `rotation_opportunity` | 全市场一般甚至偏弱，但少数板块成交额、相对强度和涨停梯队明显占优 | `rotation_only` |
| `broad_risk_on` | 指数、宽度、成交额和板块扩散同步改善 | `normal` |
| `mixed_chop` | 指数上蹿下跳、板块快速切换、宽度不稳定 | `selective` |
| `overheated_chase_risk` | 普涨或热门板块过热、融资/散户拥挤、顶背离增加 | `selective` 或 `blocked` |
| `unknown` | 数据不足 | `selective`，降低置信度 |

最小输入优先级：

- 全市场成交额及相对 20 日均值。
- 上涨 / 下跌家数、涨跌停数量、20 日新高 / 新低数量。
- 沪深 300、中证 500、中证 1000、创业板指、科创 50、上证指数、深证成指。
- 大盘 / 中盘 / 小盘指数分化，用于判断权重护盘和小盘踩踏。
- 板块成交额、板块相对强度、板块内涨停 / 大涨个股扩散度。
- 北证 50 或北交所成交活跃度，仅作为小盘风险偏好参考。
- 可得时加入北向、两融、ETF 份额、龙虎榜机构席位等资金代理。

买入触发原则：

- `blocked`：不新增买入；已有持仓进入风险复核。
- `rebound_watch`：不追权重护盘本身，只观察跌停压力收敛后是否向真实高景气板块扩散。
- `rotation_only`：允许来自强势板块的候选进入后续筛选，但普通弱板块不放行。
- `selective`：只允许技术面、板块、流动性、对手盘信号同时较强的少量候选。
- `normal`：允许常规策略运行，但仍必须满足个股流动性、盈亏比和卖出风险价位。

旧版“至少两个指数在 MA20 上方、上涨家数大于 50%”只能作为证据之一，不能作为硬性买入开关。

### 4.2 股票池过滤

排除：

- ST、*ST、退市风险、长期停牌、重大异常状态。
- 上市不足 120 个交易日的新股和次新股。
- 近 20 日日均成交额过低的股票。
- 已有重大异常状态的股票，例如 ST、退市风险、长期停牌或明确无法交易状态。
- 短期连续一字涨停导致无法合理成交的股票。
- 当日收盘接近跌停且流动性恶化的股票。

分层：

- 主板：涨跌幅约束、流动性和机构抱团影响较稳定，第一阶段主覆盖。
- 创业板 / 科创板：保留，但单独设置更高波动和更宽止损参数。
- 北交所：第一阶段不交易，只作为扩展市场和情绪参考。

### 4.3 板块强度过滤

候选股必须来自强势或转强板块。

板块评分输入：

- 5 日、20 日相对强度。
- 板块成交额相对 20 日均值。
- 板块内涨停 / 大涨个股数量。
- 板块内中军股、龙头股、补涨股是否形成梯队。
- 政策、产业、业绩、资金面催化是否存在。

### 4.4 个股信号 A：强趋势回踩

主策略，偏高胜率。

触发条件：

- 股价在 MA20、MA60 上方。
- MA20 上行，MA60 走平或上行。
- 近 20 日个股相对强度高于所属板块中位数。
- 回踩 MA10 / MA20 附近缩量企稳。
- 当日出现放量阳线、反包、突破短期下降趋势线或重新站上 MA5。
- EMA12 / EMA26 不处于空头发散状态。
- RSI14 从 40-55 区间回升，避免 RSI 已经严重超买后追入。
- MACD 柱体收缩后重新放大，或 DIF 上穿 DEA 后未明显背离。
- KDJ 的 K/D 从低位或中位转强，J 值极端高位时降低追入优先级。
- 当前价距离 MA20 不超过策略参数上限。

交易计划：

- 理想买入区间：次日不高开过多，回踩关键位不破。
- 止损：跌破 MA20、近期低点或信号 K 线低点。
- 目标：前高、箱体高度投影或固定 R 倍数。
- 要求：目标收益 / 止损风险大于 1.5。

### 4.5 个股信号 B：放量平台突破

次策略，偏趋势延续。

触发条件：

- 20-60 日箱体整理。
- 突破箱体上沿。
- 成交量大于 20 日均量 1.5 倍。
- 收盘价靠近当日高位。
- 距离 MA20 不过度乖离。
- EMA 短周期上穿或保持在长周期上方。
- MACD 不出现明显顶背离。
- RSI 未进入极端高位钝化后的衰减状态。

风险控制：

- 次日高开过大不追。
- 跌回箱体内视为突破失败。
- 涨停无法成交时只记录为错过机会，不用涨停价假设成交。

### 4.6 观察项 C：超跌修复

不作为买入信号。仅在市场从 `liquidity_crisis` 切换为 `policy_support_rebound` 或 `mixed_chop` 后观察，用于发现风险释放后的修复方向，但不能左侧赌底部和反转。

观察条件：

- 板块同步修复。
- 个股放量站回短期均线，但仍需等待右侧结构确认。
- 下跌趋势线突破后形成回踩不破或平台再突破。
- 止损位非常明确，且后续必须通过盈亏比检查。
- RSI / KDJ 出现底背离或从低位修复。
- MACD 绿柱收敛，DIF 向 DEA 靠拢或形成低位金叉。

限制：

- `oversold_reversal` 不得作为 `buy_ready` 或 `buy_watch` 的 setup。
- 底背离和超跌修复只能作为观察证据，不能绕过 C3 的右侧信号门。
- 真正进入候选的 setup 仍只能是 `trend_pullback` 或 `platform_breakout` 等右侧形态。

### 4.7 卖出风险价位与失效提示

买入建议必须同时给出卖出风险价位。该价位不是自动卖出指令，而是“该笔交易原始逻辑失效”的风险提示线，最终是否卖出由用户判断。

卖出风险价位分为三类：

| 类型 | 作用 | 推荐触发依据 |
|---|---|---|
| `technical_exit_price` | 技术面失效价 | 跌破 MA20 / 平台上沿 / 信号 K 线低点 / 近期 swing low / ATR 风险带 |
| `fundamental_exit_trigger` | 基本面风险触发 | 业绩预告显著低于预期、监管处罚、审计异常、重大减持、商誉或应收账款风险暴露 |
| `time_exit_rule` | 时间止损 | 买入后 N 个交易日未按预期走强、跌破相对强度阈值、板块热度衰减 |

推导原则：

- 技术面风险价必须优先使用可量化价格，例如 `min(MA20, recent_swing_low, signal_candle_low) - buffer`。
- `buffer` 可由 ATR、市场板块波动率或用户风险偏好决定。
- 若技术面风险价距离入场价过远，导致仓位过小或盈亏比低于 1.5，则拒绝该买入建议。
- 基本面风险不一定能转化为单一价格，但必须转化为“风险事件触发条件”。一旦触发，应提示用户重新评估持仓。
- 若价格没有跌破技术风险价，但基本面风险事件触发，建议状态应从 `buy_ready` 降级为 `hold_review` 或 `exit_review`。
- 对涨停、跌停、停牌、重大公告前后等无法稳定成交场景，风险价位只能作为提示，不假设一定成交。

基础卖出风险提示规则：

- 趋势回踩型：跌破 MA20、回踩低点或信号 K 线低点，取更贴近交易逻辑的一项作为主风险价。
- 平台突破型：有效跌回平台上沿下方，或突破 K 线低点被跌破。
- 超跌修复观察：跌破修复 K 线低点或再次放量新低，仅作为观察失败提示，不作为买入策略。
- 板块失效：所属板块相对强度跌出前 50%，且个股同步跌破短期均线。
- 基本面失效：业绩、现金流、监管、解禁、减持等事件使原有做多逻辑不成立。

### 4.8 技术指标与背离形态

有必要纳入 RSI、EMA、MACD、KDJ 和顶 / 底背离，但它们应作为“确认层”和“风险提示层”，不应单独生成买入信号。

纳入原因：

- A 股短中线资金博弈强，动量衰减和背离常常先于价格破位出现。
- 均线和 K 线形态只描述价格位置，RSI / KDJ / MACD 能补充动量、速度和趋势强弱。
- 顶背离有助于降低追高和末端加速风险；底背离只能用于观察超跌修复质量，不能单独触发买入。

使用原则：

- 指标不直接决定买入，只提高或降低候选评分。
- 背离必须结合价格结构和成交量确认，不能只比较指标数值。
- 同一类动量指标高度相关，避免 RSI、KDJ、MACD 重复加权导致过拟合。
- 日线策略第一阶段只计算日线指标；后续可扩展周线共振和 60 分钟辅助确认。

建议指标：

| 指标 | 参数 | 用途 |
|---|---|---|
| EMA | EMA5 / EMA10 / EMA20 / EMA60 / EMA12 / EMA26 | 趋势方向、短中期均线结构、MACD 计算基础 |
| RSI | RSI6 / RSI14 | 判断超买超卖、动量修复、顶底背离 |
| MACD | 12 / 26 / 9 | 趋势动能、金叉死叉、柱体扩张 / 收敛、背离 |
| KDJ | 9 / 3 / 3 | 短周期动量拐点、超买超卖、辅助背离 |
| ATR | ATR14 | 风险价 buffer、波动率过滤、仓位反推 |

背离定义：

- 顶背离：价格创阶段新高，但 RSI / MACD DIF / MACD histogram / KDJ 未创新高，且成交量或板块强度同步衰减。
- 底背离：价格创阶段新低，但 RSI / MACD DIF / MACD histogram / KDJ 未创新低，且跌幅收敛或放量止跌。
- 有效背离至少需要两个 swing point，且 swing point 间隔不得过短。
- 背离输出为 `bullish_divergence / bearish_divergence / none`，并保留证据字段，不由 LLM 临场主观判断。

评分建议：

```text
technical_score =
  trend_score
  + momentum_score
  + volume_price_score
  + divergence_score
  - overextension_penalty
```

其中 `divergence_score` 只作为修正项：底背离提高观察优先级，顶背离降低买入优先级或触发 `exit_review`。

### 4.9 散户 / 机构对手盘意识

需要显式纳入。A 股很多短中线机会不是单纯由价格形态决定，而是由筹码从弱手向强手转移、或从强手向弱手派发所驱动。系统不能把“放量上涨”“资金流入”“热度上升”直接等价为正向信号，必须判断这些信号更像机构布局，还是散户拥挤后的接盘风险。

原则：

- 散户大量涌入、机构席位或中长期资金退出的板块 / 标的，应作为风险警示，降低买入优先级；若同时出现顶背离、放量滞涨、龙虎榜机构净卖出、大宗交易折价、股东户数快速上升等证据，应触发 `reject` 或 `buy_watch` 降级。
- 散户大量离场、户均持股上升、机构或北向 / 基金 / ETF 等中长期资金开始布局，并叠加趋势修复、底背离、缩量企稳或平台突破时，可提高观察优先级。
- 散户和机构持仓通常无法被实时、完整、精确观察，因此第一阶段使用代理指标组合，不把单一数据源当作真相。
- 对手盘信号只作为确认层和风险层，不单独生成买入信号；最终仍需通过市场环境、板块强度、技术形态、盈亏比和卖出风险价位约束。

建议代理指标：

| 代理指标 | 倾向解释 | 注意事项 |
|---|---|---|
| 股东户数变化 | 户数快速上升常意味着筹码分散、散户拥挤；户数下降且户均持股上升可能意味着筹码集中 | 披露频率低，有滞后 |
| 户均持股变化 | 户均上升可作为筹码集中参考 | 需要结合价格位置和成交量 |
| 北向持股变化 | 可作为外资 / 机构偏好代理 | 非所有行业都适用 |
| 融资余额与融资买入占比 | 短期杠杆资金拥挤度代理 | 上涨末端融资快速扩张要警惕 |
| 龙虎榜机构席位 | 短期机构净买 / 净卖线索 | 只覆盖异动股票，样本偏差大 |
| 大宗交易折溢价与金额 | 折价大宗和连续减持可能提示派发风险 | 需要结合公告与锁定期 |
| 基金持仓变化 | 中长期机构配置代理 | 季报滞后明显 |
| ETF 份额 / 资金流 | 板块级配置热度代理 | 被动资金和主动观点需要区分 |
| 重要股东减持 / 解禁 / 质押 | 潜在供给压力和风险事件 | 应进入 `fundamental_exit_trigger` |

标准化输出为 `ownership_flow_signal`：

```yaml
symbol:
trade_date:
retail_crowding_score:
institutional_accumulation_score:
institutional_exit_score:
counterparty_signal: retail_institution_exit_risk | retail_exit_institution_accumulation | mixed | unknown
evidence:
data_lag_days:
```

策略解释：

- `retail_institution_exit_risk`：散户拥挤、机构退出风险。若为买入候选，必须降级或拒绝，除非有更强的反证。
- `retail_exit_institution_accumulation`：散户离场、机构布局线索。若技术面和板块强度同步确认，可提高候选优先级。
- `mixed`：证据冲突，只作中性或轻微修正。
- `unknown`：数据不足，不加分，必要时降低置信度。

### 4.10 板块景气度衡量

A 股日线策略不应只使用通用宏观景气指标，也不存在单一特殊指标可以直接判断板块是否值得交易。更合适的做法是拆成两层：

1. 日线交易景气：用于当天筛选，优先使用板块相对强度、成交额放大、板块内涨停 / 大涨扩散、板块轮动位置、资金代理和指数风格分化。
2. 行业基本面景气：用于中低频确认和风险注释，可参考 PMI、PPI、行业产量 / 价格 / 库存 / 利润 / 产能利用率、订单与出口等数据。

第一阶段 C2 只实现日线交易景气，因为它最容易从免费行情与本地 fixture 中验证，也最符合“先市场状态，再板块，再个股”的成本路径。

基本原则：

- `rotation_only` 状态下，只允许 C1 确认的活跃板块进入后续股票池阶段。
- `selective` 状态下，只允许相对强度、成交额和当日表现同时不弱的板块进入后续阶段。
- `normal` 状态下，板块强度仍用于排序和仓位优先级，不取消个股风控。
- 慢变量行业景气不能替代日线流动性和轮动确认；它只能作为解释、加分或风险注释。
- 基本面风险事件不作为前置筛选硬条件；对已经满足买入要求的个股，只在最终建议阶段输出 `fundamental_exit_trigger` 和 `fundamental_risk`，由用户自行判断。

第一版板块评分：

```text
sector_score =
  relative_strength_5d
  + relative_strength_20d
  + amount_ratio_20d
  + daily_pct_change
  + rotation_bonus
```

后续可扩展数据：

- 国家统计局 PMI、PPI、工业企业利润、库存、产能利用率。
- 行业产量、价格、订单、出口、库存周期。
- ETF 份额变化、北向 / 两融 / 龙虎榜 / 大宗交易等资金代理。
- 产业政策、业绩预告与行业高频数据。

## 5. 数据需求

### 5.1 行情与交易状态

- 股票列表、证券代码、交易所、板块、上市日期。
- 日线 OHLCV。
- 前复权 / 后复权价格。
- 成交额、换手率、振幅。
- 涨跌停价格。
- 停复牌状态。
- ST / 退市风险标记。
- 新股、次新股标记。
- ATR、均线、近期 swing high / swing low、平台上下沿等用于推导风险价位的技术特征。
- RSI、EMA、MACD、KDJ、ATR、相对强度、背离形态等本地计算后的技术指标。
- 技术指标计算所需的完整历史窗口，至少覆盖最长参数的 3 倍以上，例如 MA60 至少需要 180 个交易日用于稳定预热。

### 5.2 指数与市场宽度

- 沪深 300、中证 500、中证 1000、创业板指、科创 50、上证指数、深证成指。
- 北证 50 或北交所相关指数，只作为景气度参考。
- 上涨 / 下跌家数。
- 涨停 / 跌停数量。
- 创 20 日新高 / 新低数量。
- 全市场成交额。

### 5.3 板块与主题

- 申万 / 中信 / 东方财富行业板块。
- 概念板块。
- 板块日线行情。
- 板块成交额、涨跌幅、相对强度。
- 板块内成分股。
- 板块内涨停、强趋势、突破个股数量。

### 5.4 资金流与交易行为

- 个股资金流。
- 行业 / 概念资金流。
- 北向资金，若免费源可稳定获取。
- 融资融券余额变化。
- 龙虎榜。
- 大宗交易。
- ETF 资金流。
- 股东户数、户均持股、前十大流通股东变化。
- 基金持仓变化，优先作为低频中长期配置代理。
- 重要股东增减持、解禁、质押等筹码供给压力。
- 板块级散户拥挤与机构布局代理信号。
- `ownership_flow_signal` 对手盘信号，用于识别散户接盘风险与机构布局机会。

### 5.5 财务与风险事件

- 营收、净利润、扣非净利润。
- 经营现金流。
- 资产负债率。
- 商誉。
- 应收账款。
- 业绩预告 / 业绩快报。
- 审计意见。
- 监管问询、处罚、立案调查。
- 股东减持、解禁、质押。
- 基本面风险事件发生日期与公告日期，用于触发 `fundamental_exit_trigger`，避免未来函数。

### 5.6 策略运行与回测数据

- 至少 3-5 年历史日线。
- 停牌、退市、ST 历史状态。
- 指数和板块历史成分变化。
- 历史公告发布日期，防止未来函数。
- 交易成本、滑点、涨跌停无法成交规则。
- T+1 持仓约束。

## 6. 数据源分层

验证阶段优先免费源。

| 层级 | 数据源 | 用途 | 备注 |
|---|---|---|---|
| L0 | 本地 CSV / Parquet fixture | 最小验证、单元测试 | 第一阶段必须先支持 |
| L1 | AkShare | A 股行情、指数、板块、资金、北交所参考 | 免费源，适合验证；字段稳定性需用 adapter 隔离 |
| L1 | baostock | 历史行情、基础财务 | 免费源，可作为 AkShare 兜底 |
| L1 | 交易所 / 巨潮 / 公开公告 | 公告、监管、事件 | 需要缓存和解析层 |
| L1 | 交易所公开数据 / 港交所公开查询 | 融资融券、龙虎榜、陆股通持股等对手盘代理 | 字段和频率按来源隔离 |
| L1.5 | TradingView 页面 / 手工导出 | 人工校验、可视化、技术字段参考 | 不作为默认自动化数据源；自动抓取和批量使用需谨慎处理授权与稳定性 |
| L2 | Tushare Pro | 更完整的行情、财务、公告 | 验证阶段可选，部分接口需要积分或 token |
| L2 | TradingView 付费订阅 / 市场数据订阅 | 图表、更多历史 bars、指标、导出和交易所数据参考 | 更适合人工分析和校验；不是第一阶段后端主数据源 |
| L3 | Wind / Choice / iFinD | 权威商用数据 | 策略稳定后再接 |

原则：

- 所有外部源必须通过 `data_adapter` 抽象层接入。
- 策略逻辑不得直接依赖某个第三方字段名。
- 数据获取必须分阶段执行，不允许默认一次性获取全市场所有个股细节再筛选。
- 第一版最小验证只依赖本地 fixture，避免网络、接口限流和字段漂移。
- 技术指标默认由本地 OHLCV 计算，不直接依赖 TradingView 的指标结果。
- TradingView 只作为可选 reference provider；若未来使用其数据，必须先确认订阅、交易所授权和使用条款。

### 6.1 分阶段数据获取顺序

正式运行必须按以下顺序获取和处理数据：

1. 市场状态层：先读取前一交易日宏观市场数据，包括流动性变化、上涨 / 下跌家数、涨跌停压力、主要上涨和下跌板块、指数与大小盘分化、板块成交额和主力资金代理信号。输出 `market_state`、`buy_permission` 和允许继续观察的板块范围。
2. 股票池风险层：只有当 `buy_permission` 不是 `blocked` 时，才读取股票池信息，并排除 ST、退市风险、停牌、次新股、流动性不足、散户拥挤且机构退出等高风险个股。基本面风险事件不在此阶段作为硬排除条件。
3. 板块候选层：只在存在机会的板块内继续获取低风险个股列表，优先处理高景气度、资金集中、相对强度改善的板块。
4. 个股技术层：只对前面阶段留下的候选标的计算 EMA、RSI、MACD、KDJ、ATR、相对强度和背离证据，判断是否达到高赔率入场点。

这个顺序是成本控制和风险控制的一部分：若市场层没有机会，不应浪费 token、接口额度和计算资源去拉全市场个股细节；若板块层没有机会，也不应对弱势板块里的个股强行寻找技术形态。

参考：

- AkShare 股票数据文档：https://akshare.akfamily.xyz/data/stock/stock.html
- TradingView 中国股票页面：https://www.tradingview.com/markets/stocks-china/market-movers-all-stocks/
- TradingView 价格与功能页：https://www.tradingview.com/pricing/
- TradingView Charting Library Datafeed API：https://www.tradingview.com/charting-library-docs/latest/connecting_data/Datafeed-API/

## 7. Agent 架构

第一阶段建议创建独立 package：`examples/a-share-monitor/`。

### 7.1 Creature 角色

| 角色 | 职责 | 是否高频 |
|---|---|---|
| `market-root` | 接收用户目标、风险偏好、输出最终建议 | 高频 |
| `data-collector` | 获取行情、指数、板块、资金、公告数据 | 高频 |
| `data-auditor` | 检查缺失、异常、未来函数、停牌和复权问题 | 高频 |
| `regime-analyst` | 判断 A 股市场状态与买入权限：`market_state` / `buy_permission` | 高频 |
| `sector-analyst` | 计算板块强度与景气度 | 高频 |
| `stock-screener` | 执行股票池过滤和形态识别 | 高频 |
| `risk-manager` | 计算止损、目标价、盈亏比、仓位 | 高频 |
| `recommendation-writer` | 生成用户可读交易计划 | 高频 |
| `strategy-critic` | 检查建议是否违反策略、风控和数据质量约束 | 高频 |
| `backtest-analyst` | 回测和绩效分析 | 低频 |
| `execution-adapter` | paper order / future broker adapter | 默认关闭 |

### 7.2 推荐 Terrarium

最小链路：

```text
market-root
  -> data-collector
  -> data-auditor
  -> regime-analyst
  -> sector-analyst
  -> stock-screener
  -> risk-manager
  -> recommendation-writer
  -> strategy-critic
  -> market-root
```

第一版实现不需要每个节点都是真实 LLM creature。低层计算应优先做成 deterministic tool / Python module，再由少量 creature 负责编排和解释，降低成本和漂移。

## 8. 核心模块边界

| 模块 | 建议形态 | 原因 |
|---|---|---|
| 数据下载 | Python module + tool | 可测试、可缓存、低 token |
| 指标计算 | Python module | 避免 LLM 算数 |
| 策略筛选 | Python module | 必须可回测 |
| 风险收益比 | Python module | 必须确定性 |
| 卖出风险价位 | Python module | 必须确定性；LLM 只解释原因，不负责计算 |
| 背离检测 | Python module | 必须确定性；输出 swing point 与指标证据 |
| 建议生成 | creature / skill | 需要文本表达 |
| 策略审查 | creature + deterministic checks | 文本审查与硬规则结合 |
| 自动交易 | plugin / adapter | 默认关闭，强审计 |

## 9. 输出契约

单只股票建议必须输出：

```yaml
symbol:
name:
decision: buy_watch | buy_ready | reject
trade_date:
next_action_date:
setup_type:
entry_zone:
stop_loss:
technical_exit_price:
technical_exit_reason:
fundamental_exit_trigger:
time_exit_rule:
target_1:
target_2:
risk_reward:
position_size:
holding_period:
invalidation:
market_regime:
sector_reason:
technical_reason:
technical_indicators:
divergence:
fundamental_risk:
ownership_flow_risk:
liquidity_risk:
data_quality:
confidence:
audit_notes:
```

其中 `fundamental_risk` 与 `fundamental_exit_trigger` 是最终建议阶段的保险提示，不是前置筛选条件。系统只负责揭示风险和失效条件，最终是否继续执行交易计划由用户判断。

组合级输出必须包含：

- 当日市场环境。
- 允许新增仓位比例。
- 候选列表。
- 拒绝列表及拒绝原因。
- 风险集中度。
- 次日观察事项。

## 10. 风险偏好配置

用户可配置：

```yaml
risk_profile:
  name: balanced
  max_portfolio_drawdown: 0.15
  max_single_position_risk: 0.01
  max_position_size: 0.2
  max_total_exposure: 0.8
  min_risk_reward: 1.5
  max_exit_distance_pct: 0.08
  max_hold_days_without_confirmation: 5
  allow_chinext: true
  allow_star_market: true
  allow_bse_trading: false
  use_bse_as_sentiment_reference: true
```

风险偏好不是策略目标本身，而是收益最大化过程中的约束条件。

## 11. 自动交易扩展边界

第一阶段不接真实交易。

保留接口：

```text
trade_signal -> paper_order -> broker_adapter -> order_status -> audit_log
```

真实交易启用前必须满足：

- 至少一个稳定回测周期。
- 至少一个 forward paper trading 周期。
- 人工确认开关。
- 单笔和单日风险限额。
- 撤单 / 失败重试策略。
- 交易日志和审计记录。
- 平台 API 合规确认。

## 12. 任务 Todo

状态值：

- `已完成`：已在当前仓库完成并可验证。
- `进行中`：已开始但未达到完成标准。
- `待开始`：尚未实现。
- `待重构`：已有雏形但不符合当前蓝图。

### 任务组 A. 蓝图与边界

- [x] `A0` 创建 A 股监控 agent 业务蓝图
  - 状态：已完成
  - 解决问题：业务目标、策略原则、数据需求、agent 架构和交易扩展边界未统一
  - 交付物：`docs/zh-CN/dev/a-share-monitor-blueprint.md`
  - 完成标准：明确股票范围、优化目标、数据源分层、策略框架、输出契约和任务台账

- [x] `A1` 创建 `a-share-monitor` package 骨架
  - 状态：已完成
  - 解决问题：业务 agent 缺少独立 package，不能与 `test-kit` 分离迭代
  - 适合模块：`examples/a-share-monitor`
  - 交付物：`kohaku.yaml`、README、基础目录、fixtures、scripts
  - 完成标准：可被 `kt install -e` 识别，且不污染 `test-kit`
  - 备注：已新增 `examples/a-share-monitor/`、最小 `lab-runner` creature、Python 模块占位、schema / fixture / script 目录占位，以及 `verify_a1_package_skeleton.py` 验证脚本。

### 任务组 B. 数据契约与最小 fixture

- [x] `B1` 定义 market data schema
  - 状态：已完成
  - 解决问题：外部数据源字段不稳定，策略不能直接绑定第三方字段名
  - 适合模块：`examples/a-share-monitor/data-schema`
  - 完成标准：覆盖日线、指数、板块、资金、交易状态、财务风险和推荐输出
  - 备注：已新增 `examples/a-share-monitor/data-schema/market-data-schema.yaml` 与 `verify_b1_market_data_schema.py`；schema 覆盖 security master、daily/index/sector bars、market breadth、technical indicators、divergence、fundamental risk events、ownership flow signals、sector score、stock signal 与 recommendation，并明确 TradingView 只作为可选 reference provider。

- [x] `B2` 创建最小本地 fixture
  - 状态：已完成
  - 解决问题：最小验证不能依赖网络和实时 API
  - 适合模块：`examples/a-share-monitor/fixtures`
  - 完成标准：包含至少 5 只样例股票、2 个指数、2 个板块、60 个交易日以上日线
  - 备注：已新增 `fixtures/b2_minimal/` 合成离线数据集、`generate_b2_fixture.py` 生成脚本与 `verify_b2_offline_fixture.py` 验证脚本；当前 fixture 包含 5 只可交易样例股、1 个北交所参考项、3 个指数、2 个板块、180 个交易日和对手盘代理信号，全部可在无网络环境下验证。

- [x] `B3` 实现数据加载 adapter
  - 状态：已完成
  - 解决问题：fixture、AkShare、baostock、付费源需要统一接口
  - 适合模块：`examples/a-share-monitor/a_share_monitor/data`
  - 完成标准：最小验证可从 fixture 加载统一数据对象
  - 备注：已新增 `a_share_monitor/data/models.py`、`a_share_monitor/data/fixture_adapter.py` 与 `verify_b3_fixture_adapter.py`；当前 adapter 可将 B2 CSV fixture 加载为统一 `MarketDataset`，并覆盖可交易股票、北交所参考项、日线、指数、板块、市场宽度、风险事件和对手盘代理信号。

### 任务组 C. 策略与风控

- [ ] `C0` 实现技术指标与背离检测
  - 状态：待开始
  - 完成标准：基于本地 OHLCV 计算 EMA、RSI、MACD、KDJ、ATR、相对强度、顶背离和底背离，并输出可回测的证据字段；只对 C1/C2/C3 后留下的候选标的计算，不做无条件全市场扫描

- [x] `C1` 实现 A 股市场状态判断
  - 状态：已完成
  - 完成标准：输出 `market_state`、`buy_permission` 与证据；状态至少覆盖 `liquidity_crisis`、`policy_support_rebound`、`rotation_opportunity`、`broad_risk_on`、`mixed_chop`、`overheated_chase_risk` 和 `unknown`，不得用单一指数趋势或上涨家数阈值作为硬开关
  - 备注：已新增 `a_share_monitor/strategy/market_state.py` 与 `verify_c1_market_state.py`；C1 只读取 `load_market_context()`，不读取全量股票池、个股日线、个股对手盘或基本面风险事件。

- [x] `C2` 实现板块强度评分
  - 状态：已完成
  - 完成标准：输出板块相对强度、成交额放大和景气度参考
  - 备注：已新增 `a_share_monitor/strategy/sector_strength.py` 与 `verify_c2_sector_strength.py`；C2 只读取市场状态和板块历史，不读取全量股票池、个股日线、个股对手盘或个股基本面风险事件。

- [x] `C3` 实现个股过滤、右侧信号识别与观察列表
  - 状态：已完成
  - 完成标准：只在 C2 放行板块内读取股票池和候选个股；只允许明确右侧信号进入候选，例如强趋势回踩和平台突破；不交易左侧抄底、赌底部或未确认反转，`oversold_reversal` 不得作为买入候选；散户 / 机构对手盘信号作为确认层和风险层；技术面尚未达标但基础条件通过的个股进入 `watchlist`，用于后续增量跟踪。
  - 备注：已新增 `a_share_monitor/strategy/stock_screen.py` 与 `verify_c3_stock_screen.py`；C3 不读取完整数据集，不读取基本面风险事件，基本面风险保留到最终建议阶段作为用户判断用的保险提示；当前输出分为 `candidate`、`watchlist`、`rejected` 三类。

- [ ] `C4` 实现风险收益比与仓位计算
  - 状态：待开始
  - 完成标准：所有买入候选必须满足 `risk_reward > 1.5`，并输出技术面卖出风险价位、风险价依据、基本面风险触发条件、对手盘风险提示和时间止损规则

### 任务组 D. Agent 与 Terrarium

- [ ] `D1` 创建最小单 creature 分析入口
  - 状态：待开始
  - 完成标准：能读取 fixture 并生成结构化候选报告

- [ ] `D2` 创建最小 terrarium
  - 状态：待开始
  - 完成标准：完成 `data -> regime -> screen -> risk -> recommendation -> critic` 的最短链路

- [ ] `D3` 添加策略审查 critic
  - 状态：待开始
  - 完成标准：能拒绝盈亏比不足、缺少卖出风险价位、数据缺失、追高、一字板和风险偏好冲突的建议

### 任务组 E. 验证与回测

- [ ] `E1` 建立最小离线验证脚本
  - 状态：待开始
  - 完成标准：无网络运行，验证 schema、fixture、技术指标、背离形态、策略输出、风险收益比、卖出风险价位和拒绝原因

- [ ] `E2` 建立简单事件驱动回测
  - 状态：待开始
  - 完成标准：考虑 T+1、涨跌停、交易成本、滑点和无法成交

- [ ] `E3` 建立 paper trading 日志格式
  - 状态：待开始
  - 完成标准：能记录信号、计划、模拟订单、成交假设、持仓和退出原因

### 任务组 F. 外部数据源与交易扩展

- [ ] `F1` 接入 AkShare adapter
  - 状态：待开始
  - 完成标准：在可用网络环境下拉取 A 股日线、指数、板块和基础资金数据

- [ ] `F2` 接入 baostock fallback
  - 状态：待开始
  - 完成标准：作为历史行情和基础数据兜底

- [ ] `F3` 设计 broker adapter 接口
  - 状态：待开始
  - 完成标准：只支持 paper order，不包含真实下单实现

## 13. 当前优先级

下一项任务：

```text
C0 实现技术指标与背离检测
```

理由：

- schema、fixture 与 fixture adapter 已经存在。
- 市场状态层 C1、板块强度层 C2 与右侧股票筛选 / 观察列表层 C3 已经完成。
- 下一步应进入 C0 技术指标与背离检测，但只对 C3 留下的 `candidate` 与 `watchlist` 标的做增量计算，不做全市场扫描。
- 背离和超跌信息只能作为确认或风险提示，不得绕过 C3 的右侧信号门。

## 14. 每项任务完成规则

后续每完成一项，必须：

1. 更新本文档对应任务状态。
2. 提供可运行验证方式。
3. 若涉及 Python 代码，补充最小测试或验证脚本。
4. 保持 Linux / Windows 双端路径兼容。
5. 完成一项后暂停，等待用户验收。
