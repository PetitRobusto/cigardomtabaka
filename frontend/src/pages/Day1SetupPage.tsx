import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { Link } from 'react-router-dom';
import { apiErrorMessage, clearDay1ValidationDetails, confirmDay1, day1ErrorMessage, day1ValidationDetails, fetchDay1State, saveDay1Draft } from '../api';
import { usePageMeta } from '../hooks/usePageMeta';
import { moscowBusinessDate } from '../utils/businessDate';
import Day1AccountsStep from '../components/day1/Day1AccountsStep';
import Day1InventoryStep from '../components/day1/Day1InventoryStep';
import Day1ReviewStep, { restoreDay1DialogTriggerFocus } from '../components/day1/Day1ReviewStep';
import {
  canConfirmWithAcknowledgement, completionSummaryViewModel,
  day1RouteMode, day1StepTotal, emptyDay1Draft, nextDay1Step, normalizeDay1Draft, previousDay1Step,
  validateDay1Draft, type Day1DraftInput,
} from '../features/day1/day1State';
import { day1WriteGate, refreshDay1State, saveDay1DraftAtBase, saveThenConfirmDay1 } from '../features/day1/day1Workflow';
import type { Day1State } from '../types';

const stepLabels = ['规则与日期', '账户', '库存', '核对生效'];

