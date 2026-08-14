import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiErrorMessage, confirmDay1, day1ErrorMessage, fetchDay1State, saveDay1Draft } from '../api';
import { usePageMeta } from '../hooks/usePageMeta';
import { moscowBusinessDate } from '../utils/businessDate';
import Day1AccountsStep from '../components/day1/Day1AccountsStep';
import Day1InventoryStep from '../components/day1/Day1InventoryStep';
import Day1ReviewStep from '../components/day1/Day1ReviewStep';
import {
  buildDay1Payload, day1RouteMode, day1StepTotal, emptyDay1Draft, nextDay1Step, normalizeDay1Draft, previousDay1Step,
  validateDay1Draft, type Day1DraftInput,
} from '../features/day1/day1State';
import type { Day1State } from '../types';

const stepLabels = ['规则与日期', '账户', '库存', '核对生效'];

export default function Day1SetupPage() {
  const { setMeta } = usePageMeta();
  const [server, setServer] = useState<Day1State | null>(null);
  const [draft, setDraft] = useState<Day1DraftInput>(() => emptyDay1Draft(moscowBusinessDate()));
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  useEffect(() => { setMeta({ title: 'Day 1 初始化', breadcrumbs: [{ label: '首页', to: '/' }, { label: '账务工作台', to: '/accounting' }, { label: 'Day 1 初始化' }] }); }, [setMeta]);

  const load = useCallback(() => {
    setLoading(true); setError('');
    fetchDay1State().then(data => { setServer(data); setDraft(normalizeDay1Draft(data, moscowBusinessDate())); }).catch(reason => setError(apiErrorMessage(reason, 'Day 1 状态加载失败'))).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);

  const mode = day1RouteMode(server?.status || 'not_started');
  const errors = useMemo(() => validateDay1Draft(draft), [draft]);
  const save = () => {
    setSaving(true); setError(''); setMessage('');
    // Keep local draft on failure so another operator's update cannot overwrite it.
    saveDay1Draft(buildDay1Payload(draft), server?.version || 0).then(data => { setServer(data); setDraft(normalizeDay1Draft(data, moscowBusinessDate())); setMessage('草稿已保存，其他经营者可继续核对。'); }).catch(reason => setError(day1ErrorMessage(reason))).finally(() => setSaving(false));
  };
  const confirm = () => {
    if (errors.length || !server) return;
    setConfirming(true); setError('');
    // Idempotency protects retries from posting the opening transaction twice.
    confirmDay1(server.version, `day1-confirm-${server.version}-${Date.now()}`).then(data => { setServer(data); setMessage('初始化已完成，账务快照已冻结。'); }).catch(reason => setError(day1ErrorMessage(reason))).finally(() => setConfirming(false));
  };

  if (loading) return <div className="rounded-md border border-border bg-white p-8 text-center text-sm text-muted">正在加载 Day 1 共享草稿…</div>;
  if (error && !server) return <section className="rounded-md border border-red-200 bg-red-50 p-6 text-sm text-red-700"><p>{error}</p><button type="button" onClick={load} className="mt-4 rounded bg-accent px-4 py-2 font-semibold text-white">重新加载</button></section>;
  if (mode === 'readonly-summary') return <ReadonlySummary server={server!} message={message} />;

  const setStepSafe = (target: number) => setStep(Math.max(1, Math.min(day1StepTotal, target)));
  return <div className="w-full animate-fade-in"><header className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Opening setup · Day 1</p><h1 className="mt-1 font-display text-3xl font-semibold tracking-tight sm:text-4xl">一次性初始化</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-muted">共同整理期初账户和库存。确认前不会影响账务；确认后一次性生效且不可重跑。</p></div><div className="flex items-center gap-2 text-xs text-muted"><span>共享版本 v{server?.version || 0}</span><button type="button" onClick={() => setRefreshKey(key => key + 1)} className="rounded border border-border bg-white px-3 py-2 hover:border-gold">刷新</button></div></header>
    {message && <div className="mb-4 rounded border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">{message}</div>}
    {error && <div className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
    <div className="grid gap-5 lg:grid-cols-[220px_1fr]"><aside className="rounded-md border border-border bg-white p-2 shadow-sm"><div className="hidden lg:block">{stepLabels.map((label, index) => <button type="button" key={label} onClick={() => setStepSafe(index + 1)} className={`flex w-full items-center gap-3 rounded px-3 py-3 text-left text-sm ${step === index + 1 ? 'bg-accent-light text-accent font-semibold' : 'text-muted hover:bg-cream'}`}><span className={`grid h-7 w-7 place-items-center rounded-full text-xs font-bold ${step > index + 1 ? 'bg-green-600 text-white' : 'bg-cream'}`}>{index + 1}</span>{label}</button>)}</div><div className="flex justify-between gap-1 lg:hidden">{stepLabels.map((label, index) => <button type="button" key={label} onClick={() => setStepSafe(index + 1)} className={`flex flex-1 flex-col items-center gap-1 rounded px-1 py-2 text-center text-[11px] ${step === index + 1 ? 'bg-accent-light text-accent font-semibold' : 'text-muted'}`}><span className="grid h-6 w-6 place-items-center rounded-full bg-cream text-xs">{index + 1}</span>{label}</button>)}</div></aside>
      <main className="min-w-0">{step === 1 && <RulesStep date={draft.business_date} readOnly={false} onDateChange={businessDate => setDraft(current => ({ ...current, business_date: businessDate }))} />}{step === 2 && <Day1AccountsStep accounts={draft.accounts} onChange={accounts => setDraft(current => ({ ...current, accounts }))} />}{step === 3 && <Day1InventoryStep inventory={draft.inventory} onChange={inventory => setDraft(current => ({ ...current, inventory }))} />}{step === 4 && <Day1ReviewStep draft={draft} errors={errors} confirming={confirming} onConfirm={confirm} />}<div className="mt-4 flex flex-wrap justify-between gap-2"><button type="button" disabled={step === 1} onClick={() => setStepSafe(previousDay1Step(step))} className="rounded border border-border bg-white px-4 py-2 text-sm disabled:opacity-40">上一步</button><div className="flex gap-2"><button type="button" disabled={saving} onClick={save} className="rounded border border-border bg-white px-4 py-2 text-sm hover:border-gold disabled:opacity-40">{saving ? '保存中…' : '保存草稿'}</button>{step < day1StepTotal && <button type="button" onClick={() => setStepSafe(nextDay1Step(step))} className="rounded bg-accent px-4 py-2 text-sm font-semibold text-white">下一步</button>}</div></div></main></div>
  </div>;
}

function RulesStep({ date, onDateChange }: { date: string; readOnly: boolean; onDateChange: (date: string) => void }) {
  return <section className="rounded-md border border-border bg-white p-5 shadow-sm"><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Step 1 · Rules</p><h2 className="mt-1 font-display text-2xl font-semibold">先确认初始化规则</h2><div className="mt-5 grid gap-4 md:grid-cols-2"><div className="rounded bg-cream p-4 text-sm leading-6 text-muted"><p className="font-semibold text-fg">这是共同草稿</p><p className="mt-2">保存后会共享给另一位经营者。保存使用版本号保护，若对方先更新，系统会提示刷新，不会覆盖你的本地表单。</p></div><div className="rounded bg-gold/10 p-4 text-sm leading-6 text-muted"><p className="font-semibold text-fg">确认是不可逆操作</p><p className="mt-2">确认后生成账户、期初库存和账务交易，并冻结完成摘要；同一初始化不能再次运行。</p></div></div><label className="mt-6 block text-sm font-medium text-fg">业务日期<input type="date" value={date} onChange={event => onDateChange(event.target.value)} className="mt-2 block w-full max-w-xs rounded border border-border px-3 py-2" /></label></section>;
}

function ReadonlySummary({ server, message }: { server: Day1State; message: string }) {
  return <section className="w-full rounded-md border border-green-200 bg-white p-6 shadow-sm"><p className="text-[11px] font-bold uppercase tracking-[.12em] text-green-700">Day 1 · Completed</p><h1 className="mt-1 font-display text-3xl font-semibold">初始化已完成</h1><p className="mt-3 text-sm leading-6 text-muted">完成摘要已由后端冻结，不能编辑或再次确认。业务日期：{server.business_date || '—'} · 版本 v{server.version}</p>{message && <p className="mt-3 rounded bg-green-50 px-3 py-2 text-sm text-green-800">{message}</p>}<div className="mt-6 grid gap-3 sm:grid-cols-2">{Object.entries(server.completion_summary || {}).map(([key, value]) => <div key={key} className="rounded bg-cream p-3"><p className="text-xs text-muted">{key}</p><p className="mt-1 font-mono text-sm">{String(value ?? '—')}</p></div>)}</div><Link to="/accounting" className="mt-6 inline-flex rounded bg-accent px-4 py-2 text-sm font-semibold text-white">返回账务工作台</Link></section>;
}
