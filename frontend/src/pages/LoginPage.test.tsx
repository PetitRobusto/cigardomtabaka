// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it } from 'vitest';
import { PageMetaProvider } from '../contexts/PageMetaContext';
import LoginPage from './LoginPage';
import loginCopy from '../../login-page.json';

afterEach(() => { cleanup(); document.head.replaceChildren(); });

it('presents a branded account login, closed registration and matching page metadata', () => {
  const description = document.createElement('meta');
  description.name = 'description';
  document.head.append(description);
  render(<MemoryRouter initialEntries={['/login?next=/en/']}><PageMetaProvider><LoginPage /></PageMetaProvider></MemoryRouter>);
  expect(screen.getByRole('heading', { name: 'CigarDomTabaka' })).toBeTruthy();
  expect(screen.getByText(loginCopy.subtitle)).toBeTruthy();
  expect(screen.getByText('注册暂未开放')).toBeTruthy();
  expect(screen.queryByText('内部管理系统')).toBeNull();
  expect(screen.getByLabelText('用户名').getAttribute('autocomplete')).toBe('username');
  expect(screen.getByLabelText('密码').getAttribute('autocomplete')).toBe('current-password');
  expect(document.title).toBe(loginCopy.title);
  expect(description.content).toBe(loginCopy.description);
});
