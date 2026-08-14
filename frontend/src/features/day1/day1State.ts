import type { Day1CompletionSummary } from '../../types';
import { moscowBusinessDate } from '../../utils/businessDate';

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

export interface Day1CompletionViewModel {
  accounts: Array<{ name: string; currency: string; originalAmount: string; bookCost: string }>;
  inventory: Array<{ cigar: string; boxSize: number; boxQuantity: number; looseSticks: number; quantity: number; unitCost: string; totalCost: string }>;
  totals: { openingCapital: string; totalNetAssets: string; accountsTotal: string; inventoryTotal: string };
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

export function buildDay1ConfirmationPlan(currentVersion: number, savedVersion: number): { saveExpectedVersion: number; confirmExpectedVersion: number } {
  return { saveExpectedVersion: currentVersion, confirmExpectedVersion: savedVersion };
}

export function canConfirmWithAcknowledgement(state: { dialogOpen: boolean; acknowledged: boolean }): boolean {
  return state.dialogOpen && state.acknowledged;
}

export function mergeDay1Refresh<T extends Day1DraftInput, S>(localDraft: T, incomingServer: S, incomingDraft: T, preserveLocal: boolean): { server: S; draft: T } {
  return { server: incomingServer, draft: preserveLocal ? localDraft : incomingDraft };
}

function summaryAmount(summary: Day1CompletionSummary, key: string): string {
  const value = (summary as unknown as Record<string, unknown>)[key];
  return value == null ? '0.00' : String(value);
}

export function completionSummaryViewModel(summary: Day1CompletionSummary | null): Day1CompletionViewModel {
  if (!summary) return { accounts: [], inventory: [], totals: { openingCapital: '0.00', totalNetAssets: '0.00', accountsTotal: '0.00', inventoryTotal: '0.00' } };
  return {
    accounts: Array.isArray(summary.accounts) ? summary.accounts.map(account => ({
      name: String(account.name || '未命名账户'), currency: String(account.currency || '—'),
      originalAmount: String(account.original_amount ?? '0.00'), bookCost: String(account.cny_book_cost ?? '0.00'),
    })) : [],
    inventory: Array.isArray(summary.inventory) ? summary.inventory.map(item => ({
      // Frozen summaries currently carry cigar_id; keep an optional name for compatible future payloads.
      cigar: item.cigar_name ? String(item.cigar_name) : `目录雪茄 #${item.cigar_id}`,
      boxSize: Number(item.box_size || 0), boxQuantity: Number(item.box_quantity || 0), looseSticks: Number(item.loose_sticks || 0),
      quantity: Number(item.quantity || 0), unitCost: String(item.unit_cost_cny ?? '0.00'), totalCost: String(item.total_cost_cny ?? '0.00'),
    })) : [],
    totals: {
      openingCapital: summaryAmount(summary, 'opening_capital_cny'), totalNetAssets: summaryAmount(summary, 'total_net_assets_cny'),
      accountsTotal: summaryAmount(summary, 'accounts_total_cny'), inventoryTotal: summaryAmount(summary, 'inventory_total_cny'),
    },
  };
}

export function inventoryLineTotal(line: Pick<Day1InventoryInput, 'box_size' | 'box_quantity' | 'loose_sticks' | 'unit_cost_cny'>): { sticks: number; cost: string } {
  const sticks = line.box_quantity * line.box_size + line.loose_sticks;
  return { sticks, cost: (sticks * Number(line.unit_cost_cny || 0)).toFixed(2) };
}

function amount(value: string): number {
  return Number(value);
}

const DAY1_CUTOVER_DATE = '2026-08-10';

function decimalPlaces(value: string): number | null {
  const normalized = value.trim();
  if (!normalized || !Number.isFinite(Number(normalized))) return null;
  const match = normalized.match(/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE]([+-]?\d+))?$/);
  if (!match) return null;
  const mantissa = normalized.split(/[eE]/i)[0].replace(/^[+-]/, '');
  const exponent = Number(match[1] || 0);
  return Math.max(0, (mantissa.split('.')[1]?.length || 0) - exponent);
}

function hasExcessDecimalPlaces(value: string, places: number): boolean {
  const decimals = decimalPlaces(value);
  return decimals !== null && decimals > places;
}

function validBusinessDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}

function isNonNegativeNumber(value: number): boolean {
  return Number.isFinite(value) && value >= 0;
}

