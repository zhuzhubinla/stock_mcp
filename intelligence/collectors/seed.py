"""种子数据：Intelligence Graph 初始数据
行业 / 产业链（AI 眼镜、半导体）/ watchlist 公司业务分拆 / 关系 / 因子 / 指标 / 财务驱动
幂等可重复执行。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from intelligence.repositories import graph_repo, factor_repo, forecast_repo
from intelligence.stock.resolver import resolve
from intelligence.repositories import graph_repo as gr


def _src():
    return forecast_repo.upsert_source("seed", "种子数据", source_type="manual")


def seed_industries():
    """行业层级：半导体 → AI芯片/存储/晶圆制造；消费电子 → AI眼镜/TWS/智能穿戴"""
    semicon = graph_repo.upsert_industry("semiconductor", "半导体", level=1)
    ai_chip = graph_repo.upsert_industry("ai_chip", "AI 芯片", level=2, parent_id=semicon)
    memory = graph_repo.upsert_industry("memory", "存储（DRAM/NAND）", level=2, parent_id=semicon)
    foundry = graph_repo.upsert_industry("foundry", "晶圆制造", level=2, parent_id=semicon)
    osat = graph_repo.upsert_industry("osat", "封装测试", level=2, parent_id=semicon)
    network = graph_repo.upsert_industry("network", "网络/互连芯片", level=2, parent_id=semicon)
    cloud = graph_repo.upsert_industry("cloud", "云计算基础设施", level=1)
    edge_ai = graph_repo.upsert_industry("edge_ai", "端侧 AI", level=1)
    ai_glass = graph_repo.upsert_industry("ai_glass", "AI 眼镜", level=2, parent_id=edge_ai)
    tws = graph_repo.upsert_industry("tws", "TWS 耳机", level=2, parent_id=edge_ai)
    wearable = graph_repo.upsert_industry("wearable", "智能穿戴", level=2, parent_id=edge_ai)

    return {
        "semicon": semicon, "ai_chip": ai_chip, "memory": memory, "foundry": foundry,
        "osat": osat, "network": network, "cloud": cloud, "edge_ai": edge_ai,
        "ai_glass": ai_glass, "tws": tws, "wearable": wearable,
    }


def seed_chains(ind):
    """AI 眼镜产业链（文档第 7 节示例）"""
    chain_id = graph_repo.upsert_chain("AI 眼镜产业链", "从晶圆到终端消费者的完整链路", "消费电子")
    nodes = {}
    for name, ntype in [
        ("晶圆制造", "upstream"), ("封装测试", "upstream"),
        ("SoC / AI 芯片", "upstream"), ("Memory", "upstream"),
        ("Camera", "upstream"), ("Display", "upstream"),
        ("Battery / Power", "upstream"), ("AI Glass Assembly", "midstream"),
        ("品牌厂商", "downstream"), ("终端消费者", "end_market"),
    ]:
        nodes[name] = graph_repo.upsert_chain_node(chain_id, name, ntype)

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
    sc_id = graph_repo.upsert_chain("AI 服务器半导体链", "AI 芯片到云厂商部署", "半导体")
    sc = {}
    for name, ntype in [
        ("EDA / IP", "upstream"), ("晶圆制造", "upstream"), ("封装测试", "upstream"),
        ("HBM 存储", "upstream"), ("AI 芯片设计", "midstream"),
        ("服务器整机", "downstream"), ("云厂商 / 终端", "end_market"),
    ]:
        sc[name] = graph_repo.upsert_chain_node(sc_id, name, ntype)
    for f, t in [
        ("EDA / IP", "AI 芯片设计"), ("晶圆制造", "AI 芯片设计"),
        ("封装测试", "AI 芯片设计"), ("HBM 存储", "AI 芯片设计"),
        ("AI 芯片设计", "服务器整机"), ("服务器整机", "云厂商 / 终端"),
    ]:
        graph_repo.upsert_chain_edge(sc_id, sc[f], sc[t])
    return chain_id


def seed_companies(ind):
    """watchlist 公司 + 业务分拆 + 行业暴露 + 关系"""
    src = _src()
    companies = {}
    plan = {
        "NVDA": ("NVIDIA Corp", "美国", "NASDAQ", "半导体", [
            ("数据中心 AI 芯片", "ai_chip", 0.78, 1),
            ("网络互连（Mellanox）", "network", 0.14, 0),
            ("游戏 GPU", "ai_chip", 0.06, 0),
            ("汽车与机器人", "edge_ai", 0.02, 0),
        ]),
        "AMD": ("Advanced Micro Devices", "美国", "NASDAQ", "半导体", [
            ("数据中心（EPYC/MI）", "ai_chip", 0.50, 1),
            ("客户端（Ryzen）", "ai_chip", 0.30, 0),
            ("游戏（Radeon）", "ai_chip", 0.12, 0),
            ("嵌入式", "edge_ai", 0.08, 0),
        ]),
        "MSFT": ("Microsoft Corp", "美国", "NASDAQ", "软件/云", [
            ("智能云（Azure）", "cloud", 0.42, 1),
            ("生产力与商业流程", "cloud", 0.33, 0),
            ("更多个人计算", "cloud", 0.25, 0),
        ]),
        "GOOGL": ("Alphabet Inc", "美国", "NASDAQ", "互联网/云", [
            ("Google Cloud", "cloud", 0.12, 0),
            ("搜索与广告", "cloud", 0.75, 1),
            ("其他押注", "cloud", 0.13, 0),
        ]),
        "ORCL": ("Oracle Corp", "美国", "NYSE", "软件/云", [
            ("云基础设施（OCI）", "cloud", 0.40, 1),
            ("云应用（SaaS）", "cloud", 0.35, 0),
            ("许可与支持", "cloud", 0.25, 0),
        ]),
        "MRVL": ("Marvell Technology", "美国", "NASDAQ", "半导体", [
            ("数据中心定制芯片", "ai_chip", 0.55, 1),
            ("网络互连", "network", 0.25, 0),
            ("运营商基础设施", "network", 0.12, 0),
            ("汽车/工业", "edge_ai", 0.08, 0),
        ]),
        "MU": ("Micron Technology", "美国", "NASDAQ", "半导体", [
            ("DRAM", "memory", 0.70, 1),
            ("NAND/SSD", "memory", 0.30, 0),
        ]),
    }
    for sym, (name, country, exch, sector, segs) in plan.items():
        comp = resolve(sym)
        cid = comp["company_id"]
        graph_repo.upsert_company(sym, name, country=country, exchange=exch, sector=sector,
                                  description=f"{name}（种子数据）", source_id=src)
        for seg_name, ind_code, share, primary in segs:
            graph_repo.upsert_business_segment(
                cid, seg_name, industry_id=ind[ind_code],
                revenue_share=share, is_primary=primary)
            graph_repo.upsert_industry_company(ind[ind_code], cid, exposure=share,
                                               role=seg_name, source_id=src)
        companies[sym] = cid

    # 关系（供应商/客户/竞争对手/foundry）
    rel = [
        ("NVDA", "MU", "customer", 0.30, 0.8),          # NVDA 采购 HBM
        ("MU", "NVDA", "supplier", 0.30, 0.8),
        ("NVDA", "AMD", "competitor", 0.50, 0.9),
        ("NVDA", "MSFT", "partner", 0.60, 0.9),          # Azure OpenAI 算力
        ("AMD", "NVDA", "competitor", 0.50, 0.9),
        ("MRVL", "NVDA", "competitor", 0.25, 0.6),
        ("MSFT", "NVDA", "customer", 0.55, 0.85),        # Azure 采购 GPU
        ("GOOGL", "NVDA", "customer", 0.45, 0.8),
        ("ORCL", "NVDA", "customer", 0.40, 0.75),        # OCI 采购 GPU
        ("MRVL", "MSFT", "partner", 0.35, 0.7),          # 定制芯片
    ]
    for a, b, rtype, imp, conf in rel:
        graph_repo.upsert_relationship(companies[a], companies[b], rtype,
                                       importance=imp, confidence=conf, source_id=src)
    # foundry（挂到非 watchlist 公司主体）
    tsmc = graph_repo.upsert_company(None, "TSMC", "台积电", country="中国台湾",
                                     exchange="NYSE", listed=1, sector="半导体",
                                     source_id=src)
    for sym in ("NVDA", "AMD", "MRVL"):
        graph_repo.upsert_relationship(companies[sym], tsmc, "foundry",
                                       importance=0.9, confidence=0.9, source_id=src)

    # AI 眼镜产业链受益公司（文档第 15 节示例）
    glass_plan = [
        ("688608.SH", "恒玄科技", "中国", "SH", "端侧 AI SoC", [
            ("AI 眼镜 SoC", "ai_glass", 0.35, 1),
            ("TWS 耳机 SoC", "tws", 0.45, 0),
            ("智能穿戴 SoC", "wearable", 0.20, 0),
        ]),
        ("002241.SZ", "歌尔股份", "中国", "SZ", "消费电子制造", [
            ("AI 眼镜整机组装", "ai_glass", 0.30, 1),
            ("TWS 声学器件", "tws", 0.50, 0),
        ]),
        ("META", "Meta Platforms", "美国", "NASDAQ", "互联网/硬件", [
            ("AI 眼镜品牌（Ray-Ban Meta）", "ai_glass", 0.15, 0),
            ("社交平台", "cloud", 0.85, 1),
        ]),
    ]
    for sym, name, country, exch, sector, segs in glass_plan:
        cid = graph_repo.upsert_company(sym, name, country=country, exchange=exch,
                                        sector=sector, source_id=src)
        for seg_name, ind_code, share, primary in segs:
            graph_repo.upsert_business_segment(
                cid, seg_name, industry_id=ind[ind_code],
                revenue_share=share, is_primary=primary)
            graph_repo.upsert_industry_company(ind[ind_code], cid, exposure=share,
                                               role=seg_name, source_id=src)
        companies[sym] = cid
    return companies


def seed_factors_and_indicators(ind):
    """行业因子 + 指标 + 供需 + 预测 + 财务驱动"""
    src = _src()
    # AI 眼镜行业
    factors = [
        ("ai_glass", "AI 眼镜出货量", "demand", "positive", "Meta/字节等品牌新品带动"),
        ("ai_glass", "端侧 AI 芯片渗透率", "technology", "positive", "SoC 集成 NPU 能力提升"),
        ("ai_glass", "光学方案成本", "cost", "negative", "衍射光波导成本下降利好放量"),
        ("ai_glass", "政策/监管", "policy", "neutral", "摄像头隐私监管风险"),
        ("memory", "HBM 供需", "demand", "positive", "AI 服务器 HBM 需求爆发"),
        ("memory", "DRAM 合约价", "price", "positive", "涨价周期"),
        ("foundry", "先进制程产能利用率", "supply", "positive", "3nm/5nm 满载"),
        ("ai_chip", "AI 资本开支", "demand", "positive", "云厂商 capex 指引"),
        ("cloud", "云资本开支", "demand", "positive", "Azure/GCP/OCI 扩容"),
    ]
    for ind_code, name, ftype, direction, desc in factors:
        factor_repo.upsert_industry_factor(ind[ind_code], name, factor_type=ftype,
                                           direction=direction, description=desc, source_id=src)

    # 指标（AI 眼镜出货量，百万台）
    for period, v in [("2024", 12.0), ("2025", 45.0), ("2026E", 120.0)]:
        factor_repo.upsert_indicator(ind["ai_glass"], "shipment", v, unit="百万台",
                                     period=period, source_id=src)
    for period, v in [("2024", 420), ("2025", 380), ("2026E", 320)]:
        factor_repo.upsert_indicator(ind["ai_glass"], "asp", v, unit="美元",
                                     period=period, source_id=src)
    # DRAM 合约价指数
    for period, v in [("2024", 100), ("2025", 135), ("2026E", 160)]:
        factor_repo.upsert_indicator(ind["memory"], "dram_contract_price", v,
                                     unit="指数", period=period, source_id=src)
    # 云资本开支（十亿美元）
    for period, v in [("2024", 230), ("2025", 320), ("2026E", 420)]:
        factor_repo.upsert_indicator(ind["cloud"], "capex", v, unit="十亿美元",
                                     period=period, source_id=src)
    # AI 芯片出货量（百万颗）
    for period, v in [("2024", 8.0), ("2025", 14.0), ("2026E", 22.0)]:
        factor_repo.upsert_indicator(ind["ai_chip"], "shipment", v, unit="百万颗",
                                     period=period, source_id=src)

    # 供需：AI 眼镜（百万台）
    for period, cap, prod, dem in [("2025", 60, 42, 45), ("2026E", 150, 110, 120)]:
        factor_repo.upsert_supply_demand(ind["ai_glass"], period, capacity=cap,
                                         production=prod, demand=dem,
                                         gap=round(dem - prod, 2), source_id=src)

    # 行业预测
    for period, v in [("2026E", 120.0), ("2027E", 220.0)]:
        forecast_repo.upsert_industry_forecast(ind["ai_glass"], "shipment", period, v,
                                               confidence=0.7, model="intelligence-v1")

    # 财务驱动（指标 → 公司财务）
    inds = {}
    for r in factor_repo.get_indicators():
        inds[(r["industry_code"], r["indicator_name"], r["period"])] = r["id"]

    def ind_id(code, name):
        # 取最新 period 的指标 id
        rows = factor_repo.get_indicators(industry_id=ind[code], indicator_name=name)
        if not rows:
            return None
        return sorted(rows, key=lambda r: r["period"] or "")[-1]["id"]

    drivers = [
        # (symbol, segment, driver_type, driver_name, indicator_code, indicator_name, impact_metric, direction, coeff, base)
        ("NVDA", "数据中心 AI 芯片", "demand", "AI 芯片出货量", "ai_chip", "shipment", "revenue", "positive", 0.9, 14.0),
        ("NVDA", "数据中心 AI 芯片", "price", "HBM 涨价传导", "memory", "dram_contract_price", "gross_margin", "positive", 0.25, 100.0),
        ("MU", "DRAM", "price", "DRAM 合约价", "memory", "dram_contract_price", "revenue", "positive", 1.2, 100.0),
        ("MU", "DRAM", "demand", "HBM 需求", "memory", "dram_contract_price", "eps", "positive", 1.0, 100.0),
        ("MSFT", "智能云（Azure）", "demand", "云资本开支", "cloud", "capex", "revenue", "positive", 0.5, 230.0),
        ("GOOGL", "Google Cloud", "demand", "云资本开支", "cloud", "capex", "revenue", "positive", 0.35, 230.0),
        ("ORCL", "云基础设施（OCI）", "demand", "云资本开支", "cloud", "capex", "revenue", "positive", 0.45, 230.0),
        ("MRVL", "数据中心定制芯片", "demand", "AI 芯片出货量", "ai_chip", "shipment", "revenue", "positive", 0.7, 14.0),
        ("AMD", "数据中心（EPYC/MI）", "demand", "AI 芯片出货量", "ai_chip", "shipment", "revenue", "positive", 0.6, 14.0),
    ]
    companies = {c["stock_symbol"]: c["id"] for c in graph_repo.list_companies()}
    for sym, seg, dtype, dname, icode, iname, metric, direction, coeff, base in drivers:
        comp = graph_repo.get_company(symbol=sym)
        if not comp:
            continue
        segs = graph_repo.get_business_segments(symbol=sym)
        seg_id = next((s["id"] for s in segs if s["name"] == seg), None)
        iid = ind_id(icode, iname)
        factor_repo.upsert_financial_driver(
            comp["id"], dname, driver_type=dtype, business_segment_id=seg_id,
            source_indicator_id=iid, impact_metric=metric, impact_direction=direction,
            impact_coefficient=coeff, base_value=base, forecast_value=None,
            confidence=0.8, source_id=src)


def seed_all():
    ind = seed_industries()
    seed_chains(ind)
    companies = seed_companies(ind)
    seed_factors_and_indicators(ind)
    return {"industries": len(ind), "companies": len(companies),
            "note": "Intelligence Graph 种子数据就绪"}


if __name__ == "__main__":
    print(seed_all())
