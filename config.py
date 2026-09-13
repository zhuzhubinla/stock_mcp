# Stock Agent 配置
import os
from pathlib import Path

# 轻量 .env 加载（无第三方依赖）：优先读环境变量，其次读项目根 .env
# 用途：METACULUS_API_KEY 等敏感值不入库不入 git
_ENV_FILE = Path(__file__).resolve().parent / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
        if _k and _k not in os.environ:
            os.environ[_k] = _v

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")

# 新闻源 API Keys（环境变量注入，缺省留空=该源不可用）
ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")
BENZINGA_API_KEY = os.environ.get("BENZINGA_API_KEY", "")

# Metaculus API Token（预测源，2026-09 起强制鉴权）
# 获取：登录 https://www.metaculus.com → Settings/Account → API token
METACULUS_API_KEY = os.environ.get("METACULUS_API_KEY", "")
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "stock-agent admin@example.com")

# MySQL 配置
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3306
MYSQL_USER = "admin"
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DB = "stock_db"

# 数据刷新阈值（秒）：超过则从数据源拉新
QUOTE_TTL = 300        # 行情 5 分钟
HISTORY_TTL = 3600     # 历史 1 小时
NEWS_TTL = 1800        # 新闻 30 分钟
FUNDAMENTAL_TTL = 86400  # 基本面 1 天

# LLM 配置（AI 新闻分析：sentiment/event/impact；无 key 时回退规则引擎）
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = "deepseek-v4-flash"

# 兼容旧 ai_analysis.py（OpenAI SDK 用法）
OPENAI_KEY = DEEPSEEK_API_KEY
OPENAI_BASE = DEEPSEEK_BASE_URL

# 微信推送 Webhook（留空则跳过推送）
WECHAT_WEBHOOK = os.environ.get("WECHAT_WEBHOOK", "")

# 新闻体系配置
WATCHLIST_PATH = "/home/admin/stock_agent/watchlist.json"
NEWS_FETCH_HOURS = 24          # 单次采集时间窗口（小时）
NEWS_ANALYZE_BATCH = 10        # 单轮最多分析条数
NEWS_COLLECT_INTERVAL_MIN = 15 # watchlist 采集间隔
NEWS_HOT_INTERVAL_MIN = 5      # 热门股采集间隔（预留）
NEWS_POOL_INTERVAL_MIN = 60    # 全股票池采集间隔
ANOMALY_SCAN_DAYS = 30         # 异常检测扫描窗口
ANOMALY_NEWS_WINDOW_HOURS = 48 # 异常前后新闻关联窗口
MODEL = "deepseek/deepseek-v4-flash"
