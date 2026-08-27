# 新闻打分机制说明（News Scoring）

系统对新闻的打分分**两套独立机制**，用途不同：
- **AI 分析管线**（analyzer.py）：新闻入库后打 6 维深度标签，长期保存
- **Signal Engine**（scoring.py）：综合分析瞬间对标题快速扫词，临时用

新闻分数**只影响短期信号与归因，不参与估值计算**。估值 = 真实 EPS × 行业 PE（见 `docs/VALUATION.md`）。

---

## 一、AI 分析管线（data/collectors/news/analyzer.py）

### 输出维度（6+2 个字段）

| 字段 | 范围 | 含义 |
|------|------|------|
| event_type | 28 种 | 事件类型：earnings/guidance/m_and_a/lawsuit/recall... |
| sentiment | positive/negative/neutral | 利好/利空方向 |
| sentiment_score | -1.0 ~ 1.0 | 利好利空程度 |
| impact_score | 0 ~ 1 | 对股价潜在影响**力度**（与方向独立） |
| relevance_score | 0 ~ 1 | 与涉及股票的相关度 |
| confidence | 0 ~ 1 | 打分置信度 |
| time_horizon | 1-5d / 5-30d | 影响时间窗口 |
| summary / reasoning | 文本 | 摘要与推理依据 |

**关键原则**：impact（力度）与 sentiment（方向）互相独立。
例："产品爆炸召回" = high impact + negative；"例行财报" = low impact + neutral。

### 执行路径

```
analyze_one(item, symbols)
  ├─ LLM（DeepSeek，JSON 输出，response_format=json_object，temperature=0.2）
  │    ├─ 成功 → _sanitize() 清洗/clamp 后返回
  │    └─ 失败/无 key → 回退规则引擎
  └─ 规则引擎 _rule_analyze()
```

### 规则引擎三步计算

**① 事件识别**（ai/event_extractor.py）
- 标题+摘要跑 28 类关键词表（EVENT_KEYWORDS）
- 多事件命中：命中词多者胜；平局按预置影响分高者胜

**② impact_score**（IMPACT_BY_EVENT 预置分 + 关键词加成）
```
impact = IMPACT_BY_EVENT[event_type] + 0.05 × 命中关键词数（上限 1.0）
```
预置分示例：bankruptcy 0.90 / earnings 0.80 / product_failure 0.80 /
cyber_attack 0.75 / m_and_a 0.75 / guidance 0.70 / regulation 0.70 /
revenue 0.60 / customer 0.60 / lawsuit 0.60 / other 0.20

**③ sentiment_score**（POS_WORDS / NEG_WORDS 词频）
```
pos = 正词命中数（beat/surge/record/upgrade/rally/raise/boost...）
neg = 负词命中数（miss/plunge/downgrade/lawsuit/recall/ban...）
raw = (pos - neg) / max(1, pos + neg)
sentiment_score = clamp(raw × 1.2, -1, 1)
sentiment = positive 若 pos>neg；negative 若 neg>pos；否则 neutral
```

relevance_score：取实体解析（entity_resolver）给出的相关度，缺省 0.5。
confidence：规则引擎固定 0.5；LLM 可自评。
time_horizon：按事件类型映射（财报/评级/召回=1-5d；并购/监管/宏观=5-30d）。

### 真实示例（2026-08-27 SeekingAlpha）

标题：*Nvidia Reports Triple-Digit Revenue Growth; Now Supply Is The Constraint*

```
① 事件识别: 命中 "revenue" → event_type = revenue
② impact    = 0.60 + 0.05×1 = 0.65
③ 情感词    = pos(1: growth) / neg(0) → positive
   sentiment_score = (1-0)/1 × 1.2 → 1.0
④ relevance = 0.9（实体解析 NVDA）
   time_horizon = 1-5d（revenue 类）
```

### 结果落库与下游

- 全部字段写入 `stock_news_analysis`（每新闻每模型一条，uk_news_model）
- `impact_score ≥ 0.5 且 event_type ≠ other` → 额外写入 `stock_news_event`（事件聚合表）
- 下游用途：每日简报标注影响度 / 异常波动归因（explain_price_move）/ 事件驱动查询

---

## 二、Signal Engine 新闻信号（analytics/scoring.py）

综合分析（stock_analyze）时，对最近 5 条新闻**标题**快速扫词：

```
每条新闻: 正词 +2/词，负词 -2/词，单条 clamp ±6
score 累加后 clamp ±100 并入 total_score
```

信号词表（简化）：beat/surge/record/growth/upgrade/rally → +2；
miss/plunge/downgrade/lawsuit/recall/ban → -2。

它是综合评分（涨跌幅/RSI/量比/基本面/新闻）的一个组件，**不持久化、不进估值**。

---

## 三、两套机制对比

| | AI 管线 | Signal Engine |
|---|---|---|
| 触发时机 | 新闻入库后（cron 15min） | 综合分析调用时 |
| 数据源 | 标题+摘要+正文(800字) | 仅标题 |
| 打分方式 | LLM 优先，规则兜底 | 固定关键词表 |
| 输出 | 6 维标签，落库 | 单一分数，实时 |
| 保存 | stock_news_analysis / _event | 不保存 |
| 用途 | 简报/归因/事件查询 | total_score 组件 |

---

## 四、如何查看效果

```bash
# 查看最近新闻及打分
python -c "
from data.adapters import stock_service
print(stock_service.get_news('NVDA', limit=5))"

# 手动跑一条新闻打分
python -c "
from data.collectors.news.analyzer import analyze_one
from data.collectors.news.providers.base import NewsItem
item = NewsItem(source_news_id='x', title='Nvidia beats Q2 earnings, raises guidance', summary='', content='', url='', publisher='demo', published_at=None)
print(analyze_one(item, [{'symbol':'NVDA','relevance_score':0.9}]))"
```
