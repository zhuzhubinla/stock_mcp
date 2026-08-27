"""种子数据：Intelligence Graph 初始数据（v2 schema）
⚠️ 引导/兑底数据（bootstrap）：真实数据源接入后由同步任务覆盖：
- SEC EDGAR XBRL → 公司真实财报（data/collectors/sec_financials.py）
- FRED → 行业指标（data/collectors/fred_industry.py）
- jobs/industry_sync.py 每日 08:50 自动同步
幂等可重复执行。依据《Detailed Technical Design》字段级设计。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories import graph_repo, factor_repo, forecast_repo
from domain.stock.resolver import resolve


def _src():
    return forecast_repo.upsert_source("Seed Data", source_type="manual",
                                       provider="internal", reliability_score=0.5)


def seed_industries():
    semicon = graph_repo.upsert_industry("semiconductor", "半导体", level=1, name_en="Semiconductor")
    ai_chip = graph_repo.upsert_industry("ai_chip", "AI 芯片", level=2, parent_id=semicon,
                                         name_en="AI Chip")
    memory = graph_repo.upsert_industry("memory", "存储（DRAM/NAND）", level=2, parent_id=semicon,
                                        name_en="Memory")
    foundry = graph_repo.upsert_industry("foundry", "晶圆制造", level=2, parent_id=semicon,
                                         name_en="Foundry")
    osat = graph_repo.upsert_industry("osat", "封装测试", level=2, parent_id=semicon,
                                      name_en="OSAT")
    network = graph_repo.upsert_industry("network", "网络/互连芯片", level=2, parent_id=semicon,
                                         name_en="Networking")
    cloud = graph_repo.upsert_industry("cloud", "云计算基础设施", level=1, name_en="Cloud Infra")
    edge_ai = graph_repo.upsert_industry("edge_ai", "端侧 AI", level=1, name_en="Edge AI")
    ai_glass = graph_repo.upsert_industry("ai_glass", "AI 眼镜", level=2, parent_id=edge_ai,
                                          name_en="AI Glasses")
    tws = graph_repo.upsert_industry("tws", "TWS 耳机", level=2, parent_id=edge_ai,
                                     name_en="TWS")
    wearable = graph_repo.upsert_industry("wearable", "智能穿戴", level=2, parent_id=edge_ai,
                                          name_en="Wearable")
    return {"semicon": semicon, "ai_chip": ai_chip, "memory": memory, "foundry": foundry,
            "osat": osat, "network": network, "cloud": cloud, "edge_ai": edge_ai,
            "ai_glass": ai_glass, "tws": tws, "wearable": wearable}


def seed_chains(ind):
    """AI 眼镜产业链（文档第 7 节示例）"""
    chain_id = graph_repo.upsert_chain("AI 眼镜产业链", "从晶圆到终端消费者的完整链路",
                                       industry_id=ind["ai_glass"])
    nodes = {}
    for i, (name, ntype) in enumerate([
        ("晶圆制造", "wafer"), ("封装测试", "packaging"),
        ("SoC / AI 芯片", "chip"), ("Memory", "chip"),
        ("Camera", "component"), ("Display", "component"),
        ("Battery / Power", "component"), ("AI Glass Assembly", "assembly"),
        ("品牌厂商", "brand"), ("终端消费者", "end_market"),
    ]):
        nodes[name] = graph_repo.upsert_chain_node(chain_id, name, ntype, position=i)
    edges = [
        ("晶圆制造", "SoC / AI 芯片"), ("封装测试", "SoC / AI 芯片"),
        ("Memory", "AI Glass Assembly"), ("Camera", "AI Glass Assembly"),
        ("Display", "AI Glass Assembly"), ("Battery / Power", "AI Glass Assembly"),
        ("SoC / AI 芯片", "AI Glass Assembly"),
        ("AI Glass Assembly", "品牌厂商"), ("品牌厂商", "终端消费者"),
    ]
    for f, t in edges:
        graph_repo.upsert_chain_edge(chain_id, nodes[f], nodes[t])

    # 半导体产业链（AI 服务器视角）
    sc_id = graph_repo.upsert_chain("AI 服务器半导体链", "AI 芯片到云厂商部署",
                                    industry_id=ind["ai_chip"])
    sc = {}
    for i, (name, ntype) in enumerate([
        ("EDA / IP", "equipment"), ("晶圆制造", "wafer"), ("封装测试", "packaging"),
        ("HBM 存储", "chip"), ("AI 芯片设计", "chip"),
        ("服务器整机", "assembly"), ("云厂商 / 终端", "end_market"),
    ]):
        sc[name] = graph_repo.upsert_chain_node(sc_id, name, ntype, position=i)
    for f, t in [
        ("EDA / IP", "AI 芯片设计"), ("晶圆制造", "AI 芯片设计"),
        ("封装测试", "AI 芯片设计"), ("HBM 存储", "AI 芯片设计"),
        ("AI 芯片设计", "服务器整机"), ("服务器整机", "云厂商 / 终端"),
    ]:
        graph_repo.upsert_chain_edge(sc_id, sc[f], sc[t])
    return chain_id


def seed_companies(ind):
    src = _src()
    companies = {}
    plan = {
        "NVDA": ("NVIDIA Corp", "NVIDIA Corporation", "美国", "public", "半导体", [
            ("数据中心 AI 芯片", "ai_chip", 0.78, 1, 0.75),
            ("网络互连（Mellanox）", "network", 0.14, 0, 0.60),
            ("游戏 GPU", "ai_chip", 0.06, 0, 0.50),
            ("汽车与机器人", "edge_ai", 0.02, 0, 0.30),
        ]),
        "AMD": ("Advanced Micro Devices", "Advanced Micro Devices, Inc.", "美国", "public", "半导体", [
            ("数据中心（EPYC/MI）", "ai_chip", 0.50, 1, 0.45),
            ("客户端（Ryzen）", "ai_chip", 0.30, 0, 0.35),
            ("游戏（Radeon）", "ai_chip", 0.12, 0, 0.30),
            ("嵌入式", "edge_ai", 0.08, 0, 0.20),
        ]),
        "MSFT": ("Microsoft Corp", "Microsoft Corporation", "美国", "public", "软件/云", [
            ("智能云（Azure）", "cloud", 0.42, 1, 0.40),
            ("生产力与商业流程", "cloud", 0.33, 0, 0.30),
            ("更多个人计算", "cloud", 0.25, 0, 0.25),
        ]),
        "GOOGL": ("Alphabet Inc", "Alphabet Inc.", "美国", "public", "互联网/云", [
            ("Google Cloud", "cloud", 0.12, 0, 0.10),
            ("搜索与广告", "cloud", 0.75, 1, 0.70),
            ("其他押注", "cloud", 0.13, 0, 0.10),
        ]),
        "ORCL": ("Oracle Corp", "Oracle Corporation", "美国", "public", "软件/云", [
            ("云基础设施（OCI）", "cloud", 0.40, 1, 0.35),
            ("云应用（SaaS）", "cloud", 0.35, 0, 0.30),
            ("许可与支持", "cloud", 0.25, 0, 0.20),
        ]),
        "MRVL": ("Marvell Technology", "Marvell Technology, Inc.", "美国", "public", "半导体", [
            ("数据中心定制芯片", "ai_chip", 0.55, 1, 0.50),
            ("网络互连", "network", 0.25, 0, 0.40),
            ("运营商基础设施", "network", 0.12, 0, 0.25),
            ("汽车/工业", "edge_ai", 0.08, 0, 0.15),
        ]),
        "MU": ("Micron Technology", "Micron Technology, Inc.", "美国", "public", "半导体", [
            ("DRAM", "memory", 0.70, 1, 0.65),
            ("NAND/SSD", "memory", 0.30, 0, 0.30),
        ]),
    }
    for sym, (name, name_en, country, ctype, sector, segs) in plan.items():
        comp = resolve(sym)
        cid = comp["company_id"]
        graph_repo.upsert_company(stock_symbol=sym, name=name, name_en=name_en,
                                  country=country, company_type=ctype,
                                  description=f"{name}（种子数据）", source_id=src)
        for seg_name, ind_code, share, primary, exp in segs:
            seg_id = graph_repo.upsert_business_segment(
                cid, seg_name, industry_id=ind[ind_code], segment_type="product",
                revenue_share=share, gross_margin=0.5, is_primary=primary, source_id=src)
            graph_repo.upsert_industry_company(
                ind[ind_code], cid, business_segment_id=seg_id,
                exposure_weight=share, revenue_exposure=share,
                profit_exposure=exp, confidence=0.8, role=seg_name, source_id=src)
        companies[sym] = cid

    # 关系（供应商/客户/竞争对手/foundry）
    rel = [
        ("NVDA", "MU", "customer", 0.30, 0.8),
        ("MU", "NVDA", "supplier", 0.30, 0.8),
        ("NVDA", "AMD", "competitor", 0.50, 0.9),
        ("NVDA", "MSFT", "partner", 0.60, 0.9),
        ("AMD", "NVDA", "competitor", 0.50, 0.9),
        ("MRVL", "NVDA", "competitor", 0.25, 0.6),
        ("MSFT", "NVDA", "customer", 0.55, 0.85),
        ("GOOGL", "NVDA", "customer", 0.45, 0.8),
        ("ORCL", "NVDA", "customer", 0.40, 0.75),
        ("MRVL", "MSFT", "partner", 0.35, 0.7),
    ]
    for a, b, rtype, imp, conf in rel:
        graph_repo.upsert_relationship(companies[a], companies[b], rtype,
                                       importance=imp, confidence=conf, source_id=src)
    # foundry（挂到非 watchlist 公司主体）
    tsmc = graph_repo.upsert_company(name="TSMC", name_en="Taiwan Semiconductor",
                                     country="中国台湾", company_type="public",
                                     description="台积电", source_id=src)
    for sym in ("NVDA", "AMD", "MRVL"):
        graph_repo.upsert_relationship(companies[sym], tsmc, "foundry",
                                       importance=0.9, confidence=0.9, source_id=src)

    # AI 眼镜产业链受益公司
    glass_plan = [
        ("688608.SH", "恒玄科技", "Bestechnic", "中国", "public", "端侧 AI SoC", [
            ("AI 眼镜 SoC", "ai_glass", 0.35, 1, 0.30),
            ("TWS 耳机 SoC", "tws", 0.45, 0, 0.35),
            ("智能穿戴 SoC", "wearable", 0.20, 0, 0.20),
        ]),
        ("002241.SZ", "歌尔股份", "Goertek", "中国", "public", "消费电子制造", [
            ("AI 眼镜整机组装", "ai_glass", 0.30, 1, 0.25),
            ("TWS 声学器件", "tws", 0.50, 0, 0.40),
        ]),
        ("META", "Meta Platforms", "Meta Platforms, Inc.", "美国", "public", "互联网/硬件", [
            ("AI 眼镜品牌（Ray-Ban Meta）", "ai_glass", 0.15, 0, 0.12),
            ("社交平台", "cloud", 0.85, 1, 0.80),
        ]),
    ]
    for sym, name, name_en, country, ctype, sector, segs in glass_plan:
        cid = graph_repo.upsert_company(stock_symbol=sym, name=name, name_en=name_en,
                                        country=country, company_type=ctype,
                                        description=f"{name}（种子数据）", source_id=src)
        for seg_name, ind_code, share, primary, exp in segs:
            seg_id = graph_repo.upsert_business_segment(
                cid, seg_name, industry_id=ind[ind_code], segment_type="product",
                revenue_share=share, is_primary=primary, source_id=src)
            graph_repo.upsert_industry_company(
                ind[ind_code], cid, business_segment_id=seg_id,
                exposure_weight=share, revenue_exposure=share,
                profit_exposure=exp, confidence=0.7, role=seg_name, source_id=src)
        companies[sym] = cid
    return companies


def seed_factors_and_indicators(ind):
    src = _src()
    factors = [
        ("ai_glass", "AI 眼镜出货量", "demand", "positive", "Meta/字节等品牌新品带动", 0.9, "百万台"),
        ("ai_glass", "端侧 AI 芯片渗透率", "technology", "positive", "SoC 集成 NPU 能力提升", 0.8, "%"),
        ("ai_glass", "光学方案成本", "cost", "negative", "衍射光波导成本下降利好放量", 0.7, "美元"),
        ("ai_glass", "政策/监管", "policy", "neutral", "摄像头隐私监管风险", 0.4, None),
        ("memory", "HBM 供需", "demand", "positive", "AI 服务器 HBM 需求爆发", 0.9, None),
        ("memory", "DRAM 合约价", "price", "positive", "涨价周期", 0.8, "指数"),
        ("foundry", "先进制程产能利用率", "capacity", "positive", "3nm/5nm 满载", 0.8, "%"),
        ("ai_chip", "AI 资本开支", "demand", "positive", "云厂商 capex 指引", 0.9, "十亿美元"),
        ("cloud", "云资本开支", "demand", "positive", "Azure/GCP/OCI 扩容", 0.8, "十亿美元"),
    ]
    for ind_code, name, ftype, direction, desc, importance, unit in factors:
        factor_repo.upsert_industry_factor(ind[ind_code], name, factor_type=ftype,
                                           impact_direction=direction, description=desc,
                                           importance=importance, unit=unit, source_id=src)

    # 指标（AI 眼镜出货量，百万台）
    for period, v in [("2024", 12.0), ("2025", 45.0), ("2026", 120.0)]:
        factor_repo.upsert_indicator(ind["ai_glass"], "ai_glass_shipment", "AI 眼镜出货量",
                                     v, unit="百万台", period=period, source_id=src)
    for period, v in [("2024", 420), ("2025", 380), ("2026", 320)]:
        factor_repo.upsert_indicator(ind["ai_glass"], "ai_glass_asp", "AI 眼镜 ASP",
                                     v, unit="美元", period=period, source_id=src)
    # DRAM 合约价指数
    for period, v in [("2024", 100), ("2025", 135), ("2026", 160)]:
        factor_repo.upsert_indicator(ind["memory"], "dram_contract_price", "DRAM 合约价",
                                     v, unit="指数", period=period, source_id=src)
    # 云资本开支（十亿美元）
    for period, v in [("2024", 230), ("2025", 320), ("2026", 420)]:
        factor_repo.upsert_indicator(ind["cloud"], "cloud_capex", "云资本开支",
                                     v, unit="十亿美元", period=period, source_id=src)
    # AI 芯片出货量（百万颗）
    for period, v in [("2024", 8.0), ("2025", 14.0), ("2026", 22.0)]:
        factor_repo.upsert_indicator(ind["ai_chip"], "ai_chip_shipment", "AI 芯片出货量",
                                     v, unit="百万颗", period=period, source_id=src)

    # 供需：AI 眼镜（百万台）
    for period, cap, prod, dem in [("2025", 60, 42, 45), ("2026", 150, 110, 120)]:
        factor_repo.upsert_supply_demand(ind["ai_glass"], period, capacity=cap,
                                         production=prod, demand=dem,
                                         utilization_rate=round(prod / cap, 4) if cap else None,
                                         supply_demand_gap=round(dem - prod, 2),
                                         unit="百万台", source_id=src)

    # 行业预测（+scenario/low/high）
    for period, v in [("2026", 120.0), ("2027", 220.0)]:
        forecast_repo.upsert_industry_forecast(ind["ai_glass"], "ai_glass_shipment", period, v,
                                               scenario="base", low_value=v * 0.8,
                                               high_value=v * 1.2, confidence=0.7,
                                               model_version="intelligence-v1", source_id=src)

    # 财务驱动（指标 → 公司财务）
    def ind_id(code, name):
        rows = factor_repo.get_indicators(industry_id=ind[code], indicator_name=name)
        if not rows:
            return None
        return sorted(rows, key=lambda r: str(r["period"] or ""))[-1]["id"]

    drivers = [
        ("NVDA", "数据中心 AI 芯片", "demand", "AI 芯片出货量", "ai_chip", "AI 芯片出货量", "revenue", "positive", 0.9, 14.0),
        ("NVDA", "数据中心 AI 芯片", "price", "HBM 涨价传导", "memory", "DRAM 合约价", "gross_margin", "positive", 0.25, 100.0),
        ("MU", "DRAM", "price", "DRAM 合约价", "memory", "DRAM 合约价", "revenue", "positive", 1.2, 100.0),
        ("MU", "DRAM", "demand", "HBM 需求", "memory", "DRAM 合约价", "eps", "positive", 1.0, 100.0),
        ("MSFT", "智能云（Azure）", "demand", "云资本开支", "cloud", "云资本开支", "revenue", "positive", 0.5, 230.0),
        ("GOOGL", "Google Cloud", "demand", "云资本开支", "cloud", "云资本开支", "revenue", "positive", 0.35, 230.0),
        ("ORCL", "云基础设施（OCI）", "demand", "云资本开支", "cloud", "云资本开支", "revenue", "positive", 0.45, 230.0),
        ("MRVL", "数据中心定制芯片", "demand", "AI 芯片出货量", "ai_chip", "AI 芯片出货量", "revenue", "positive", 0.7, 14.0),
        ("AMD", "数据中心（EPYC/MI）", "demand", "AI 芯片出货量", "ai_chip", "AI 芯片出货量", "revenue", "positive", 0.6, 14.0),
    ]
    for sym, seg, dtype, dname, icode, iname, metric, direction, coeff, base in drivers:
        comp = graph_repo.get_company(symbol=sym)
        if not comp:
            continue
        segs = graph_repo.get_business_segments(symbol=sym)
        seg_id = next((s["id"] for s in segs if s["name"] == seg), None)
        iid = ind_id(icode, iname)
        factor_repo.upsert_financial_driver(
            comp["id"], dname, impact_metric=metric, impact_direction=direction,
            business_segment_id=seg_id, indicator_id=iid,
            impact_coefficient=coeff, elasticity=round(coeff * 0.8, 4),
            base_value=base, forecast_value=None, confidence=0.8, source_id=src)


def seed_all():
    ind = seed_industries()
    seed_chains(ind)
    companies = seed_companies(ind)
    seed_factors_and_indicators(ind)
    return {"industries": len(ind), "companies": len(companies),
            "note": "Intelligence Graph v2 种子数据就绪"}


if __name__ == "__main__":
    print(seed_all())
