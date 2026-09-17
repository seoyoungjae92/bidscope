"""배치 스케줄러. API 프로세스 안에서 데몬 스레드로 돈다.

Railway 볼륨은 서비스당 하나라서 크론을 별도 서비스로 빼면
같은 SQLite 파일을 볼 수 없다. 그래서 한 프로세스에 넣는다.

    SCHEDULER=on python3 api.py     # 스케줄러 켜기
    python3 g2b.py run              # 수동 실행은 그대로

스케줄(KST):
    09:00 / 13:00 / 18:00   수집 + 매칭
    09:10                   공고 예고 + 신규 공고 푸시
    15:00                   마감 임박 푸시
"""
import os
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

# (시, 분, 작업 이름)
JOBS = [
    (9, 0, "collect"),
    (9, 10, "push"),
    (13, 0, "collect"),
    (15, 0, "push_closing"),
    (18, 0, "collect"),
]


def _run(name):
    import db
    import g2b
    import push

    con = db.init()
    try:
        if name == "collect":
            key = os.environ.get("G2B_KEY")
            if not key:
                print("[scheduler] G2B_KEY 없음, 수집 건너뜀")
                return
            n = g2b.collect(con, key) + g2b.collect_prespec(con, key)
            print(f"[scheduler] 수집 {n}건 · 공고큐 {g2b.match(con)} "
                  f"· 예고큐 {g2b.match_prespec(con)}")
        elif name == "push":
            send = os.environ.get("PUSH_SEND") == "on"
            push.run_batch(con, "공고 예고", g2b.prespec_digest(con),
                           push.render_prespec, push.TEMPLATE_PRESPEC,
                           g2b.mark_prespec_sent, send)
            push.run_batch(con, "신규 공고", g2b.pending_digest(con),
                           push.render, push.TEMPLATE_NEW, g2b.mark_sent, send)
        elif name == "push_closing":
            send = os.environ.get("PUSH_SEND") == "on"
            push.run_batch(con, "마감 임박", g2b.closing_digest(con),
                           push.render_closing, push.TEMPLATE_CLOSING,
                           g2b.mark_closing_sent, send)
    finally:
        con.close()


def _next_at(now, hh, mm):
    t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return t if t > now else t + timedelta(days=1)


def _loop():
    # 재시작 직후 같은 슬롯을 다시 돌지 않도록, 시작 시각 이후 것만 예약한다
    while True:
        now = datetime.now(KST)
        when, name = min(((_next_at(now, h, m), n) for h, m, n in JOBS),
                         key=lambda x: x[0])
        sleep = (when - now).total_seconds()
        print(f"[scheduler] 다음: {name} @ {when:%m-%d %H:%M} ({sleep/60:.0f}분 뒤)")
        time.sleep(max(sleep, 1))
        try:
            _run(name)
        except Exception:
            # 한 번 실패해도 스케줄러는 살아있어야 한다
            traceback.print_exc()
        time.sleep(61)   # 같은 분에 두 번 트리거되는 것 방지


def start():
    if os.environ.get("SCHEDULER") != "on":
        print("[scheduler] 꺼짐 (SCHEDULER=on 으로 켠다)")
        return
    threading.Thread(target=_loop, daemon=True, name="scheduler").start()
    print("[scheduler] 켜짐  " + ", ".join(f"{h:02d}:{m:02d} {n}" for h, m, n in JOBS))
