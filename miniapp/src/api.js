/** 서버 호출. 사용자 식별은 토스 익명키 하나로 끝난다. */
import { User } from '@apps-in-toss/web-framework';

const BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

// 심사 반려(2026-09-19) 「최초 접속 20초 초과」 대응 — 어떤 대기도 무한정 두지 않는다.
// 최악의 경우 익명키 3초 + 조건 5초 + 목록 5초 = 13초 안에 화면이 뜬다.
const KEY_TIMEOUT_MS = 3000;
const REQUEST_TIMEOUT_MS = 5000;

let keyPromise = null;

function timeout(ms) {
  return new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), ms));
}

/** 익명키를 못 받으면 이 기기 전용 임의 키로 대신한다.
 * 예전엔 모두가 같은 'dev-local-key'로 떨어져 서로의 조건이 섞였다.
 * 이 키로는 푸시가 안 가지만 앱은 쓸 수 있다. */
function localKey() {
  const k = 'bidscope.localKey';
  try {
    let v = localStorage.getItem(k);
    if (!v) {
      v = 'local-' + (crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`);
      localStorage.setItem(k, v);
    }
    return v;
  } catch {
    return 'local-' + Math.random().toString(36).slice(2);
  }
}

/** 익명키는 앱 삭제·기기 변경에도 유지된다. 한 번만 받아서 재사용.
 *
 * 토스 앱 밖(브라우저)에서는 SDK가 Promise를 거절하는 게 아니라
 * 동기적으로 던진다. .catch()로는 안 잡혀서 async 함수로 감싼다.
 * 응답이 안 오는 경우도 있어서 시간 상한을 둔다. */
function tossKey() {
  if (!keyPromise) {
    keyPromise = (async () => {
      try {
        const r = await Promise.race([User.getAnonymousKey(), timeout(KEY_TIMEOUT_MS)]);
        const key = r?.hash ?? r;
        if (typeof key === 'string' && key) return key;
      } catch { /* 아래로 */ }
      return import.meta.env.DEV ? 'dev-local-key' : localKey();
    })();
  }
  return keyPromise;
}

async function call(path, { method = 'GET', body } = {}) {
  const key = await tossKey();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: {
        'X-Toss-Key': key,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
  } catch (e) {
    throw new Error(e.name === 'AbortError'
      ? '서버 응답이 늦어요. 잠시 후 다시 시도해 주세요.'
      : '서버에 연결하지 못했어요. 네트워크를 확인해 주세요.');
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.error ?? `요청에 실패했어요 (${res.status})`);
  return data;
}

export const getClassifications = () => call('/classifications');
export const getConditions = () => call('/conditions');
export const addCondition = (body) => call('/conditions', { method: 'POST', body });
export const delCondition = (id) => call(`/conditions/${id}`, { method: 'DELETE' });
export const getNotices = (condId) =>
  call('/notices' + (condId ? `?cond_id=${condId}` : ''));
export const getPrespecs = () => call('/prespecs');
export const getPushConsent = () => call('/push-consent');
export const setPushConsent = (kind, agreed) =>
  call('/push-consent', { method: 'POST', body: { kind, agreed } });
