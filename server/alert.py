"""운영 알림.

2026-09-20~22 푸시가 사흘간 죽었는데 print 로그뿐이라 아무도 몰랐다.
ALERT_WEBHOOK_URL이 있으면 배치 실패와 푸시 발송 실패를 거기로 한 줄 보낸다.
슬랙과 디스코드 웹훅이 둘 다 받도록 text와 content를 같이 넣는다.
없으면 로그만 남긴다. 알림이 실패해도 배치는 멈추지 않는다.
"""
import json
import os
import urllib.request


def send(text):
    print(f"[alert] {text}")
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        return False
    body = json.dumps({"text": text, "content": text}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).close()
        return True
    except Exception as e:
        print(f"[alert] 전송 실패: {e}")
        return False
