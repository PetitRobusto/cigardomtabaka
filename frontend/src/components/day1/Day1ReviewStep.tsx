import { useEffect, useRef, type RefObject } from 'react';
import { inventoryLineTotal, type Day1DraftInput } from '../../features/day1/day1State';

export function nextDay1DialogFocusIndex(currentIndex: number, focusableCount: number, reverse: boolean): number {
  if (focusableCount <= 0) return -1;
  return (currentIndex + (reverse ? -1 : 1) + focusableCount) % focusableCount;
}

export function day1DialogFocusIndexForActiveElement(currentIndex: number, focusableCount: number, reverse: boolean): number {
  // A focus jump from outside the aria-modal enters at the corresponding edge.
  return nextDay1DialogFocusIndex(currentIndex < 0 ? (reverse ? 0 : -1) : currentIndex, focusableCount, reverse);
}

export function createDay1DialogFocusController(dialog: HTMLElement, documentRef: Document = document) {
  const focusableControls = () => Array.from(dialog.querySelectorAll<HTMLElement>('button, input, select, textarea, a[href]'))
    .filter(element => !element.hasAttribute('disabled') && element.tabIndex !== -1);
  const handleTab = (event: KeyboardEvent) => {
    if (event.key !== 'Tab') return;
    const focusable = focusableControls();
    if (!focusable.length) return;
    const currentIndex = focusable.indexOf(documentRef.activeElement as HTMLElement);
    const nextIndex = day1DialogFocusIndexForActiveElement(currentIndex, focusable.length, event.shiftKey);
    event.preventDefault();
    focusable[nextIndex]?.focus();
  };
  const handleFocusIn = (event: FocusEvent) => {
    if (dialog.contains(event.target as Node)) return;
    focusableControls()[0]?.focus();
  };
  return {
    attach() {
      // Capture at document level so an aria-modal cannot leak focus from outside its subtree.
      documentRef.addEventListener('keydown', handleTab, true);
      documentRef.addEventListener('focusin', handleFocusIn, true);
      return () => {
        documentRef.removeEventListener('keydown', handleTab, true);
        documentRef.removeEventListener('focusin', handleFocusIn, true);
      };
    },
  };
}

export function restoreDay1DialogTriggerFocus(wasOpen: boolean, isOpen: boolean, focus: () => void): void {
  // Closing returns keyboard focus to the button that opened the irreversible confirmation.
  if (wasOpen && !isOpen) focus();
}

interface Props {
  draft: Day1DraftInput;
  errors: string[];
  readOnly?: boolean;
  confirmationOpen?: boolean;
  acknowledged?: boolean;
  onPrepare?: () => void;
  onAcknowledge?: (checked: boolean) => void;
  onCancel?: () => void;
  onConfirm?: () => void;
  confirming?: boolean;
  prepareButtonRef?: RefObject<HTMLButtonElement | null>;
}

export default function Day1ReviewStep({ draft, errors, readOnly = false, confirmationOpen = false, acknowledged = false, onPrepare, onAcknowledge, onCancel, onConfirm, confirming = false, prepareButtonRef }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!confirmationOpen) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    return createDay1DialogFocusController(dialog).attach();
  }, [confirmationOpen]);
  const total = draft.inventory.reduce((sum, line) => sum + Number(inventoryLineTotal(line).cost), 0).toFixed(2);
  return <section className="rounded-md border border-border bg-white p-5 shadow-sm">
    <div className="mb-5"><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Step 4 · Review</p><h2 className="mt-1 font-display text-2xl font-semibold">核对并一次性生效</h2><p className="mt-2 text-sm text-muted">业务日期：{draft.business_date || '未选择'}</p></div>
    <div className="grid gap-4 md:grid-cols-2"><div className="rounded bg-cream p-4"><h3 className="font-semibold">账户</h3>{draft.accounts.map(account => <div key={account.slot} className="mt-3 flex justify-between gap-3 text-sm"><span>{account.name || account.slot} <small className="text-muted">({account.currency})</small></span><span className="font-mono">{account.original_amount} / ¥ {account.cny_book_cost || account.original_amount}</span></div>)}</div><div className="rounded bg-cream p-4"><h3 className="font-semibold">库存</h3><p className="mt-3 text-sm">{draft.inventory.length} 款 · {draft.inventory.reduce((sum, line) => sum + inventoryLineTotal(line).sticks, 0)} 支</p><p className="mt-2 text-sm">账面成本 <strong>¥ {total}</strong></p></div></div>
    {!readOnly && <div className="mt-5 rounded border border-gold/40 bg-gold/10 p-4 text-sm leading-6 text-muted">确认后会立即写入账务、账户和期初库存；这是一次性生效操作，不能重跑或撤回。请确认以上数据准确无误。</div>}
    {errors.length > 0 && <div className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700"><p className="font-semibold">请先修正以下问题：</p><ul className="mt-1 list-disc pl-5">{errors.map(error => <li key={error}>{error}</li>)}</ul></div>}
    {!readOnly && !confirmationOpen && <button ref={prepareButtonRef} type="button" disabled={confirming || errors.length > 0} onClick={onPrepare} className="mt-5 rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">准备生效</button>}
    {!readOnly && confirmationOpen && <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="确认 Day 1 初始化" className="mt-5 rounded border-2 border-accent bg-accent-light p-4"><p className="font-semibold text-fg">最后确认</p><p className="mt-2 text-sm leading-6 text-muted">确认后会立即写入账户、期初库存和账务交易，一次性生效且不可撤回。</p><label className="mt-3 flex items-start gap-2 text-sm text-fg"><input autoFocus type="checkbox" checked={acknowledged} onChange={event => onAcknowledge?.(event.target.checked)} className="mt-1" />我已核对数据，并理解此操作不可撤回</label><div className="mt-4 flex gap-2"><button type="button" onClick={onCancel} className="rounded border border-border bg-white px-4 py-2 text-sm">返回修改</button><button type="button" disabled={confirming || !acknowledged} onClick={onConfirm} className="rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">{confirming ? '正在确认…' : '确认并一次性生效'}</button></div></div>}
  </section>;
}
