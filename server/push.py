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
TEMPLATE_NEW = os.environ.get("TOSS_TEMPLATE_NEW", "BIDNOTE_NEW")
TEMPLATE_CLOSING = os.environ.get("TOSS_TEMPLATE_CLOSING", "BIDNOTE_CLOSING")
TEMPLATE_PRESPEC = os.environ.get("TOSS_TEMPLATE_PRESPEC", "BIDNOTE_PRESPEC")

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


def render_closing(digest: dict) -> dict:
    """마감 임박 다이제스트 → 제목·본문."""
    items, total = digest["items"], digest["total"]
    title = "마감 임박"
    if total == 1:
        it = items[0]
        hhmm = str(it["bid_clse_dt"])[11:16]
        tail = f" {hhmm} 마감이에요" if hhmm else " 곧 마감이에요"
        name = it["bid_ntce_nm"][:BODY_MAX - len(tail)].strip()
        body = f"{name}{tail}"
    else:
        body = f"관심 공고 {total}건 곧 마감이에요"
        if len(body) > BODY_MAX:
            body = f"공고 {total}건 곧 마감이에요"
    assert len(title) <= TITLE_MAX, f"제목 {len(title)}자: {title}"
    assert len(body) <= BODY_MAX, f"본문 {len(body)}자: {body}"
    return {"title": title, "body": body}


def render_prespec(digest: dict) -> dict:
    """사전규격 = 공고 예고. 중앙값 7일 먼저 뜬다."""
    items, total = digest["items"], digest["total"]
    title = "공고 예고"
    if total == 1:
        tail = " 공고 예정이에요"
        name = items[0]["spec_nm"][:BODY_MAX - len(tail)].strip()
        body = f"{name}{tail}"
    else:
        body = f"관심 분야 {total}건 공고 예정이에요"
        if len(body) > BODY_MAX:
            body = f"{total}건 공고 예정이에요"
    assert len(title) <= TITLE_MAX, f"제목 {len(title)}자: {title}"
    assert len(body) <= BODY_MAX, f"본문 {len(body)}자: {body}"
    return {"title": title, "body": body}


def send_one(template: str, anon_key: str, context: dict) -> tuple:
    """mTLS로 단건 발송. (성공여부, 응답) 반환."""
    if not (CERT and CERT_KEY):
        return False, "TOSS_CERT / TOSS_KEY 환경변수 없음"
    ctx = ssl.create_default_context()
    ctx.load_cert_chain(certfile=CERT, keyfile=CERT_KEY)
    conn = http.client.HTTPSConnection(HOST, context=ctx, timeout=20)
    payload = json.dumps({"templateSetCode": template, "context": context},
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


def run_batch(con, label, digests, renderer, template, mark, send):
    if not digests:
        print(f"[{label}] 보낼 것 없음")
        return 0
    print(f"[{label}] 대상 {len(digests)}명")
    sent, failed = [], 0
    for uid, d in digests.items():
        msg = renderer(d)
        head = f"  user {uid}  [{msg['title']}] {msg['body']}"
        if not send:
            print(f"{head}   ({d['total']}건 중 본문 {len(d['items'])}건)")
            for i in d["items"][:2]:
                # 공고는 bid_ntce_nm, 사전규격은 spec_nm
                name = i.get("bid_ntce_nm") or i.get("spec_nm") or "?"
                print(f"        · {name[:44]}")
            continue
        ok, resp = send_one(template, d["toss_key"], {**msg, "count": str(d["total"])})
        print(f"{head}  →  {'OK' if ok else 'FAIL ' + resp}")
        sent.append(uid) if ok else None
        failed += 0 if ok else 1
    if send and sent:
        mark(con, sent)
        print(f"  발송 {len(sent)} · 실패 {failed}")
    return len(digests)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="실제 발송 (기본은 dry-run)")
    ap.add_argument("--kind", choices=["new", "closing", "prespec", "all"], default="all")
    args = ap.parse_args()

    con = db.init()
    total = 0
    if args.kind in ("prespec", "all"):
        total += run_batch(con, "공고 예고", g2b.prespec_digest(con), render_prespec,
                           TEMPLATE_PRESPEC, g2b.mark_prespec_sent, args.send)
    if args.kind in ("new", "all"):
        total += run_batch(con, "신규 공고", g2b.pending_digest(con), render,
                           TEMPLATE_NEW, g2b.mark_sent, args.send)
    if args.kind in ("closing", "all"):
        total += run_batch(con, "마감 임박", g2b.closing_digest(con), render_closing,
                           TEMPLATE_CLOSING, g2b.mark_closing_sent, args.send)
    if not args.send:
        print("\n(dry-run — 실제 발송은 --send)")


if __name__ == "__main__":
    main()
