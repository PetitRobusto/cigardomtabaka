import { useRef, useState, type FormEvent } from 'react';
import { createPortal } from 'react-dom';
import { Check, X } from 'lucide-react';
import { apiErrorMessage, recordOtherIncome } from '../../api';
import type { FundAccount, OtherIncomePayload } from '../../types';
import { otherIncomeCny } from '../../features/accounting/otherIncome';
import { incomeClassification, incomeGroups } from '../../features/accounting/incomeCategories';
import { incomeCreateScope, isRetryableIncomeWriteError, pendingIncomeRequest } from '../../features/accounting/incomeRequests';
import { useDialogFocus } from '../../hooks/useDialogFocus';
import { formatDecimalAmount } from '../../utils/decimalDisplay';

interface Confirmation { payload: OtherIncomePayload; accountName: string; currency: 'CNY' | 'RUB'; cny: string }

export default function OtherIncomeAction({ accounts, businessDate, onChanged, submit = recordOtherIncome }: {
  accounts: FundAccount[]; businessDate: string; onChanged?: () => void;
  submit?: (payload: OtherIncomePayload) => Promise<unknown>;
}) {
  const [recovery] = useState(() => {
    try { return { pending: pendingIncomeRequest<OtherIncomePayload>(incomeCreateScope), error: '' }; }
    catch { return { pending: null, error: '浏览器无法读取待确认收入，请检查浏览器存储后重新加载，暂不能新增入账。' }; }
  });
  const restored = recovery.pending?.payload;
  const restoredGroup = incomeGroups.find(group => group.items.some(item => item.value === restored?.subcategory));
  const [groupCode, setGroupCode] = useState(restoredGroup?.value || (restored ? { interest: 'financial', used_item: 'disposal', other: 'other' }[restored.category] : incomeGroups[0].value));
  const [subcategory, setSubcategory] = useState(restored ? restoredGroup ? restored.subcategory! : '' : incomeGroups[0].items[0].value);
  const group = incomeGroups.find(group => group.value === groupCode)!;
  const item = group.items.find(item => item.value === subcategory);
  const category = item?.category;
  const [recognitionConfirmed, setRecognitionConfirmed] = useState(restored?.recognition_confirmed || false);
  const [currency, setCurrency] = useState<'CNY' | 'RUB'>(restored?.exchange_rate === undefined ? 'CNY' : 'RUB');
  const [accountId, setAccountId] = useState(restored?.fund_account_id || 0);
  const [amount, setAmount] = useState(restored?.amount || '');
  const [date, setDate] = useState(restored?.business_date || businessDate);
  const [rate, setRate] = useState(restored?.exchange_rate || '');
  const [source, setSource] = useState(restored?.rate_source || '');
  const [note, setNote] = useState(restored?.note || '');
  const [reference, setReference] = useState(restored?.reference || '');
  const [zeroBookValue, setZeroBookValue] = useState(restored?.zero_book_value_confirmed || false);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(() => {
    if (!restored) return null;
    const restoredCurrency = restored.exchange_rate === undefined ? 'CNY' : 'RUB';
    return { payload: restored, currency: restoredCurrency, accountName: accounts.find(item => item.id === restored.fund_account_id)?.name || `账户 #${restored.fund_account_id}`, cny: otherIncomeCny(restored.amount, restoredCurrency, restored.exchange_rate) || '0.00' };
  });
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(Boolean(restored));
  const inFlight = useRef(false);
  const available = accounts.filter(account => account.is_active && account.currency === currency);
  const account = available.find(item => item.id === accountId) || (accountId === 0 ? available[0] : undefined);
  const cny = otherIncomeCny(amount, currency, rate);

  const prepare = (event: FormEvent) => {
    event.preventDefault();
    if (confirmation || inFlight.current || recovery.error) return;
    setError(''); setNotice('');
    if (!item || !category) { setError('请重新选择收入二级明细后核对入账。'); return; }
    if (!item.manual_entry_enabled) { setError(item.notice); return; }
    if (item.requires_recognition && !recognitionConfirmed) { setError('请先确认收益符合该明细条件且未重复入账。'); return; }
    if (!account || !cny || !date || !note.trim() || (currency === 'RUB' && !source.trim())) {
      setError('请检查收款账户、金额、日期和来源说明；卢布还需有效汇率及来源。'); return;
    }
    if (category === 'used_item' && !zeroBookValue) { setError('请先核实旧物已费用化且账面价值为零。'); return; }
    setConfirmation({ accountName: account.name, currency, cny, payload: {
      category, subcategory, recognition_confirmed: item.requires_recognition && recognitionConfirmed,
      fund_account_id: account.id, amount, business_date: date, note, reference,
      zero_book_value_confirmed: category === 'used_item' && zeroBookValue,
      ...(currency === 'RUB' ? { exchange_rate: rate, rate_source: source } : {}),
    } });
  };

  const confirm = async () => {
    if (!confirmation || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError('');
    let saved = false;
    try {
      await submit(confirmation.payload);
      setConfirmation(null); setUncertain(false);
      setAmount(''); setNote(''); setReference(''); setRate(''); setSource(''); setZeroBookValue(false); setRecognitionConfirmed(false);
      setNotice('其他收入已入账'); saved = true;
    } catch (failure) {
      setError(apiErrorMessage(failure)); setUncertain(isRetryableIncomeWriteError(failure));
    } finally { inFlight.current = false; setBusy(false); }
    if (saved) onChanged?.();
  };

  return <section className="expense-entry expense-panel" aria-labelledby="income-entry-title">
    <header className="expense-panel-head"><div><h2 id="income-entry-title" className="expense-panel-title">登记其他收入</h2><p className="expense-caption">按实际到账币种登记，统一以人民币核算。</p></div></header>
    <form onSubmit={prepare} inert={confirmation !== null} className="space-y-3 p-5">
      <p className="expense-caption">仅登记公司已取得并到账的非销售收益。客户货款、费用退款和资本投入请使用对应入口。</p>
      {recovery.error && <p role="alert" className="expense-hint expense-hint--danger">{recovery.error}</p>}
      {notice && <p role="status" className="expense-hint expense-hint--success">{notice}</p>}
      {error && !confirmation && <p role="alert" className="expense-hint expense-hint--danger">{error}</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="expense-field-label">一级分类<select className="expense-field" value={groupCode} onChange={event => { const next = incomeGroups.find(group => group.value === event.target.value)!; setGroupCode(next.value); setSubcategory(next.items[0].value); setZeroBookValue(false); setRecognitionConfirmed(false); setError(''); }}>{incomeGroups.map(group => <option key={group.value} value={group.value}>{group.label}</option>)}</select></label>
        <label className="expense-field-label">二级明细<select required className="expense-field" value={subcategory} onChange={event => { setSubcategory(event.target.value); setZeroBookValue(false); setRecognitionConfirmed(false); setError(''); }}><option value="" disabled>请选择二级明细</option>{group.items.map(item => <option key={item.value} value={item.value}>{item.label}{item.manual_entry_enabled ? '' : '（需专门核算）'}</option>)}</select></label>
        <p aria-live="polite" className={`expense-hint sm:col-span-2 ${item?.manual_entry_enabled ? '' : 'expense-hint--warning'}`}>{item ? `${item.manual_entry_enabled ? '确认条件：' : '暂不能在此登记：'}${item.notice}` : '原请求未细分收入来源，请选择二级明细后重新核对。'}</p>
        <label className="expense-field-label">收款币种<select className="expense-field" value={currency} onChange={event => { setCurrency(event.target.value as 'CNY' | 'RUB'); setAccountId(0); setRate(''); setSource(''); }}><option value="CNY">人民币（CNY）</option><option value="RUB">卢布（RUB）</option></select></label>
        <label className="expense-field-label">公司收款账户<select required className="expense-field" value={account?.id || ''} disabled={!available.length} onChange={event => setAccountId(Number(event.target.value))}><option value="" disabled>{available.length ? `请选择可用 ${currency} 账户` : `暂无可用 ${currency} 账户`}</option>{available.map(item => <option key={item.id} value={item.id}>{item.name} · {item.currency}</option>)}</select></label>
        <label className="expense-field-label">业务日期（收益确认与到账同日）<input className="expense-field" type="date" required min="2026-08-10" max={businessDate} value={date} onChange={event => setDate(event.target.value)} /></label>
        <label className="expense-field-label">到账金额（{currency}）<input className="expense-field font-mono" inputMode="decimal" required maxLength={24} value={amount} onChange={event => setAmount(event.target.value)} placeholder="0.00" /></label>
        {currency === 'RUB' && <><label className="expense-field-label">业务日汇率（1 CNY = X RUB）<input className="expense-field font-mono" inputMode="decimal" required maxLength={24} value={rate} onChange={event => setRate(event.target.value)} placeholder="最多 8 位小数" /></label><label className="expense-field-label">汇率来源<input className="expense-field" required maxLength={500} value={source} onChange={event => setSource(event.target.value)} placeholder="例如：业务日银行报价及日期" /></label></>}
        <div className="min-w-0"><p className="expense-field-label">人民币账面金额（预览）</p><p aria-live="polite" className="mt-1.5 break-words rounded border border-dashed border-border bg-[#FFFCF7] p-3 text-right font-mono text-sm">{cny ? `${currency === 'RUB' ? `${formatDecimalAmount(amount, 'RUB')} RUB ÷ ${rate} = ` : ''}¥${formatDecimalAmount(cny, 'CNY')}` : '—'}</p></div>
      </div>
      {category === 'used_item' && <div className="expense-hint"><label className="flex items-start gap-2"><input type="checkbox" required checked={zeroBookValue} onChange={event => setZeroBookValue(event.target.checked)} className="mt-1 accent-accent" />确认该旧物已费用化，且剩余账面价值为零</label><p className="expense-caption">请核实原购买记录；有剩余账面价值的资产暂不能在此登记。</p></div>}
      {item?.manual_entry_enabled && item.requires_recognition && <div className="expense-hint"><label className="flex items-start gap-2"><input type="checkbox" required checked={recognitionConfirmed} onChange={event => setRecognitionConfirmed(event.target.checked)} className="mt-1 accent-accent" />确认该收入已实现并到账、符合所选明细条件，且此前未确认为收入</label></div>}
      <label className="expense-field-label">来源说明<textarea className="expense-field" rows={2} required maxLength={2000} value={note} onChange={event => setNote(event.target.value)} placeholder="例如：公司银行账户本月结息" /></label>
      <label className="expense-field-label">凭证参考（可选）<input className="expense-field" maxLength={500} value={reference} onChange={event => setReference(event.target.value)} placeholder="银行回单号或原购买记录" /></label>
      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3"><p className="expense-caption">入账后保留原币金额与本次汇率。</p><button className="expense-button expense-button--primary" disabled={!!recovery.error || !account || !cny || !item?.manual_entry_enabled || (item.requires_recognition && !recognitionConfirmed) || (category === 'used_item' && !zeroBookValue)} type="submit">核对收入</button></footer>
    </form>
    {confirmation && <IncomeConfirmation confirmation={confirmation} busy={busy} uncertain={uncertain} error={error} onCancel={() => { if (!inFlight.current && !uncertain) { setConfirmation(null); setError(''); } }} onConfirm={confirm} />}
  </section>;
}

function IncomeConfirmation({ confirmation: { payload, currency, cny, accountName }, busy, uncertain, error, onCancel, onConfirm }: {
  confirmation: Confirmation; busy: boolean; uncertain: boolean; error: string; onCancel: () => void; onConfirm: () => void;
}) {
  const locked = busy || uncertain;
  const dialog = useDialogFocus(onCancel, locked);
  const classification = incomeClassification(payload);
  return createPortal(<div className="expense-modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !locked) onCancel(); }}>
    <div ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="income-confirm-title" className="expense-modal">
      <header className="expense-modal-head"><h2 id="income-confirm-title" className="expense-modal-title">确认其他收入</h2><button type="button" disabled={locked} onClick={onCancel} className="expense-icon-button" aria-label="关闭"><X size={18} /></button></header>
      <div className="expense-modal-body space-y-3"><dl className="expense-detail-kv">{[
        ['一级分类', classification.group], ['二级明细', classification.item], ['公司收款账户', accountName],
        ['原币入账', `${formatDecimalAmount(payload.amount, currency)} ${currency}`], ['人民币账面金额', `¥${formatDecimalAmount(cny, 'CNY')}`],
        ...(currency === 'RUB' ? [['汇率快照', `1 CNY = ${payload.exchange_rate} RUB`], ['汇率来源', payload.rate_source!]] : []),
        ['业务日期', payload.business_date], ['来源说明', payload.note], ['凭证参考', payload.reference || '—'],
        ...(payload.category === 'used_item' ? [['账面价值', '已确认费用化且账面价值为零']] : []),
        ...(payload.recognition_confirmed ? [['收益确认', '已实现并到账、符合明细条件且此前未确认收入']] : []),
      ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="whitespace-pre-wrap">{value}</dd></div>)}</dl>
        <p className="expense-hint">确认后增加公司收款账户及本期收益。正式记录不能直接修改或删除；录错需通过冲正处理。</p>
        {error && <p role="alert" className="expense-hint expense-hint--danger">{error}</p>}
        {uncertain && <p className="expense-hint expense-hint--warning">尚未确认入账结果，请重试本次提交。原内容已保留，重试不会重复入账。</p>}
      </div>
      <footer className="expense-modal-foot"><button className="expense-button" disabled={locked} onClick={onCancel}>返回修改</button><button className="expense-button expense-button--primary" disabled={busy} onClick={onConfirm}><Check size={14} />{busy ? '入账中…' : uncertain ? '重试本次入账' : '确认收入并入账'}</button></footer>
    </div>
  </div>, document.body);
}
