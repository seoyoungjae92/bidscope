import { useEffect, useRef, useState } from 'react';
import { TossAds } from '@apps-in-toss/web-framework';

/**
 * 앱인토스 배너 광고.
 *
 * 정책상 지켜야 하는 것:
 *  · 같은 화면에 같은 포맷 2개 금지        → 화면당 한 번만 쓴다
 *  · 결제·온보딩·로딩·모달에 배치 금지      → 공고 목록에만 붙인다
 *  · 버튼에 인접 배치 금지(오탭 유도)       → 위아래 여백을 크게 준다
 *  · 콘텐츠 위장 금지                      → "AD" 라벨은 SDK가 그린다
 *  · 10초+ 자동 갱신. 임의 강제 갱신 금지    → 마운트/언마운트만 관리한다
 *
 * adGroupId는 콘솔에서 발급한다. 테스트 키가 운영 번들에 남아 있으면
 * 비게임 전체 점검에서 걸리는 항목이라 .env로 분리했다.
 */

/** initialize()는 비동기다 — onInitialized를 기다리지 않고 attachBanner를 부르면
 * 첫 진입에서만 조용히 실패하고, 화면을 나갔다 오면 붙는다(2026-09-29 실제 증상).
 * 앱 전체에서 한 번만 초기화하고, 그 결과를 모두가 기다린다. */
let ready = null;

function ensureReady() {
  if (!ready) {
    ready = new Promise((resolve, reject) => {
      try {
        TossAds.initialize({
          callbacks: { onInitialized: resolve, onInitializationFailed: reject },
        });
      } catch (e) {
        reject(e);   // 토스 앱 밖에서는 SDK가 동기적으로 던진다
      }
    });
  }
  return ready;
}

export default function Banner() {
  const ref = useRef(null);
  const [state, setState] = useState('loading');   // loading | shown | failed
  const adGroupId = import.meta.env.VITE_AD_GROUP_ID;

  useEffect(() => {
    // 토스 앱 밖(브라우저/AIT Devtools)에서는 지원되지 않는다. 조용히 넘어간다.
    if (!adGroupId || !TossAds.attachBanner.isSupported?.()) {
      setState('failed');
      return;
    }
    let slot;
    let alive = true;
    ensureReady()
      .then(() => {
        if (!alive || !ref.current) return;
        slot = TossAds.attachBanner(adGroupId, ref.current, {
          theme: 'light',      // 미니앱이 라이트 모드 고정이라 맞춘다
          variant: 'card',
          callbacks: {
            onAdRendered: () => alive && setState('shown'),
            onNoFill: () => alive && setState('failed'),
            onAdFailedToRender: () => alive && setState('failed'),
          },
        });
      })
      .catch(() => alive && setState('failed'));
    return () => {
      alive = false;
      slot?.destroy?.();
    };
  }, [adGroupId]);

  // 광고가 안 뜨면 빈 칸을 남기지 않는다 (데드엔드 UI 금지).
  // 붙기 전에도 자리를 잡아두지 않는다 — 안 채워지면 빈 여백만 남는다.
  if (state === 'failed') return null;
  return <div className={state === 'shown' ? 'banner shown' : 'banner'} ref={ref} />;
}
