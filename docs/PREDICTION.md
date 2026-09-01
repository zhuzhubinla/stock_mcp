# Prediction Intelligence：Polymarket / Kalshi 真实数据接入（2026-08-30）

依据《Stock Agent — Investment Intelligence & Prediction Scoring Engine》V1.0
第 8 节（Prediction Intelligence）、第 18.1 节（MySQL 模型）、第 21 节（Collector 部署）落地。

## 1. 数据源接入状态

| 源 | 优先级 | 状态 | 说明 |
|---|---|---|---|
| Kalshi | P0 | ✅ 真实接入 | `demo-api.kalshi.co` 大陆直连可用（2026-08-30 实测 27 事件/229 市场） |
| Polymarket | P0 | 🔧 代码就绪 | gamma/clob 大陆直连超时 → 海外 VPS 或代理模式（设计文档 21 节 Option B） |
| Metaculus | P1 | ✅ 代码就绪（待 token） | API v2 强制鉴权；`Authorization: Token`；概率=社区中位数（q2） |
| Manifold | P1 | 待接入 | 社区预测 |

> **Metaculus（2026-09-01 接入）**：API 已全面要求认证（匿名 403），需 API token
> （`https://www.metaculus.com/settings/account/` 生成）。token 通过环境变量
> `METACULUS_API_KEY` 注入，或写入项目根 `.env`（已 gitignore）。
> 模式：question 即事件+市场，无订单簿 → yes_ask/bid/volume/OI 置空，
> 概率取 `community_prediction.full.q2`（社区中位数，回退 mean）。
> 动量靠每次 sync 快照累积（Metaculus 无公开时序端点）。

## 2. 架构

```
data/collectors/prediction/
  base.py          # PredictionAdapter 抽象（fetch_events/fetch_markets/fetch_market_detail）
  kalshi.py        # Kalshi v2 API（demo 默认，生产换 base_url+api_key）
  polymarket.py    # Gamma + CLOB API（海外 VPS/代理部署）
  metaculus.py     # Metaculus API v2（Token 鉴权；question=事件+市场；社区中位数概率）
  collector.py     # 编排：拉取 → 归一化 → 落库（含体育 shard 过滤）
data/repositories/prediction_repo.py   # prediction_* 7 表读写
domain/prediction/
  engine.py        # Consensus（ΣP×W/ΣW + dispersion）+ Momentum（24h/7d）+ 方向强度
  mapper.py        # Prediction→Stock 映射（Knowledge Graph 传播，8.6 节）
jobs/prediction_sync.py  # 定时：采集→共识→映射（cron 09:45）
```

## 3. DB（48 表）

prediction_source / prediction_event / prediction_market / prediction_outcome /
prediction_probability / prediction_consensus / prediction_signal

## 4. 统一流程（8.3 节）

`Source API → Adapter → Normalization → Event/Market Mapping → 落库 → Consensus → Momentum → Signal`

- **Consensus** = Σ(P_i × W_i) / Σ(W_i)，W = 源可靠性 × 流动性因子（OI）
- **Dispersion** = 加权标准差：源一致 → 高置信；差异大 → 低置信 + 冲突
- **Momentum_24h/7d** = P_now - P_{n}h_ago（prediction_probability 时序）

## 5. Prediction → Stock 映射（8.6 节）

预测事件本身不是股票信号，必须经 Knowledge Graph 传播：
`AI CapEx → Data Center → GPU → NVDA/AMD/HBM → MU/TSMC/MRVL`

- 关键词规则（KEYWORD_MAP）：ai capex/data center/gpu/memory/foundry/cloud/fed/cpi...
- 行业 → 公司：优先 industry_company（exposure_weight），兜底静态表
- 输出 prediction_signal（entity/direction/strength/confidence/probability/propagation_path）

## 6. MCP 工具（61 → 67）

- prediction_sync：同步预测源（kalshi 默认，polymarket 需 proxy）
- prediction_events / prediction_markets：事件/市场列表（实时概率）
- prediction_consensus：多源共识 + 动量
- prediction_signals：股票预测信号 / 聚合分
- prediction_map_events：全部事件 → 股票映射

## 7. 实测（2026-08-30）

- Kalshi demo 真实采集：27 事件 / 229 市场 / 229 条概率
- 共识：27 个事件全部计算（Fed 利率 21 市场 / GDP / IPO 等）
- 映射：`Will OpenAI or Anthropic IPO first?` p=0.99 bullish →
  NVDA/AMD/MRVL（path: AI CapEx → Data Center → GPU → NVDA）
- NVDA prediction 成分分：50 → 68.29（进入 Phase 8 Overall Score）
- 回归全过（quote/fundamentals/news/stock_first/intelligence_v2/calibration/consensus）

## 8. Polymarket 海外 VPS 部署（设计文档 21 节 Option B）

```bash
# 海外 VPS 上：
pip install requests
python -c "from data.collectors.prediction.collector import collect_all; print(collect_all(sources=['polymarket']))"
# 或本机配置代理：
from data.collectors.prediction.collector import collect_source
collect_source('polymarket', proxy='http://your-proxy:port')
```

## 9. 踩坑记录

1. Kalshi events 列表不带 status 字段（None）→ 误判 closed 导致事件全被过滤，
   修正：None 视为 open
2. Kalshi 多市场事件（如 NATO 8 个市场）：/markets/{ticker} 单市场端点取不到，
   需用 /events/{event_ticker} 返回 markets[]（新增 fetch_event_markets）
3. Kalshi demo 大量体育跨类 shard 市场（"yes X,yes Y"）无股票意义 →
   collector 过滤（_is_sports_shard）
4. Kalshi 价格字段是 *_dollars 后缀（last_price_dollars/yes_bid_dollars），非 last_price

## 10. 待办

- Polymarket 海外 VPS 实拉后验证 Gamma 字段映射
- Metaculus 实拉验证（.env 配置 token 后）
- Prediction 事件的置信度校准（Brier）纳入 Phase 8 循环
- 更多 KEYWORD_MAP 规则 + 产业链传播权重（industry_chain_edge）
