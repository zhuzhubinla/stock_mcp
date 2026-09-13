# Phase 7（Macro→Industry Transmission Engine）差距分析报告

> 依据：《Stock Agent Phase 7 — Industry Transmission Engine 设计文档》V1.0（2026-09-03）
> 对照代码库：`/home/admin/stock_agent`（截至 2026-09-03）
> 结论口径：**已有 / 部分 / 缺失**；本报告只读分析，未改动任何代码与表结构。

---

## 一、核心结论（摘要）

1. **系统已具备 Phase 7 的"地基"，但缺"传导层"本体**：行业主数据（`industry` 树 + `industry_company` 暴露度 + `industry_factor` 含 macro 类型 + `industry_indicator` 承载 FRED 宏观序列）、Regime 检测（`market_regime` + `regime_detector.py`）、因子→财务弹性传导（`financial_driver` + Factor-First）、事件→标的路径映射（prediction KG）全部已有。缺的是：**宏观因子规范层（信号方向/标准化）、宏观因子→行业的敏感性矩阵、可计算的加权传导图、Regime/Event/Horizon 修正、industry_macro_score 落库**。
2. **"macro" 目前是个伪行业**：FRED 宏观序列（INDPRO/CPI/UMCSENT）挂在名为 `macro` 的伪行业下做指标存储，Regime 宏观分直接读它。没有"宏观因子→各实体行业"的敏感性概念——这是 Phase 7 与现状最本质的差别。
3. **两张现成可复用的图**：`industry_chain_node/edge`（产业链图，含 relation_type）与 prediction KG（`prediction_signal.propagation_path` 字符串路径）提供了"节点+边+路径"的模式先例，但**都缺 Phase 7 需要的边属性：weight/direction/confidence/lag/model_version**，且路径传播目前是硬编码/规则映射，非数值化加权计算。
4. **信号与学习基建可平移**：`signals/`（normalizer/decay/confidence/conflict）、`learning/online_calibration.py`（IC→动态权重、版本化、防泄漏）、`market_regime` 快照机制、`jobs/` + cron 调度模式，都可被 Phase 7 直接复用；Exposure Learning（V2 回归）与监控可复用 Phase 8 的校准/回测框架。
5. **落地量级适中**：核心新增 ≈ 4 张表 + 1 个 macro 因子/信号层 + 1 个 transmission 引擎 + 1 个行业打分器 + MCP 工具包装；不涉及现有表重构，全部可增量叠加。

---

## 二、差距矩阵（设计文档组件 → 现状）

| 设计文档组件 | 现有实现位置 | 状态 | 差异备注 |
|---|---|---|---|
| Macro Factor 定义（8 因子） | `industry_factor.factor_type='macro'`（种子） | 部分 | 因子按行业存，无全局因子表；**无方向约定**（如 FED_POLICY +1 含义），无法判符号一致性 |
| 宏观原始数据 | `data/collectors/fred_industry.py`（INDPRO/CPIAUCSL/UMCSENT）→ `industry_indicator`；prediction 源 Kalshi/Metaculus | 部分 | 仅 3 条月频序列；缺 NFP/CPI 日历、2Y/10Y、DXY、VIX、油价、FedWatch；无实际值/共识/前值结构 |
| Surprise / Z-Score / Macro Signal [-1,+1] | `signals/normalizer.py`（个股信号用） | 缺失 | 无宏观信号归一化层；无 consensus-available_at 版本化（数据泄露控制点） |
| Industry Exposure（宏观因子→行业敏感性） | `industry_company`（公司↔行业）、`industry_factor.impact_direction/importance` | 缺失 | 无 `macro_industry_exposure`（因子×行业×regime×horizon×版本）；敏感性表语义（10Y→半导体 -0.75）不存在 |
| EffectiveExposure 乘数（Regime/Event/Horizon） | — | 缺失 | 无乘数模型；`industry_company.effective_date/expire_date` 提供有效期版本先例 |
| Direct Transmission | `financial_driver`（指标→公司财务影响，Factor-First） | 部分 | 已有单指标→财务弹性；无"宏观变量→行业"直传语义（利率→折现率→成长股） |
| Indirect Transmission（多跳） | prediction KG：`prediction_signal.propagation_path`（"AI CapEx→Data Center→GPU→NVDA"） | 部分 | 有路径传播先例，但**字符串硬映射、无权重/置信度/时滞/衰减** |
| Transmission Graph（Node/Edge 数值化） | `industry_chain_node/edge`、`prediction_event/prediction_signal` | 缺失 | 无 `macro_transmission_edge`（weight/direction/confidence/lag/version）；现有链边无 confidence/lag |
| PathScore + 路径衰减 | `signals/decay.py`（时间衰减 exp(-λt)） | 缺失 | decay.py 是时间衰减非路径衰减；无多跳衰减与置信度连乘处理 |
| Regime 修正（Goldilocks/Overheating/Recession/Stagflation） | `context/regime_detector.py` → `market_regime`（仅 risk_on/risk_off/neutral） | 部分 | 市场风险偏好已有；**宏观四态 regime 缺失**，无 regime 乘数 |
| Event 修正（1.0/1.5/2.0） | `event` 表（event_type/industry_id/impact_score） | 部分 | 表结构够用；无事件级别分级与乘数作用点定义 |
| Horizon 修正 | `prediction_signal.horizon`（short/medium/long） | 部分 | 文档 intraday/1-3D/1-4W/3-12M 分档未落地 |
| Industry Macro Score 落库 | `industry_forecast`（指标情景预测） | 缺失 | 无 `industry_macro_score`（score/expected_return/confidence/regime/horizon） |
| Scenario Simulation（宏→行业条件影响） | `factor_first.analyze_indicator(new_value=...)`（个股/行业弹性）；`run_scenario`（个股 EPS 三情景） | 部分 | 单指标 what-if 已有雏形；无宏观事件→行业组合情景、不落库 |
| Exposure Learning（回归+Walk-Forward） | `learning/online_calibration.py`（IC 权重学习）、`learning/history_replay.py` | 部分 | 方法学同源（版本化+防泄漏+walk-forward 概念）；目标变量是评分成分权重而非行业收益 β |
| 数据泄露控制 | PHASE8.md 记录 replay 无 look-ahead | 部分 | 缺 consensus-发布版本、feature available_at、目标严格后置的行业级管线约定 |
| 监控（行业 IC/分 regime/事件日） | `calibration_run/calibration_component`（个股评分） | 缺失 | 行业层无 IC/MAE 监控 |
| API（macro-score/transmission/simulate） | `mcp_server.py` 薄包装 + `app/use_cases/` | 缺失 | 挂载模式成熟，直接加 3-4 个工具即可 |
| V1 推荐行业清单 | `industry` 树（含 semiconductor/edge_ai/cloud/macro 伪行业等） | 部分 | 需核对补齐 Banks/Energy/Airlines/Utilities/REIT 等节点 |

