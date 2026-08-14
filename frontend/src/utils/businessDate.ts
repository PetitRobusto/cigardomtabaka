export function moscowBusinessDate(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Moscow',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}


export function moscowBusinessMonth(now = new Date()): string {
  return moscowBusinessDate(now).slice(0, 7);
}
