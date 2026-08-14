import { describe, expect, it } from 'vitest';
import { moscowBusinessDate } from './businessDate';

describe('Moscow business date', () => {
  it('uses Moscow date when UTC has crossed midnight', () => {
    expect(moscowBusinessDate(new Date('2026-08-13T23:00:00.000Z'))).toBe('2026-08-14');
  });

  it('keeps the previous Moscow date before its midnight boundary', () => {
    expect(moscowBusinessDate(new Date('2026-08-13T20:59:59.000Z'))).toBe('2026-08-13');
  });
});
