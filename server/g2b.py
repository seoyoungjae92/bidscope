"""나라장터 수집 + 조건 매칭 배치.

    python3 g2b.py collect          # 증분 수집 (커서 이후 신규 공고)
    python3 g2b.py match            # 신규 공고 → 조건 매칭 → 알림 큐
    python3 g2b.py run              # collect + match (크론에 이것만 걸면 된다)

증분 조회(inqryBgnDt/inqryEndDt)가 실측으로 정확히 동작하므로 스냅샷 diff는 없다.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import db

BASE = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService"
OPS = {
    "용역": "getBidPblancListInfoServcPPSSrch",
    "물품": "getBidPblancListInfoThngPPSSrch",
    "공사": "getBidPblancListInfoCnstwkPPSSrch",
    "외자": "getBidPblancListInfoFrgcptPPSSrch",
}
# MVP는 용역만. 분류체계가 채워져 오는 유일한 업무유형이다(VERIFIED.md).
ACTIVE_TYPES = os.environ.get("BIDNOTE_TYPES", "용역").split(",")

ROWS = 300          # 페이지당. 일 400여건이라 넉넉하다
MAX_PAGES = 20      # 안전장치: 백필 폭주 방지
BACKFILL_DAYS = 3   # 커서가 없을 때 처음 긁을 기간


def _key():
    k = os.environ.get("G2B_KEY")
    if not k:
        sys.exit("G2B_KEY 환경변수가 없다.")
    return k


def fetch(op, bgn, end, page, key):
    """한 페이지 조회. (items, total) 반환."""
    q = {
        "ServiceKey": key, "type": "json", "inqryDiv": "1",
        "inqryBgnDt": bgn, "inqryEndDt": end,
        "pageNo": str(page), "numOfRows": str(ROWS),
    }
    url = f"{BASE}/{op}?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                raw = r.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200] if e.fp else ""
            raise RuntimeError(f"HTTP {e.code} {detail}")
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"{type(e).__name__}: {e}")
            time.sleep(2 ** attempt)
    body = json.loads(raw).get("response", {}).get("body", {})
    items = body.get("items") or []
    if isinstance(items, dict):
        items = items.get("item", items)
    if isinstance(items, dict):
        items = [items]
    return items, int(body.get("totalCount", 0))


def _amt(v):
    """추정가격은 문자열로 오고 빈값·소수점이 섞인다."""
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _dt(v):
    """'2026-09-17 14:30' 형태로 통일. 빈값은 None."""
    s = (v or "").strip()
    return s if s else None


def row_of(item, work_type):
    return (
        item.get("bidNtceNo", ""),
        str(item.get("bidNtceOrd", "0")),
        work_type,
        item.get("bidNtceNm", ""),
        item.get("ntceInsttNm"),
        item.get("dminsttNm"),
        item.get("pubPrcrmntLrgClsfcNm"),
        item.get("pubPrcrmntMidClsfcNm"),
        item.get("cntrctCnclsMthdNm"),
        _amt(item.get("presmptPrce")),
        _dt(item.get("bidNtceDt")),
        _dt(item.get("bidClseDt")),
        _dt(item.get("opengDt")),
        item.get("bidNtceDtlUrl") or item.get("bidNtceUrl"),
        json.dumps(item, ensure_ascii=False),
    )


def collect(con, key):
    """커서 이후 신규 공고를 적재. 적재 건수 반환."""
    now = datetime.now()
    end = now.strftime("%Y%m%d%H%M")
    inserted = 0

    for wt in ACTIVE_TYPES:
        op = OPS.get(wt)
        if not op:
            print(f"  {wt}: 알 수 없는 업무유형, 건너뜀")
            continue

        cur = con.execute("select last_dt from cursor where work_type=?", (wt,)).fetchone()
        bgn = cur["last_dt"] if cur else (now - timedelta(days=BACKFILL_DAYS)).strftime("%Y%m%d%H%M")
        if bgn >= end:
            print(f"  {wt}: 커서가 현재 이후({bgn}), 건너뜀")
            continue

        page, got, total = 1, 0, None
        while page <= MAX_PAGES:
            items, total = fetch(op, bgn, end, page, key)
            if not items:
                break
            rows = [row_of(i, wt) for i in items if i.get("bidNtceNo")]
            con.executemany(
                """insert or replace into notice
                   (bid_ntce_no,bid_ntce_ord,work_type,bid_ntce_nm,ntce_instt_nm,
                    dminstt_nm,lrg_clsfc,mid_clsfc,cntrct_mthd,presmpt_prce,
                    bid_ntce_dt,bid_clse_dt,openg_dt,detail_url,raw)
                   values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
            got += len(rows)
            if got >= (total or 0):
                break
            page += 1
            time.sleep(0.2)

        # 커서는 조회 성공 후에만 전진. 실패하면 다음 실행이 같은 구간을 다시 긁는다.
        con.execute(
            "insert into cursor(work_type,last_dt) values(?,?) "
            "on conflict(work_type) do update set last_dt=excluded.last_dt", (wt, end))
        con.commit()
        inserted += got
        print(f"  {wt}: {bgn}~{end}  {got}건 (전체 {total})")

    return inserted


