import { describe, expect, it } from 'vitest';
import { formatShanghaiDateTime, moscowBusinessDate, shanghaiBusinessDate, shiftIsoDate } from './businessDate';

describe('Moscow business date', () => {
  it('uses Moscow date when UTC has crossed midnight', () => {
    expect(moscowBusinessDate(new Date('2026-08-13T23:00:00.000Z'))).toBe('2026-08-14');
  });

  it('keeps the previous Moscow date before its midnight boundary', () => {
    expect(moscowBusinessDate(new Date('2026-08-13T20:59:59.000Z'))).toBe('2026-08-13');
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
