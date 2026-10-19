// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { PageMetaContext } from '../../contexts/pageMetaStore';
import Breadcrumb from './Breadcrumb';

afterEach(cleanup);

it('uses the current public route and language instead of stale brand metadata', () => {
  render(<MemoryRouter initialEntries={['/ru/contacts']}>
    <PageMetaContext.Provider value={{ meta: { title: '高希霸', breadcrumbs: [{ label: '首页', to: '/' }, { label: '高希霸' }] }, setMeta: vi.fn() }}>
      <Breadcrumb />
    </PageMetaContext.Provider>
  </MemoryRouter>);
  expect(screen.queryByText('高希霸')).toBeNull();
  expect(screen.getByText('Адрес и контакты')).not.toBeNull();
  expect(screen.getByRole('link', { name: /^Каталог/ }).getAttribute('href')).toBe('/ru/');
});
