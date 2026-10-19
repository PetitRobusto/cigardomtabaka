import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchDividendRounds, parseAccountingApiError, recordPaidDividend } from '../../api';
import { isRetryableWriteError } from '../../api/idempotency';
import type { DividendPreview, FundAccount, PaidDividendPayload } from '../../types';
import { dividendCents, dividendMoney } from './DividendRoundsAction.logic';

type Attempt = { payload: PaidDividendPayload; warning?: DividendPreview; uncertain: boolean };

export function usePaidDividendForm(accounts: FundAccount[], businessDate: string, onChanged?: () => void) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ['dividend-rounds', 'defaults'], queryFn: () => fetchDividendRounds() });
  const recipients = query.data?.recipients ?? [];
  const cnyAccounts = accounts.filter(account => account.is_active && account.currency === 'CNY');
  const [input, setInput] = useState({ total: '', a: undefined as string | undefined, b: undefined as string | undefined, account: undefined as string | undefined, date: businessDate, note: '' });
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const inFlight = useRef(false);
  const defaults = query.data?.defaults;
  const a = input.a ?? (recipients.some(user => user.id === defaults?.partner_a_id) ? String(defaults!.partner_a_id) : '');
  const b = input.b ?? (recipients.some(user => user.id === defaults?.partner_b_id) ? String(defaults!.partner_b_id) : '');
  const account = input.account ?? (cnyAccounts.some(item => item.id === defaults?.fund_account_id) ? String(defaults!.fund_account_id) : '');
  const cents = dividendCents(input.total);
  const half = cents !== null && cents > 0n && cents % 2n === 0n ? dividendMoney(cents / 2n) : null;
  const valid = Boolean(half && input.date && a !== b
    && recipients.some(user => String(user.id) === a) && recipients.some(user => String(user.id) === b)
    && cnyAccounts.some(item => String(item.id) === account));

  const save = async (payload: PaidDividendPayload) => {
    if (inFlight.current) return;
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
      inFlight.current = false; setBusy(false); return;
    }
    setAttempt(null);
    setInput({ total: '', a: String(payload.partner_a_id), b: String(payload.partner_b_id), account: String(payload.fund_account_id), date: payload.business_date, note: '' });
    setNotice(`分红已记录 · ${payload.business_date} · ${payload.total_cny} CNY，可在下方对应月份的分红明细查看。`);
    inFlight.current = false; setBusy(false);
    void client.invalidateQueries({ queryKey: ['dividend-rounds'] });
    try { onChanged?.(); } catch { setNotice('记账成功；页面刷新失败，请点击重新加载。'); }
  };

  const submit = () => {
    if (!valid || cents === null || attempt) return;
    void save({ total_cny: dividendMoney(cents), partner_a_id: Number(a), partner_b_id: Number(b),
      fund_account_id: Number(account), business_date: input.date, note: input.note });
  };
  return { query, recipients, cnyAccounts, input: { ...input, a, b, account }, setInput,
    attempt, busy, error, notice, half, valid, submit, save,
    cancelWarning: () => { if (!inFlight.current && !attempt?.uncertain) { setAttempt(null); setError(''); } },
  };
}
