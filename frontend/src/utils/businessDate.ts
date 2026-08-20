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
