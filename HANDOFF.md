# 인수인계 — 다른 PC에서 이어서 하기

마지막 갱신: 2026-09-17 · 토스 콘솔에 **앱 등록 검토 요청까지 완료**

---

## 지금 어디까지 왔나

| 항목 | 상태 |
|---|---|
| 서버 | ✅ Railway 배포·가동 중 — https://bidscope-production.up.railway.app |
| DB | ✅ 볼륨 `/data/bidscope.db` · 재배포에도 유지됨(검증 완료) |
| 데이터 수집 | ✅ 09/13/18시 자동 (공고 + 사전규격) |
| 미니앱 | ✅ 빌드 통과 · `bidscope.ait` 생성됨 |
| 토스 콘솔 | ⏳ **앱 등록 검토 중** (1~2영업일) |
| 푸시 | ⏸ dry-run만. mTLS 인증서 + 템플릿 검수 후 켠다 |
| 구독(IAP) | ⏸ 안 함. 무료 출시 후 반응 보고 결정 |

---

## 새 PC에서 5분 안에 이어가기

### 1. 저장소

```bash
git clone https://github.com/seoyoungjae92/bidscope.git
cd bidscope
```

비공개 저장소다. GitHub 계정 `seoyoungjae92`로 로그인돼 있어야 한다.

### 2. 필요한 것

| 도구 | 확인 |
|---|---|
| Python 3.9+ | 서버는 **의존성 0** — 설치할 패키지 없음 |
| Node 20+ | 미니앱용 |
| Railway CLI | `npm i -g @railway/cli && railway login` |
| GitHub CLI(선택) | `gh auth login` |

### 3. 비밀값 — git에 없다. 직접 넣어야 한다

**공공데이터 인증키**
data.go.kr → 마이페이지 → 오픈API → 인증키 (일반 인증키 **Decoding**)
이미 승인된 API 2개: 입찰공고정보서비스(15129394), 사전규격정보서비스(15129437)

> 현재 Railway에 들어있는 키는 `railway variables`로 확인할 수 있다.
> 이 대화에 노출됐던 키라 재발급을 권한다 — 재발급하면 Railway 변수도 같이 바꿀 것.

**미니앱 `.env`** (gitignore됨)
```bash
cd miniapp && cp .env.example .env
```
기본값이 배포 서버를 가리키고 있어서 그대로 쓰면 된다.

### 4. 로컬 실행

```bash
# 서버 (선택 — 배포본을 쓰면 안 띄워도 된다)
cd server
export G2B_KEY='디코딩_인증키'
ALLOW_ORIGINS=http://localhost:5180 python3 api.py

# 미니앱
cd miniapp && npm install && npm run dev -- --port 5180
```

로컬 미니앱이 **배포 서버**를 보게 돼 있다. 로컬 서버를 쓰려면
`.env`의 `VITE_API_BASE`를 `http://localhost:8000`으로 바꾼다.

### 5. 테스트

```bash
cd server  && python3 test_match.py && python3 test_api.py
cd miniapp && npm test
```

### 6. Railway 연결

```bash
railway login
railway link -p brilliant-imagination -s bidscope
railway logs              # 배포 로그
railway variables         # 환경변수 확인
```

⚠️ Railway 계정에 프로젝트가 둘이다.
`brilliant-imagination` = **bidscope(이 프로젝트)**
`triumphant-dream` = 시소 (crawler, siso) — **건드리지 말 것**

---

## 다음에 할 일 (순서대로)

### ① 앱 등록 검토 결과 확인
1~2영업일. 반려되면 사유를 보고 수정 후 재요청.

### ② 푸시 템플릿 3종 검수 제출
콘솔 → 스마트발송 → **기능성 캠페인**. 2~3영업일.
제목 **7자**, 본문 **25자** 이내(공백 포함), 해요체.

```
[새 입찰공고]  {키워드} 공고 {n}건 올라왔어요
[공고 예고]    관심 분야 {n}건 공고 예정이에요
[마감 임박]    {공고명} {시}시 마감이에요
```

알림동의문도 함께 등록해야 한다 — `Notification.requestAgreement()`가 이걸 참조한다.

승인되면 받은 `templateSetCode`를 Railway 변수에:
```
TOSS_TEMPLATE_NEW=...
TOSS_TEMPLATE_CLOSING=...
TOSS_TEMPLATE_PRESPEC=...
```

### ③ mTLS 인증서 발급
콘솔에서 받아서 Railway 볼륨(`/data/`)에 올리고:
```
TOSS_CERT=/data/toss-cert.pem
TOSS_KEY=/data/toss-key.pem
PUSH_SEND=on          ← 이걸 켜야 실제 발송된다
```

켜기 전에 반드시 dry-run으로 문구를 눈으로 확인할 것:
```bash
railway run python3 push.py        # --send 없이
```

### ④ 번들 업로드 + QR 실기기 테스트
```bash
cd miniapp && npm run build        # → bidscope.ait
```
콘솔에 업로드 → QR로 실기기 테스트 **최소 1회** (안 하면 검토 요청 버튼이 안 열린다)

이때 확인할 것:
- 뒤로가기 버튼 동작 ← 전체 점검 항목
- 테스트용 광고 키가 남아있지 않은지 ← 전체 점검 항목
  (`miniapp/.env`의 `VITE_AD_GROUP_ID`가 `ait-ad-test-banner-id`로 돼 있다.
   콘솔에서 운영 광고그룹 ID를 받아 교체할 것)
