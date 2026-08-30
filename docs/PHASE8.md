# Phase 8：Online Learning / Continuous Calibration（2026-08-30）

依据《Stock Agent — Investment Intelligence & Prediction Scoring Engine》V1.0
第 7/9-14/18-19/23/26 节落地。设计文档模型演进路线中的 **Phase 8 直接实现**，
同时补齐 **Market Precondition**。

## 1. 架构新增

```
app/use_cases/intelligence_pipeline.py   # Phase 8 全链路编排（23 节 Agent 工作流）
context/
  regime_detector.py       # Market Regime 检测（7 节 Market Precondition 市场层）
  precondition_engine.py   # Context Vector（7 节：估值/行业周期/盈利趋势/价格/预期/宏观/Market）
  expectation_engine.py    # Expectation Gap（6 节：Actual vs Expected vs Priced-in）
signals/                   # 注意：命名 signals 避开标准库 signal 模块
  normalizer.py            # 信号标准化 [-1,+1]（9 节）
  decay.py                 # 时间衰减 exp(-λt)（10 节，版本化）
  confidence.py            # 置信度（11 节：来源质量×一致性×新鲜度×样本×稳定性）
  conflict.py              # 冲突检测（12 节：Fundamental/Market Divergence 等 5 对）
scoring/
  weight_engine.py         # 动态权重版本化（13 节：基础权重 30/25/15/15/15）
  score_engine.py          # Overall Score 0-100 + 快照持久化（14 节）
learning/
  online_calibration.py    # Phase 8 核心：IC 计算 + 在线权重学习 + 校准记录
  history_replay.py        # 历史重放：生成带真实 forward return 的校准样本（首次搭建用）
  calibration_job.py       # 每日持续校准任务
```

## 2. DB 新增（41 张表）

| 表 | 用途 |
|---|---|
| market_regime | 市场状态快照（regime/regime_score/trend/volatility/breadth/macro） |
| stock_precondition | Context Vector（7 维 0~1 + 置信度，unique stock_id+computed_at） |
| score_weight_config | 动态权重版本（weights JSON + active） |
| score_snapshot | 历史评分（score/confidence/direction/权重版本/forward_return_5d/20d） |
| score_component | 评分拆解（成分分/权重/贡献） |
| signal_conflict | 冲突记录（domains/severity/description） |
| calibration_run | 校准运行（run_type/horizon/ic_mean/版本变更/status） |
| calibration_component | 每成分校准（IC/old_weight/new_weight/accepted） |

## 3. Market Precondition

- **市场层**（`context/regime_detector.py`）：SPY/QQQ 指数（yfinance）→ 趋势分(MA20/MA60/MACD/动量)
  + 波动分(20日年化反向) + 宽度分(watchlist 涨跌占比) + 宏观分(FRED INDPRO/UMCSENT/CPI)
  → regime_score 0~1 → risk_on(≥0.6)/neutral/risk_off(≤0.4)
  - 指数被限流时自动降级：FRED 宏观 + watchlist 宽度仍可算
- **个股层**（`context/precondition_engine.py`）：Context Vector 7 维
  valuation(PE/60) / industry_cycle(行业指标环比) / earnings_trend(增速) /
  price_trend(均线+RSI) / expectation(PEG 反向) / macro_regime / **market_regime**
- Context 是 Signal 的**条件变量**：`scoring/score_engine.py::_precondition_score`
  把估值/预期反向、趋势/市场正向合成"环境友好度"，参与动态评分

## 4. Phase 8 在线学习闭环

```
每日快照(save_snapshot) → 回填 forward return(5d/20d) → Spearman IC 每成分
→ new_weight = old_weight × (1 + lr×IC)（lr=0.2，|IC|<0.15 不调）
→ 限幅 [0.05,0.60] + 归一化 → 新版本落库(active) → calibration_run 记录
```

- **信息系数**：成分分 vs 未来实际收益的 Spearman 秩相关（已验证修复：分母 n(n²-1)）
- **安全阀**：MIN_SAMPLES=5、MIN_ABS_IC=0.15、权重 [0.05,0.60]、学习率 0.2
- **no_change 检测**：IC 未达门槛时不产生新版本（防版本号空转）
- **历史重放**（首次搭建）：用历史价格在多个时点重放评分（只用当时数据，无 look-ahead），
  立即获得带真实收益的样本。实测 7 只股票 34 个历史快照

## 5. MCP 工具（50 → 61）

- stock_intelligence_v2：Phase 8 全链路
- stock_get_market_regime / stock_get_precondition / stock_get_expectation
- stock_get_score（refresh=True 重新评分）/ stock_get_score_history
- stock_get_conflicts / stock_get_weight_config
- stock_run_calibration（dry_run 预览）/ stock_get_calibration
- stock_replay_history（初始化样本）

## 6. cron

- 18:00 每日在线校准（20d horizon）

## 7. 实测结果（2026-08-30）

- 7 只 watchlist 全链路跑通，快照落库（NVDA 63.78/NEUTRAL/conf 0.92）
- NVDA 识别 Fundamental/Market Divergence 冲突（severity 0.43）
- 20d 校准：IC fundamental 0.15 / market -0.32 / news 0.20 → 权重 v1→v2
  （fundamental 0.30→0.322、market 0.15→0.112、news 0.15→0.167）
- 5d 校准 IC 均未达门槛 → no_change，不空转版本

## 8. 待办（设计文档后续 Phase）

- Prediction Intelligence 数据源接入（Polymarket/Kalshi，P0）后 prediction 成分才有真实分
- 置信度校准（Brier score）纳入校准循环
- 阈值重校准（Phase 8 文档 14 节：>70 Bullish 等阈值按历史分布调整）
- 指数数据源稳定化（当前 yfinance SPY/QQQ 限流时走降级）
