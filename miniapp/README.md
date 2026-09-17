# 입찰레이더 미니앱

토스 앱인토스 WebView 미니앱. Vite + React 19 + `@apps-in-toss/web-framework` 3.4.1.

```
src/
  App.jsx        화면 2개 (조건 등록 / 공고 예고·공고 목록)
  api.js         서버 호출. 익명키를 X-Toss-Key 헤더로
  format.js      금액·D-day·조건 요약 포맷
  format.test.js 포맷 로직 점검 (node만 있으면 돌아감)
apps-in-toss.config.ts   appName·브랜드 컬러·번들 경로
```

## 실행

```bash
npm install
npm test                 # 포맷 로직 점검
npm run dev              # 브라우저에서 개발 (AIT Devtools)
npm run build            # vite build && ait build → bidscope.ait
```

서버 주소는 `.env`로:
```
VITE_API_BASE=https://api.example.com
```
없으면 `http://localhost:8000`을 본다.

## 화면

**조건 등록** — 조건이 하나도 없으면 첫 화면이 여기다.
분야(대분류) → 세부 분야(중분류) → 사업 규모 → 계약 방법을 칩으로 고른다.
분류 목록은 서버가 **실제 공고에 존재하는 것만** 내려주므로 빈 분류를 고를 일이 없다.

**공고 예고** — 사전규격. 공고보다 중앙값 7일 먼저 뜬다. 목록 맨 위에 둔다 — 차별화가 여기 있다.

**공고 목록** — 내 조건 + 매칭된 공고. 마감 임박순.
공고를 누르면 `Device.openURL()`로 나라장터 원문이 열린다.

## 설계 메모

- **분류 2단계 선택이 핵심 UX다.** 키워드 입력은 노이즈가 많다 — 실측으로 계약방법만 걸면 일 180건, 분류를 걸면 일 13건이다.
- **알림 동의는 나중에 묻는다.** 토스 심사 기준상 진입 직후 요구가 금지돼 있고, 조건을 등록해 가치를 본 뒤에 물어야 수락률이 높다.
- **커버리지를 화면 하단에 명시한다.** 한전·LH 공고를 기대하고 들어온 사람이 바로 알게 해야 나쁜 리뷰가 안 달린다.
- **브라우저에서도 뜬다.** `User.getAnonymousKey()`가 실패하면 개발용 고정 키로 떨어져서 AIT Devtools 없이도 화면을 볼 수 있다.
- 분류명에 앞뒤 공백이 섞여 와서(`" 디자인"`, `"교육서비스 "`) 렌더 시 `.trim()` 한다.

## 심사 체크리스트 대응

- [x] 라이트 모드 (`App.css`에 다크 모드 미디어쿼리 없음)
- [x] 확대·축소 비활성 (`touch-action: manipulation`)
- [x] CSR only (Vite SPA)
- [x] 자사 로그인 없음 — 익명키만
- [x] 진입 직후 바텀시트·알림 동의 요구 없음
- [ ] 테스트용 광고 키 — 아직 광고 미연동
- [ ] 뒤로가기 동작 — 실기기 확인 필요

## 아직 없는 것

- **광고** — `TossAds.attachBanner()`. 공고 목록 하단에 배너 1개가 자리다.
- **구독** — `IAP.createSubscriptionPurchaseOrder()`. 무료 3개 한도는 서버 `api.FREE_CONDITIONS`에 있다.
- **조건 수정** — 지금은 삭제 후 재등록.
- **공고 상세 화면** — 지금은 나라장터 원문으로 바로 보낸다. 앱 안에 두면 세션이 길어져 배너 노출이 늘지만, 원문이 더 정확하다.
