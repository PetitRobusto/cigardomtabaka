import { describe, expect, it, vi } from 'vitest';
import {
  day1WriteGate,
  refreshDay1State,
  saveDay1DraftAtBase,
  saveThenConfirmDay1,
} from './day1Workflow';
import { emptyDay1Draft } from './day1State';

const state = (version: number, status: 'draft' | 'completed' = 'draft') => ({
  status,
  version,
  business_date: '2026-08-14',
  draft: status === 'completed' ? null : { accounts: [], inventory: [] },
  completion_summary: null,
});

describe('Day 1 production workflow', () => {
  it('saves the dirty draft against its base and confirms with the returned version', async () => {
    const save = vi.fn().mockResolvedValue(state(2));
    const confirm = vi.fn().mockResolvedValue(state(2, 'completed'));
    const result = await saveThenConfirmDay1({
      draft: emptyDay1Draft('2026-08-14'), baseVersion: 1, idempotencyKey: 'day1-key', save, confirm,
    });
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ business_date: '2026-08-14' }), 1);
    expect(confirm).toHaveBeenCalledWith(2, 'day1-key');
    expect(result.confirmed.status).toBe('completed');
  });

  it('does not confirm when saving the dirty draft rejects', async () => {
    const save = vi.fn().mockRejectedValue(new Error('版本冲突'));
    const confirm = vi.fn();
    await expect(saveThenConfirmDay1({
      draft: emptyDay1Draft('2026-08-14'), baseVersion: 1, idempotencyKey: 'day1-key', save, confirm,
    })).rejects.toThrow('版本冲突');
    expect(confirm).not.toHaveBeenCalled();
  });

  it('uses the page save path with the supplied local base version', async () => {
    const save = vi.fn().mockResolvedValue(state(2));
    const result = await saveDay1DraftAtBase({ draft: emptyDay1Draft('2026-08-14'), baseVersion: 1, save });
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ business_date: '2026-08-14' }), 1);
    expect(result.version).toBe(2);
  });

  it('preserves local draft and base on shared refresh, but discard adopts both', () => {
    const local = emptyDay1Draft('2026-08-14');
    const incoming = state(3);
    const preserved = refreshDay1State({ localDraft: local, baseVersion: 1, incoming, mode: 'preserve-local' });
    expect(preserved).toEqual({ server: incoming, draft: local, baseVersion: 1 });
    const discarded = refreshDay1State({ localDraft: local, baseVersion: 1, incoming, mode: 'discard-local' });
    expect(discarded.baseVersion).toBe(3);
    expect(discarded.draft).not.toBe(local);
  });

  it('blocks all write/confirmation gates for completed state', () => {
    expect(day1WriteGate('completed', true)).toBe(false);
    expect(day1WriteGate('draft', false)).toBe(false);
    expect(day1WriteGate('draft', true)).toBe(true);
  });
});
