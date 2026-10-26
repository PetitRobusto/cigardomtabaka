// @vitest-environment jsdom
import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import App, { StaffNotFoundRoute } from './App';
import { PageMetaProvider } from './contexts/PageMetaContext';
import { usePageMetaContext } from './contexts/usePageMetaContext';
import { notFoundCopy } from './components/site/notFoundCopy';

function CurrentPageTitle() {
  const { meta } = usePageMetaContext();
  return <output data-testid="page-title">{meta.title}</output>;
}

afterEach(() => {
  cleanup();
  document.head.replaceChildren();
  document.documentElement.lang = '';
  document.title = '';
});

it('renders a standalone localized not-found page and updates noindex page metadata', async () => {
  render(
    <MemoryRouter initialEntries={['/ru/unknown-workspace-route']}>
      <PageMetaProvider>
        <Routes><Route path="*" element={<StaffNotFoundRoute />} /></Routes>
        <CurrentPageTitle />
      </PageMetaProvider>
    </MemoryRouter>,
  );

  expect(await screen.findByRole('heading', { name: notFoundCopy.ru.heading })).toBeTruthy();
  await waitFor(() => expect(screen.getByTestId('page-title').textContent).toContain(notFoundCopy.ru.title));
  expect(document.documentElement.lang).toBe('ru');
  expect(document.querySelector('meta[name="robots"]')?.getAttribute('content')).toBe('noindex, nofollow');
  expect(document.title).toBe(notFoundCopy.ru.title);
  expect(screen.getByRole('main')).toBeTruthy();
});

it.each(['zh', 'ru', 'en'] as const)('keeps an unknown %s app route outside the shared header, footer and staff dock', async (locale) => {
  window.history.replaceState(null, '', `/${locale}/unknown-workspace-route`);
  const { container } = render(<App />);
  expect(await screen.findByRole('heading', { name: notFoundCopy[locale].heading })).toBeTruthy();
  expect(document.documentElement.lang).toBe(locale === 'zh' ? 'zh-CN' : locale);
  expect(document.title).toBe(notFoundCopy[locale].title);
  expect(container.querySelector('.not-found-header')).toBeTruthy();
  expect(container.querySelector('.not-found-footer')).toBeTruthy();
  expect(container.querySelector('.site-header, .site-footer, .staff-dock')).toBeNull();
  expect(container.querySelectorAll('main')).toHaveLength(1);
  window.history.replaceState(null, '', '/');
});
