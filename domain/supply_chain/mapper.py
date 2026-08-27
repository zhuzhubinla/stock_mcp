"""Chain Mapper：产业链图谱（节点 + 上下游边）
Agent 流程第 5 步。支持按行业/公司反查产业链，双向追踪上游/下游。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories import graph_repo


def get_chain(chain_id=None, name=None):
    """产业链全图：节点 + 边（含上下游展开）"""
    chain = graph_repo.get_chain(chain_id=chain_id, name=name)
    if not chain:
        return {"error": f"chain not found: {name or chain_id}"}
    g = graph_repo.get_chain_graph(chain["id"])
    node_map = {n["id"]: n for n in g["nodes"]}
    edges = [{
        "from": e["from_node_id"], "from_name": node_map[e["from_node_id"]]["name"],
        "to": e["to_node_id"], "to_name": node_map[e["to_node_id"]]["name"],
        "relation": e["relation_type"],
    } for e in g["edges"] if e["from_node_id"] in node_map and e["to_node_id"] in node_map]
    return {
        "chain_id": chain["id"], "name": chain["name"],
        "description": chain["description"], "industry_id": chain.get("industry_id"),
        "nodes": [{"id": n["id"], "name": n["name"], "node_type": n["node_type"],
                   "position": n.get("position"),
                   "description": n["description"]} for n in g["nodes"]],
        "edges": edges,
    }


def upstream(chain_id, node_name, depth=2):
    """从某节点向上游追踪（多级）"""
    g = graph_repo.get_chain_graph(chain_id)
    node_map = {n["name"]: n["id"] for n in g["nodes"]}
    if node_name not in node_map:
        return {"error": f"node not found: {node_name}"}
    start = node_map[node_name]
    adj = {}
    for e in g["edges"]:
        adj.setdefault(e["to_node_id"], []).append(e["from_node_id"])
    result, visited = [], {start}
    frontier = [start]
    for _ in range(depth):
        nxt = []
        for nid in frontier:
            for pid in adj.get(nid, []):
                if pid not in visited:
                    visited.add(pid)
                    nxt.append(pid)
        if not nxt:
            break
        frontier = nxt
    names = {n["id"]: n["name"] for n in g["nodes"]}
    return {"node": node_name, "direction": "upstream", "depth": depth,
            "found": [names[i] for i in frontier if i in names]}


def downstream(chain_id, node_name, depth=2):
    """从某节点向下游追踪（多级）"""
    g = graph_repo.get_chain_graph(chain_id)
    node_map = {n["name"]: n["id"] for n in g["nodes"]}
    if node_name not in node_map:
        return {"error": f"node not found: {node_name}"}
    start = node_map[node_name]
    adj = {}
    for e in g["edges"]:
        adj.setdefault(e["from_node_id"], []).append(e["to_node_id"])
    result, visited = [], {start}
    frontier = [start]
    for _ in range(depth):
        nxt = []
        for nid in frontier:
            for cid in adj.get(nid, []):
                if cid not in visited:
                    visited.add(cid)
                    nxt.append(cid)
        if not nxt:
            break
        frontier = nxt
    names = {n["id"]: n["name"] for n in g["nodes"]}
    return {"node": node_name, "direction": "downstream", "depth": depth,
            "found": [names[i] for i in frontier if i in names]}


def _industry_ancestors(industry_id):
    """行业自身 + 逐级父行业（用于链名匹配）"""
    names, seen = [], set()
    cur = graph_repo.get_industry(industry_id=industry_id)
    while cur and cur["id"] not in seen:
        seen.add(cur["id"])
        names.append(cur["name"])
        cur = graph_repo.get_industry(industry_id=cur["parent_id"]) if cur.get("parent_id") else None
    return names


def chain_for_company(symbol):
    """公司 → 业务 → 行业 → 所属产业链
    匹配策略：行业自身名/父行业名 与 链名 双向包含；否则 code 关键字命中。
    """
    from domain.business.decomposer import decompose
    segs = decompose(symbol=symbol).get("segments", [])
    chains = {}
    all_chains = _list_all_chains()
    for s in segs:
        industry_id = s.get("industry_id")
        industry = s.get("industry")
        if not industry_id and not industry:
            continue
        candidates = _industry_ancestors(industry_id) if industry_id else [industry]
        hit = None
        for c in all_chains:
            for cand in candidates:
                if cand and (c["name"] in cand or cand in c["name"]):
                    hit = c
                    break
            if hit:
                break
        if hit:
            chains.setdefault(hit["name"], []).append(s["name"])
    return {"symbol": symbol, "chains": [{"chain": k, "segments": v}
                                         for k, v in chains.items()]}


def _list_all_chains():
    from data.repositories.mysql_db import get_conn
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name FROM industry_chain ORDER BY id")
        return cur.fetchall()
