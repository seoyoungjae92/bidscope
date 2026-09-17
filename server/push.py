"""토스 기능성 푸시 발송.

    python3 push.py              # dry-run: 보낼 내용만 출력
    python3 push.py --send       # 실제 발송 (인증서 + 승인된 템플릿 필요)

토스 제약:
  · 제목 7자 / 본문 25자 이내 (공백 포함) — RENDER가 이걸 보장한다
  · templateSetCode는 콘솔에서 사전 검수 통과해야 함 (미승인 시 에러 5004)
  · mTLS 클라이언트 인증서 필요
  · 유저당 분당 10건, 앱당 분당 15,000건
"""
import argparse
import http.client
import json
import os
import ssl
import sys

import db
import g2b

HOST = "apps-in-toss-api.toss.im"
PATH = "/api-partner/v1/apps-in-toss/messenger/send-message"

CERT = os.environ.get("TOSS_CERT")      # 클라이언트 인증서 (.pem)
CERT_KEY = os.environ.get("TOSS_KEY")   # 개인키 (.pem)
TEMPLATE = os.environ.get("TOSS_TEMPLATE", "BIDNOTE_NEW")

TITLE_MAX, BODY_MAX = 7, 25


def _man(won: int) -> str:
    """금액을 짧게. 본문 25자 안에 넣어야 한다."""
    if won >= 100_000_000:
        v = won / 100_000_000
        return f"{v:.0f}억" if v >= 10 else f"{v:.1f}억"
    return f"{won // 10_000:,}만"


def render(digest: dict) -> dict:
    """다이제스트 → 푸시 제목·본문. 길이 제한을 여기서 강제한다."""
    items, total = digest["items"], digest["total"]
    title = "새 입찰공고"
    if total == 1:
        it = items[0]
        # 공고명을 남는 자리에 맞춰 자른다
        tail = f" {_man(it['presmpt_prce'])}" if it["presmpt_prce"] else ""
        room = BODY_MAX - len(tail) - len("  올라왔어요")
        name = it["bid_ntce_nm"][:room].strip()
        body = f"{name}{tail} 올라왔어요"
    else:
        labels = {i["label"] for i in items if i["label"]}
        who = next(iter(labels)) if len(labels) == 1 else "내 조건"
        tail = f" 공고 {total}건 올라왔어요"
        # 조건 이름은 사용자 입력이다. 길면 자른다 —
        # assert로 두면 한 유저의 긴 라벨이 배치 전체를 죽인다.
        who = who[:max(0, BODY_MAX - len(tail))]
        body = (who + tail) if who else f"공고 {total}건 올라왔어요"
    assert len(title) <= TITLE_MAX, f"제목 {len(title)}자: {title}"
    assert len(body) <= BODY_MAX, f"본문 {len(body)}자: {body}"
    return {"title": title, "body": body}


def send_one(anon_key: str, context: dict) -> tuple:
    """mTLS로 단건 발송. (성공여부, 응답) 반환."""
    if not (CERT and CERT_KEY):
        return False, "TOSS_CERT / TOSS_KEY 환경변수 없음"
    ctx = ssl.create_default_context()
    ctx.load_cert_chain(certfile=CERT, keyfile=CERT_KEY)
    conn = http.client.HTTPSConnection(HOST, context=ctx, timeout=20)
    payload = json.dumps({"templateSetCode": TEMPLATE, "context": context},
                         ensure_ascii=False)
    conn.request("POST", PATH, body=payload.encode(), headers={
        "Content-Type": "application/json",
        "x-anon-key": anon_key,
    })
    r = conn.getresponse()
    raw = r.read().decode("utf-8", "replace")
    conn.close()
    ok = r.status == 200 and '"FAIL"' not in raw
    return ok, raw[:200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="실제 발송 (기본은 dry-run)")
    args = ap.parse_args()

    con = db.init()
    digests = g2b.pending_digest(con)
    if not digests:
        print("보낼 것 없음")
        return

    sent_users, failed = [], 0
    for uid, d in digests.items():
        msg = render(d)
        head = f"user {uid}  [{msg['title']}] {msg['body']}"
        if not args.send:
            print(f"{head}   ({d['total']}건 중 본문 {len(d['items'])}건)")
            for i in d["items"][:3]:
                print(f"      · {i['bid_ntce_nm'][:44]}")
            continue
        ok, resp = send_one(d["toss_key"], {**msg, "count": str(d["total"])})
        print(f"{head}  →  {'OK' if ok else 'FAIL ' + resp}")
        if ok:
            sent_users.append(uid)
        else:
            failed += 1

    if args.send and sent_users:
        g2b.mark_sent(con, sent_users)
    print(f"\n대상 {len(digests)}명" +
          (f" · 발송 {len(sent_users)} · 실패 {failed}" if args.send else " (dry-run)"))


if __name__ == "__main__":
    main()
