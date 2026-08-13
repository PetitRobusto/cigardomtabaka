import axios from 'axios';

const pendingKeys = new Map<string, string>();
let nextKey = 1;

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, entry]) => [key, stableValue(entry)]),
    );
  }
  return value;
}

function registryKey(scope: string, payload: unknown): string {
  return `${scope}:${JSON.stringify(stableValue(payload))}`;
}

export function acquireIdempotencyKey(scope: string, payload: unknown): string {
  const key = registryKey(scope, payload);
  const existing = pendingKeys.get(key);
  if (existing) return existing;

  const idempotencyKey = `${scope}-${Date.now()}-${nextKey++}`;
  pendingKeys.set(key, idempotencyKey);
  return idempotencyKey;
}

export function releaseIdempotencyKey(scope: string, payload: unknown): void {
  pendingKeys.delete(registryKey(scope, payload));
}

/** Whether an error is uncertain and should keep its pending idempotency key. */
export function isRetryableWriteError(error: unknown): boolean {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    if (status === undefined || status >= 500) return true;
    if (status === 409 && error.response?.data?.error === '请求正在处理中，请稍后重试') return true;
    return false;
  }
  return true;
}

export type WriteRequestConfig = { headers: { 'Idempotency-Key': string } };

export function writeWithIdempotency<T>(
  scope: string,
  payload: unknown,
  request: (config: WriteRequestConfig) => Promise<{ data: T }>,
): Promise<T> {
  const key = acquireIdempotencyKey(scope, payload);

  return request({ headers: { 'Idempotency-Key': key } }).then(
    response => {
      releaseIdempotencyKey(scope, payload);
      return response.data;
    },
    error => {
      if (!isRetryableWriteError(error)) releaseIdempotencyKey(scope, payload);
      throw error;
    },
  );
}
