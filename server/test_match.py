"""매칭 로직 자체 점검.  python3 test_match.py

조건의 null은 '전체'를 뜻한다 — 이 규칙이 깨지면 엉뚱한 알림이 나가고,
그게 이 제품에서 가장 치명적인 버그다.
"""
import json
import os
import tempfile

import db
import g2b

NOTICES = [
    # (공고번호, 차수, 공고명, 대분류, 중분류, 계약방법, 추정가격)
    ("A1", "0", "OO시 홈페이지 개편", "ICT 서비스", "SW 및 시스템 개발", "제한경쟁", 50_000_000),
    ("A2", "0", "차세대 시스템 구축", "ICT 서비스", "시스템 운영환경 구축", "일반경쟁", 3_000_000_000),
    ("A3", "0", "청사 청소용역", "시설물관리 및 청소서비스", "시설물관리, 청소 등", "수의계약", 20_000_000),
    ("A4", "0", "학술연구 위탁", "연구조사서비스", "학술연구서비스", "수의계약", 80_000_000),
    ("A1", "1", "OO시 홈페이지 개편(변경)", "ICT 서비스", "SW 및 시스템 개발", "제한경쟁", 55_000_000),
    # 마감이 지난 공고. 절대 알리면 안 된다
    ("A5", "0", "지난 감리용역", "ICT 서비스", "SW 및 시스템 개발", "일반경쟁", 10_000_000),
]
EXPIRED = "A5"


def seed(con):
    for no, ord_, nm, lrg, mid, mthd, amt in NOTICES:
        item = {"bidNtceNo": no, "bidNtceOrd": ord_, "bidNtceNm": nm}
        con.execute(
            """insert or replace into notice
               (bid_ntce_no,bid_ntce_ord,work_type,bid_ntce_nm,lrg_clsfc,mid_clsfc,
                cntrct_mthd,presmpt_prce,bid_clse_dt,raw)
               values (?,?,'용역',?,?,?,?,?,?,?)""",
            (no, ord_, nm, lrg, mid, mthd, amt,
             "2020-01-01 00:00:00" if no == EXPIRED else None,
             json.dumps(item, ensure_ascii=False)))
    con.execute("insert into app_user(id,toss_key,push_ok) values (1,'t1',1)")
    con.commit()


def cond(con, **kw):
    kw.setdefault("user_id", 1)
    cols = ",".join(kw)
    cur = con.execute(
        f"insert into condition({cols}) values({','.join('?' * len(kw))})", tuple(kw.values()))
    con.commit()
    return cur.lastrowid


def matched(con, cid):
    return {r["bid_ntce_no"] for r in con.execute(
        "select bid_ntce_no from notified where condition_id=?", (cid,))}


def main():
    path = os.path.join(tempfile.mkdtemp(), "t.db")
    con = db.init(path)
    seed(con)

    c_all = cond(con)                                            # 전부 null = 전체
    c_ict = cond(con, lrg_clsfc="ICT 서비스")
    c_sw = cond(con, lrg_clsfc="ICT 서비스", mid_clsfc="SW 및 시스템 개발")
    c_small = cond(con, amt_max=100_000_000)                     # 1억 이하
    c_band = cond(con, amt_min=30_000_000, amt_max=100_000_000)
    c_su = cond(con, cntrct_mthd="수의계약")
    c_kw = cond(con, keyword="청소")
    c_mix = cond(con, lrg_clsfc="ICT 서비스", amt_max=100_000_000)
    c_off = cond(con, lrg_clsfc="ICT 서비스", active=0)           # 비활성
    c_none = cond(con, lrg_clsfc="없는분류")

    g2b.match(con)

    # A1은 차수 0,1 두 건이 있지만 최신 차수(1)만 보고 공고번호로 1건이다
    assert matched(con, c_all) == {"A1", "A2", "A3", "A4"}, "null 조건은 전체를 매칭해야 한다"
    assert matched(con, c_ict) == {"A1", "A2"}, "대분류 필터"
    assert matched(con, c_sw) == {"A1"}, "중분류 필터"
    assert matched(con, c_small) == {"A1", "A3", "A4"}, "amt_max 상한 (30억 A2 제외)"
    assert matched(con, c_band) == {"A1", "A4"}, "금액 구간 (2천만 A3 제외)"
    assert matched(con, c_su) == {"A3", "A4"}, "계약방법 필터"
    assert matched(con, c_kw) == {"A3"}, "키워드 부분일치"
    assert matched(con, c_mix) == {"A1"}, "분류+금액 동시 적용"
    assert matched(con, c_off) == set(), "비활성 조건은 매칭 안 됨"
    assert matched(con, c_none) == set(), "없는 분류는 0건"
    assert EXPIRED not in matched(con, c_all), "마감 지난 공고는 알리지 않는다"
    assert EXPIRED not in matched(con, c_sw), "마감 지난 공고는 알리지 않는다"

    # 변경공고(차수 1)는 재알림하지 않는다 — 차수까지 키에 넣으면 실측상 한 공고를 8번 알린다
    assert len(matched(con, c_sw)) == 1, "변경공고는 중복 알림 안 됨"
    # 최신 차수의 금액(5,500만)이 반영된다: 5천만 상한이면 빠져야 함
    c_tight = cond(con, mid_clsfc="SW 및 시스템 개발", amt_max=52_000_000)
    g2b.match(con)
    assert matched(con, c_tight) == set(), "최신 차수의 변경된 금액이 반영돼야 한다"

    # 재실행해도 중복이 안 쌓인다 (primary key + insert or ignore)
    n1 = con.execute("select count(*) c from notified").fetchone()["c"]
    g2b.match(con)
    n2 = con.execute("select count(*) c from notified").fetchone()["c"]
    assert n1 == n2, f"중복 방지 실패: {n1} -> {n2}"

    # 다이제스트는 동의한 유저만, 미발송분만
    d = g2b.pending_digest(con)
    assert set(d) == {1}, "push_ok=1인 유저만"

    # 일일 상한: 본문 건수는 cap, total은 전체
    d2 = g2b.pending_digest(con, cap=2)
    assert len(d2[1]["items"]) == 2, "cap만큼만 본문에 싣는다"
    assert d2[1]["total"] == d[1]["total"] > 2, "total은 전체 건수"

    # 발송 처리하면 큐가 비고, 상한에 걸려 안 실린 것도 함께 소진된다
    g2b.mark_sent(con, [1])
    assert g2b.pending_digest(con) == {}, "발송 후 큐가 비어야 한다"

    con.execute("update app_user set push_ok=0 where id=1")
    con.commit()
    assert g2b.pending_digest(con) == {}, "미동의 유저는 제외"

    print(f"통과. 조건 10종 · 공고 {len(NOTICES)}건 · 큐 {n1}건")


if __name__ == "__main__":
    main()