export default function Day1SetupPage() {
  const { setMeta } = usePageMeta();
  const [server, setServer] = useState<Day1State | null>(null);
  const [draft, setDraft] = useState<Day1DraftInput>(() => emptyDay1Draft(moscowBusinessDate()));
  const [draftBaseVersion, setDraftBaseVersion] = useState(0);
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [confirmationKey, setConfirmationKey] = useState('');
  const draftRef = useRef(draft);
  const draftBaseVersionRef = useRef(draftBaseVersion);
  const prepareButtonRef = useRef<HTMLButtonElement>(null);
  // Confirmation success replaces the trigger, so retain a focusable frozen-summary fallback.
  const completedSummaryRef = useRef<HTMLDivElement>(null);
  const wasConfirmationOpen = useRef(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [validationDetails, setValidationDetails] = useState<Record<string, string>>({});
  useEffect(() => { draftRef.current = draft; }, [draft]);
  useEffect(() => { draftBaseVersionRef.current = draftBaseVersion; }, [draftBaseVersion]);
  useEffect(() => {
    restoreDay1DialogTriggerFocus(wasConfirmationOpen.current, confirmationOpen, () => prepareButtonRef.current, () => completedSummaryRef.current);
    wasConfirmationOpen.current = confirmationOpen;
  }, [confirmationOpen]);
  useEffect(() => { setMeta({ title: 'Day 1 初始化', breadcrumbs: [{ label: '首页', to: '/' }, { label: '账务工作台', to: '/accounting' }, { label: 'Day 1 初始化' }] }); }, [setMeta]);

  const load = useCallback((preserveLocal = false) => {
    setLoading(true); setError(''); setValidationDetails({});
    fetchDay1State().then(data => {
      const merged = refreshDay1State({
        localDraft: draftRef.current,
        baseVersion: draftBaseVersionRef.current,
        incoming: data,
        mode: preserveLocal ? 'preserve-local' : 'discard-local',
      });
      setServer(merged.server); setDraft(merged.draft); setDraftBaseVersion(merged.baseVersion);
    }).catch(reason => setError(apiErrorMessage(reason, 'Day 1 状态加载失败'))).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const mode = day1RouteMode(server?.status || 'not_started');
  const errors = useMemo(() => validateDay1Draft(draft), [draft]);
  const save = () => {
    setSaving(true); setError(''); setMessage(''); setValidationDetails({});
    // Keep local draft on failure so another operator's update cannot overwrite it.
    if (!server || server.status === 'completed') { setSaving(false); return; }
    saveDay1DraftAtBase({ draft, baseVersion: draftBaseVersion, save: saveDay1Draft }).then(data => { setServer(data); setDraft(normalizeDay1Draft(data, moscowBusinessDate())); setDraftBaseVersion(data.version); setMessage('草稿已保存，其他经营者可继续核对。'); }).catch(reason => { setValidationDetails(day1ValidationDetails(reason)); setError(day1ErrorMessage(reason)); }).finally(() => setSaving(false));
  };
  const clearValidationDetails = (prefix: string) => setValidationDetails(current => clearDay1ValidationDetails(current, prefix));
  const prepareConfirm = () => {
    if (errors.length || !server || !day1WriteGate(server.status, true)) return;
    setAcknowledged(false);
    setConfirmationKey(`day1-confirm-${server.version}-${Math.random().toString(36).slice(2, 12)}`);
    setConfirmationOpen(true);
  };
  const cancelConfirm = () => { setConfirmationOpen(false); setAcknowledged(false); setConfirmationKey(''); };
  const confirm = () => {
    if (errors.length || !server || !day1WriteGate(server.status, acknowledged) || !canConfirmWithAcknowledgement({ dialogOpen: confirmationOpen, acknowledged }) || !confirmationKey) return;
    setConfirming(true); setError(''); setValidationDetails({});
    // The workflow saves the current form against the local base before confirming its returned version.
    saveThenConfirmDay1({
      draft, baseVersion: draftBaseVersion, idempotencyKey: confirmationKey,
      save: saveDay1Draft, confirm: confirmDay1,
      onSaved: saved => { setServer(saved); setDraft(normalizeDay1Draft(saved, moscowBusinessDate())); setDraftBaseVersion(saved.version); },
    }).then(({ confirmed }) => {
      setServer(confirmed); setMessage('初始化已完成，账务快照已冻结。'); setConfirmationOpen(false); setAcknowledged(false);
    }).catch(reason => { setValidationDetails(day1ValidationDetails(reason)); setError(day1ErrorMessage(reason)); }).finally(() => setConfirming(false));
  };

  if (loading) return <div className="rounded-md border border-border bg-white p-8 text-center text-sm text-muted">正在加载 Day 1 共享草稿…</div>;
  if (error && !server) return <section className="rounded-md border border-red-200 bg-red-50 p-6 text-sm text-red-700"><p>{error}</p><button type="button" onClick={() => load()} className="mt-4 rounded bg-accent px-4 py-2 font-semibold text-white">重新加载</button></section>;
  if (mode === 'readonly-summary' && server) return <Day1ReadonlySummary server={server} summaryRef={completedSummaryRef} />;

  const setStepSafe = (target: number) => setStep(Math.max(1, Math.min(day1StepTotal, target)));
  const versionMismatch = Boolean(server && server.status !== 'completed' && draftBaseVersion !== server.version);
  return <div className="w-full animate-fade-in"><header className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Opening setup · Day 1</p><h1 className="mt-1 font-display text-3xl font-semibold tracking-tight sm:text-4xl">一次性初始化</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-muted">共同整理期初账户和库存。确认前不会影响账务；确认后一次性生效且不可重跑。</p></div><div className="flex flex-wrap items-center justify-end gap-2 text-xs text-muted"><span>本地基准 v{draftBaseVersion} · 共享 v{server?.version || 0}</span><button type="button" onClick={() => load(true)} className="rounded border border-border bg-white px-3 py-2 hover:border-gold">刷新共享状态</button><button type="button" onClick={() => load(false)} className="rounded border border-border bg-white px-3 py-2 text-accent hover:border-gold">放弃本地并加载共享草稿</button></div></header>
    {versionMismatch && <div className="mb-4 rounded border border-gold/50 bg-gold/10 px-4 py-3 text-sm text-gold-900">共享草稿已更新（v{server?.version}），你的本地表单仍基于 v{draftBaseVersion}。保存会得到版本冲突；请自行合并，或明确放弃本地草稿加载共享版本。</div>}
    {message && <div className="mb-4 rounded border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">{message}</div>}
    {error && <div className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
    {Object.keys(validationDetails).length > 0 && <div className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"><p className="font-semibold">服务器校验详情：</p><ul className="mt-1 list-disc pl-5">{Object.entries(validationDetails).map(([field, detail]) => <li key={field}><span className="font-medium">{field}</span>：{detail}</li>)}</ul></div>}
    <div className="grid gap-5 lg:grid-cols-[220px_1fr]"><aside className="rounded-md border border-border bg-white p-2 shadow-sm"><div className="hidden lg:block">{stepLabels.map((label, index) => <button type="button" key={label} aria-current={step === index + 1 ? 'step' : undefined} onClick={() => setStepSafe(index + 1)} className={`flex w-full items-center gap-3 rounded px-3 py-3 text-left text-sm ${step === index + 1 ? 'bg-accent-light text-accent font-semibold' : 'text-muted hover:bg-cream'}`}><span className={`grid h-7 w-7 place-items-center rounded-full text-xs font-bold ${step > index + 1 ? 'bg-green-600 text-white' : 'bg-cream'}`}>{index + 1}</span>{label}</button>)}</div><div className="flex justify-between gap-1 lg:hidden">{stepLabels.map((label, index) => <button type="button" key={label} aria-current={step === index + 1 ? 'step' : undefined} onClick={() => setStepSafe(index + 1)} className={`flex flex-1 flex-col items-center gap-1 rounded px-1 py-2 text-center text-[11px] ${step === index + 1 ? 'bg-accent-light text-accent font-semibold' : 'text-muted'}`}><span className="grid h-6 w-6 place-items-center rounded-full bg-cream text-xs">{index + 1}</span>{label}</button>)}</div></aside>
      <main className="min-w-0">{step === 1 && <RulesStep date={draft.business_date} readOnly={false} businessDateError={validationDetails.business_date} onDateChange={businessDate => { clearValidationDetails('business_date'); setDraft(current => ({ ...current, business_date: businessDate })); }} />}{step === 2 && <Day1AccountsStep accounts={draft.accounts} fieldErrors={validationDetails} onChange={accounts => { clearValidationDetails('accounts'); setDraft(current => ({ ...current, accounts })); }} />}{step === 3 && <Day1InventoryStep inventory={draft.inventory} fieldErrors={validationDetails} onChange={inventory => { clearValidationDetails('inventory'); setDraft(current => ({ ...current, inventory })); }} />}{step === 4 && <Day1ReviewStep draft={draft} errors={errors} confirmationOpen={confirmationOpen} acknowledged={acknowledged} confirming={confirming} prepareButtonRef={prepareButtonRef} onPrepare={prepareConfirm} onAcknowledge={setAcknowledged} onCancel={cancelConfirm} onConfirm={confirm} />}<div className="mt-4 flex flex-wrap justify-between gap-2"><button type="button" disabled={step === 1 || confirming} onClick={() => setStepSafe(previousDay1Step(step))} className="rounded border border-border bg-white px-4 py-2 text-sm disabled:opacity-40">上一步</button><div className="flex gap-2">{!confirmationOpen && <button type="button" disabled={saving || confirming} onClick={save} className="rounded border border-border bg-white px-4 py-2 text-sm hover:border-gold disabled:opacity-40">{saving ? '保存中…' : '保存草稿'}</button>}{step < day1StepTotal && <button type="button" disabled={confirming} onClick={() => setStepSafe(nextDay1Step(step))} className="rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">下一步</button>}</div></div></main></div>
  </div>;
}

function RulesStep({ date, businessDateError, onDateChange }: { date: string; readOnly: boolean; businessDateError?: string; onDateChange: (date: string) => void }) {
  return <section className="rounded-md border border-border bg-white p-5 shadow-sm"><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Step 1 · Rules</p><h2 className="mt-1 font-display text-2xl font-semibold">先确认初始化规则</h2><div className="mt-5 grid gap-4 md:grid-cols-2"><div className="rounded bg-cream p-4 text-sm leading-6 text-muted"><p className="font-semibold text-fg">这是共同草稿</p><p className="mt-2">保存后会共享给另一位经营者。保存使用版本号保护，若对方先更新，系统会提示刷新，不会覆盖你的本地表单。</p></div><div className="rounded bg-gold/10 p-4 text-sm leading-6 text-muted"><p className="font-semibold text-fg">确认是不可逆操作</p><p className="mt-2">确认后生成账户、期初库存和账务交易，并冻结完成摘要；同一初始化不能再次运行。</p></div></div><label className="mt-6 block text-sm font-medium text-fg">业务日期<input type="date" value={date} onChange={event => onDateChange(event.target.value)} className="mt-2 block w-full max-w-xs rounded border border-border px-3 py-2" />{businessDateError && <span className="mt-1 block text-xs text-red-700">{businessDateError}</span>}</label></section>;
}

export function Day1ReadonlySummary({ server, summaryRef }: { server: Day1State; summaryRef?: RefObject<HTMLDivElement | null> }) {
  const summary = completionSummaryViewModel(server.completion_summary);
  return <section ref={summaryRef} tabIndex={-1} className="w-full rounded-md border border-green-200 bg-white p-6 shadow-sm"><p className="text-[11px] font-bold uppercase tracking-[.12em] text-green-700">Day 1 · Completed</p><h1 className="mt-1 font-display text-3xl font-semibold">初始化已完成</h1><p className="mt-3 text-sm leading-6 text-muted">完成摘要已由后端冻结，不能编辑或再次确认。业务日期：{server.business_date || '—'} · 版本 v{server.version}</p><div className="mt-6 space-y-5"><div><h2 className="font-display text-xl font-semibold">账户</h2><div className="mt-2 overflow-x-auto"><table className="w-full min-w-[560px] text-left text-sm"><thead className="border-b border-border text-xs text-muted"><tr><th scope="col" className="py-2">名称</th><th scope="col">币种</th><th scope="col">原币</th><th scope="col">CNY 账面成本</th></tr></thead><tbody>{summary.accounts.map(account => <tr key={`${account.name}-${account.currency}`} className="border-b border-border"><td className="py-2">{account.name}</td><td>{account.currency}</td><td className="font-mono">{account.originalAmount}</td><td className="font-mono">¥ {account.bookCost}</td></tr>)}</tbody></table></div></div><div><h2 className="font-display text-xl font-semibold">库存</h2><div className="mt-2 overflow-x-auto"><table className="w-full min-w-[700px] text-left text-sm"><thead className="border-b border-border text-xs text-muted"><tr><th scope="col" className="py-2">雪茄</th><th scope="col">包装</th><th scope="col">数量</th><th scope="col">单位成本</th><th scope="col">总成本</th></tr></thead><tbody>{summary.inventory.map((item, index) => <tr key={`${item.cigar}-${index}`} className="border-b border-border"><td className="py-2">{item.cigar}</td><td>{item.boxSize} 支/盒</td><td>{item.quantity}（{item.boxQuantity} 盒 + {item.looseSticks} 支）</td><td className="font-mono">¥ {item.unitCost}</td><td className="font-mono">¥ {item.totalCost}</td></tr>)}</tbody></table></div></div><div className="grid gap-3 sm:grid-cols-4">{[['期初资本', summary.totals.openingCapital], ['净资产', summary.totals.totalNetAssets], ['账户合计', summary.totals.accountsTotal], ['库存合计', summary.totals.inventoryTotal]].map(([label, value]) => <div key={label} className="rounded bg-cream p-3"><p className="text-xs text-muted">{label}</p><p className="mt-1 font-mono text-sm">¥ {value}</p></div>)}</div></div><Link to="/accounting" className="mt-6 inline-flex rounded bg-accent px-4 py-2 text-sm font-semibold text-white">返回账务工作台</Link></section>;
}
