# 估值计算机制说明（Valuation）

系统推测股价的核心公式：

```
目标价 = 每股盈利(EPS) × 市盈率(PE)
```

新闻、情绪、技术指标**不参与估值**，只影响短期信号与归因。
估值完全由 **真实财报 EPS × 行业 PE 区间** 得出。

---

## 一、数据链路总览

```
SEC EDGAR XBRL（真实财报）
    │  Revenues / NetIncome / EPS / OCF / Capex
    ▼
company_forecast (scenario=actual)  ← 真实值基准
    │
    ▼
financial_model/scenario.py → Bull / Base / Bear 三档 EPS
    │
    ▼
financial_model/valuation.py → EPS × 行业 PE → 目标价区间
    │
    ▼
valuation 表（model_type/fair_value/upside/assumption_json）
```

行业驱动（financial_driver）只做**弹性修正**：给 Bull/Bear 增加/减小幅度，
不改变 Base（真实值）。

---

## 二、EPS 基准获取链（scenario.py）

`run_scenarios()` 按以下优先级取 Base EPS：

1. **SEC actual 真实值**（company_forecast, scenario=actual，最新年份）
   ← 每日 08:50 industry_sync 从 EDGAR XBRL 同步
2. 已有 base 预测（company_forecast, scenario=base, 当期）
3. 基本面表 eps（stock_fundamental）
4. 当前价 ÷ PE（无 PE 时按行业默认 PE 30 反推）

```
Base EPS = 真实 EPS（如 NVDA 4.90）
Bull EPS = Base × 1.3 + 驱动修正
Bear EPS = Base × 0.7 - 驱动修正
驱动修正 = (正向驱动数 - 负向驱动数) × 2%（每个净正向驱动 +2% 弹性）
```

三档结果写入 company_forecast（scenario=bull/base/bear，含 low/high 区间）。

---

## 三、PE 区间选择（valuation.py）

按公司所属行业属性（company profile 从 industry 反推 sector）：

| 行业属性 | PE 区间 |
|---------|--------|
| tech/semiconductor/software/半导体/芯片/云/科技/互联网/消费电子 | 25 ~ 35 |
| 其他（传统行业） | 15 ~ 25 |

> ⚠️ 踩坑记录：v2 数据库 company 表删除了 sector 列，profile 返回 sector=None，
> 导致所有股票按默认 15~25 算，目标价偏低。已修复：从公司所属行业
> （industry_company → industry name/code）反推 sector 属性。

---

## 四、目标价计算

```
target_low  = Base EPS × PE_low
target_high = Base EPS × PE_high
```

示例（2026-08-27，SEC 真实 EPS）：

| 股票 | Base EPS | PE | 目标价区间 |
|------|---------|-----|-----------|
| NVDA | 4.90 | 25~35 | 122.5 ~ 171.5 |
| MSFT | 17.95 | 25~35 | 448.8 ~ 628.3 |
| AMD | 2.65 | 25~35 | 66.3 ~ 92.8 |
| GOOGL | 10.81 | 25~35 | 270.3 ~ 378.4 |

写入 valuation 表：model_type=PE（+PE_low），scenario=bull/base/bear，
assumption_json 记录 {eps, pe, method}，upside = (fair_value/eps - pe)/pe。

---

## 五、情景引擎假设记录（第 22 节要求）

Scenario Engine 记录每个变量的假设值、来源、置信度与敏感度：

- 假设值 → assumption_json（valuation 表）
- 来源 → model_version=sec-xbrl / intelligence-v1 + source 表
- 置信度 → confidence 列（company_forecast）
- 敏感度 → financial_driver.elasticity（指标变动 1% → 财务影响 %）

---

## 六、相关文件

| 文件 | 职责 |
|------|------|
| data/collectors/sec_financials.py | SEC XBRL 真实财报采集 |
| data/collectors/fred_industry.py | FRED 行业指标采集 |
| financial_model/scenario.py | Bull/Base/Bear 情景 |
| financial_model/valuation.py | PE 估值与落库 |
| financial_model/margin/earnings/fcf.py | 公式链（毛利/净利/现金流） |
| domain/company/profile.py | 公司画像 + sector 反推 |
| jobs/industry_sync.py | 每日 08:50 同步编排 |
