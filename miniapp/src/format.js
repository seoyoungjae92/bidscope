/** 표시용 포맷. 로직이 있어 test.js가 검증한다. */

/** 12345000 → "1,234만" / 350000000 → "3.5억" */
export function money(won) {
  const n = Number(won) || 0;
  if (n <= 0) return '금액 미공개';
  if (n >= 100_000_000) {
    const v = n / 100_000_000;
    return (v >= 10 ? Math.round(v) : v.toFixed(1).replace(/\.0$/, '')) + '억';
  }
  return Math.round(n / 10_000).toLocaleString() + '만';
}

/** 마감까지 남은 시간. 임박할수록 사용자가 봐야 할 이유가 커진다. */
export function dday(clseDt, now = new Date()) {
  if (!clseDt) return { text: '마감일 미정', urgent: false };
  const t = new Date(String(clseDt).replace(' ', 'T'));
  if (Number.isNaN(t.getTime())) return { text: '마감일 미정', urgent: false };
  const ms = t - now;
  if (ms < 0) return { text: '마감', urgent: false, past: true };
  const h = Math.floor(ms / 3_600_000);
  if (h < 1) return { text: '곧 마감', urgent: true };
  if (h < 24) return { text: `${h}시간 뒤 마감`, urgent: true };
  const d = Math.floor(h / 24);
  return { text: `${d}일 뒤 마감`, urgent: d <= 3 };
}

/** 조건을 한 줄로. 목록에서 뭘 등록했는지 바로 보여야 한다. */
export function conditionSummary(c) {
  const parts = [c.mid_clsfc || c.lrg_clsfc || c.keyword];
  if (c.amt_max > 0 && c.amt_min > 0) parts.push(`${money(c.amt_min)}~${money(c.amt_max)}`);
  else if (c.amt_max > 0) parts.push(`${money(c.amt_max)} 이하`);
  else if (c.amt_min > 0) parts.push(`${money(c.amt_min)} 이상`);
  if (c.cntrct_mthd) parts.push(c.cntrct_mthd);
  if (c.keyword && (c.lrg_clsfc || c.mid_clsfc)) parts.push(`"${c.keyword}"`);
  return parts.filter(Boolean).join(' · ');
}
