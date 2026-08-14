import { describe, expect, it } from 'vitest';
import { nextDay1DialogFocusIndex } from './Day1ReviewStep';

describe('Day1 confirmation dialog keyboard loop', () => {
  it('wraps Tab and Shift+Tab within dialog focusable controls', () => {
    expect(nextDay1DialogFocusIndex(2, 3, false)).toBe(0);
    expect(nextDay1DialogFocusIndex(0, 3, true)).toBe(2);
    expect(nextDay1DialogFocusIndex(1, 3, false)).toBe(2);
  });
});
