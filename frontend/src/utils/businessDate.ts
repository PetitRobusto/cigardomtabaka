export function businessDateInTimeZone(timeZone: string, now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}

export function moscowBusinessDate(now = new Date()): string {
  return businessDateInTimeZone('Europe/Moscow', now);
}

export function shanghaiBusinessDate(now = new Date()): string {
  return businessDateInTimeZone('Asia/Shanghai', now);
}

export function shiftIsoDate(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function formatShanghaiDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  if (!value.includes('T')) return value;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date).replace(/\//g, '-');
}


export function moscowBusinessMonth(now = new Date()): string {
  return moscowBusinessDate(now).slice(0, 7);
}

export function recentMoscowBusinessMonths(count = 12, now = new Date()): Array<{ value: string; label: string }> {
  if (!Number.isInteger(count) || count < 1) return [];
  const [currentYear, currentMonth] = moscowBusinessMonth(now).split('-').map(Number);
  return Array.from({ length: count }, (_, offset) => {
    const date = new Date(Date.UTC(currentYear, currentMonth - 1 - offset, 1));
    const year = date.getUTCFullYear();
    const month = String(date.getUTCMonth() + 1).padStart(2, '0');
    const prefix = offset === 0 ? '本月 · ' : offset === 1 ? '上月 · ' : '';
    return { value: `${year}-${month}`, label: `${prefix}${year}年${month}月` };
  });
}
