// @vitest-environment jsdom

import { cleanup, render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PageMetaProvider } from '../../contexts/PageMetaContext';
import { useAuthStore } from '../../store/authStore';
import AppLayout from './AppLayout';

beforeEach(() => {
  useAuthStore.setState({
    user: { username: 'staff', is_staff: true, is_superuser: false },
    isAuthenticated: true,
    isLoading: false,
    checkAuth: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
  });
});

afterEach(() => {
  cleanup();
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: true });
});

describe('AppLayout navigation', () => {
  it('keeps desktop and mobile app tabs selected on a nested route', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/accounting/day1']}>
        <PageMetaProvider><AppLayout><div>页面内容</div></AppLayout></PageMetaProvider>
      </MemoryRouter>,
    );

    const desktopCurrent = container.querySelector('nav[aria-label="应用导航"] a[aria-current="page"]');
    const mobileCurrent = container.querySelector('nav[aria-label="移动应用导航"] a[aria-current="page"]');
    expect(desktopCurrent?.textContent).toContain('账务');
    expect(mobileCurrent?.textContent).toContain('账务');
    expect(container.querySelector('nav[aria-label="应用导航"] a[href="/"]')?.getAttribute('aria-current')).toBeNull();
  });
});

