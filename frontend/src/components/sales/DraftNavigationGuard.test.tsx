// @vitest-environment jsdom
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createMemoryRouter, Link, RouterProvider } from 'react-router-dom';
import DraftNavigationGuard from './DraftNavigationGuard';

const NativeRequest = globalThis.Request;
beforeEach(() => {
  // jsdom's AbortSignal belongs to a different realm than Node's fetch Request.
  // These navigation-only routes have no loaders to abort.
  vi.stubGlobal('Request', class extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) { super(input, { ...init, signal: undefined }); }
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('keeps edits on cancelled link navigation and lets explicit discard leave', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const router = createMemoryRouter([
    { path: '/sales', element: <><DraftNavigationGuard dirty busy={false} /><Link to="/inventory">库存</Link></> },
    { path: '/inventory', element: <p>库存页面</p> },
  ], { initialEntries: ['/sales'] });
  const screen = render(<RouterProvider router={router} />);
  fireEvent.click(screen.getByRole('link', { name: '库存' }));
  await waitFor(() => expect(confirm).toHaveBeenCalled());
  expect(router.state.location.pathname).toBe('/sales');
  confirm.mockReturnValue(true);
  fireEvent.click(screen.getByRole('link', { name: '库存' }));
  await screen.findByText('库存页面');
  router.dispose();
});

it('blocks browser back and unload while dirty, and never leaves while saving', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const router = createMemoryRouter([
    { path: '/sales', element: <DraftNavigationGuard dirty busy={false} /> },
    { path: '/previous', element: <p>上一页</p> },
  ], { initialEntries: ['/previous', '/sales'], initialIndex: 1 });
  render(<RouterProvider router={router} />);
  const event = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(event);
  expect(event.defaultPrevented).toBe(true);
  await router.navigate(-1);
  await waitFor(() => expect(confirm).toHaveBeenCalled());
  expect(router.state.location.pathname).toBe('/sales');
  cleanup(); router.dispose();
  confirm.mockClear().mockReturnValue(true);
  const saving = createMemoryRouter([
    { path: '/sales', element: <DraftNavigationGuard dirty={false} busy /> },
    { path: '/previous', element: <p>上一页</p> },
  ], { initialEntries: ['/sales'] });
  render(<RouterProvider router={saving} />);
  await saving.navigate('/previous');
  await waitFor(() => expect(saving.state.blockers.values().next().value?.state).toBe('unblocked'));
  expect(saving.state.location.pathname).toBe('/sales');
  expect(confirm).not.toHaveBeenCalled();
  saving.dispose();
});
