import type { AccountingExpense } from '../../types';
import { formatCny, formatOriginalAmount } from '../sales/salesState';

interface ExpenseDetailsProps {
  month: string;
  expenses?: AccountingExpense[];
  loading?: boolean;
  error?: string;
}

type ExpenseTone = 'logistics' | 'purchase' | 'facility' | 'platform' | 'office' | 'default';

const CATEGORY_TONES: Array<{ match: string[]; tone: ExpenseTone }> = [
  { match: ['交通', '物流'], tone: 'logistics' },
  { match: ['采购', '进货'], tone: 'purchase' },
  { match: ['场地', '设备', '仓储', '房租'], tone: 'facility' },
  { match: ['销售', '营销', '平台', '佣金'], tone: 'platform' },
  { match: ['办公', '通讯', '行政'], tone: 'office' },
];

function expenseTone(category: string): ExpenseTone {
  return CATEGORY_TONES.find(({ match }) => match.some(keyword => category.includes(keyword)))?.tone || 'default';
}

function categoryToneClass(tone: ExpenseTone): string {
  return {
    logistics: 'bg-[#EAF0F4] text-[#466681]', purchase: 'bg-[#F5E8D8] text-[#A56B2A]',
    facility: 'bg-[#F9EEE6] text-[#A75B27]', platform: 'bg-[#E9F1EB] text-[#3D6B4F]',
    office: 'bg-[#F4F0EA] text-[#8A7E6E]', default: 'bg-[#F4F0EA] text-[#6F6558]',
  }[tone];
}

function categoryDotClass(tone: ExpenseTone): string {
  return {
    logistics: 'bg-[#466681]', purchase: 'bg-[#B87A3A]', facility: 'bg-[#A75B27]',
    platform: 'bg-[#3D6B4F]', office: 'bg-[#8A7E6E]', default: 'bg-[#6F6558]',
  }[tone];
}

function splitSubcategory(expense: AccountingExpense): { category: string; detail: string } {
  const label = expense.subcategory_label || '未分类明细';
  const separator = label.indexOf(' · ');
  if (separator >= 0) return { category: label.slice(0, separator), detail: label.slice(separator + 3) };
  return { category: expense.category_label || '其他', detail: label };
}

function monthLabel(month: string): string {
  const [year, value] = month.split('-');
  return year && value ? `${year} 年 ${value} 月` : month;
}

function originalTotalLabel(expenses: AccountingExpense[]): string {
  const totals = new Map<string, number>();
  expenses.forEach(expense => totals.set(expense.currency, (totals.get(expense.currency) || 0) + Number(expense.original_amount || 0)));
  return Array.from(totals.entries()).map(([currency, amount]) => `${currency} ${formatOriginalAmount(amount, currency)}`).join(' · ') || '—';
}

function LoadingRows() {
  return <>{[0, 1, 2].map(index => <tr key={index} aria-hidden="true">{[44, 84, 150, 76, 88, 120, 110].map((width, cellIndex) => <td key={cellIndex} className="px-3 py-3 first:pl-5 last:pr-5"><span className="block h-3 animate-pulse rounded bg-[#F1ECE5]" style={{ width }} /></td>)}</tr>)}</>;
}

