import { isRetryableWriteError, type WriteRequestConfig } from '../../api/idempotency';
import { useAuthStore } from '../../store/authStore';

interface PendingIncome<T> { key: string; payload: T }
export const incomeCreateScope = 'record-other-income';
export const incomeReverseScope = (id: number) => `reverse-other-income-${id}`;
const storageKey = (scope: string) => `cdt:income-pending:v1:${encodeURIComponent(useAuthStore.getState().user?.username || 'session')}:${scope}`;
class IncomePreparationError extends Error {}
export const isRetryableIncomeWriteError = (error: unknown) => !(error instanceof IncomePreparationError) && isRetryableWriteError(error);

/** Per-operator recovery, including a closed/reopened tab. Only unresolved writes remain. */
export function pendingIncomeRequest<T>(scope: string): PendingIncome<T> | null {
  if (typeof window === 'undefined') return null;
  return readPending<T>(window.localStorage, storageKey(scope));
}

function readPending<T>(storage: Storage, location: string): PendingIncome<T> | null {
  const raw = storage.getItem(location);
  if (!raw) return null;
  const value = JSON.parse(raw) as PendingIncome<T>;
  if (!value || typeof value.key !== 'string' || !value.payload) throw new Error('待确认收入记录无法读取，请先核对原入账结果。');
  return value;
}

const fingerprint = (value: object) => JSON.stringify(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)));

export async function writeIncomeRequest<T, P extends object>(scope: string, payload: P, request: (config: WriteRequestConfig) => Promise<{ data: T }>): Promise<T> {
  // Capture identity before awaiting: a subsequent login must not clear another user's request.
  const location = storageKey(scope);
  let storage: Storage;
  let key: string;
  try {
    if (typeof window === 'undefined' || !navigator.locks || !crypto.randomUUID) throw new Error('当前浏览器无法安全登记收入，请使用新版浏览器并通过 HTTPS 访问。');
    storage = window.localStorage;
    // Only lock acquisition/persistence; concurrent retries may send the SAME key.
    key = await navigator.locks.request(location, () => {
      const pending = readPending<P>(storage, location);
      if (pending && fingerprint(pending.payload) !== fingerprint(payload)) throw new Error('还有一笔收入操作尚未确认，请先重试原内容，勿重新登记。');
      const chosen = pending?.key || `${scope}-${crypto.randomUUID()}`;
      storage.setItem(location, JSON.stringify({ key: chosen, payload }));
      return chosen;
    });
  } catch (error) {
    throw new IncomePreparationError(error instanceof Error ? error.message : '无法保存待确认收入，本次未发送。');
  }
  const clear = () => navigator.locks.request(location, () => {
    // Another tab may already have completed this request and started a new one.
    if (readPending<P>(storage, location)?.key === key) storage.removeItem(location);
  });
  try {
    const response = await request({ headers: { 'Idempotency-Key': key } });
    await clear();
    return response.data;
  } catch (error) {
    if (!isRetryableWriteError(error)) {
      await clear();
    }
    throw error;
  }
}
