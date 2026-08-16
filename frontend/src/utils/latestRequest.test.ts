import { describe, expect, it, vi } from 'vitest';
import { invalidateLatestRequest, runLatestRequest } from './latestRequest';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

describe('latest request guard', () => {
  it('ignores an older response that finishes after a newer request', async () => {
    const sequence = { current: 0 };
    const first = deferred<string>();
    const second = deferred<string>();
    const onSuccess = vi.fn();
    const onSettled = vi.fn();

    const firstRun = runLatestRequest({
      sequence,
      request: () => first.promise,
      onSuccess,
      onSettled,
    });
    const secondRun = runLatestRequest({
      sequence,
      request: () => second.promise,
      onSuccess,
      onSettled,
    });

    second.resolve('new');
    await secondRun;
    first.resolve('old');
    await firstRun;

    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onSuccess).toHaveBeenCalledWith('new');
    expect(onSettled).toHaveBeenCalledTimes(1);
  });

  it('ignores a response after its owner invalidates the request', async () => {
    const sequence = { current: 0 };
    const pending = deferred<string>();
    const onSuccess = vi.fn();
    const run = runLatestRequest({ sequence, request: () => pending.promise, onSuccess });

    invalidateLatestRequest(sequence);
    pending.resolve('stale');
    await run;

    expect(onSuccess).not.toHaveBeenCalled();
  });
});
