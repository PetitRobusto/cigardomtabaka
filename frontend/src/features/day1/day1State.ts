export const day1StepTotal = 4;

export type Day1Status = 'not_started' | 'draft' | 'completed' | string;
export type Day1RouteMode = 'editable-wizard' | 'readonly-summary';
export type Day1AccountSlot = 'owner_cny' | 'partner_cny' | 'rub' | 'usdt';
export type Day1Currency = 'CNY' | 'RUB' | 'USDT';

export interface Day1AccountInput {
  slot: Day1AccountSlot;
  name: string;
  currency: Day1Currency;
  original_amount: string;
  cny_book_cost: string;
}

export interface Day1InventoryInput {
  cigar_id: number;
  cigar_name?: string;
  box_size: number;
  box_quantity: number;
  loose_sticks: number;
  unit_cost_cny: string;
}

export interface Day1DraftInput {
  business_date: string;
  accounts: Day1AccountInput[];
  inventory: Day1InventoryInput[];
}

export interface Day1Payload {
  business_date: string;
  accounts: Array<Omit<Day1AccountInput, 'name'> & { name: string }>;
  inventory: Array<Omit<Day1InventoryInput, 'cigar_name'> & { cigar_id: number }>;
}

const ACCOUNT_SLOTS: ReadonlyArray<{ slot: Day1AccountSlot; currency: Day1Currency }> = [
  { slot: 'owner_cny', currency: 'CNY' },
  { slot: 'partner_cny', currency: 'CNY' },
  { slot: 'rub', currency: 'RUB' },
  { slot: 'usdt', currency: 'USDT' },
];

export function nextDay1Step(step: number): number {
  return Math.min(day1StepTotal, Math.max(1, step + 1));
}

export function previousDay1Step(step: number): number {
  return Math.max(1, Math.min(day1StepTotal, step - 1));
}

export function day1RouteMode(status: Day1Status): Day1RouteMode {
  return status === 'completed' ? 'readonly-summary' : 'editable-wizard';
}

export function inventoryLineTotal(line: Pick<Day1InventoryInput, 'box_size' | 'box_quantity' | 'loose_sticks' | 'unit_cost_cny'>): { sticks: number; cost: string } {
  const sticks = line.box_quantity * line.box_size + line.loose_sticks;
  return { sticks, cost: (sticks * Number(line.unit_cost_cny || 0)).toFixed(2) };
}

function amount(value: string): number {
  return Number(value);
}

function isNonNegativeNumber(value: number): boolean {
  return Number.isFinite(value) && value >= 0;
}

export function validateDay1Draft(state: Day1DraftInput): string[] {
  const errors: string[] = [];
  if (!state.business_date) errors.push('请选择业务日期');

  for (const { slot, currency } of ACCOUNT_SLOTS) {
    const account = state.accounts.find(item => item.slot === slot);
    if (!account) {
      errors.push(`缺少${slot}账户`);
      continue;
    }
    if (account.currency !== currency) errors.push(`${slot}账户币种不可修改`);
    if (!account.original_amount.trim() || !isNonNegativeNumber(amount(account.original_amount))) errors.push(`${slot}账户原币余额必须是非负金额`);
    if (currency !== 'CNY' && (!account.cny_book_cost.trim() || !isNonNegativeNumber(amount(account.cny_book_cost)))) errors.push(`${slot}账户账面成本必须是非负金额`);
    if (currency === 'CNY' && account.cny_book_cost.trim() && !isNonNegativeNumber(amount(account.cny_book_cost))) errors.push(`${slot}账户账面成本必须是非负金额`);
    if ((currency === 'CNY' && account.cny_book_cost !== '' && amount(account.cny_book_cost) !== amount(account.original_amount))) {
      errors.push(`${slot}账户人民币原币与账面成本必须一致`);
    }
  }

  state.inventory.forEach((line, index) => {
    if (!Number.isInteger(line.cigar_id) || line.cigar_id <= 0) errors.push(`库存第 ${index + 1} 行必须选择目录雪茄`);
    if (!Number.isInteger(line.box_size) || line.box_size <= 0) errors.push(`库存第 ${index + 1} 行盒规必须为正整数`);
    if (!Number.isInteger(line.box_quantity) || line.box_quantity < 0 || !Number.isInteger(line.loose_sticks) || line.loose_sticks < 0) errors.push(`库存第 ${index + 1} 行数量不能为负数`);
    if (!line.unit_cost_cny.trim() || !isNonNegativeNumber(amount(line.unit_cost_cny))) errors.push(`库存第 ${index + 1} 行成本必须是非负金额`);
  });
  return errors;
}

export function buildDay1Payload(state: Day1DraftInput): Day1Payload {
  const accounts = ACCOUNT_SLOTS.map(({ slot, currency }) => {
    const source = state.accounts.find(account => account.slot === slot) || {
      slot, currency, name: '', original_amount: '0', cny_book_cost: '0',
    };
    // CNY has one source of truth: its original amount is also book cost.
    const cnyBookCost = currency === 'CNY' ? source.original_amount : source.cny_book_cost;
    return {
      slot,
      name: source.name,
      currency,
      original_amount: source.original_amount || '0',
      cny_book_cost: cnyBookCost || '0',
    };
  });
  return {
    business_date: state.business_date,
    accounts,
    inventory: state.inventory.map(({ cigar_name: _cigarName, ...line }) => line),
  };
}

export function emptyDay1Draft(today: string): Day1DraftInput {
  return {
    business_date: today,
    accounts: ACCOUNT_SLOTS.map(({ slot, currency }) => ({ slot, currency, name: '', original_amount: '', cny_book_cost: '' })),
    inventory: [],
  };
}

export function normalizeDay1Draft(data: { business_date: string | null; draft: { accounts: Day1AccountInput[]; inventory: Day1InventoryInput[] } | null }, today: string): Day1DraftInput {
  if (!data.draft) return emptyDay1Draft(data.business_date || today);
  const draft = emptyDay1Draft(data.business_date || today);
  draft.accounts = draft.accounts.map(base => data.draft?.accounts.find(account => account.slot === base.slot) || base);
  draft.inventory = data.draft.inventory;
  return draft;
}

export const day1AccountSlots = ACCOUNT_SLOTS;
