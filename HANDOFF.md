# 인수인계 — 다른 PC에서 이어서 하기

마지막 갱신: 2026-09-19 · 새 노트북으로 이전. 1차 심사 반려 → 수정 번들 재검토 중

---

## 지금 어디까지 왔나

| 항목 | 상태 |
|---|---|
| 서버 | ✅ Railway 배포·가동 중 — https://bidscope-production.up.railway.app |
| DB | ✅ 볼륨 `/data/bidscope.db` · 재배포에도 유지됨(검증 완료) |
| 데이터 수집 | ✅ 09/13/18시 자동 (공고 + 사전규격) |
| 미니앱 | ✅ 빌드 통과 · `bidscope.ait` 생성됨 |
| 토스 콘솔 | ✅ 앱 등록 · 푸시 템플릿 3종 · 알림동의문 3종 등록 완료 |
| mTLS 인증서 | ✅ 2026-09-19 재발급 `bidscope-prod-2026-09` → Railway 반영·재배포 완료. 이전 `bidscope`는 첫 푸시 확인 후 폐기 |
| 푸시 | ✅ 2026-09-19 `PUSH_SEND=on`. 매일 09:10 새 공고·예고, 15:00 마감 임박 |
| 광고 | ⏸ 사업자등록 필요 — 광고 없이 출시. `VITE_AD_GROUP_ID` 비워둠 |
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

### ⓪ 새 PC에서 **로그인부터** 확인 — 이게 막히면 나머지가 다 막힌다

| 계정 | 없으면 |
|---|---|
| GitHub `seoyoungjae92` | 소스가 **여기에만** 있다 (비공개 저장소) |
| Railway | mTLS 개인키·공공데이터 인증키가 **여기에만** 있다 |
| 토스 콘솔 | 앱·푸시 템플릿 |
| data.go.kr | 인증키 (재발급은 가능) |

⚠️ 이 노트북을 초기화하면 **인증서 개인키의 사본은 Railway 환경변수뿐**이다.
백업본은 비밀번호 관리자의 `TOSS_KEY_B64` / `TOSS_CERT_B64`에 있다.

**✅ mTLS 인증서 재발급 — 2026-09-19 완료.** 새 인증서 `bidscope-prod-2026-09`를
Railway와 비밀번호 관리자에 넣었다. **남은 것: 이전 `bidscope` 인증서 폐기.**
연결만 확인하는 기능이 없어서, 출시 후 실기기로 첫 푸시를 받아본 뒤에 콘솔에서 폐기한다.

다음에 또 교체할 때:

```bash
railway variables --set TOSS_CERT_B64="$(base64 -i 새인증서.pem)" \
                  --set TOSS_KEY_B64="$(base64 -i 새키.pem)"
```

비밀번호 관리자 백업도 같이 갱신하고, 내려받은 인증서 파일은 지운다.

### 나중에 일괄 교체할 것 (2026-09-19 보류)

대화에 노출됐던 값들. 한 번에 몰아서 처리하기로 했다.

- [ ] **GitHub 토큰** (`ghp_…`) — 폐기 후 `gh auth logout && gh auth login`(브라우저 방식)
- [ ] **data.go.kr 인증키** — 재발급 즉시 이전 키가 죽고 새 키는 활성화에 ~1시간.
      수집(09/13/18시) 직후에 할 것. 넣는 법: Decoding 값 복사 후
      `railway variables --set G2B_KEY="$(pbpaste)" && pbcopy < /dev/null`
- [ ] **이전 mTLS 인증서 `bidscope` 폐기** — 새 인증서로 첫 푸시 수신 확인 후

### ① 앱 등록 검토 결과 확인
1~2영업일. 반려되면 사유를 보고 수정 후 재요청.

### ② 푸시 — 다 됐다. 켜기만 남았다

콘솔 발송 코드가 그대로 Railway 변수에 들어가 있다. 앱의 알림 동의
(`miniapp/src/push.js`)도 같은 코드를 쓴다 — **콘솔에서 코드를 바꾸면 양쪽 다** 고쳐야 한다.

