// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { act } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppSkeleton, DelayedAppSkeleton } from './AppSkeleton';

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('AppSkeleton', () => {
  it('renders a route-matched, accessible busy state', () => {
    render(<AppSkeleton path="/sales" label="订单加载中" />);
    expect(screen.getByRole('status').getAttribute('aria-busy')).toBe('true');
    expect(screen.getByText('订单加载中')).not.toBeNull();
    expect(document.querySelectorAll('.app-skeleton-block').length).toBeGreaterThan(20);
  });

  it('waits before showing the visual skeleton', () => {
    vi.useFakeTimers();
    render(<DelayedAppSkeleton path="/inventory" delay={140} />);
    expect(screen.queryByRole('status')).toBeNull();
    act(() => vi.advanceTimersByTime(139));
    expect(screen.queryByRole('status')).toBeNull();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByRole('status')).not.toBeNull();
  });
});
