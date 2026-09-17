import { useCallback, useEffect, useState } from 'react';
import { Device, Notification } from '@apps-in-toss/web-framework';
import * as api from './api';
import Banner from './Banner';
import { conditionSummary, dday, money } from './format';
import './App.css';

const AMOUNTS = [
  { label: '전체', min: 0, max: 0 },
  { label: '5천만 이하', min: 0, max: 50_000_000 },
  { label: '5천만~3억', min: 50_000_000, max: 300_000_000 },
  { label: '3억 이상', min: 300_000_000, max: 0 },
];
const METHODS = ['전체', '수의계약', '제한경쟁', '일반경쟁'];

export default function App() {
  const [view, setView] = useState('loading'); // loading | list | new
  const [conditions, setConditions] = useState([]);
  const [notices, setNotices] = useState([]);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const cs = await api.getConditions();
      setConditions(cs);
      if (cs.length === 0) return setView('new');
      setNotices(await api.getNotices());
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
      error={error}
      onAdd={() => setView('new')}
      onReload={load}
    />
  );
}

function Main({ conditions, notices, error, onAdd, onReload }) {
  const [consent, setConsent] = useState(null);

  async function askPush() {
    try {
      const r = await Notification.requestAgreement({ templateCode: 'BIDNOTE_NEW' });
      const ok = r === 'newAgreement' || r === 'alreadyAgreed';
      await api.setPushConsent(ok);
      setConsent(ok ? 'on' : 'off');
    } catch {
      setConsent('off');
    }
  }

  return (
    <div className="page">
      <header className="top">
        <h1>입찰알리미</h1>
        <p className="sub">공공기관 입찰공고 알림</p>
      </header>

      {error && <p className="error">{error}</p>}

      <section>
        <div className="row-head">
          <h2>내 조건 {conditions.length}개</h2>
          <button className="link" onClick={onAdd}>추가</button>
        </div>
        {conditions.map((c) => (
          <div key={c.id} className="cond">
            <div>
              <strong>{c.label || c.mid_clsfc || c.lrg_clsfc || c.keyword}</strong>
              <span className="dim">{conditionSummary(c)}</span>
            </div>
            <button
              className="link dim"
              onClick={async () => { await api.delCondition(c.id); onReload(); }}
            >삭제</button>
          </div>
        ))}
      </section>

      {consent !== 'on' && (
        <button className="cta" onClick={askPush}>
          공고 올라오면 알림 받기
        </button>
      )}

      <section>
        <h2>새 공고 {notices.length}건</h2>
        {notices.length === 0 && (
          <p className="dim pad">
            아직 매칭된 공고가 없어요. 새로 올라오면 알려드릴게요.
          </p>
        )}
        {notices.map((n) => {
          const d = dday(n.bid_clse_dt);
          return (
            <button
              key={n.bid_ntce_no}
              className="notice"
              onClick={() => n.detail_url && Device.openURL({ url: n.detail_url })}
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

      {notices.length > 0 && <Banner />}

      <footer className="dim foot">
        조달청 나라장터 공고를 기준으로 알려드려요.
        한국전력·LH 등 자체 조달시스템 공고는 포함되지 않아요.
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
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { api.getClassifications().then(setTree).catch((e) => setError(e.message)); }, []);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.addCondition({
        label: (mid || lrg)?.slice(0, 12),
        lrg_clsfc: lrg,
        mid_clsfc: mid,
        amt_min: amt.min,
        amt_max: amt.max,
        cntrct_mthd: method === '전체' ? null : method,
      });
      onDone();
    } catch (e) {
      setError(e.message);
      setSaving(false);
    }
  }

  if (!tree) return <div className="center">{error ?? '불러오는 중…'}</div>;

  const children = tree.find((t) => t.name === lrg)?.children ?? [];

  return (
    <div className="page">
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
              {t.name.trim()}
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
                {(c.name || '기타').trim()} <span className="dim">{c.count}</span>
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
