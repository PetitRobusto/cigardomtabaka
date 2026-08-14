import { describe, expect, it, vi } from 'vitest';
import {
  buildDay1Payload,
  buildDay1ConfirmationPlan,
  canConfirmWithAcknowledgement,
  day1RouteMode,
  mergeDay1Refresh,
  completionSummaryViewModel,
  day1StepTotal,
  inventoryLineTotal,
  emptyDay1Draft,
  nextDay1Step,
  validateDay1Draft,
  declaredBoxSizes,
  isLatestDay1SearchRequest,
  uniqueDay1InventoryCigarIds,
  day1BackgroundInteractionDisabled,
  runDay1BackgroundAction,
} from './day1State';
import type { Day1DraftInput, Day1InventoryInput } from './day1State';

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

  it('freezes background actions while the confirmation dialog is open', () => {
    const action = vi.fn();
    expect(day1BackgroundInteractionDisabled(false)).toBe(false);
    expect(runDay1BackgroundAction(false, action)).toBe(true);
    expect(action).toHaveBeenCalledTimes(1);
    expect(day1BackgroundInteractionDisabled(true)).toBe(true);
    expect(runDay1BackgroundAction(true, action)).toBe(false);
    expect(action).toHaveBeenCalledTimes(1);
  });

  it('builds the four fixed account slots and validates non-negative values', () => {
    const state: Day1DraftInput = {
      business_date: '2026-08-14',
      accounts: [
        { slot: 'owner_cny', name: '我的人民币账户', currency: 'CNY', original_amount: '100', cny_book_cost: '' },
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

  it('plans save-before-confirm against the version returned by save', () => {
    expect(buildDay1ConfirmationPlan(0, 1)).toEqual({ saveExpectedVersion: 0, confirmExpectedVersion: 1 });
    expect(buildDay1ConfirmationPlan(1, 2)).toEqual({ saveExpectedVersion: 1, confirmExpectedVersion: 2 });
  });

  it('requires a second acknowledgement before the irreversible command', () => {
    expect(canConfirmWithAcknowledgement({ dialogOpen: false, acknowledged: false })).toBe(false);
    expect(canConfirmWithAcknowledgement({ dialogOpen: true, acknowledged: false })).toBe(false);
    expect(canConfirmWithAcknowledgement({ dialogOpen: true, acknowledged: true })).toBe(true);
  });

  it('keeps local edits when a manual refresh receives another shared version', () => {
    const local = { business_date: '2026-08-14', accounts: [], inventory: [] } as any;
    const incoming = { status: 'draft', version: 3, business_date: '2026-08-14', draft: { accounts: [], inventory: [] }, completion_summary: null };
    expect(mergeDay1Refresh(local, incoming, local, true)).toEqual({ server: incoming, draft: local });
  });

  it('formats the frozen summary as account and inventory rows', () => {
    const model = completionSummaryViewModel({
      initialization_id: 1, idempotency_key: 'key', request_hash: 'hash', operator_id: 2, business_date: '2026-08-14',
      retained_earnings_cny: '0.00', opening_capital_cny: '347.50', total_net_assets_cny: '347.50', accounts_total_cny: '10.00', inventory_total_cny: '337.50',
      account_count: 1, inventory_count: 1, ledger_transaction_id: 3,
      accounts: [{ slot: 'owner_cny', name: '我的人民币账户', currency: 'CNY', original_amount: '10.00', cny_book_cost: '10.00', account_id: 4 }],
      inventory: [{ cigar_id: 4, box_size: 25, box_quantity: 1, loose_sticks: 2, unit_cost_cny: '12.50', quantity: 27, total_cost_cny: '337.50', batch_id: 5 }],
    });
    expect(model.accounts[0]).toMatchObject({ name: '我的人民币账户', originalAmount: '10.00', bookCost: '10.00' });
    expect(model.inventory[0]).toMatchObject({ quantity: 27, totalCost: '337.50' });
    expect(model.totals.openingCapital).toBe('347.50');
  });

  it('matches backend account and inventory validation rules', () => {
    const draft = emptyDay1Draft('2026-08-14');
    draft.accounts = draft.accounts.map(account => ({ ...account, original_amount: '0', cny_book_cost: account.currency === 'CNY' ? '' : '0' }));
    draft.accounts[1] = { ...draft.accounts[1], name: draft.accounts[0].name };
    draft.accounts[2] = { ...draft.accounts[2], original_amount: '1', cny_book_cost: '0' };
    draft.inventory = [{ cigar_id: 4, box_size: 25, box_quantity: 0, loose_sticks: 0, unit_cost_cny: '0' }];
    const errors = validateDay1Draft(draft);
    expect(errors).toContain('partner_cny账户名称不可重复');
    expect(errors).toContain('rub账户外币余额与账面成本必须同时为零或同时为正');
    expect(errors).toContain('库存第 1 行库存数量必须大于零');
    expect(errors).toContain('库存第 1 行单支成本必须大于零');
  });

  it('uses only declared directory box sizes and rejects duplicate inventory rows', () => {
    expect(declaredBoxSizes([25, 10])).toEqual([25, 10]);
    expect(declaredBoxSizes([])).toEqual([]);
    const draft = emptyDay1Draft('2026-08-14');
    draft.accounts = draft.accounts.map(account => ({ ...account, original_amount: '0', cny_book_cost: account.currency === 'CNY' ? '' : '0' }));
    draft.inventory = [
      { cigar_id: 4, box_size: 25, box_quantity: 1, loose_sticks: 0, unit_cost_cny: '1.00' },
      { cigar_id: 4, box_size: 25, box_quantity: 1, loose_sticks: 0, unit_cost_cny: '1.00' },
    ];
    expect(validateDay1Draft(draft)).toContain('库存第 2 行雪茄和包装规格不可重复');
  });

  it('matches backend cutover date and decimal precision boundaries', () => {
    const draft = emptyDay1Draft('2026-08-09');
    draft.accounts = draft.accounts.map(account => ({ ...account, original_amount: account.currency === 'USDT' ? '1.123456789' : '1.234', cny_book_cost: account.currency === 'CNY' ? '1.234' : '1.00' }));
    expect(validateDay1Draft(draft)).toContain('业务日期不能早于账务切换日');
    expect(validateDay1Draft({ ...draft, business_date: '2099-01-01' })).toContain('业务日期不能晚于莫斯科当前业务日');
    expect(validateDay1Draft(draft).some(error => error.includes('小数位数超出允许精度'))).toBe(true);
  });

  it('rejects stale search responses after the query request changes', () => {
    expect(isLatestDay1SearchRequest(1, 2)).toBe(false);
    expect(isLatestDay1SearchRequest(2, 2)).toBe(true);
  });

  it('deduplicates catalog detail loads for existing inventory rows', () => {
    expect(uniqueDay1InventoryCigarIds([
      { cigar_id: 4, box_size: 10, box_quantity: 1, loose_sticks: 0, unit_cost_cny: '1.00' },
      { cigar_id: 4, box_size: 25, box_quantity: 1, loose_sticks: 0, unit_cost_cny: '1.00' },
      { cigar_id: 9, box_size: 25, box_quantity: 1, loose_sticks: 0, unit_cost_cny: '1.00' },
    ] as Day1InventoryInput[])).toEqual([4, 9]);
  });
});
