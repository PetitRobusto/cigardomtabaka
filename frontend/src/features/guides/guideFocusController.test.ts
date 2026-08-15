import { describe, expect, it } from 'vitest';
import { resolveTarget, restoreTarget } from './guideFocusController';

describe('引导 focus controller 纯契约', () => {
  it('产生 focus/restore 描述，不执行 click 或 submit', () => {
    const focused = resolveTarget('[data-guide="accounting-actions-exchange"]');
    expect(focused).toMatchObject({ selector: '[data-guide="accounting-actions-exchange"]', action: 'focus' });
    expect(focused.restoreId).toEqual(expect.any(String));
    expect(restoreTarget(focused.restoreId)).toMatchObject({ restoreId: focused.restoreId, action: 'restore' });
    expect(JSON.stringify({ focused, restored: restoreTarget(focused.restoreId) })).not.toMatch(/click|submit/i);
  });
});
