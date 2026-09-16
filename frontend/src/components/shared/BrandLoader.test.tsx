// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BrandLoader } from './BrandLoader';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('BrandLoader', () => {
  it('keeps the motion logo hidden until the SVG has loaded', () => {
    const { container } = render(<BrandLoader />);
    const logo = container.querySelector<HTMLImageElement>('.cdt-loader__motion-logo')!;

    expect(logo.classList.contains('cdt-loader__motion-logo--ready')).toBe(false);
    fireEvent.load(logo);
    expect(logo.classList.contains('cdt-loader__motion-logo--ready')).toBe(true);
  });

  it('pairs the specialist mark with the loading status', () => {
    render(<BrandLoader />);

    expect(screen.getByRole('img', { name: 'Habanos Specialist' })).not.toBeNull();
    expect(screen.getByRole('status').textContent).toContain('莫斯科持证雪茄服务商');
    expect(document.querySelectorAll('.cdt-loading-dots i')).toHaveLength(3);
  });

  it('changes to the slow-loading message after ten seconds', () => {
    vi.useFakeTimers();
    render(<BrandLoader />);

    act(() => vi.advanceTimersByTime(10_000));
    expect(screen.getByRole('status').textContent).toContain('加载时间较长，请稍候');
    expect(screen.getByRole('button', { name: '重新加载' })).not.toBeNull();
  });
});