# 조건 ↔ 공고 매칭. 전부 SQL 한 방으로 끝난다.
# notice_latest 뷰를 보므로 변경공고(차수 1~5)가 재알림되지 않는다.
MATCH_SQL = """
insert or ignore into notified (condition_id, bid_ntce_no)
select c.id, n.bid_ntce_no
  from condition c
  join notice_latest n
    on n.work_type = c.work_type
   and (c.lrg_clsfc   is null or n.lrg_clsfc   = c.lrg_clsfc)
   and (c.mid_clsfc   is null or n.mid_clsfc   = c.mid_clsfc)
   and (c.cntrct_mthd is null or n.cntrct_mthd = c.cntrct_mthd)
   and (c.amt_min = 0 or n.presmpt_prce >= c.amt_min)
   and (c.amt_max = 0 or n.presmpt_prce <= c.amt_max)
   and (c.keyword is null or n.bid_ntce_nm like '%' || c.keyword || '%')
 where c.active = 1
   and n.seen_at >= datetime('now','localtime','-1 day')
   -- 이미 마감된 공고는 알리지 않는다. 마감일시가 없는 건(14%)은 통과시킨다
   and (n.bid_clse_dt is null or n.bid_clse_dt >= datetime('now','localtime'))
"""

# 푸시 피로 방지. 실측상 넓은 조건은 일 180건까지 나온다(VERIFIED.md).
DAILY_CAP = 20


def match(con):
    """신규 공고를 조건에 매칭해 알림 큐에 넣는다. 큐 적재 건수 반환."""
    before = con.execute("select count(*) c from notified").fetchone()["c"]
    con.execute(MATCH_SQL)
    con.commit()
    return con.execute("select count(*) c from notified").fetchone()["c"] - before


def pending_digest(con, cap=DAILY_CAP):
    """발송 대기분을 사용자별로 묶는다. 푸시는 사용자당 1건 다이제스트.

    cap은 푸시 본문에 실을 상위 건수다. total은 실제 전체 건수라
    "N건 중 상위 20건" 식으로 안내할 수 있다.
    """
    rows = con.execute("""
        select u.id user_id, u.toss_key, c.id cond_id, c.label,
               n.bid_ntce_no, n.bid_ntce_nm, n.presmpt_prce, n.bid_clse_dt
          from notified t
          join condition    c on c.id = t.condition_id
          join app_user     u on u.id = c.user_id
          join notice_latest n on n.bid_ntce_no = t.bid_ntce_no
         where t.sent_at is null and u.push_ok = 1
           and (n.bid_clse_dt is null or n.bid_clse_dt >= datetime('now','localtime'))
         order by u.id, (n.bid_clse_dt is null), n.bid_clse_dt
    """).fetchall()
    out = {}
    for r in rows:
        v = out.setdefault(r["user_id"], {"toss_key": r["toss_key"], "items": [], "total": 0})
        v["total"] += 1
        if len(v["items"]) < cap:
            v["items"].append(dict(r))
    return out