---

## 三、目标 4 表 vs 现有 Schema（字段级差异）

### 3.1 macro_industry_exposure（新建）
文档：`factor_id / industry_id / sensitivity / confidence / source('expert') / model_version / regime / horizon / valid_from / valid_to`
- 现状复用：`industry.id`（行业主数据）、`industry_factor`（可取宏观因子行作为 factor 主数据源，或新建独立 macro_factor 表）
- 缺口：现无任何"因子×行业×敏感性×版本窗口"的存储；**建议建新表**，sensitivity 存 DECIMAL 符号化值并强制约定因子方向含义（入库注释 + 文档）。
- 注意：与 `industry_company`（公司↔行业暴露）是两层概念，勿混淆；V1 专家先验可做一次性 seed（参照文档 §10 示例表，需先补 Banks/Energy/Airlines/Utilities/REIT 行业节点）。

### 3.2 macro_transmission_edge（新建）
文档：`source_type/source_id / target_type/target_id / weight / direction / confidence / lag_min/lag_max / source / model_version / valid_from / valid_to`
- 先例：`industry_chain_edge`（chain_id/from/to/relation_type）——无 confidence/lag/weight；`prediction_signal` 用字符串 propagation_path。
- 建议：独立新表，Node 类型枚举 `macro_indicator / macro_factor / market_variable / industry`；V1 可先用固定路径 seed（NFP→Labor→FedCutProb→2Y→10Y→Semiconductor 等文档示例）。

### 3.3 industry_transmission_event（新建）
文档：`event_id / industry_id / impact_score / direction / confidence / explanation`
- 现状：`event` 表（有 industry_id/impact_direction/impact_score，但无 confidence/explanation，且为通用事件）；prediction_event 是预测市场事件。
- 建议：新表承接**单次宏观事件对多行业的传导结果快照**，字段按文档建；复用 `event.id` 或 `prediction_event.id` 做 event_id 外键。

### 3.4 industry_macro_score（新建）
文档：`industry_id / score_date / horizon / regime / score / expected_return / confidence / model_version`
- 现状：`industry_forecast` 只存指标数值情景（period/scenario/value）；`score_snapshot` 是**个股**评分快照（含 forward_return_5d/20d，Phase 8 校准样本）。
- 建议：仿 `score_snapshot` 结构建行业版（加 regime/horizon 维度，forward_return 可回填做行业 IC 监控），与个股 score_snapshot 形成行业→个股两级样本链。

---

## 四、代码集成点建议

