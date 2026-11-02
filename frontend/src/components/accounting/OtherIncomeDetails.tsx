import { useEffect, useRef, useState, type FormEvent } from 'react';
import { createPortal } from 'react-dom';
import { ReceiptText, X } from 'lucide-react';
import { apiErrorMessage, fetchOtherIncome, reverseOtherIncome } from '../../api';
import { incomeReverseScope, isRetryableIncomeWriteError, pendingIncomeRequest } from '../../features/accounting/incomeRequests';
import type { OtherIncome, OtherIncomesResponse } from '../../types';
import { useDialogFocus } from '../../hooks/useDialogFocus';
import { moscowBusinessDate } from '../../utils/businessDate';
import { formatDecimalAmount } from '../../utils/decimalDisplay';

const money = (amount: string, currency = 'CNY') => `${formatDecimalAmount(amount, currency)} ${currency}`;

export default function OtherIncomeDetails({ month, data, loading, error, page, onPageChange, onChanged }: {
  month: string; data?: OtherIncomesResponse; loading: boolean; error?: string; page: number;
  onPageChange: (page: number) => void; onChanged: () => void;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const rows = [
    ...(data?.incomes || []).map(income => ({ ...income, key: `income-${income.id}`, incomeId: income.id, reversed: false, originalDate: '' })),
    ...(data?.reversals || []).map(reversal => ({ ...reversal, key: `reversal-${reversal.id}`, incomeId: reversal.income_id, reversed: true, originalDate: reversal.income_business_date, status: 'reversed' })),
  ].sort((left, right) => right.business_date.localeCompare(left.business_date) || right.id - left.id);
  return <section className="expense-ledger" aria-labelledby="other-income-details-title">
    <dl aria-label="其他收入概览" className="expense-panel expense-overview">{[
      ['当月收入', data?.summary.received_cny], ['当月冲正', data?.summary.reversed_cny], ['净收入小计', data?.summary.net_cny],
    ].map(([label, amount]) => <div key={label} className="expense-stat"><dt>{label}</dt><dd>{loading ? '…' : error || amount == null ? '—' : money(amount)}</dd><small>{label === '净收入小计' ? '当月收入 − 当月冲正' : '按实际业务月份 · 人民币口径'}</small></div>)}</dl>
    <div className="expense-panel">
      <header className="expense-panel-head"><div><h2 className="expense-panel-title" id="other-income-details-title">其他收入明细</h2><p className="expense-caption">收入与冲正按各自业务日期归属月份，保留原币与人民币账面金额。</p></div><span className="text-xs text-muted">{month} · 第 {page} 页</span></header>
      {loading && <p role="status" className="p-5 text-sm text-muted">收入明细加载中…</p>}
      {error && <p role="alert" className="expense-hint expense-hint--danger m-4">{error}</p>}
      {!loading && !error && <>
        <div className="expense-table-head" aria-hidden="true"><span>日期</span><span>分类 / 状态</span><span>说明</span><span className="text-right">原币金额</span><span className="text-right">人民币账面</span><span>收款账户</span><span /></div>
        <ul>{rows.map(row => <li className="expense-row" key={row.key}>
          <time className="expense-row-date" dateTime={row.business_date}>{row.business_date.slice(5).replace('-', '/')}</time>
          <div className="expense-row-category"><span className="expense-category expense-category--financial">{row.income_group_label || row.category_label}</span><span className={`expense-status expense-status--${row.reversed || row.status === 'reversed' ? 'reversed' : 'full'}`}>{row.reversed ? '冲正' : row.status === 'reversed' ? '已冲正' : '已入账'}</span></div>
          <div className="expense-row-description"><p className="expense-caption">{row.subcategory_label || `${row.category_label}（历史未细分）`}</p><p className="whitespace-pre-wrap">{row.note}</p>{row.reversed && <p className="expense-caption">原收入日期 {row.originalDate}</p>}</div>
          <div className="expense-row-amounts"><p className="expense-row-original">{row.reversed ? '−' : ''}{money(row.amount, row.currency)}</p><p className="expense-row-cny">{row.reversed ? '−' : ''}{money(row.amount_cny)}</p></div>
          <p className="expense-row-account">{row.fund_account_name}</p>
          <div className="expense-row-actions"><button className="expense-icon-button" onClick={() => setSelected(row.incomeId)} aria-label={`${row.reversed ? '冲正' : '收入'} ${row.id} 详情`} title="查看收入详情"><ReceiptText size={16} /></button></div>
        </li>)}</ul>
        {!rows.length && <p className="expense-empty text-sm text-muted">本月暂无其他收入或冲正记录</p>}
        {(page > 1 || data?.next_page) && <div className="expense-pagination"><button className="expense-button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>上一页</button><span className="text-xs text-muted">第 {page} 页</span><button className="expense-button" disabled={!data?.next_page} onClick={() => data?.next_page && onPageChange(data.next_page)}>下一页</button></div>}
      </>}
    </div>
    {selected !== null && <IncomeDetailDialog key={selected} id={selected} onClose={() => setSelected(null)} onChanged={onChanged} />}
  </section>;
}

function IncomeDetailDialog({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const [recovery] = useState(() => {
    try { return { pending: pendingIncomeRequest<{ business_date: string; note: string }>(incomeReverseScope(id)), error: '' }; }
    catch { return { pending: null, error: '浏览器无法读取待确认冲正，请检查浏览器存储后重新加载。' }; }
  });
  const [income, setIncome] = useState<OtherIncome | null>(null);
  const [reload, setReload] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [reverse, setReverse] = useState(Boolean(recovery.pending));
  const [date, setDate] = useState(recovery.pending?.payload.business_date || moscowBusinessDate());
  const [note, setNote] = useState(recovery.pending?.payload.note || '');
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(Boolean(recovery.pending));
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const inFlight = useRef(false);
  const pending = useRef<{ business_date: string; note: string } | null>(recovery.pending?.payload || null);
  const locked = busy || uncertain;
  const dialog = useDialogFocus(onClose, locked);
  useEffect(() => {
    let active = true;
    fetchOtherIncome(id).then(value => { if (active) { setIncome(value); setLoadError(''); } }, failure => { if (active) setLoadError(apiErrorMessage(failure)); });
    return () => { active = false; };
  }, [id, reload]);
  const confirmReverse = async (event: FormEvent) => {
    event.preventDefault();
    if (!income || inFlight.current || recovery.error || (income.status === 'reversed' && !pending.current)) return;
    const payload = pending.current || { business_date: date, note };
    if (!payload.note.trim()) { setError('请填写冲正原因'); return; }
    inFlight.current = true; pending.current = payload; setBusy(true); setError('');
    let saved = false;
    try {
      const updated = await reverseOtherIncome(income.id, payload);
      setIncome(updated); setReverse(false); setUncertain(false); pending.current = null;
      setNotice('冲正已入账，原收入记录保留。'); saved = true;
    } catch (failure) {
      setError(apiErrorMessage(failure));
      const retryable = isRetryableIncomeWriteError(failure);
      setUncertain(retryable);
      if (!retryable) pending.current = null;
    } finally { inFlight.current = false; setBusy(false); }
    if (saved) onChanged();
  };
  return createPortal(<div className="expense-modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !locked) onClose(); }}>
    <div ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="income-detail-title" className="expense-modal">
      <header className="expense-modal-head"><h2 id="income-detail-title" className="expense-modal-title">{reverse ? '确认冲正收入' : '收入详情'}</h2><button className="expense-icon-button" disabled={locked} onClick={onClose} aria-label="关闭"><X size={18} /></button></header>
      <div className="expense-modal-body space-y-3">
        {recovery.error && <p role="alert" className="expense-hint expense-hint--danger">{recovery.error}</p>}
        {loadError ? <p role="alert" className="expense-hint expense-hint--danger">{loadError}<button className="expense-button ml-2" onClick={() => { setLoadError(''); setReload(value => value + 1); }}>重新加载</button></p> : !income ? <p role="status">正在加载收入…</p> : <>
          {notice && <p role="status" className="expense-hint expense-hint--success">{notice}</p>}
          <dl className="expense-detail-kv">{[
            ['一级分类', income.income_group_label || income.category_label], ['二级明细', income.subcategory_label || `${income.category_label}（历史未细分）`], ['状态', income.status === 'reversed' ? '已冲正' : '已入账'],
            ['业务日期', income.business_date], ['收款账户', income.fund_account_name],
            ['原币金额', money(income.amount, income.currency)], ['人民币账面金额', money(income.amount_cny)],
            ...(income.currency === 'RUB' ? [['汇率快照', `1 CNY = ${income.exchange_rate} RUB`], ['汇率来源', income.rate_source]] : []),
            ['来源说明', income.note], ['凭证参考', income.reference || '—'],
            ...(income.category === 'used_item' ? [['账面价值', '已确认费用化且账面价值为零']] : []),
            ...(income.recognition_confirmed ? [['收益确认', '已实现并到账、符合明细条件且此前未确认收入']] : []),
            ...(income.reversal ? [['冲正日期', income.reversal.business_date], ['冲正原因', income.reversal.note]] : []),
          ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="whitespace-pre-wrap">{value}</dd></div>)}</dl>
          {reverse && <form id="income-reverse-form" onSubmit={confirmReverse} className="space-y-3">
            <p className="expense-hint expense-hint--warning">将从原收款账户扣回 {money(income.amount, income.currency)}，并按原人民币金额 {money(income.amount_cny)} 冲减冲正月份的收益。原记录保留。</p>
            <label className="expense-field-label">冲正日期<input className="expense-field" type="date" required min={income.business_date} max={moscowBusinessDate()} value={date} disabled={locked} onChange={event => setDate(event.target.value)} /></label>
            <label className="expense-field-label">冲正原因<textarea className="expense-field" rows={2} required maxLength={2000} value={note} disabled={locked} onChange={event => setNote(event.target.value)} /></label>
            <p className="expense-caption">若账户已有后续资金流水，或原收入日期已被确认对账覆盖，系统会拒绝直接冲正。</p>
            {error && <p role="alert" className="expense-hint expense-hint--danger">{error}</p>}
            {uncertain && <p className="expense-hint expense-hint--warning">结果尚未确认，请重试同一笔冲正。内容已固定，不会重复扣款。</p>}
          </form>}
        </>}
      </div>
      <footer className="expense-modal-foot">{reverse ? <><button className="expense-button" disabled={locked} onClick={() => { setReverse(false); setError(''); }}>返回详情</button><button type="submit" form="income-reverse-form" className="expense-button expense-button--danger" disabled={busy || !!recovery.error}>{busy ? '冲正中…' : uncertain ? '重试本次冲正' : '确认冲正并入账'}</button></> : <><button className="expense-button" onClick={onClose}>关闭</button>{income?.status === 'posted' && !loadError && <button className="expense-button expense-button--danger" disabled={!!recovery.error} onClick={() => setReverse(true)}>冲正收入</button>}</>}</footer>
    </div>
  </div>, document.body);
}
