import { useEffect, useMemo, useState } from 'react';
import type {
  DividendAction as DividendDraft,
  DividendConfirmPayload,
  DividendCreatePayload,
  DividendPreview,
  DividendUpdatePayload,
  FundAccount,
} from '../../types';
import {
  confirmDividend,
  createDividend,
  parseAccountingApiError,
  previewDividend,
  updateDividend,
} from '../../api';
import { initialActionState, reduceActionState, type ActionState } from '../../features/accounting/actionState';

export interface DividendActionProps {
  accounts: FundAccount[];
  draft?: DividendDraft | null;
  preview?: DividendPreview | null;
  warningAcknowledged?: boolean;
  businessDate?: string;
  onCreate?: (payload: DividendCreatePayload) => Promise<DividendDraft> | DividendDraft | unknown;
  onUpdate?: (id: number, payload: DividendUpdatePayload) => Promise<DividendDraft> | DividendDraft | unknown;
  onPreview?: (id: number) => Promise<DividendPreview> | DividendPreview | unknown;
  onConfirm?: (id: number, payload: DividendConfirmPayload) => Promise<DividendDraft> | DividendDraft | unknown;
  onChanged?: () => void;
}

export type DraftInput = {
  total: string;
  partnerA: string;
  partnerB: string;
  accountA: string;
  accountB: string;
  businessDate: string;
  note: string;
};

export function validateDividendDraft({
  draftDirty,
  accountA,
  accountB,
}: { draftDirty: boolean; accountA: number | string | null | undefined; accountB: number | string | null | undefined }) {
  if (draftDirty) return { ok: false, code: 'draft_dirty', message: '编辑已变更，请先保存分红草稿' };
  const idA = Number(accountA);
  const idB = Number(accountB);
  if (!Number.isInteger(idA) || idA <= 0 || !Number.isInteger(idB) || idB <= 0) {
    return { ok: false, code: 'account_required', message: '请选择两个人民币账户' };
  }
  if (idA === idB) return { ok: false, code: 'account_same', message: '两个合伙人必须选择不同的人民币账户' };
  return { ok: true as const };
}

export function dividendAccountOptions(accounts: FundAccount[], otherSelectedId: number | string | null | undefined) {
  const otherId = otherSelectedId == null || otherSelectedId === '' ? null : Number(otherSelectedId);
  return accounts
    .filter(account => account.currency === 'CNY' && account.is_active)
    .map(account => ({ account, disabled: account.id === otherId }));
}

function halfSplit(total: string): [string, string] {
  const text = String(total || "").trim();
  if (!/^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(text)) return ["", ""];
  const [whole, fraction = ""] = text.split(".");
  const cents = BigInt(whole) * 100n + BigInt((fraction + "00").slice(0, 2));
  const a = cents / 2n;
  const format = (value: bigint) => `${value / 100n}.${String(value % 100n).padStart(2, "0")}`;
  return [format(a), format(cents - a)];
}

function inputFromDraft(draft: DividendDraft | null | undefined, businessDate: string): DraftInput {
  const total = draft?.total_cny ?? '';
  const [a, b] = halfSplit(total);
  return {
    total,
    partnerA: draft?.partner_a_amount_cny ?? a,
    partnerB: draft?.partner_b_amount_cny ?? b,
    accountA: draft?.partner_a_account_id == null ? '' : String(draft.partner_a_account_id),
    accountB: draft?.partner_b_account_id == null ? '' : String(draft.partner_b_account_id),
    businessDate: draft?.business_date || businessDate,
    note: '',
  };
}

function sameDraftInput(left: DraftInput, right: DraftInput): boolean {
  return ['total', 'partnerA', 'partnerB', 'accountA', 'accountB', 'note'].every(key =>
    left[key as keyof DraftInput] === right[key as keyof DraftInput],
  );
}

function validMoney(value: string): boolean {
  return /^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(value.trim());
}

function failure(error: unknown) {
  const parsed = parseAccountingApiError(error);
  return { ...parsed, conflict: parsed.status === 409 };
}