export function validateDay1Draft(state: Day1DraftInput): string[] {
  const errors: string[] = [];
  if (!state.business_date) errors.push('请选择业务日期');
  else if (!validBusinessDate(state.business_date)) errors.push('业务日期必须是有效日期');
  else if (state.business_date < DAY1_CUTOVER_DATE) errors.push('业务日期不能早于账务切换日');
  else if (state.business_date > moscowBusinessDate()) errors.push('业务日期不能晚于莫斯科当前业务日');

  const names = new Set<string>();

  for (const { slot, currency } of ACCOUNT_SLOTS) {
    const account = state.accounts.find(item => item.slot === slot);
    if (!account) {
      errors.push(`缺少${slot}账户`);
      continue;
    }
    if (account.currency !== currency) errors.push(`${slot}账户币种不可修改`);
    if (!account.name.trim()) errors.push(`${slot}账户名称不能为空`);
    else if (names.has(account.name.trim())) errors.push(`${slot}账户名称不可重复`);
    names.add(account.name.trim());
    const originalPlaces = currency === 'USDT' ? 8 : 2;
    if (!account.original_amount.trim() || !isNonNegativeNumber(amount(account.original_amount))) errors.push(`${slot}账户原币余额必须是非负金额`);
    else if (hasExcessDecimalPlaces(account.original_amount, originalPlaces)) errors.push(`${slot}账户原币余额小数位数超出允许精度`);
    if (currency !== 'CNY' && (!account.cny_book_cost.trim() || !isNonNegativeNumber(amount(account.cny_book_cost)))) errors.push(`${slot}账户账面成本必须是非负金额`);
    if (currency === 'CNY' && account.cny_book_cost.trim() && !isNonNegativeNumber(amount(account.cny_book_cost))) errors.push(`${slot}账户账面成本必须是非负金额`);
    if (account.cny_book_cost.trim() && hasExcessDecimalPlaces(account.cny_book_cost, 2)) errors.push(`${slot}账户账面成本小数位数超出允许精度`);
    if (currency !== 'CNY' && ((amount(account.original_amount) === 0) !== (amount(account.cny_book_cost) === 0))) errors.push(`${slot}账户外币余额与账面成本必须同时为零或同时为正`);
    if ((currency === 'CNY' && account.cny_book_cost !== '' && amount(account.cny_book_cost) !== amount(account.original_amount))) {
      errors.push(`${slot}账户人民币原币与账面成本必须一致`);
    }
  }

  state.inventory.forEach((line, index) => {
    if (!Number.isInteger(line.cigar_id) || line.cigar_id <= 0) errors.push(`库存第 ${index + 1} 行必须选择目录雪茄`);
    if (!Number.isInteger(line.box_size) || line.box_size <= 0) errors.push(`库存第 ${index + 1} 行盒规必须为正整数`);
    if (!Number.isInteger(line.box_quantity) || line.box_quantity < 0 || !Number.isInteger(line.loose_sticks) || line.loose_sticks < 0) errors.push(`库存第 ${index + 1} 行数量不能为负数`);
    if (line.box_quantity * line.box_size + line.loose_sticks <= 0) errors.push(`库存第 ${index + 1} 行库存数量必须大于零`);
    if (!line.unit_cost_cny.trim() || !Number.isFinite(amount(line.unit_cost_cny)) || amount(line.unit_cost_cny) <= 0) errors.push(`库存第 ${index + 1} 行单支成本必须大于零`);
    else if (hasExcessDecimalPlaces(line.unit_cost_cny, 2)) errors.push(`库存第 ${index + 1} 行单支成本小数位数超出允许精度`);
  });
  const seenInventory = new Set<string>();
  state.inventory.forEach((line, index) => {
    const key = `${line.cigar_id}:${line.box_size}`;
    if (seenInventory.has(key)) errors.push(`库存第 ${index + 1} 行雪茄和包装规格不可重复`);
    seenInventory.add(key);
  });
  return errors;
}

export function declaredBoxSizes(boxSizes: unknown[]): number[] {
  const sizes: number[] = [];
  for (const candidate of boxSizes) {
    if (typeof candidate === 'number' && Number.isInteger(candidate) && candidate > 0 && !sizes.includes(candidate)) sizes.push(candidate);
  }
  return sizes;
}

export function isLatestDay1SearchRequest(requestId: number, currentRequestId: number): boolean {
  return requestId === currentRequestId;
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
    accounts: ACCOUNT_SLOTS.map(({ slot, currency }) => ({ slot, currency, name: defaultAccountName(slot), original_amount: '', cny_book_cost: '' })),
    inventory: [],
  };
}

export function defaultAccountName(slot: Day1AccountSlot): string {
  return { owner_cny: '我的人民币账户', partner_cny: '合伙人人民币账户', rub: '卢布账户', usdt: 'USDT账户' }[slot];
}

export function normalizeDay1Draft(data: { business_date: string | null; draft: { accounts: Day1AccountInput[]; inventory: Day1InventoryInput[] } | null }, today: string): Day1DraftInput {
  if (!data.draft) return emptyDay1Draft(data.business_date || today);
  const draft = emptyDay1Draft(data.business_date || today);
  draft.accounts = draft.accounts.map(base => data.draft?.accounts.find(account => account.slot === base.slot) || base);
  draft.inventory = data.draft.inventory;
  return draft;
}

export const day1AccountSlots = ACCOUNT_SLOTS;
