# 입찰레이더

공공기관 입찰공고를 **뜨기 전에** 알려주는 앱인토스 미니앱.

사전규격(공고 예고)이 입찰공고보다 **중앙값 7일** 먼저 뜬다는 실측에서 출발했다.
2주짜리 마감에서 일주일을 더 버는 게 이 제품의 핵심이다.

조달청 나라장터의 입찰공고와 사전규격을 하루 몇 번 증분 수집해서,
사용자가 등록한 분야·금액·계약방법 조건에 맞는 것만 다이제스트 푸시로 보낸다.

푸시는 3종: **공고 예고**(사전규격) → **새 입찰공고** → **마감 임박**.

```
server/     수집·매칭·푸시·API + 스케줄러  (Python 3.9+, 의존성 0)
miniapp/    토스 미니앱                  (Vite + React 19 + SDK 3.4.1)
```

**배포처**: 서버만 Railway에 올린다(볼륨 1개 + 서비스 1개).
미니앱은 `.ait` 번들을 토스 콘솔에 올리면 토스가 호스팅하므로
Vercel 같은 프론트 배포처가 필요 없다. 자세한 건 [server/README](server/README.md).

> **다른 PC에서 이어서 작업한다면 [HANDOFF.md](HANDOFF.md)부터 읽는다.**
> 현재 진행 상황, 비밀값 위치, 다음 할 일, 이미 겪은 함정이 정리돼 있다.

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
