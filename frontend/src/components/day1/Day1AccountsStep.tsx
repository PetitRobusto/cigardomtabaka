import type { Day1AccountInput, Day1AccountSlot, Day1Currency } from '../../features/day1/day1State';
import { day1AccountSlots } from '../../features/day1/day1State';

const labels: Record<Day1AccountSlot, string> = {
  owner_cny: '我的人民币账户',
  partner_cny: '合伙人人民币账户',
  rub: '卢布账户',
  usdt: 'USDT 账户',
};

interface Props {
  accounts: Day1AccountInput[];
  onChange: (accounts: Day1AccountInput[]) => void;
  readOnly?: boolean;
}

export default function Day1AccountsStep({ accounts, onChange, readOnly = false }: Props) {
  const update = (slot: Day1AccountSlot, key: 'name' | 'original_amount' | 'cny_book_cost', value: string) => {
    onChange(accounts.map(account => {
      if (account.slot !== slot) return account;
      const next = { ...account, [key]: value };
      // CNY is entered once and shown as the same book cost.
      if (account.currency === 'CNY' && key === 'original_amount') next.cny_book_cost = value;
      return next;
    }));
  };

  return <section className="rounded-md border border-border bg-white p-5 shadow-sm">
    <div className="mb-5"><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Step 2 · Funds</p><h2 className="mt-1 font-display text-2xl font-semibold">四个固定账户</h2><p className="mt-2 text-sm text-muted">币种和账户槽位由系统固定；名称可以按实际账户补充。</p></div>
    <div className="space-y-4">
      {day1AccountSlots.map(({ slot, currency }) => {
        const account = accounts.find(item => item.slot === slot) || { slot, currency, name: '', original_amount: '', cny_book_cost: '' };
        return <div key={slot} className="grid gap-3 border-b border-border pb-4 last:border-0 sm:grid-cols-[1.25fr_90px_1fr_1fr] sm:items-end">
          <div><p className="font-medium text-fg">{labels[slot]}</p><p className="mt-1 text-xs text-muted">{slot}</p></div>
          <div><label className="mb-1 block text-xs font-medium text-muted">币种</label><div className="rounded border border-border bg-cream px-3 py-2 text-sm font-semibold">{currency}</div></div>
          <label className="text-xs font-medium text-muted">账户名称<input disabled={readOnly} value={account.name} onChange={event => update(slot, 'name', event.target.value)} placeholder="可选" className="mt-1 w-full rounded border border-border px-3 py-2 text-sm text-fg" /></label>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs font-medium text-muted">原币余额<input disabled={readOnly} type="number" min="0" step="any" value={account.original_amount} onChange={event => update(slot, 'original_amount', event.target.value)} className="mt-1 w-full rounded border border-border px-3 py-2 text-sm text-fg" /></label>
            <label className="text-xs font-medium text-muted">账面成本 CNY<input disabled={readOnly || currency === 'CNY'} type="number" min="0" step="any" value={account.cny_book_cost} onChange={event => update(slot, 'cny_book_cost', event.target.value)} className="mt-1 w-full rounded border border-border px-3 py-2 text-sm text-fg disabled:bg-cream" /></label>
          </div>
        </div>;
      })}
    </div>
    <p className="mt-4 rounded bg-gold/10 px-3 py-2 text-xs leading-5 text-muted">人民币账户的原币余额自动同步为账面成本；RUB 与 USDT 请分别填写原币和估算人民币账面成本。</p>
  </section>;
}

export type { Day1Currency };
