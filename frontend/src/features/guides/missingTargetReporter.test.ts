import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createMissingTargetReporter } from './missingTargetReporter';

describe('missing target reporter', () => {
  beforeEach(() => vi.useFakeTimers());
  it('waits for async page content and reports only once', () => {
    const onMissingTarget = vi.fn();
    const reporter = createMissingTargetReporter(onMissingTarget);
    reporter.report(); reporter.report();
    vi.advanceTimersByTime(1199);
    expect(onMissingTarget).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onMissingTarget).toHaveBeenCalledTimes(1);
    reporter.report();
    vi.advanceTimersByTime(1200);
    expect(onMissingTarget).toHaveBeenCalledTimes(1);
  });
  it('cancels a pending report when the target appears or the tour unmounts', () => {
    const onMissingTarget = vi.fn();
    const reporter = createMissingTargetReporter(onMissingTarget);
    reporter.report(); reporter.cancel();
    vi.advanceTimersByTime(1200);
    expect(onMissingTarget).not.toHaveBeenCalled();
  });
});
