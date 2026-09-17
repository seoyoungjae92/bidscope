/** 표시 포맷 자체 점검.  node src/format.test.js */
import assert from 'node:assert/strict';
import { conditionSummary, dday, money } from './format.js';

// money — 억/만 경계
assert.equal(money(0), '금액 미공개');
assert.equal(money(null), '금액 미공개');
assert.equal(money(12_345_000), '1,235만');
assert.equal(money(99_999_999), '10,000만');   // 1억 미만은 만 단위 유지
assert.equal(money(100_000_000), '1억');
assert.equal(money(350_000_000), '3.5억');
assert.equal(money(1_000_000_000), '10억');    // 10억 이상은 반올림
assert.equal(money(11_487_272_727), '115억');

// dday — 마감 임박 표시
const now = new Date('2026-09-17T10:00:00');
const at = (s) => dday(s, now);
assert.equal(at(null).text, '마감일 미정');
assert.equal(at('엉터리').text, '마감일 미정');
assert.equal(at('2026-09-16 10:00:00').past, true);
assert.equal(at('2026-09-17 10:30:00').text, '곧 마감');
assert.equal(at('2026-09-17 15:00:00').text, '5시간 뒤 마감');
assert.equal(at('2026-09-19 10:00:00').text, '2일 뒤 마감');
assert.equal(at('2026-09-19 10:00:00').urgent, true);   // 3일 이내는 긴급
assert.equal(at('2026-09-30 10:00:00').urgent, false);
// 서버는 'YYYY-MM-DD HH:MM:SS'로 준다. 사파리가 공백을 못 읽어서 T로 바꾼다
assert.equal(at('2026-09-19 10:00:00').text, at('2026-09-19T10:00:00').text);

// conditionSummary — 사용자가 뭘 등록했는지 한 줄로
assert.equal(
  conditionSummary({ lrg_clsfc: 'ICT 서비스', mid_clsfc: 'SW 및 시스템 개발', amt_max: 100_000_000 }),
  'SW 및 시스템 개발 · 1억 이하');
assert.equal(
  conditionSummary({ lrg_clsfc: 'ICT 서비스', amt_min: 50_000_000, amt_max: 300_000_000 }),
  'ICT 서비스 · 5,000만~3억');
assert.equal(
  conditionSummary({ lrg_clsfc: 'ICT 서비스', cntrct_mthd: '수의계약', keyword: '홈페이지' }),
  'ICT 서비스 · 수의계약 · "홈페이지"');
assert.equal(conditionSummary({ keyword: '청소' }), '청소');  // 키워드만일 땐 중복 안 함

console.log('통과. money 8 · dday 9 · summary 4');
