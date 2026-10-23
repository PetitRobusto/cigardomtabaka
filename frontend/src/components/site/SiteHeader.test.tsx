// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SiteHeader, StaffDock } from './SiteHeader';
import { Storefront } from '../../storefront/Storefront';
import { backendPageFixture } from '../../storefront/fixture';

afterEach(cleanup);
const staff = { username: 'owner', is_staff: true, is_superuser: false };

describe('unified site navigation', () => {
  it('uses one header and retains the original footer for public store pages', () => {
    const { container } = render(<Storefront page={backendPageFixture} ageConfirmed />);
    expect(container.querySelectorAll('header')).toHaveLength(1);
    expect(container.querySelectorAll('footer')).toHaveLength(1);
    expect(screen.getByRole('search')).toBeTruthy();
    expect(screen.getByRole('img', { name: 'Habanos Specialist' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Telegram: +79296384878' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Management' })).toBeNull();
    expect(screen.queryByRole('navigation', { name: '移动应用导航' })).toBeNull();
  });

  it('groups management links and retains the staff mobile dock', () => {
    const { container } = render(<Storefront page={backendPageFixture} user={staff} ageConfirmed />);
    fireEvent.click(screen.getByRole('button', { name: 'Management' }));
    expect(container.querySelector('#site-management-menu a[href="/library"]')).toBeTruthy();
    expect(container.querySelector('#site-management-menu a[href="/inventory"]')).toBeTruthy();
    expect(screen.getByRole('navigation', { name: '移动应用导航' })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole('button', { name: 'Management' }), { key: 'Escape' });
    expect(container.querySelector('#site-management-menu')).toBeNull();
  });

  it('keeps internal management navigation in the app but uses a real link to the shop', () => {
    const navigate = vi.fn();
    const { container } = render(<SiteHeader user={staff} pathname="/inventory" onNavigate={navigate} storeLocale="ru" />);
    fireEvent.click(screen.getByRole('button', { name: '管理工具' }));
    fireEvent.click(screen.getByRole('link', { name: '资料库' }));
    expect(navigate).toHaveBeenCalledWith('/library');
    expect(container.querySelector('.site-brand')?.getAttribute('href')).toBe('/ru/');
    expect(screen.getByRole('search').getAttribute('action')).toBe('/ru/catalog');
  });

  it('omits staff controls and personal data from shared server-rendered store HTML', () => {
    const html = renderToString(<Storefront page={backendPageFixture} />);
    expect(html).not.toContain('site-staff-dock');
    expect(html).not.toContain('site-management-menu');
    expect(html).not.toContain(staff.username);
  });

  it('does not render a dock for an ordinary signed-in customer', () => {
    const { container } = render(<StaffDock user={{ ...staff, is_staff: false }} pathname="/" />);
    expect(container.innerHTML).toBe('');
  });
});