```
TOSS_TEMPLATE_NEW=bidscope-new
TOSS_TEMPLATE_PRESPEC=bidscope-prespec
TOSS_TEMPLATE_CLOSING=bidscope-closing
TOSS_CERT_B64=...        ← 인증서(base64). 로컬 파일 보관 불필요
TOSS_KEY_B64=...         ← 개인키(base64)
```

인증서는 `CN=bidscope`, **2027-10-13 만료**. Railway에만 있고 git에는 없다.
새 PC에서 파일로 꺼내려면:

```bash
railway variables --kv | grep '^TOSS_CERT_B64=' | cut -d= -f2- | base64 -d > cert.pem
railway variables --kv | grep '^TOSS_KEY_B64='  | cut -d= -f2- | base64 -d > key.pem
```

실기기에서 알림 수신을 확인한 뒤 마지막으로:

```bash
railway variables --set PUSH_SEND=on
```

켜기 전 문구 확인(발송 안 함):
```bash
railway run python3 server/push.py
```

### ③ 번들 업로드 + QR 실기기 테스트
```bash
cd miniapp && npm run build        # → bidscope.ait
```
콘솔에 업로드 → QR로 실기기 테스트 **최소 1회** (안 하면 검토 요청 버튼이 안 열린다)

이때 확인할 것:
- 뒤로가기 동작
- 실기기에서 푸시 수신 → 확인되면 `PUSH_SEND=on`

> **광고 없이 출시한다 (2026-09-19 결정).** 인앱 광고는 사업자등록이 있어야
> 콘솔에서 약관 등록·광고그룹 발급이 된다. `VITE_AD_GROUP_ID`를 비워두면
> `Banner.jsx`가 배너를 아예 그리지 않으니 코드 수정은 필요 없다.
> 테스트 키(`ait-ad-test-banner-id`)가 번들에 남으면 **전체 점검에서 반려**되니
> 빌드 후 `grep -r ait-ad-test dist/`로 한 번 확인할 것.

### ④ 출시 검토 요청 → 출시
최대 3영업일(카테고리에 따라 7일+). 승인되면 "출시하기"를 눌러야 실제로 나간다.

### ⑤ 사업자등록 — 광고를 붙일 때 한다
출시에는 필요 없다. **인앱 광고·IAP·토스 로그인·토스페이·프로모션은 필수**다
([공지 2025-12-09](https://techchat-apps-in-toss.toss.im/t/topic/1666)).
~~광고는 누적 수익 5,000원까지 유예~~ — 틀린 정보였다. 콘솔이 광고 약관 등록에서
사업자번호를 요구한다. 등록 후 광고그룹 ID를 `.env`에 넣고 다시 빌드하면 된다.
등록 시 **업종이 앱 카테고리와 일치**해야 한다(소프트웨어 개발/정보서비스업).
정산정보 심사가 별도로 2~3영업일.

### ⑥ 출시 후
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
| 알림 동의 시트가 안 뜸 | `templateCode`가 콘솔 **발송 코드**와 달랐다 | `push.js`의 `KINDS` = 콘솔 코드 |
| 공고가 반나절 안 들어옴 | 재배포로 컨테이너가 재시작해 09:00 수집 슬롯을 통째로 건너뜀 | 부팅 시 커서가 5시간 넘게 묵었으면 즉시 수집 (`scheduler._catch_up`) |
| 공고가 9시간 늦게 들어옴 | 조회 구간에 naive `datetime.now()` (컨테이너 UTC) | `g2b.now_kst()` |
| 심사 반려 「최초 접속 20초 초과」 + 「메인 스킴 접속 불가」 | 익명키·fetch에 타임아웃이 없어 심사 환경에서 첫 화면이 "불러오는 중…"에 무한정 멈춤 | `api.js` 익명키 3초·요청 5초 상한, 실패 시 "다시 시도" 버튼 (2026-09-19) |
| 익명키 실패한 사용자끼리 조건이 섞임 | 실패 시 모두 같은 `'dev-local-key'`로 떨어졌다 | 운영에선 기기별 임의 키(`local-…`, localStorage). 푸시는 이 키를 건너뛴다 |
| 공고를 눌러도 아무 반응 없음 | `Device.openURL({ url })` — SDK는 **문자열**을 받는다(`openURL(url: string)`) | `App.jsx`의 `openLink(url)` 하나로 모음 (2026-09-19) |
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