function warningText(preview: DividendPreview | null): string | null {
  if (!preview?.warning) return null;
  if (typeof preview.warning === 'string') return preview.warning;
  return `本次分红 ${preview.warning.requested_cny} 元超过当前未分配利润 ${preview.warning.retained_earnings_cny} 元，请确认。`;
}

/** 分红必须经历编辑、预览和 warning acknowledgement，确认请求始终带版本。 */
export default function DividendAction({
  accounts,
  draft: incomingDraft = null,
  preview: incomingPreview = null,
  warningAcknowledged: incomingAcknowledged = false,
  businessDate = '',
  onCreate = payload => createDividend(payload),
  onUpdate = (id, payload) => updateDividend(id, payload),
  onPreview = id => previewDividend(id),
  onConfirm = (id, payload) => confirmDividend(id, payload),
  onChanged,
}: DividendActionProps) {
  const cnyAccounts = useMemo(() => accounts.filter(account => account.currency === 'CNY' && account.is_active), [accounts]);
  const [draft, setDraft] = useState<DividendDraft | null>(incomingDraft);
  const [preview, setPreview] = useState<DividendPreview | null>(incomingPreview);
  const [input, setInput] = useState<DraftInput>(() => inputFromDraft(incomingDraft, businessDate));
  const [persistedInput, setPersistedInput] = useState<DraftInput>(() => inputFromDraft(incomingDraft, businessDate));
  const [previewDraftVersion, setPreviewDraftVersion] = useState<number | null>(() => incomingPreview && incomingDraft ? incomingDraft.version : null);
  const [acknowledged, setAcknowledged] = useState(incomingAcknowledged);
  const [state, setState] = useState<ActionState>(() => initialActionState());

  useEffect(() => {
    const nextInput = inputFromDraft(incomingDraft, businessDate);
    setDraft(incomingDraft);
    setPreview(incomingPreview);
    setInput(nextInput);
    setPersistedInput(nextInput);
    setPreviewDraftVersion(incomingPreview && incomingDraft ? incomingDraft.version : null);
    setAcknowledged(incomingAcknowledged);
  }, [incomingDraft?.id, incomingDraft?.version, incomingPreview?.warning_fingerprint, businessDate, incomingAcknowledged]);

  const draftDirty = Boolean(draft && !sameDraftInput(input, persistedInput));
  const activeAccountA = cnyAccounts.some(account => account.id === Number(input.accountA));
  const activeAccountB = cnyAccounts.some(account => account.id === Number(input.accountB));
  // 两个下拉互相禁用对侧账户，避免切换后形成同账户选择。
  const accountOptionsA = dividendAccountOptions(cnyAccounts, input.accountB);
  const accountOptionsB = dividendAccountOptions(cnyAccounts, input.accountA);
  const accountValidation = validateDividendDraft({ draftDirty, accountA: input.accountA, accountB: input.accountB });
  const amountComplete = validMoney(input.total) && validMoney(input.partnerA) && validMoney(input.partnerB);
  const accountSelectionValid = activeAccountA && activeAccountB && Number(input.accountA) !== Number(input.accountB);
  const canSave = Boolean(draft && amountComplete && accountSelectionValid);
  const previewValidation = !draft
    ? { ok: false as const, code: 'draft_required', message: '请先创建分红草稿' }
    : (!amountComplete || !accountSelectionValid)
      ? { ok: false as const, code: 'draft_incomplete', message: !amountComplete ? '请完整填写分红金额' : '请选择两个不同的启用人民币账户' }
      : accountValidation;
  const busy = state.status === 'loading';

  const patchInput = (patch: Partial<DraftInput>) => setInput(previous => ({ ...previous, ...patch }));
  const run = async (operation: () => Promise<unknown> | unknown) => {
    setState(previous => reduceActionState(previous, { type: 'loading' }));
    try {
      const result = await operation();
      setState(previous => reduceActionState(previous, { type: 'success', result }));
      onChanged?.();
      return result;
    } catch (error) {
      const parsed = failure(error);
      setState(previous => reduceActionState(previous, {
        type: parsed.conflict ? 'conflict' : 'error', code: parsed.code, message: parsed.message,
      }));
      return null;
    }
  };

  const create = () => {
    if (!validMoney(input.total) || !input.businessDate) return;
    const payload: DividendCreatePayload = { total_cny: input.total, business_date: input.businessDate, note: input.note };
    void run(async () => {
      const result = await onCreate(payload);
      if (result && typeof result === 'object' && 'id' in result) {
        const saved = result as DividendDraft;
        const savedInput = inputFromDraft(saved, businessDate);
        savedInput.note = input.note;
        setDraft(saved);
        setInput(savedInput);
        setPersistedInput(savedInput);
        setPreviewDraftVersion(null);
      }
      return result;
    });
  };

  const update = () => {
    if (!draft || !canSave) return;
    const expectedVersion = draft.version;
    const payload: DividendUpdatePayload = {
      total_cny: input.total, partner_a_amount_cny: input.partnerA, partner_b_amount_cny: input.partnerB,
      partner_a_account_id: Number(input.accountA), partner_b_account_id: Number(input.accountB),
      expected_version: expectedVersion, note: input.note,
    };
    void run(async () => {
      const result = await onUpdate(draft.id, payload);
      if (result && typeof result === 'object' && 'id' in result) {
        const saved = result as DividendDraft;
        const savedInput = inputFromDraft(saved, businessDate);
        // serializer 当前不返回 note；保留刚刚成功提交的值作为本地持久化基线。
        savedInput.note = input.note;
        setDraft(saved);
        setInput(savedInput);
        setPersistedInput(savedInput);
        setPreview(null);
        setPreviewDraftVersion(null);
        setAcknowledged(false);
      }
      return result;
    });
  };

  const previewAction = () => {
    if (!draft || !previewValidation.ok) return;
    const persistedVersion = draft.version;
    void run(async () => {
      const result = await onPreview(draft.id);
      if (result && typeof result === 'object' && 'warning_fingerprint' in result) {
        setPreview(result as DividendPreview);
        setPreviewDraftVersion(persistedVersion);
        setAcknowledged(false);
      }
      return result;
    });
  };

  const confirm = () => {
    if (!draft || !preview || draftDirty || previewDraftVersion !== draft.version) return;
    const warning = warningText(preview);
    if (warning && !acknowledged) return;
    const payload: DividendConfirmPayload = {
      expected_version: draft.version,
      warning_fingerprint: preview.warning_fingerprint || '',
      warning_ack: warning ? acknowledged : true,
    };
    void run(async () => {
      const result = await onConfirm(draft.id, payload);
      if (result && typeof result === 'object' && 'id' in result) {
        const saved = result as DividendDraft;
        const savedInput = inputFromDraft(saved, businessDate);
        savedInput.note = input.note;
        setDraft(saved);
        setInput(savedInput);
        setPersistedInput(savedInput);
        setPreview(null);
        setPreviewDraftVersion(null);
      }
      return result;
    });
  };

  const warning = warningText(preview);
  const previewIsCurrent = Boolean(preview && draft && !draftDirty && previewDraftVersion === draft.version);
  const showAccountSame = Boolean(input.accountA && input.accountB && Number(input.accountA) === Number(input.accountB));
  return (
    <section tabIndex={-1} data-guide="accounting-actions-dividend" className="rounded-2xl border border-[#E8E0D6] bg-[#FAF8F5] p-5 text-[#2C2416]">
      <div className="mb-4 flex items-start justify-between gap-3"><div><p className="text-xs uppercase tracking-[0.18em] text-[#8A7E6E]">Dividend</p><h2 className="text-xl font-semibold">合伙人分红</h2><p className="mt-1 text-sm text-[#8A7E6E]">两位合伙人分别从不同的人民币账户领取。</p></div><span className="rounded-full bg-[#F5EFE8] px-3 py-1 text-xs text-[#7A1F2E]">CNY</span></div>
      {!draft ? (
        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"><label className="text-sm">分红总额<input inputMode="decimal" value={input.total} onChange={event => patchInput({ total: event.target.value })} placeholder="0.00" className="mt-1 block w-full rounded-lg border border-[#E8E0D6] p-2" /></label><label className="text-sm">业务日期<input type="date" value={input.businessDate} onChange={event => patchInput({ businessDate: event.target.value })} className="mt-1 block w-full rounded-lg border border-[#E8E0D6] p-2" /></label><button type="button" disabled={busy || !input.total || !input.businessDate} onClick={create} className="rounded-lg bg-[#7A1F2E] px-3 py-2 text-sm text-white disabled:opacity-50">{busy ? '处理中…' : '创建分红草稿'}</button></div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3"><label className="text-sm">总额<input inputMode="decimal" value={input.total} onChange={event => patchInput({ total: event.target.value })} className="mt-1 block w-full rounded-lg border border-[#E8E0D6] p-2" /></label><label className="text-sm">合伙人 A<input inputMode="decimal" value={input.partnerA} onChange={event => patchInput({ partnerA: event.target.value })} className="mt-1 block w-full rounded-lg border border-[#E8E0D6] p-2" /></label><label className="text-sm">合伙人 B<input inputMode="decimal" value={input.partnerB} onChange={event => patchInput({ partnerB: event.target.value })} className="mt-1 block w-full rounded-lg border border-[#E8E0D6] p-2" /></label></div>
          <div className="grid gap-3 sm:grid-cols-2"><label className="text-sm">合伙人 A 人民币账户<select value={input.accountA} onChange={event => patchInput({ accountA: event.target.value })} className="mt-1 block w-full rounded-lg border border-[#E8E0D6] bg-white p-2"><option value="">选择账户</option>{accountOptionsA.map(({ account, disabled }) => <option key={account.id} value={account.id} disabled={disabled}>{account.name}</option>)}</select></label><label className="text-sm">合伙人 B 人民币账户<select value={input.accountB} onChange={event => patchInput({ accountB: event.target.value })} className="mt-1 block w-full rounded-lg border border-[#E8E0D6] bg-white p-2"><option value="">选择账户</option>{accountOptionsB.map(({ account, disabled }) => <option key={account.id} value={account.id} disabled={disabled}>{account.name}</option>)}</select></label></div>
          {showAccountSame && <p role="alert" className="text-sm text-[#7A1F2E]">两个合伙人必须选择不同的人民币账户</p>}
          {!amountComplete && <p role="alert" className="text-sm text-[#7A1F2E]">请完整填写分红总额及两位合伙人金额</p>}
          {draftDirty && <p role="status" className="text-sm text-[#7A1F2E]">编辑后请先保存分红草稿，再预览或确认。</p>}
          <div className="flex flex-wrap gap-2"><button type="button" disabled={busy || !canSave} onClick={update} className="rounded-lg border border-[#7A1F2E] px-3 py-2 text-sm text-[#7A1F2E] disabled:opacity-50">{busy ? '处理中…' : '保存分红编辑'}</button><button type="button" disabled={busy || !previewValidation.ok} onClick={previewAction} className="rounded-lg bg-[#7A1F2E] px-3 py-2 text-sm text-white disabled:opacity-50">预览</button></div>
          {preview && previewIsCurrent && <div className="rounded-xl border border-[#E8E0D6] bg-white p-3 text-sm"><div className="grid gap-2 sm:grid-cols-3"><span>未分配利润：{preview.retained_earnings_cny || '—'} 元</span><span>申请分红：{preview.requested_cny || '—'} 元</span><span>提示指纹：{preview.warning_fingerprint || '—'}</span></div>{warning && <label className="mt-3 flex items-start gap-2 text-[#7A1F2E]"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} />我已确认：{warning}</label>}<button type="button" disabled={busy || draftDirty || !previewIsCurrent || Boolean(warning && !acknowledged)} onClick={confirm} className="mt-3 rounded-lg bg-[#7A1F2E] px-3 py-2 text-sm text-white disabled:opacity-50">确认分红</button></div>}
        </div>
      )}
      {state.status === 'success' && <p role="status" className="mt-3 text-sm text-green-700">已提交</p>}
      {(state.status === 'error' || state.status === 'conflict') && <p role="alert" className="mt-3 text-sm text-[#7A1F2E]">{state.status === 'conflict' ? '数据已被另一位经营者更新，请刷新后重试。' : state.error?.message}</p>}
    </section>
  );
}
