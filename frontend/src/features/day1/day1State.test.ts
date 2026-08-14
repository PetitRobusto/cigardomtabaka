import { describe, expect, it } from 'vitest';
import {
  buildDay1Payload,
  day1RouteMode,
  day1StepTotal,
  inventoryLineTotal,
  nextDay1Step,
  validateDay1Draft,
} from './day1State';

describe('Day 1 state rules', () => {
  it('advances through the four fixed wizard steps', () => {
    expect(day1StepTotal).toBe(4);
    expect(nextDay1Step(1)).toBe(2);
  });

  it('calculates inventory sticks and cost from boxes plus loose sticks', () => {
    const line = { cigar_id: 4, box_size: 25, box_quantity: 2, loose_sticks: 3, unit_cost_cny: '12.50' };
    expect(inventoryLineTotal(line)).toEqual({ sticks: 53, cost: '662.50' });
  });

  it('uses a readonly summary after completion and an editable wizard otherwise', () => {
    expect(day1RouteMode('completed')).toBe('readonly-summary');
    expect(day1RouteMode('draft')).toBe('editable-wizard');
    expect(day1RouteMode('not_started')).toBe('editable-wizard');
  });

  it('builds the four fixed account slots and validates non-negative values', () => {
    const state = {
      business_date: '2026-08-14',
      accounts: [
        { slot: 'owner_cny', name: '', currency: 'CNY', original_amount: '100', cny_book_cost: '' },
        { slot: 'partner_cny', name: '合伙人', currency: 'CNY', original_amount: '0', cny_book_cost: '0' },
        { slot: 'rub', name: '卢布', currency: 'RUB', original_amount: '1200', cny_book_cost: '100' },
        { slot: 'usdt', name: 'USDT', currency: 'USDT', original_amount: '10', cny_book_cost: '70' },
      ],
      inventory: [{ cigar_id: 4, box_size: 25, box_quantity: 1, loose_sticks: 0, unit_cost_cny: '12.50' }],
    };
    expect(validateDay1Draft(state)).toEqual([]);
    expect(buildDay1Payload(state).accounts.map(account => account.slot)).toEqual(['owner_cny', 'partner_cny', 'rub', 'usdt']);
    expect(buildDay1Payload(state).accounts[0]).toMatchObject({ original_amount: '100', cny_book_cost: '100' });
    expect(validateDay1Draft({ ...state, inventory: [{ ...state.inventory[0], loose_sticks: -1 }] })).toContain('库存第 1 行数量不能为负数');
  });
});
