"""스키마 + 커넥션. SQLite 하나로 간다."""
import os
import sqlite3

DB_PATH = os.environ.get("BIDNOTE_DB", "bidnote.db")

SCHEMA = """
-- 공고 원장. 자연키는 (공고번호, 차수) — 변경공고는 차수가 올라온다.
create table if not exists notice (
  bid_ntce_no   text not null,
  bid_ntce_ord  text not null,
  work_type     text not null,           -- 용역|물품|공사|외자
  bid_ntce_nm   text not null,
  ntce_instt_nm text,                    -- 공고기관
  dminstt_nm    text,                    -- 수요기관
  lrg_clsfc     text,                    -- 공공조달 대분류 (용역만 채워짐)
  mid_clsfc     text,                    -- 중분류
  cntrct_mthd   text,                    -- 제한경쟁|수의계약|일반경쟁|지명경쟁
  presmpt_prce  integer default 0,       -- 추정가격(원)
  bid_ntce_dt   text,                    -- 공고일시 YYYY-MM-DD HH:MM
  bid_clse_dt   text,                    -- 입찰마감일시 (86%만 채워짐)
  openg_dt      text,                    -- 개찰일시
  detail_url    text,
  raw           text not null,           -- 원본 JSON. 나중에 필드 추가할 때 재파싱용
  seen_at       text not null default (datetime('now','localtime')),
  primary key (bid_ntce_no, bid_ntce_ord)
);
create index if not exists notice_dt on notice (bid_ntce_dt desc);
create index if not exists notice_match on notice (work_type, lrg_clsfc, mid_clsfc);

-- 증분 커서. 업무유형별 마지막 수집 시각(YYYYMMDDHHMM).
create table if not exists cursor (
  work_type text primary key,
  last_dt   text not null
);

create table if not exists app_user (
  id         integer primary key autoincrement,
  toss_key   text unique not null,       -- 익명키 해시 또는 userKey
  push_ok    integer not null default 0, -- 알림 동의 여부
  created_at text not null default (datetime('now','localtime'))
);

-- 사용자가 등록한 알림 조건. 컬럼이 곧 조건 등록 UX다.
create table if not exists condition (
  id          integer primary key autoincrement,
  user_id     integer not null references app_user(id),
  label       text,                      -- 사용자가 붙인 이름
  work_type   text not null default '용역',
  lrg_clsfc   text,                      -- null = 전체
  mid_clsfc   text,
  amt_min     integer default 0,
  amt_max     integer default 0,         -- 0 = 상한 없음
  cntrct_mthd text,                      -- null = 전체, '수의계약' 등
  keyword     text,                      -- 분류로 안 잡히는 것 보완
  active      integer not null default 1,
  created_at  text not null default (datetime('now','localtime'))
);
create index if not exists condition_active on condition (active, work_type);

-- 발송 이력 = 중복 푸시 방지. 조건×공고 1건.
-- 차수(bid_ntce_ord)는 키에 넣지 않는다 — 실측상 변경공고가 6차까지 가서
-- 차수를 키에 넣으면 같은 공고를 8번 알리게 된다.
create table if not exists notified (
  condition_id integer not null,
  bid_ntce_no  text not null,
  sent_at      text,                     -- null = 큐에만 있고 미발송
  primary key (condition_id, bid_ntce_no)
);
create index if not exists notified_pending on notified (sent_at) where sent_at is null;

-- 공고번호별 최신 차수만. 매칭·조회는 전부 이걸 본다.
create view if not exists notice_latest as
select n.* from notice n
 where n.bid_ntce_ord = (select max(m.bid_ntce_ord) from notice m
                          where m.bid_ntce_no = n.bid_ntce_no);
"""


def connect(path=None):
    con = sqlite3.connect(path or DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("pragma journal_mode=WAL")
    con.execute("pragma foreign_keys=on")
    return con


def init(path=None):
    con = connect(path)
    con.executescript(SCHEMA)
    con.commit()
    return con


if __name__ == "__main__":
    init()
    print(f"초기화 완료: {DB_PATH}")