export default function ExpenseDetails({ month, expenses = [], loading = false, error }: ExpenseDetailsProps) {
  const totalCny = expenses.reduce((sum, expense) => sum + Number(expense.amount_cny || 0), 0);
  const showTable = !loading && !error && expenses.length > 0;
  const originals = originalTotalLabel(expenses);

  return <section aria-labelledby="accounting-expense-details-title" className="mb-7 overflow-hidden rounded-md border border-border bg-white shadow-sm">
    <div className="flex flex-col gap-4 border-b border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0"><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Expense ledger</p><div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1"><h2 id="accounting-expense-details-title" className="font-display text-xl font-semibold">费用明细</h2><span className="text-xs text-muted">{monthLabel(month)} · 已入账费用事实</span></div><p className="mt-1 text-xs text-muted">按一级分类归档，与月度利润使用同一记账口径。</p></div>
      <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 sm:justify-end"><div className="text-left sm:text-right"><p className="text-[11px] text-muted">记录数</p><p className="mt-0.5 font-mono text-sm font-semibold text-fg">{loading ? '…' : expenses.length} <span className="font-sans text-xs font-normal text-muted">笔</span></p></div><div className="text-left sm:text-right"><p className="text-[11px] text-muted">原币合计</p><p className="mt-0.5 max-w-[260px] truncate font-mono text-xs text-fg" title={originals}>{loading ? '…' : originals}</p></div><div className="border-l border-border pl-5 text-left sm:text-right"><p className="text-[11px] text-muted">CNY 账面合计</p><p className="mt-0.5 font-mono text-base font-semibold text-fg">{loading ? '…' : formatCny(totalCny)}</p></div></div>
    </div>
    {error && <p role="alert" className="m-5 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-[#FFFDFA] px-5 py-2.5"><p className="text-xs text-muted">费用明细按业务日期归属月份；原币保留原始金额，CNY 仅用于账面比较。</p><span className="inline-flex items-center rounded-full bg-accent-light px-2 py-1 text-[10px] font-semibold text-accent">公司承担费用</span></div>
    <div className="overflow-x-auto" aria-busy={loading}><table className="w-full min-w-[920px] text-left text-sm"><thead className="border-b border-border bg-[#FFFDFA] text-[11px] text-muted"><tr><th className="whitespace-nowrap px-5 py-3 font-semibold">日期</th><th className="whitespace-nowrap px-3 py-3 font-semibold">一级分类</th><th className="whitespace-nowrap px-3 py-3 font-semibold">费用明细</th><th className="whitespace-nowrap px-3 py-3 text-right font-semibold">原币金额</th><th className="whitespace-nowrap px-3 py-3 text-right font-semibold">CNY 账面金额</th><th className="whitespace-nowrap px-3 py-3 font-semibold">付款账户</th><th className="whitespace-nowrap px-5 py-3 font-semibold">备注</th></tr></thead><tbody>{loading && <LoadingRows />}{showTable && expenses.map(expense => { const { category, detail } = splitSubcategory(expense); const tone = expenseTone(category); return <tr key={expense.id} className="border-b border-border last:border-0 hover:bg-[#FFFCF9]"><td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-muted">{expense.business_date}</td><td className="px-3 py-3"><span className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-[11px] font-semibold ${categoryToneClass(tone)}`}><span className={`h-1.5 w-1.5 rounded-full ${categoryDotClass(tone)}`} />{category}</span></td><td className="px-3 py-3 font-medium"><span title={expense.subcategory_label}>{detail}</span>{expense.note && <small className="mt-0.5 block max-w-[210px] truncate text-[11px] font-normal text-muted">{expense.note}</small>}</td><td className="whitespace-nowrap px-3 py-3 text-right font-mono text-xs text-muted">{formatOriginalAmount(expense.original_amount, expense.currency)} <span className="text-[10px]">{expense.currency}</span></td><td className="whitespace-nowrap px-3 py-3 text-right font-mono text-sm font-semibold">{formatCny(expense.amount_cny)}</td><td className="whitespace-nowrap px-3 py-3 text-xs"><span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-gold align-middle" />{expense.fund_account_name || `账户 #${expense.fund_account_id}`}</td><td className="max-w-[240px] truncate px-5 py-3 text-xs text-muted" title={expense.note}>{expense.note || '—'}</td></tr>; })}</tbody></table></div>
    {!loading && !error && expenses.length === 0 && <div className="border-t border-dashed border-border px-5 py-10 text-center"><div className="mx-auto grid h-10 w-10 place-items-center rounded-full bg-[#F5E8D8] font-display text-lg text-accent">¥</div><h3 className="mt-3 font-display text-base font-semibold">本月还没有已入账费用</h3><p className="mx-auto mt-1 max-w-md text-xs text-muted">费用记录会按一级分类和费用明细展示在这里；可在上方“记录经营动作”中登记新的公司承担费用。</p></div>}
  </section>;
}
