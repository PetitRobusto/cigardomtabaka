import { describe, expect, it } from 'vitest';
import { shouldReuseTarget } from './targetTransition';

describe('target transition', () => {
  it('does not reuse an empty target, so missing content can be reported', () => {
    expect(shouldReuseTarget(null, null)).toBe(false);
  });

  it('reuses the same existing target while scanning repeatedly', () => {
    const target = {} as HTMLElement;
    expect(shouldReuseTarget(target, target)).toBe(true);
  });

  it('does not reuse when a target appears after a missing scan', () => {
    const target = {} as HTMLElement;
    expect(shouldReuseTarget(target, null)).toBe(false);
  });
});
