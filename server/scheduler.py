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
                           push.vars_prespec, push.TEMPLATE_PRESPEC,
                           g2b.mark_prespec_sent, send)
            push.run_batch(con, "신규 공고", g2b.pending_digest(con),
                           push.vars_new, push.TEMPLATE_NEW, g2b.mark_sent, send)
            con.execute("insert into cursor(work_type,last_dt) values(?,?) "
                        "on conflict(work_type) do update set last_dt=excluded.last_dt",
                        (PUSH_KEY, datetime.now(KST).strftime("%Y%m%d%H%M")))
            con.commit()
        elif name == "push_closing":
            send = os.environ.get("PUSH_SEND") == "on"
            push.run_batch(con, "마감 임박", g2b.closing_digest(con),
                           push.vars_closing, push.TEMPLATE_CLOSING,
                           g2b.mark_closing_sent, send)
    finally:
        con.close()


def _next_at(now, hh, mm):
    t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return t if t > now else t + timedelta(days=1)


STALE_HOURS = 5   # 수집 간격이 최대 5시간(09→13→18)이라 그보다 오래됐으면 놓친 것이다

# 푸시도 슬롯을 통째로 건너뛴다. 2026-09-20~22 사흘간 09:10 푸시가 죽은 채로 지나갔고
# 큐만 쌓였다(공고 46 · 예고 26). 부팅 때 밀린 게 있으면 따라잡는다.
PUSH_KEY = "@push"        # cursor 테이블에 섞이지 않게 @를 붙인다(수집 커서는 업무유형 이름)
PUSH_STALE_HOURS = 20     # 하루 한 번(09:10)이라 20시간 넘게 비었으면 놓친 것이다
PUSH_HOURS = (9, 21)      # 이 시간대에만 따라잡는다 — 밤에 알림이 울리면 안 된다


def _catch_up():
    """부팅 시 커서가 오래됐으면 즉시 수집한다.

    재배포·컨테이너 재시작이 수집 슬롯을 통째로 건너뛴다. 실제로
    09:00 수집이 그렇게 빠졌다. 다음 슬롯까지 몇 시간을 비워 두지 않는다.
    빈 DB(첫 배포)도 커서가 없으니 같은 경로로 처리된다.
    """
    import db
    con = db.connect()
    try:
        r = con.execute("select max(last_dt) d from cursor "
                        "where work_type not like '@%'").fetchone()
    finally:
        con.close()
    last = r and r["d"]
    if last:
        gap = datetime.now(KST) - datetime.strptime(last, "%Y%m%d%H%M").replace(tzinfo=KST)
        if gap < timedelta(hours=STALE_HOURS):
            return
        print(f"[scheduler] 마지막 수집이 {gap.total_seconds()/3600:.1f}시간 전이에요. 따라잡습니다")
    else:
        print("[scheduler] 수집 기록이 없어요. 첫 수집을 시작합니다")
    try:
        _run("collect")
    except Exception:
        traceback.print_exc()


def _push_catch_up():
    """부팅 시 09:10 푸시를 놓쳤으면 즉시 한 번 보낸다.

    수집과 달리 푸시는 사람 폰을 울리므로 조건을 좁게 둔다 —
    하루 한 번 슬롯을 실제로 놓쳤을 때(PUSH_STALE_HOURS)만, 그리고 낮에만.
    """
    import db
    con = db.connect()
    try:
        r = con.execute("select last_dt from cursor where work_type=?", (PUSH_KEY,)).fetchone()
    finally:
        con.close()
    now = datetime.now(KST)
    if not PUSH_HOURS[0] <= now.hour < PUSH_HOURS[1]:
        return
    if r and r["last_dt"]:
        gap = now - datetime.strptime(r["last_dt"], "%Y%m%d%H%M").replace(tzinfo=KST)
        if gap < timedelta(hours=PUSH_STALE_HOURS):
            return
        print(f"[scheduler] 마지막 푸시가 {gap.total_seconds()/3600:.1f}시간 전이에요. 따라잡습니다")
    else:
        print("[scheduler] 푸시 기록이 없어요. 밀린 알림을 보냅니다")
    try:
        _run("push")
    except Exception:
        traceback.print_exc()


def _loop():
    _catch_up()
    _push_catch_up()
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
