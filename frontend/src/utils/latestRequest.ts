export interface LatestRequestSequence {
  current: number;
}

interface LatestRequestOptions<T> {
  sequence: LatestRequestSequence;
  request: () => Promise<T>;
  onSuccess: (value: T) => void;
  onError?: (error: unknown) => void;
  onSettled?: () => void;
}

/** Apply only the newest async result so stale responses cannot overwrite current UI state. */
export async function runLatestRequest<T>({
  sequence,
  request,
  onSuccess,
  onError,
  onSettled,
}: LatestRequestOptions<T>): Promise<void> {
  const requestId = ++sequence.current;
  try {
    const result = await request();
    if (requestId !== sequence.current) return;
    onSuccess(result);
  } catch (error) {
    if (requestId !== sequence.current) return;
    onError?.(error);
  } finally {
    if (requestId === sequence.current) onSettled?.();
  }
}

/** Invalidate pending work during effect cleanup or route changes. */
export function invalidateLatestRequest(sequence: LatestRequestSequence): void {
  sequence.current += 1;
}