- 실기기에서 푸시 수신

### ⑤ 출시 검토 요청 → 출시
최대 3영업일(카테고리에 따라 7일+). 승인되면 "출시하기"를 눌러야 실제로 나간다.

### ⑥ 사업자등록 — 급하지 않다
출시·광고에는 필요 없다. 광고는 **누적 수익 5,000원까지 유예**되고,
도달하면 5영업일 안에 등록하면 된다. IAP(구독)를 붙일 때 필수가 된다.
등록 시 **업종이 앱 카테고리와 일치**해야 한다(소프트웨어 개발/정보서비스업).
정산정보 심사가 별도로 2~3영업일.

### ⑦ 출시 후
- 콘솔에서 **'핵심 지표'** 설정 — 토스가 이 지표로 유사 유저에게 추천한다.
  무료 유입이 사실상 이것뿐이라 중요하다. "주 1회 이상 방문" 정도가 적절.
- 6주간 등록 사용자·리텐션만 본다. 구독은 그다음.

---

## 콘솔에 넣은 값 (재입력용)

```
워크스페이스        하루하나
제작자 이름         하루하나
앱 이름(국문)       입찰레이더
앱 이름(영문)       Bidscope
appName            bidscope          ← 변경 불가
앱 유형             비게임
카테고리            생활 > 비즈니스 > 사장님
부제               공공입찰 미리 알림
앱 로고            logo/logo-light.png
다크모드 로고       logo/logo-dark.png
스크린샷           shots/01-setup, 02-home, 03-notices
검색 키워드         입찰, 나라장터, 공고, 조달, 입찰공고, 공공입찰,
                  관급, 수의계약, 사전규격, 용역
고객문의           seoyoungjae92@gmail.com
```

상세 설명(432자)은 [console-copy.md](console-copy.md)에.

---

## 겪어본 함정들 (같은 데 또 빠지지 말 것)

| 증상 | 원인 | 해결 |
|---|---|---|
| Railway 502 | 도메인이 컨테이너 **443 포트**를 보고 있었다 | Networking에서 포트를 `8080`으로 |
| `unable to open database file` | 볼륨 없이 `BIDNOTE_DB=/data/...` | 볼륨 마운트. **볼륨은 서비스 설정이 아니라 프로젝트 캔버스 `⌘K`** |
| 마감된 공고가 계속 노출 | 컨테이너가 UTC. **tzdata가 없어 `TZ=Asia/Seoul`도 안 먹는다** | SQL에 `datetime('now','+9 hours')` 직접. `db.NOW` 상수 |
| 조건 등록했는데 빈 화면 | 배치가 최근 24시간만 매칭 | 등록 직후 `backfill_condition()` |
| 같은 공고가 두 번 | `select`에 `cond_id`가 있어 `distinct` 무효 | 공고 단위 `group by` |
| 화면이 통째로 죽음 | 토스 앱 밖에서 SDK가 **동기적으로** throw | `async` 래퍼로 감쌈 |
| 공고가 9시간 늦게 들어옴 | 조회 구간에 naive `datetime.now()` (컨테이너 UTC) | `g2b.now_kst()` |
| 로컬 개발 CORS 막힘 | 허용 오리진이 tossmini.com만 | `ALLOW_ORIGINS` 환경변수 (**운영에선 비운다**) |

---

## 설계 결정 요약

전체 근거는 [round2-review.md](round2-review.md), [VERIFIED.md](VERIFIED.md)에.

- **사전규격이 입찰공고보다 중앙값 7일 먼저 뜬다**(실측, 대조 26건). 이게 제품의 이유고 화면·이름·부제가 전부 이걸 가리킨다.
- **MVP는 용역만.** 분류체계가 채워져 오는 유일한 업무유형. 물품은 표본 300건 전부 분류가 비어 있다.
- **사전규격엔 분류가 없다.** 키워드가 유일하게 정확한 매칭 축이라 조건 등록 화면에서 이유와 함께 권한다. 분류명 토큰 매칭은 재봤는데 못 쓴다("사업"이 696건 중 186건을 잡는다).
- **조건 3개 제한은 과금 축이 아니라 어뷰징 방어선.** 실제 과금 축은 반응 보고 정한다 — 참가자격 판정이나 낙찰 정보 쪽이 유력.
- **광고는 보조.** 배너 단일 수익의 천장이 월 10~40만원이다. 구독이 붙어야 의미가 생긴다(활성 126명 = 월 50만원).

---

## 문서 지도

| 파일 | 내용 |
|---|---|
| [README.md](README.md) | 프로젝트 개요 · 빠른 시작 |
| [server/README.md](server/README.md) | 서버 상세 · 배포 · **실측 근거 설계 메모** |
| [miniapp/README.md](miniapp/README.md) | 미니앱 · 화면 · 심사 체크리스트 |
| [VERIFIED.md](VERIFIED.md) | API 실측 결과와 거기서 나온 설계 결정 |
| [ROADMAP.md](ROADMAP.md) | 출시까지 8단계 |
| [round2-review.md](round2-review.md) | 아이템 선정 근거 · 수익 구조 역산 · 정책 제약 |
| [console-copy.md](console-copy.md) | 콘솔 입력값 전문 (설명·푸시 문구) |
| [apt-alert-review.md](apt-alert-review.md) | 1차 검토(부동산) — 보류된 아이디어 |
