"""스키마 + 커넥션. SQLite 하나로 간다."""
import os
import sqlite3

DB_PATH = os.environ.get("BIDNOTE_DB", "bidnote.db")

# 공고 시각은 전부 KST다. 컨테이너에 tzdata가 없으면 TZ를 설정해도
# localtime이 UTC로 폴백해서 마감 필터가 9시간 어긋난다.
# 한국은 서머타임이 없으므로 오프셋을 그대로 박는 게 가장 확실하다.
KST = "'now','+9 hours'"
NOW = f"datetime({KST})"

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
  seen_at       text not null default (datetime('now','+9 hours')),
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
  created_at text not null default (datetime('now','+9 hours'))
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
  created_at  text not null default (datetime('now','+9 hours'))
);
create index if not exists condition_active on condition (active, work_type);

-- 발송 이력 = 중복 푸시 방지. 조건×공고 1건.
-- 차수(bid_ntce_ord)는 키에 넣지 않는다 — 실측상 변경공고가 6차까지 가서
-- 차수를 키에 넣으면 같은 공고를 8번 알리게 된다.
create table if not exists notified (
  condition_id   integer not null,
  bid_ntce_no    text not null,
  sent_at        text,                   -- 신규 공고 알림 발송 시각. null = 미발송
  closing_sent_at text,                  -- 마감 임박 알림 발송 시각. 공고당 1회
  primary key (condition_id, bid_ntce_no)
);
create index if not exists notified_pending on notified (sent_at) where sent_at is null;

-- 사전규격. 입찰공고보다 중앙값 7일 먼저 뜬다(실측).
-- 공고와 달리 대/중분류 체계가 없어서 매칭 축이 다르다.
create table if not exists prespec (
  spec_no       text primary key,        -- bfSpecRgstNo
  work_type     text not null,
  spec_nm       text not null,           -- prdctClsfcNoNm (실제로는 사업명)
  order_instt   text,
  bsns_div      text,                    -- 일반용역 | 기술용역
  sw_biz        integer not null default 0,  -- swBizObjYn = Y
  budget        integer not null default 0,  -- asignBdgtAmt
  rgst_dt       text,
  opnin_clse_dt text,                    -- 규격 의견 등록 마감
  bid_ntce_no   text,                    -- 나중에 채워지는 공고번호 (88% 채워짐)
  doc_url       text,
  raw           text not null,
  seen_at       text not null default (datetime('now','+9 hours'))
);
create index if not exists prespec_clse on prespec (opnin_clse_dt);

-- 사전규격 알림 발송 이력
create table if not exists prespec_notified (
  condition_id integer not null,
  spec_no      text not null,
  sent_at      text,
  primary key (condition_id, spec_no)
);
create index if not exists prespec_pending on prespec_notified (sent_at) where sent_at is null;

-- 공고번호별 최신 차수만. 매칭·조회는 전부 이걸 본다.
create view if not exists notice_latest as
select n.* from notice n
 where n.bid_ntce_ord = (select max(m.bid_ntce_ord) from notice m
                          where m.bid_ntce_no = n.bid_ntce_no);
"""


def _check(path):
    """DB를 열기 전에 경로를 점검한다.

    절대 경로의 상위 디렉터리가 없으면 만들지 않고 실패시킨다.
    Railway 컨테이너는 root로 돌아서 /data를 그냥 만들 수 있는데,
    그러면 볼륨이 아닌 컨테이너 디스크에 쓰게 되고 재배포마다
    조용히 날아간다. 조용한 데이터 손실보다 시끄러운 실패가 낫다.
    """
    d = os.path.dirname(os.path.abspath(path))
    if os.path.isdir(d):
        return
    if os.path.isabs(path):
        raise SystemExit(
            f"\n[bidscope] DB 디렉터리가 없어요: {d}\n"
            f"  BIDNOTE_DB={path}\n"
            f"  Railway라면 볼륨이 {d} 에 마운트됐는지 확인하세요.\n"
            f"  (프로젝트 캔버스에서 Cmd+K → Volume → 서비스 선택 → "
            f"마운트 경로 {d})\n"
            f"  볼륨 없이 띄우려면 BIDNOTE_DB 변수를 지우세요 — 단 재배포마다 "
            f"데이터가 사라집니다.\n")
    os.makedirs(d, exist_ok=True)   # 상대 경로는 로컬 개발이므로 만들어 준다


def connect(path=None):
    path = path or DB_PATH
    _check(path)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("pragma journal_mode=WAL")
    con.execute("pragma foreign_keys=on")
    con.execute("pragma busy_timeout=5000")  # 스케줄러와 API가 같은 파일을 쓴다
    return con


# 기존 DB에 컬럼을 덧붙인다. create table if not exists는 컬럼을 추가하지 않는다.
MIGRATIONS = [
    ("notified", "closing_sent_at", "alter table notified add column closing_sent_at text"),
    ("condition", "want_prespec",
     "alter table condition add column want_prespec integer not null default 1"),
]


def init(path=None):
    con = connect(path)
    con.executescript(SCHEMA)
    for table, column, ddl in MIGRATIONS:
        cols = {r["name"] for r in con.execute(f"pragma table_info({table})")}
        if column not in cols:
            con.execute(ddl)
    con.commit()
    return con


if __name__ == "__main__":
    init()
    print(f"초기화 완료: {DB_PATH}")
