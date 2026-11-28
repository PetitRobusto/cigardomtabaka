// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { appRoute } from './appRoute';
import { StorefrontErrorBoundary } from './components/shared/PageError';

function BrokenPage(): never {
  throw new Error('private render details');
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState(null, '', '/');
  delete document.documentElement.dataset.cdtAppReady;
});

it.each(['/p/test-note', '/sales', '/login'])('handles an unexpected render error at %s', async path => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  const router = createMemoryRouter([{ ...appRoute, Component: BrokenPage }], { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  expect((await screen.findByRole('alert')).textContent).toContain('页面暂不可用');
  expect(screen.getByRole('button', { name: '重试' })).toBeTruthy();
  expect(document.documentElement.dataset.cdtAppReady).toBe('true');
  expect(document.body.textContent).not.toMatch(/private render details|Unexpected Application Error|Hey developer/);
  router.dispose();
});

it('shows the same localized fallback when the independent storefront crashes', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  window.history.replaceState(null, '', '/en/catalog');
  render(<StorefrontErrorBoundary><BrokenPage /></StorefrontErrorBoundary>);
  expect(screen.getByRole('alert').textContent).toContain('Page unavailable');
  expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
  expect(document.body.textContent).not.toContain('private render details');
});
