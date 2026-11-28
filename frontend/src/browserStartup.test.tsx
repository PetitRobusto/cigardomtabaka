// @vitest-environment jsdom
import { act, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

afterEach(() => {
  document.body.replaceChildren();
  delete document.documentElement.dataset.cdtAppReady;
  vi.resetModules();
});

it.each([
  '<div id="store-root"></div><script id="store-data" type="application/json">{broken</script>',
  '<div id="store-root"></div>',
  '',
])('recovers when the storefront cannot hydrate its initial document', async markup => {
  document.body.innerHTML = markup;
  await act(async () => { await import('./storefront/client'); });
  expect(screen.getByRole('alert').textContent).toBe('页面暂不可用');
  expect(screen.getByRole('link', { name: '返回首页' }).getAttribute('href')).toBe('/');
  expect(document.documentElement.dataset.cdtAppReady).toBe('true');
  expect(document.body.textContent).not.toContain('SyntaxError');
});

it('shows the recovery page if the SPA shell has no mount element', async () => {
  await act(async () => { await import('./main'); });
  expect(screen.getByRole('heading', { name: '页面暂不可用' })).toBeTruthy();
  expect(screen.getByRole('button', { name: '重试' })).toBeTruthy();
});