# 마감 임박 알림. 이 창이 좁으면 준비할 시간이 없고, 넓으면 잊는다.
CLOSING_MIN_H, CLOSING_MAX_H = 6, 48


def closing_digest(con, cap=DAILY_CAP):
    """마감이 임박한 공고를 사용자별로 묶는다.

    이미 신규 알림을 받은 공고만 대상이다 — 처음 보는 공고를
    "곧 마감"이라고만 알리면 맥락이 없다.
    """
    rows = con.execute(f"""
        select u.id user_id, u.toss_key, c.id cond_id, c.label,
               n.bid_ntce_no, n.bid_ntce_nm, n.presmpt_prce, n.bid_clse_dt
          from notified t
          join condition    c on c.id = t.condition_id
          join app_user     u on u.id = c.user_id
          join notice_latest n on n.bid_ntce_no = t.bid_ntce_no
         where t.sent_at is not null
           and t.closing_sent_at is null
           and u.push_ok = 1
           and c.active = 1
           and n.bid_clse_dt is not null
           and n.bid_clse_dt >  datetime('now','localtime','+{CLOSING_MIN_H} hours')
           and n.bid_clse_dt <= datetime('now','localtime','+{CLOSING_MAX_H} hours')
         order by u.id, n.bid_clse_dt
    """).fetchall()
    out = {}
    for r in rows:
        v = out.setdefault(r["user_id"], {"toss_key": r["toss_key"], "items": [], "total": 0})
        v["total"] += 1
        if len(v["items"]) < cap:
            v["items"].append(dict(r))
    return out


def mark_closing_sent(con, user_ids):
    """마감 임박 발송 완료. 창을 벗어난 건도 함께 닫는다 —
    안 그러면 이미 마감된 공고가 큐에 영원히 남는다."""
    con.executemany(f"""
        update notified set closing_sent_at = datetime('now','localtime')
         where closing_sent_at is null and sent_at is not null
           and condition_id in (select id from condition where user_id = ?)
           and bid_ntce_no in (
                 select bid_ntce_no from notice_latest
                  where bid_clse_dt is not null
                    and bid_clse_dt <= datetime('now','localtime','+{CLOSING_MAX_H} hours'))""",
        [(u,) for u in user_ids])
    con.commit()


def mark_sent(con, user_ids):
    """발송 완료 처리. 상한 때문에 본문에 안 실린 건도 함께 소진한다
    (다음 배치에 밀리면 계속 쌓여서 영영 안 끝난다)."""
    con.executemany("""
        update notified set sent_at = datetime('now','localtime')
         where sent_at is null and condition_id in
               (select id from condition where user_id = ?)""",
        [(u,) for u in user_ids])
    con.commit()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    con = db.init()

    if cmd in ("collect", "run"):
        print("[수집]")
        n = collect(con, _key())
        print(f"  총 {n}건 적재\n")

    if cmd in ("match", "run"):
        print("[매칭]")
        q = match(con)
        print(f"  알림 큐 {q}건 신규\n")
        d = pending_digest(con)
        print(f"[신규 발송 대기] 사용자 {len(d)}명")
        for uid, v in list(d.items())[:5]:
            print(f"  user {uid}: {v['total']}건")
        cd = closing_digest(con)
        print(f"[마감 임박 대기] 사용자 {len(cd)}명")
        for uid, v in list(cd.items())[:5]:
            print(f"  user {uid}: {v['total']}건")

    if cmd not in ("collect", "match", "run"):
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
