import { inventoryLineTotal, type Day1DraftInput } from '../../features/day1/day1State';

interface Props { draft: Day1DraftInput; errors: string[]; readOnly?: boolean; onConfirm?: () => void; confirming?: boolean }

export default function Day1ReviewStep({ draft, errors, readOnly = false, onConfirm, confirming = false }: Props) {
  const total = draft.inventory.reduce((sum, line) => sum + Number(inventoryLineTotal(line).cost), 0).toFixed(2);
  return <section className="rounded-md border border-border bg-white p-5 shadow-sm">
    <div className="mb-5"><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Step 4 · Review</p><h2 className="mt-1 font-display text-2xl font-semibold">核对并一次性生效</h2><p className="mt-2 text-sm text-muted">业务日期：{draft.business_date || '未选择'}</p></div>
    <div className="grid gap-4 md:grid-cols-2"><div className="rounded bg-cream p-4"><h3 className="font-semibold">账户</h3>{draft.accounts.map(account => <div key={account.slot} className="mt-3 flex justify-between gap-3 text-sm"><span>{account.name || account.slot} <small className="text-muted">({account.currency})</small></span><span className="font-mono">{account.original_amount} / ¥ {account.cny_book_cost || account.original_amount}</span></div>)}</div><div className="rounded bg-cream p-4"><h3 className="font-semibold">库存</h3><p className="mt-3 text-sm">{draft.inventory.length} 款 · {draft.inventory.reduce((sum, line) => sum + inventoryLineTotal(line).sticks, 0)} 支</p><p className="mt-2 text-sm">账面成本 <strong>¥ {total}</strong></p></div></div>
    {!readOnly && <div className="mt-5 rounded border border-gold/40 bg-gold/10 p-4 text-sm leading-6 text-muted">确认后会立即写入账务、账户和期初库存；这是一次性生效操作，不能重跑或撤回。请确认以上数据准确无误。</div>}
    {errors.length > 0 && <div className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700"><p className="font-semibold">请先修正以下问题：</p><ul className="mt-1 list-disc pl-5">{errors.map(error => <li key={error}>{error}</li>)}</ul></div>}
    {!readOnly && <button type="button" disabled={confirming || errors.length > 0} onClick={onConfirm} className="mt-5 rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">{confirming ? '正在确认…' : '确认并一次性生效'}</button>}
  </section>;
}
