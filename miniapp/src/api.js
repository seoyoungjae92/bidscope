/** 서버 호출. 사용자 식별은 토스 익명키 하나로 끝난다. */
import { User } from '@apps-in-toss/web-framework';

const BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

let keyPromise = null;

/** 익명키는 앱 삭제·기기 변경에도 유지된다. 한 번만 받아서 재사용.
 *
 * 토스 앱 밖(브라우저)에서는 SDK가 Promise를 거절하는 게 아니라
 * 동기적으로 던진다. .catch()로는 안 잡혀서 async 함수로 감싼다. */
function tossKey() {
  if (!keyPromise) {
    keyPromise = (async () => {
      try {
        const r = await User.getAnonymousKey();
        return r?.hash ?? r;
      } catch {
        return 'dev-local-key';   // 개발용 고정 키
      }
    })();
  }
  return keyPromise;
}

async function call(path, { method = 'GET', body } = {}) {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      'X-Toss-Key': await tossKey(),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
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
export const setPushConsent = (agreed) =>
  call('/push-consent', { method: 'POST', body: { agreed } });
