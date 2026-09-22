import { useCallback, useEffect, useState } from 'react';
import { Device } from '@apps-in-toss/web-framework';
import * as api from './api';
import Banner from './Banner';
import { KINDS, askAgreement } from './push';
import { clsfcName, conditionSummary, dday, money } from './format';
import './App.css';

const AMOUNTS = [
  { label: '전체', min: 0, max: 0 },
  { label: '5천만 이하', min: 0, max: 50_000_000 },
  { label: '5천만~3억', min: 50_000_000, max: 300_000_000 },
  { label: '3억 이상', min: 300_000_000, max: 0 },
];
const METHODS = ['전체', '수의계약', '제한경쟁', '일반경쟁'];

/** 나라장터 원문을 기기 브라우저로 연다.
 * Device.openURL은 문자열을 받는다 — 객체({ url })를 넘기면 아무 반응 없이 실패했다.
 * 토스 앱 밖에서는 SDK가 동기적으로 던지므로 async로 감싸 window.open으로 넘긴다. */
function openLink(url) {
  if (!url || !/^https?:\/\//.test(url)) return;
  (async () => {
    try {
      await Device.openURL(url);
    } catch {
      window.open(url, '_blank', 'noopener');
    }
  })();
}

export default function App() {
  const [view, setView] = useState('loading'); // loading | list | new
  const [conditions, setConditions] = useState([]);
  const [notices, setNotices] = useState([]);
  const [prespecs, setPrespecs] = useState([]);
  const [consent, setConsent] = useState({});
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const cs = await api.getConditions();
      setConditions(cs);
      if (cs.length === 0) return setView('new');
      const [ns, ps, agreed] = await Promise.all([
        api.getNotices(), api.getPrespecs(), api.getPushConsent(),
      ]);
      setNotices(ns);
      setPrespecs(ps);
      setConsent(agreed);
      setView('list');
    } catch (e) {
      setError(e.message);
      setView('list');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (view === 'loading') return <div className="center">불러오는 중…</div>;
  if (view === 'new') {
    return <NewCondition
      first={conditions.length === 0}
      onDone={load}
      onCancel={conditions.length ? () => setView('list') : null}
    />;
  }
  return (
    <Main
      conditions={conditions}
      notices={notices}
      prespecs={prespecs}
      consent={consent}
      onConsent={(c) => setConsent((p) => ({ ...p, ...c }))}
      error={error}
      onAdd={() => setView('new')}
      onReload={load}
    />
  );
}

function Main({ conditions, notices, prespecs, consent, onConsent, error, onAdd, onReload }) {
  // 어떤 종류를 처리 중인지. 묶음 동의 중에는 true.
  const [busy, setBusy] = useState(false);

  /** 동의를 순서대로 묻는다. 동의문이 종류마다 따로라 시트도 따로 뜬다. */
  async function ask(kinds) {
    setBusy(true);
    const got = {};
    for (const kind of kinds) {
      const { code } = KINDS.find((k) => k.kind === kind);
      const ok = await askAgreement(code);
      try { await api.setPushConsent(kind, ok); } catch { /* 저장 실패는 다음에 다시 묻는다 */ }
      got[kind] = ok;
    }
    onConsent(got);
    setBusy(false);
  }

  /** 켜기는 토스 동의 시트를 다시 띄우고(이미 동의했으면 alreadyAgreed로 바로 켜진다),
   *  끄기는 서버에만 알린다 — SDK에 동의 해제 함수가 없다. */
  async function toggle(kind) {
    const on = !!consent[kind];
    setBusy(kind);
    try {
      if (on) {
        await api.setPushConsent(kind, false);
        onConsent({ [kind]: false });
      } else {
        const { code } = KINDS.find((k) => k.kind === kind);
        const ok = await askAgreement(code);
        try { await api.setPushConsent(kind, ok); } catch { /* 다음에 다시 묻는다 */ }
        onConsent({ [kind]: ok });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="top">
        <h1>입찰레이더</h1>
        <p className="sub">공고 뜨기 전에 미리 알려드려요</p>
      </header>

      {error && (
        <p className="error">
          {error} <button className="link" onClick={onReload}>다시 시도</button>
        </p>
      )}

      <section>
        <div className="row-head">
          <h2>내 조건 <span className="count">{conditions.length}</span>개</h2>
          <button className="link" onClick={onAdd}>추가</button>
        </div>
        {conditions.map((c) => (
          <div key={c.id} className="cond">
            <div>
              <strong>{c.label || c.mid_clsfc || c.lrg_clsfc || c.keyword}</strong>
              <span className="dim">{conditionSummary(c)}</span>
            </div>
            <button
              className="remove"
              aria-label={`${c.label || '조건'} 삭제`}
              onClick={async () => { await api.delCondition(c.id); onReload(); }}
            >삭제</button>
          </div>
        ))}
      </section>

      {!KINDS.some((k) => consent[k.kind]) && (
        <button className="cta" disabled={!!busy}
                onClick={() => ask(['prespec', 'new'])}>
          {busy ? '동의 확인 중…' : '공고 올라오면 알림 받기'}
        </button>
      )}

      {prespecs.length > 0 && (
        <section className="lead">
          <h2>공고 예고 <span className="count">{prespecs.length}</span>건</h2>
          <p className="dim pad">
            사전규격 단계예요. 보통 일주일쯤 뒤에 공고가 나요.
          </p>
          {prespecs.map((p) => (
            <button
              key={p.spec_no}
              className="notice"
              onClick={() => openLink(p.doc_url)}
            >
              <div className="notice-top">
                <span className="badge pre">
                  {p.opnin_clse_dt ? `의견 ${dday(p.opnin_clse_dt).text}` : '공고 예정'}
                </span>
                <span className="amt">{money(p.budget)}</span>
              </div>
              <div className="title">{p.spec_nm}</div>
              <div className="dim">{p.order_instt}</div>
            </button>
          ))}
        </section>
      )}

      <section>
        <h2>새 공고 <span className="count">{notices.length}</span>건</h2>
        {notices.length === 0 && (
          <p className="dim pad">
            새 공고가 올라오면 바로 알려드릴게요.
          </p>
        )}
        {notices.map((n) => {
          const d = dday(n.bid_clse_dt);
          return (
            <button
              key={n.bid_ntce_no}
              className="notice"
              onClick={() => openLink(n.detail_url)}
            >
              <div className="notice-top">
                <span className={d.urgent ? 'badge urgent' : 'badge'}>{d.text}</span>
                <span className="amt">{money(n.presmpt_prce)}</span>
              </div>
              <div className="title">{n.bid_ntce_nm}</div>
              <div className="dim">
                {n.ntce_instt_nm}
                {n.cntrct_mthd ? ` · ${n.cntrct_mthd}` : ''}
              </div>
            </button>
          );
        })}
      </section>

      {KINDS.some((k) => consent[k.kind]) && (
        <section>
          <h2>알림</h2>
          {KINDS.map((k) => {
            const on = !!consent[k.kind];
            return (
              <button
                key={k.kind}
                className={on ? 'switch on' : 'switch'}
                disabled={busy === k.kind}
                aria-pressed={on}
                onClick={() => toggle(k.kind)}
              >
                <span>{k.label}</span>
                <span className="state">
                  {busy === k.kind ? '…' : on ? '받는 중' : '꺼짐'}
                </span>
              </button>
            );
          })}
          <p className="dim pad">눌러서 끄고 켤 수 있어요. 알림은 하루 한 번 모아서 보내요.</p>
        </section>
      )}

      {notices.length > 0 && <Banner />}

      <footer className="dim foot">
        조달청 나라장터에 올라오는 공고를 알려드려요.
        한국전력·LH처럼 자체 조달시스템을 쓰는 곳은 따로 확인해 주세요.
      </footer>
    </div>
  );
}

function NewCondition({ first, onDone, onCancel }) {
  const [tree, setTree] = useState(null);
  const [lrg, setLrg] = useState(null);
  const [mid, setMid] = useState(null);
  const [amt, setAmt] = useState(AMOUNTS[0]);
  const [method, setMethod] = useState('전체');
  const [keyword, setKeyword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const loadTree = useCallback(() => {
    setError(null);
    api.getClassifications().then(setTree).catch((e) => setError(e.message));
  }, []);
  useEffect(() => { loadTree(); }, [loadTree]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.addCondition({
        // 원본 분류명엔 '*' 구분자가 섞여 있다. 저장 전에 정리한다
        label: lrg ? clsfcName(mid || lrg).slice(0, 12) : null,
        lrg_clsfc: lrg,
        mid_clsfc: mid,
        amt_min: amt.min,
        amt_max: amt.max,
        cntrct_mthd: method === '전체' ? null : method,
        keyword: keyword.trim() || null,
      });
      onDone();
    } catch (e) {
      setError(e.message);
      setSaving(false);
    }
  }

  if (!tree) {
    return (
      <div className="center">
        {error ? <>{error} <button className="link" onClick={loadTree}>다시 시도</button></> : '불러오는 중…'}
      </div>
    );
  }

  const children = tree.find((t) => t.name === lrg)?.children ?? [];

  return (
    <div className="page has-bottom">
      <header className="top">
        <h1>{first ? '어떤 공고를 받을까요?' : '조건 추가'}</h1>
        <p className="sub">분야를 고르면 맞는 공고만 알려드려요</p>
      </header>

      <section>
        <h2>분야</h2>
        <div className="chips">
          {tree.map((t) => (
            <button
              key={t.name}
              className={lrg === t.name ? 'chip on' : 'chip'}
              onClick={() => { setLrg(t.name); setMid(null); }}
            >
              {clsfcName(t.name)}
            </button>
          ))}
        </div>
      </section>

      {lrg && children.length > 0 && (
        <section>
          <h2>세부 분야 <span className="dim">(선택)</span></h2>
          <div className="chips">
            {children.map((c) => (
              <button
                key={c.name}
                className={mid === c.name ? 'chip on' : 'chip'}
                onClick={() => setMid(mid === c.name ? null : c.name)}
              >
                {clsfcName(c.name)} <span className="dim">{c.count}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2>사업 규모</h2>
        <div className="chips">
          {AMOUNTS.map((a) => (
            <button
              key={a.label}
              className={amt.label === a.label ? 'chip on' : 'chip'}
              onClick={() => setAmt(a)}
            >{a.label}</button>
          ))}
        </div>
      </section>

      <section>
        <h2>관심 키워드 <span className="dim">(선택)</span></h2>
        <p className="dim pad">
          공고 예고는 분야 정보가 없어서 키워드로 찾아요.
          예고까지 받으려면 넣어주세요.
        </p>
        <input
          className="field"
          type="text"
          inputMode="text"
          maxLength={40}
          placeholder="예) 홈페이지, 유지관리, 데이터"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
      </section>

      <section>
        <h2>계약 방법</h2>
        <div className="chips">
          {METHODS.map((m) => (
            <button
              key={m}
              className={method === m ? 'chip on' : 'chip'}
              onClick={() => setMethod(m)}
            >{m}</button>
          ))}
        </div>
      </section>

      {error && <p className="error">{error}</p>}

      <div className="bottom">
        {onCancel && <button className="ghost" onClick={onCancel}>취소</button>}
        <button className="cta" disabled={!lrg || saving} onClick={save}>
          {saving ? '저장 중…' : '이 조건으로 받기'}
        </button>
      </div>
    </div>
  );
}
