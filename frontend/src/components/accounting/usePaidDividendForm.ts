import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchDividendRounds, parseAccountingApiError, recordPaidDividend } from '../../api';
import { isRetryableWriteError } from '../../api/idempotency';
import type { DividendPreview, FundAccount, PaidDividendPayload } from '../../types';
import { dividendCents, dividendMoney, personalDividendAmounts } from './DividendRoundsAction.logic';

type Attempt = { payload: PaidDividendPayload; warning?: DividendPreview; uncertain: boolean };

export function usePaidDividendForm(accounts: FundAccount[], businessDate: string, onChanged?: () => void) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ['dividend-rounds', 'defaults'], queryFn: () => fetchDividendRounds() });
  const recipients = query.data?.recipients ?? [];
  const cnyAccounts = accounts.filter(account => account.is_active && account.currency === 'CNY');
  const [input, setInput] = useState({ amount: '', bothPaid: false, a: undefined as string | undefined, b: undefined as string | undefined, account: undefined as string | undefined, date: businessDate, note: '' });
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const inFlight = useRef(false);
  const defaults = query.data?.defaults;
  const a = input.a ?? (recipients.some(user => user.id === defaults?.partner_a_id) ? String(defaults!.partner_a_id) : '');
  const preferredB = input.b ?? (recipients.some(user => user.id === defaults?.partner_b_id) ? String(defaults!.partner_b_id) : '');
  const b = recipients.length === 2 && recipients.some(user => String(user.id) === a)
    ? String(recipients.find(user => String(user.id) !== a)!.id)
    : preferredB === a ? '' : preferredB;
  const account = input.account ?? (cnyAccounts.some(item => item.id === defaults?.fund_account_id) ? String(defaults!.fund_account_id) : '');
  const amounts = personalDividendAmounts(input.amount, input.bothPaid);
  const valid = Boolean(amounts && input.date && a !== b
    && recipients.some(user => String(user.id) === a) && recipients.some(user => String(user.id) === b)
    && cnyAccounts.some(item => String(item.id) === account));

  const save = async (payload: PaidDividendPayload) => {
    if (inFlight.current) return false;
    inFlight.current = true; setBusy(true); setError(''); setNotice('');
    try { await recordPaidDividend(payload); }
    catch (failure) {
      const parsed = parseAccountingApiError(failure);
      setError(parsed.message);
      if ((parsed.code === 'warning_required' || parsed.code === 'warning_stale')
        && typeof parsed.details?.warning_fingerprint === 'string'
        && typeof parsed.details?.retained_earnings_cny === 'string') {
        setAttempt({ payload, warning: parsed.details as unknown as DividendPreview, uncertain: false });
      } else if (isRetryableWriteError(failure)) {
        // 不确定请求结果时，冻结完整原请求；重试复用同一幂等键。
        setAttempt(current => ({ payload, warning: current?.warning, uncertain: true }));
      } else { setAttempt(null); }
      inFlight.current = false; setBusy(false); return false;
    }
    setAttempt(null);
    setInput({ amount: '', bothPaid: false, a: String(payload.partner_a_id), b: String(payload.partner_b_id), account: String(payload.fund_account_id), date: payload.business_date, note: '' });
    const paid = (dividendCents(payload.partner_a_paid_cny!) ?? 0n) + (dividendCents(payload.partner_b_paid_cny!) ?? 0n);
    const pending = (dividendCents(payload.total_cny) ?? 0n) - paid;
    setNotice(`分红已记录 · ${payload.business_date} · 账户扣款 ${dividendMoney(paid)} CNY，待领 ${dividendMoney(pending)} CNY。可在下方对应月份的分红明细查看或补领。`);
    inFlight.current = false; setBusy(false);
    void client.invalidateQueries({ queryKey: ['dividend-rounds'] });
    try { onChanged?.(); } catch { setNotice('记账成功；页面刷新失败，请点击重新加载。'); }
    return true;
  };

  const submit = async () => {
    if (!valid || !amounts || attempt) return false;
    return save({ total_cny: amounts.total, partner_a_id: Number(a), partner_b_id: Number(b),
      partner_a_paid_cny: amounts.individual, partner_b_paid_cny: amounts.otherPaid,
      fund_account_id: Number(account), business_date: input.date, note: input.note });
  };
  return { query, recipients, cnyAccounts, input: { ...input, a, b, account }, setInput,
    attempt, busy, error, notice, amounts, valid, submit, save,
    discard: () => {
      if (inFlight.current || attempt?.uncertain) return false;
      setInput({ amount: '', bothPaid: false, a: undefined, b: undefined, account: undefined, date: businessDate, note: '' });
      setAttempt(null); setError('');
      return true;
    },
    cancelWarning: () => { if (!inFlight.current && !attempt?.uncertain) { setAttempt(null); setError(''); } },
  };
}
