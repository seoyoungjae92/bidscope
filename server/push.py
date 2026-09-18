"""토스 기능성 푸시 발송.

    python3 push.py              # dry-run: 보낼 내용만 출력
    python3 push.py --send       # 실제 발송 (인증서 + 승인된 템플릿 필요)

제목·본문은 콘솔 템플릿이 갖고 있고, 서버는 변수 값만 보낸다.

토스 제약:
  · 콘솔 템플릿이 제목 7자 / 본문 25자 이내 (공백 포함)
  · 변수가 치환되면 그보다 길어질 수 있어 서버가 값을 잘라 보낸다
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
TEMPLATE_NEW = os.environ.get("TOSS_TEMPLATE_NEW", "")
TEMPLATE_CLOSING = os.environ.get("TOSS_TEMPLATE_CLOSING", "")
TEMPLATE_PRESPEC = os.environ.get("TOSS_TEMPLATE_PRESPEC", "")

TITLE_MAX, BODY_MAX = 7, 25


def _man(won: int) -> str:
    """금액을 짧게. 변수 값도 길이 예산 안에 들어가야 한다."""
    if won >= 100_000_000:
        v = won / 100_000_000
        return f"{v:.0f}억" if v >= 10 else f"{v:.1f}억"
    return f"{won // 10_000:,}만"


def _cut(s: str, n: int) -> str:
    """변수 값이 길면 자른다.

    콘솔 템플릿이 25자 제한인데 변수가 치환되면 그보다 길어질 수 있다.
    예: '{{cond}} 공고 {{n}}건 올라왔어요.' 는 고정부가 12자라
    cond가 10자를 넘으면 렌더 결과가 25자를 넘는다.
    """
    s = (s or "").strip()
    # 자른 끝에 공백이 남으면 템플릿과 붙어 두 칸이 된다
    return s[:n].rstrip() if len(s) > n else s


# 콘솔 템플릿에 맞춘 변수 길이 상한. 템플릿을 고치면 여기도 고쳐야 한다.
# 계산: 25 - 고정부 - 다른 변수의 최대 길이
#   신규  '{{cond}} 공고 {{n}}건 올라왔어요.'  고정부 12 + n 최대 3  → 10
#   마감  '{{name}} {{t}}시 마감이에요.'        고정부  9 + t 최대 2  → 14
# 콘솔 목록에는 '{{n}} 건'처럼 변수 뒤에 공백이 붙어 보이고, 뒤에
# '(입찰레이더 알림)' 접미사도 자동으로 붙는다. 실제 길이 계산에
# 포함되는지 확인되지 않아 각각 1자씩 여유를 뒀다.
CAP_COND = 9
CAP_NAME = 13


def vars_new(digest: dict) -> dict:
    """새 입찰공고 → {{cond}}, {{n}}"""
    labels = {i["label"] for i in digest["items"] if i["label"]}
    cond = next(iter(labels)) if len(labels) == 1 else "내 조건"
    return {"cond": _cut(cond, CAP_COND), "n": str(digest["total"])}


def vars_prespec(digest: dict) -> dict:
    """공고 예고 → {{n}}"""
    return {"n": str(digest["total"])}


def vars_closing(digest: dict) -> dict:
    """마감 임박 → {{name}}, {{t}}

    여러 건이면 가장 임박한 것 하나를 대표로 보낸다.
    템플릿이 단수형이라 건수를 넣을 자리가 없다.
    """
    it = digest["items"][0]
    hhmm = str(it.get("bid_clse_dt") or "")[11:13].lstrip("0") or "0"
    return {"name": _cut(it.get("bid_ntce_nm"), CAP_NAME), "t": hhmm}


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


def run_batch(con, label, digests, make_vars, template, mark, send):
    if not digests:
        print(f"[{label}] 보낼 것 없음")
        return 0
    if not template:
        print(f"[{label}] 발송 코드가 없어요 — 환경변수를 확인하세요")
        return 0
    print(f"[{label}] 대상 {len(digests)}명  (템플릿 {template})")
    sent, failed = [], 0
    for uid, d in digests.items():
        ctx = make_vars(d)
        head = f"  user {uid}  {ctx}"
        if not send:
            print(f"{head}   ({d['total']}건 중 본문 {len(d['items'])}건)")
            for i in d["items"][:2]:
                # 공고는 bid_ntce_nm, 사전규격은 spec_nm
                name = i.get("bid_ntce_nm") or i.get("spec_nm") or "?"
                print(f"        · {name[:44]}")
            continue
        ok, resp = send_one(template, d["toss_key"], ctx)
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
        total += run_batch(con, "공고 예고", g2b.prespec_digest(con), vars_prespec,
                           TEMPLATE_PRESPEC, g2b.mark_prespec_sent, args.send)
    if args.kind in ("new", "all"):
        total += run_batch(con, "신규 공고", g2b.pending_digest(con), vars_new,
                           TEMPLATE_NEW, g2b.mark_sent, args.send)
    if args.kind in ("closing", "all"):
        total += run_batch(con, "마감 임박", g2b.closing_digest(con), vars_closing,
                           TEMPLATE_CLOSING, g2b.mark_closing_sent, args.send)
    if not args.send:
        print("\n(dry-run — 실제 발송은 --send)")


if __name__ == "__main__":
    main()
