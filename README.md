# 입찰알리미

공공기관 입찰공고를 내 조건에 맞는 것만 골라 토스 푸시로 알려주는 앱인토스 미니앱.

조달청 나라장터 공고를 하루 몇 번 증분 수집해서, 사용자가 등록한
분야·금액·계약방법 조건에 매칭되는 것만 다이제스트 푸시로 보낸다.

```
server/     수집·매칭·푸시·API   (Python 3.9+, 의존성 0)
miniapp/    토스 미니앱          (Vite + React 19 + SDK 3.4.1)
```

## 빠른 시작

```bash
# 서버
cd server
export G2B_KEY='data.go.kr 디코딩 인증키'
python3 db.py && python3 g2b.py run && python3 api.py

# 미니앱 (다른 터미널)
cd miniapp && cp .env.example .env && npm install && npm run dev
```

각 디렉터리의 README에 상세가 있다.

## 문서

| | |
|---|---|
| [VERIFIED.md](VERIFIED.md) | **API 실측 결과.** 물량·필드·리드타임과 거기서 나온 설계 결정 |
| [ROADMAP.md](ROADMAP.md) | 출시까지 8단계 — 이름 규칙, 콘솔 등록, 심사 체크리스트 |
| [PREP.md](PREP.md) | 계정·키·리드타임 체크리스트 |
| [round2-review.md](round2-review.md) | 아이템 선정 근거. 수익 구조 역산, 정책 제약, 탈락 후보 |
| [apt-alert-review.md](apt-alert-review.md) | 1차 검토(아파트 실거래가). 부동산 카테고리 제한으로 보류 |
| [apt-alert-appendix.md](apt-alert-appendix.md) | 1차 검토 부록 — 시장·API·UX·아키텍처·리스크 전문 |

## 로고

```bash
cd logo && python3 ../logo.py     # 600×600 PNG 3종 + 72px 미리보기
```

콘솔 규격: 정사각형 · **둥근 모서리 불가**(토스가 자체 마스킹) · 배경색 필수.
`logo-card-blue.png`가 기본안이다.

## 검증 스크립트

```bash
python3 g2b_check.py       # 입찰공고 API — 물량·필드·증분조회 점검
python3 prespec_check.py   # 사전규격 API — 리드타임 측정 (별도 활용신청 필요)
```

## 테스트

```bash
cd server  && python3 test_match.py && python3 test_api.py
cd miniapp && npm test
```
