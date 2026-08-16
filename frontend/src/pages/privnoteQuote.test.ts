import { describe, expect, it } from 'vitest';
import { selectedIdsOnCustomEntry } from './privnoteQuote';

describe('privnote custom quote selection', () => {
  it('uses live defaults only when entering custom mode for the first time', () => {
    expect(selectedIdsOnCustomEntry('full', [1, 2])).toBeNull();
  });

  it('preserves an explicit selection when custom mode is clicked again', () => {
    const selection = [2];
    expect(selectedIdsOnCustomEntry('custom', selection)).toBe(selection);
    expect(selectedIdsOnCustomEntry('custom', [])).toEqual([]);
  });
});
