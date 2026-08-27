import requests

from config import WECHAT_WEBHOOK


def send(msg):
    if not WECHAT_WEBHOOK:
        print("[wechat_push] 未配置 WECHAT_WEBHOOK，跳过推送")
        return
    data = {
        "msgtype": "text",
        "text": {"content": msg},
    }
    try:
        requests.post(WECHAT_WEBHOOK, json=data, timeout=10)
    except Exception as e:
        print(f"[wechat_push] 推送失败: {e}")
