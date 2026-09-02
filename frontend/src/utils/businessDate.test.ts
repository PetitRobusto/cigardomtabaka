import { describe, expect, it } from 'vitest';
import { formatShanghaiDateTime, moscowBusinessDate, recentMoscowBusinessMonths, shanghaiBusinessDate, shiftIsoDate } from './businessDate';

describe('Moscow business date', () => {
  it('uses Moscow date when UTC has crossed midnight', () => {
    expect(moscowBusinessDate(new Date('2026-08-13T23:00:00.000Z'))).toBe('2026-08-14');
  });

  it('keeps the previous Moscow date before its midnight boundary', () => {
    expect(moscowBusinessDate(new Date('2026-08-13T20:59:59.000Z'))).toBe('2026-08-13');
  });

  it('offers recent accounting months from the current Moscow month across years', () => {
    expect(recentMoscowBusinessMonths(4, new Date('2026-01-15T12:00:00.000Z'))).toEqual([
      { value: '2026-01', label: '本月 · 2026年01月' },
      { value: '2025-12', label: '上月 · 2025年12月' },
      { value: '2025-11', label: '2025年11月' },
      { value: '2025-10', label: '2025年10月' },
    ]);
  });
});

describe('Shanghai order date', () => {
  it('uses the backend timezone across the UTC date boundary', () => {
    expect(shanghaiBusinessDate(new Date('2026-08-13T16:00:00.000Z'))).toBe('2026-08-14');
    expect(shanghaiBusinessDate(new Date('2026-08-13T15:59:59.000Z'))).toBe('2026-08-13');
  });

  it('shifts ISO dates without depending on the browser timezone', () => {
    expect(shiftIsoDate('2026-03-01', -6)).toBe('2026-02-23');
  });

  it('formats order timestamps with the same Shanghai date as filters', () => {
    expect(formatShanghaiDateTime('2026-08-13T16:30:00.000Z')).toBe('2026-08-14 00:30');
    expect(formatShanghaiDateTime('2026-08-14')).toBe('2026-08-14');
  });
});
