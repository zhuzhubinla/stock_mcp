"""去重策略（四级）：
L1 source_id + source_news_id
L2 URL SHA256
L3 标题 + 摘要规范化后 SHA256
L4 Embedding 语义去重（第二阶段，预留）
"""
import hashlib


def sha256(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def url_hash(item):
    return sha256(item.url)


def content_hash(item):
    return sha256(f"{item.title}|{item.summary}")


def find_duplicate(db, source_id, item):
    """返回 (existing_id, level)；level: 1=源ID 2=URL 3=标题+摘要 0=无重复"""
    return db.find_dup_news(source_id, item.source_news_id, url_hash(item), content_hash(item))
