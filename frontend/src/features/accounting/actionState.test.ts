import { describe, expect, it } from 'vitest';
import {
  initialActionState,
  reduceActionState,
  type ActionCard,
} from './actionState';

const cards: ActionCard[] = ['exchange', 'purchase', 'expense', 'dividend'];

describe('accounting action state isolation', () => {
  it.each(cards)('keeps %s in idle state with its input intact', card => {
    const input = { amount: '100.00', business_date: '2026-08-15' };
    const state = initialActionState(input);
    expect(state.status).toBe('idle');
    expect(state.input).toEqual(input);
    expect(card).toBeTypeOf('string');
  });

  it.each([
    ['loading', { type: 'loading' }],
    ['success', { type: 'success', result: { id: 1 } }],
    ['error', { type: 'error', code: 'busy', message: '动作区暂时不可用' }],
    ['conflict', { type: 'conflict', code: 'version_conflict', message: '版本已变化' }],
  ] as const)('transitions to %s without changing the entered Decimal strings', (_status, action) => {
    const input = { amount: '100.00000000', rub_amount: '1200.00', business_date: '2026-08-15' };
    const state = reduceActionState(initialActionState(input), action);
    expect(state.status).toBe(_status);
    expect(state.input).toEqual(input);
    expect(typeof state.input.amount).toBe('string');
    expect(typeof state.input.rub_amount).toBe('string');
  });

  it('isolates one card error from all sibling card states', () => {
    const exchange = initialActionState({ source_amount: '1.00', rub_amount: '12.00' });
    const purchase = initialActionState({ box_quantity: '2', unit_price_rub_per_box: '25000.00' });
    const expense = initialActionState({ amount: '88.00' });
    const dividend = initialActionState({ total_cny: '1000.00' });

    const failedExchange = reduceActionState(exchange, { type: 'error', code: 'busy', message: '繁忙' });

    expect(failedExchange.status).toBe('error');
    expect(failedExchange.error?.code).toBe('busy');
    expect(failedExchange.input).toEqual(exchange.input);
    expect(purchase).toEqual(initialActionState(purchase.input));
    expect(expense).toEqual(initialActionState(expense.input));
    expect(dividend).toEqual(initialActionState(dividend.input));
  });
});