```
stock_agent/
├── domain/macro/                  # 新增：macro_factor.py / macro_signal.py（8 因子方向约定+归一化）
├── domain/industry/
│   ├── exposure.py                # 新增：EffectiveExposure 计算（Base×Regime×Event×Horizon）
│   ├── transmission.py            # 新增：Direct/Indirect 传导 + PathScore + 路径衰减
│   ├── graph.py                   # 新增：Transmission Graph 读写（参照 data/repositories/graph_repo.py 风格）
│   └── scoring.py                 # 新增：IndustryScorer → industry_macro_score
├── context/
│   ├── regime_detector.py         # 扩展：增加宏观四态（Goldilocks/Overheating/Recession/Stagflation）
│   └── macro_event.py             # 新增：事件分级（Normal/Important/Major）
├── data/collectors/fred_macro.py  # 新增/扩展：补齐 NFP/CPI/2Y10Y/DXY/VIX/OIL 序列 + 共识日历
├── data/repositories/             # 新增 macro_repo.py（4 张新表的 CRUD）
├── migrations/20260903_phase7_macro_transmission.sql   # 4 张新表
├── app/use_cases/industry_transmission.py              # 新增：编排（对齐 industry_first.py 风格）
├── mcp_server.py                  # +3~4 工具：industry_macro_score / industry_transmission / industry_exposure / transmission_simulate
└── jobs/industry_macro_sync.py    # 新增 cron：日更 macro signal + 重算行业分（复用 jobs/industry_sync.py 模式）
```

**复用清单**：`signals/normalizer.py`（信号 [-1,+1]）、`signals/decay.py`、`context/regime_detector.py` 的 FRED 读取、`factor_repo/graph_repo` 连接与查询风格、`mysql_db.get_conn`、`learning/` 的版本化与安全阀逻辑、`scoring/weight_engine` 的版本管理。

---

## 五、落地建议（映射文档 §24，含依赖）

| 序 | 文档步骤 | 动作 | 依赖 |
|---|---|---|---|
| P1 | 7.1 | 建 4 张表 + macro 因子全局表（含方向约定）+ seed V1 专家先验（先补行业树节点） | 无 |
| P2 | 7.2 | ExposureManager（regime/horizon/有效期选版本 → EffectiveExposure） | P1 |
| P3 | 7.3 | Direct Transmission（先用行业敏感性×信号 直算） | P1-P2 |
| P4 | 7.4 | Transmission Graph 读写 + Indirect（固定路径 V1） | P3 |
| P5 | 7.5 | Regime 四态扩展 + Event 分级 + Horizon 分档修正 | P2-P4 |
| P6 | 7.6 | IndustryScorer → industry_macro_score（可回填 forward_return） | P5 |
| P7 | 7.7 | Scenario Simulation（macro what-if → 行业影响，仿 factor_first.analyze_indicator） | P6 |
| P8 | 7.8 | 采集行业历史收益，V2 Exposure 回归（Ridge/Lasso，分 horizon） | P6 |
| P9 | 7.9 | Walk-Forward Backtest + 行业 IC/MAE 监控（仿 Phase 8） | P8 |
| P10 | 7.10 | 输出标准接口给 Phase 8（industry_macro_score → 个股传导） | P6+ |

**建议 P1-P3 一并实现（本阶段核心增量）**；P4/P5 用 V1 专家固定路径先行，P8/P9 后置。

---

## 六、风险与注意点

1. **符号约定缺失（文档本身问题，实施前必须先定）**：8 个 Macro Factor 需明确"分上升 = 利好风险资产"或各自定义，否则先验表（半导体 10Y -0.75 vs Fed Policy +0.70）无法验证是否自洽。建议 V1 先定：FED_POLICY = 降息预期（+1 鸽派利好成长）；RATES 因子与 10Y 相关性极高，实施时做因子分组避免双重计权。
2. **行业主数据核对**：`macro` 伪行业用于存宏观指标是现状 hack；Phase 7 正式化后建议保留（作为 macro indicator 的挂载点）但把敏感性表与伪行业解耦，避免语义污染。
3. **共线性**：INFLATION/RATES/FED_POLICY 同源；IndustryScorer 需按 regime 选主因子或残差化，别 8 因子全量线性相加。
4. **置信度连乘衰减**：多跳后 confidence 几何衰减失真，建议 log 域累加 + 末端归一化，并沿用 Phase 8 的 IC 校准验证。
5. **数据泄露**：宏观序列有事后修订（如 NFP 修正值），必须存"发布时点可见值"（available_at），FRED 数据用当月原值而非修订值；回测用 walk-forward。
6. **lag 对齐**：不同边 lag 不同，同一时点传播需定义事件时间轴对齐与窗口聚合，避免把未来数据卷进当前路径。

---

*报告生成：2026-09-03，依据文档 V1.0 与代码库现状；如需据此出实现计划或直接开工（P1-P3），随时可继续。*
