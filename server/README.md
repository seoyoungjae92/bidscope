# bidnote 서버

나라장터 입찰공고 + 사전규격 알림. **의존성 0** — Python 3.9+ 표준 라이브러리만 쓴다.

```
db.py          스키마 + 커넥션 (SQLite)
g2b.py         나라장터 공고·사전규격 수집(증분) + 조건 매칭
api.py         REST API (stdlib http.server)
push.py        토스 기능성 푸시
test_match.py  매칭 로직 점검
test_api.py    API 통합 점검 (실제 HTTP)
```

## 로컬

```bash
export G2B_KEY='디코딩_인증키'
python3 db.py          # 스키마 생성
python3 g2b.py run     # 수집 + 매칭
python3 push.py        # dry-run: 신규 + 마감 임박 둘 다
python3 push.py --kind closing --send   # 마감 임박만 실제 발송
python3 api.py         # :8000

python3 test_match.py && python3 test_api.py
```

## 엔드포인트

미니앱은 `X-Toss-Key` 헤더에 토스 익명키(`User.getAnonymousKey()`)를 넣는다.
로그인·사업자등록 없이 동작한다.

| | | |
|---|---|---|
| `GET` | `/health` | 공고 수, 수집 커서 |
| `GET` | `/classifications?work_type=용역` | 조건 등록용 분류 트리 (실제 공고에 있는 것만) |
| `GET` | `/conditions` | 내 조건 목록 |
| `POST` | `/conditions` | 조건 추가. 분류나 키워드 필수, 무료 3개 |
| `DELETE` | `/conditions/{id}` | 조건 삭제 |
| `GET` | `/notices?cond_id=&limit=` | 매칭 공고. 마감 임박순, 마감분 제외 |
| `GET` | `/prespecs?limit=` | **공고 예고(사전규격).** 의견 마감 임박순 |
| `POST` | `/push-consent` | `requestAgreement()` 결과 저장 |

## 배포 (Lightsail 2GB · 월 $12)

```bash
sudo apt update && sudo apt install -y python3 caddy
sudo mkdir -p /opt/bidnote && sudo chown $USER /opt/bidnote
# 소스 복사 후
cd /opt/bidnote && python3 db.py
```

로컬에서 미니앱과 붙일 때는 CORS 오리진을 열어야 한다:
```bash
ALLOW_ORIGINS=http://localhost:5180 PORT=8000 python3 api.py
```
**운영에서는 비워둔다** — 기본값으로 localhost를 열어두면 배포 후에도 열린 채 남는다.

**환경변수** `/etc/bidnote.env` (권한 `640`, root:$USER)
```
G2B_KEY=디코딩_인증키
BIDNOTE_DB=/opt/bidnote/bidnote.db
APP_NAME=bidscope
TOSS_TEMPLATE_NEW=BIDNOTE_NEW
TOSS_TEMPLATE_CLOSING=BIDNOTE_CLOSING
TOSS_TEMPLATE_PRESPEC=BIDNOTE_PRESPEC
TOSS_CERT=/opt/bidnote/toss-cert.pem
TOSS_KEY=/opt/bidnote/toss-key.pem
```

**API** `/etc/systemd/system/bidnote-api.service`
```ini
[Unit]
After=network.target
[Service]
WorkingDirectory=/opt/bidnote
EnvironmentFile=/etc/bidnote.env
ExecStart=/usr/bin/python3 /opt/bidnote/api.py
Restart=always
[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now bidnote-api
```

**배치** `crontab -e`
```cron
# 수집 + 매칭: 국토부가 아니라 조달청이라 일중에도 올라온다. 3회면 충분
0 9,13,18 * * *  cd /opt/bidnote && . /etc/bidnote.env && python3 g2b.py run >> log 2>&1
# 신규 공고: 하루 1회 오전에 다이제스트로 몰아서
10 9 * * *       cd /opt/bidnote && . /etc/bidnote.env && python3 push.py --kind new --send >> log 2>&1
# 마감 임박: 오후에 한 번 더. 6~48시간 남은 것만, 공고당 1회
0 15 * * *       cd /opt/bidnote && . /etc/bidnote.env && python3 push.py --kind closing --send >> log 2>&1
# 백업
30 3 * * *       sqlite3 /opt/bidnote/bidnote.db ".backup /opt/bidnote/backup.db"
```

**TLS** `/etc/caddy/Caddyfile` — 토스 미니앱은 https만 허용한다
```
api.example.com {
    reverse_proxy localhost:8000
}
```

## 설계 메모 (실측 근거)

- **증분 조회로 끝난다.** `inqryBgnDt`/`inqryEndDt`가 정확히 동작해서(오전 184 + 오후 381 = 종일 565) 스냅샷 diff가 없다. 커서만 전진시킨다.
- **자연키에 차수(`bidNtceOrd`)를 넣지 않는다.** 변경공고가 6차까지 가서, 차수를 키에 넣으면 한 공고를 8번 알린다. `notice_latest` 뷰가 최신 차수만 본다.
- **조건에 분류나 키워드가 필수다.** 계약방법만 걸면 일 180건이 잡힌다. 분류를 걸면 일 13~16건으로 떨어진다.
- **마감 지난 공고는 매칭·조회·푸시 전부에서 제외.** 마감일시가 없는 건(14%)은 통과시킨다.
- **MVP는 용역만.** 분류체계가 채워져 오는 유일한 업무유형이다. 물품은 표본 300건 전부 분류가 비어 있어 키워드로만 가야 한다. `BIDNOTE_TYPES=용역,물품`으로 늘릴 수는 있다.
- **사전규격이 공고보다 중앙값 7일 먼저 뜬다**(실측, 대조 26건). 92%가 3일 이상 앞선다. 제품의 차별화가 여기 있다.
- **사전규격에는 대/중분류가 없다.** 쓸 수 있는 축은 사업명·SW사업여부(`swBizObjYn`)·예산뿐이라, 조건을 근사해 매칭한다 — 키워드가 있으면 사업명, 없으면 ICT 계열은 SW사업으로.
- **의견 마감이 지난 사전규격은 안 알린다.** 규격에 개입할 수 없으면 알릴 이유가 사라진다.
- **마감 임박은 6~48시간 창에서만.** 더 임박하면 준비할 시간이 없고, 더 멀면 잊는다. 이미 신규 알림을 받은 공고만 대상이라 맥락 없는 알림이 안 나간다. 공고당 1회.
- **푸시 일일 상한 20건.** 넘는 분량은 본문에 안 싣되 큐에서는 함께 소진한다(안 그러면 영영 안 끝난다).

## 아직 없는 것

- **푸시 실발송** — 콘솔에서 mTLS 인증서 발급 + 템플릿 검수 통과 후에 `--send`가 동작한다. 그 전까진 dry-run만.
- **구독(IAP)** — 무료 한도가 `api.FREE_CONDITIONS`에 하드코딩. 붙일 때 `app_user.plan` 컬럼으로 뺀다.
- 모니터링(Healthchecks.io 핑), 로그 로테이션.
