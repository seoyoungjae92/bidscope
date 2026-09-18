import { Notification } from '@apps-in-toss/web-framework';

/**
 * 알림 동의. 종류마다 콘솔에 동의문이 따로 있어서 따로 받는다.
 * templateCode는 스마트발송 캠페인의 발송 코드다.
 */
export const KINDS = [
  { kind: 'prespec', code: 'bidscope-prespec', label: '공고 예고' },
  { kind: 'new', code: 'bidscope-new', label: '새 공고' },
  { kind: 'closing', code: 'bidscope-closing', label: '마감 임박' },
];

/**
 * requestAgreement는 Promise가 아니라 콜백을 받고 cleanup 함수를 돌려준다.
 * 순서대로 물어보려면 Promise로 감싸야 한다.
 * 반환값: true(동의) | false(거절·실패)
 */
export function askAgreement(code) {
  return new Promise((resolve) => {
    let cleanup;
    const done = (ok) => {
      try { cleanup?.(); } catch { /* 이미 해제됨 */ }
      resolve(ok);
    };
    try {
      cleanup = Notification.requestAgreement({
        options: { templateCode: code },
        onEvent: (r) => done(r?.type === 'newAgreement' || r?.type === 'alreadyAgreed'),
        onError: () => done(false),
      });
    } catch {
      // 토스 앱 밖에서는 SDK가 동기적으로 던진다
      resolve(false);
    }
  });
}
