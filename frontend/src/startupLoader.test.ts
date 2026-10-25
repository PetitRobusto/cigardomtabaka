// @vitest-environment jsdom

// @ts-expect-error Node types are intentionally absent from the browser app config.
import { readFileSync } from 'node:fs';
// @ts-expect-error Node types are intentionally absent from the browser app config.
import { createHash } from 'node:crypto';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { StartupLoader } from './components/shared/StartupLoader';
import { customerMessages } from './features/customer/messages';
import { siteStartupScriptUrl } from './components/site/siteAssets';
import { renderStorePage } from './storefront/render';
import { backendPageFixture } from './storefront/fixture';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const script = readFileSync('public/startup-loader.js', 'utf8');
const shells = ['index.html', '../templates/spa_index.html'].map((path) => ({ path, html: readFileSync(path, 'utf8') }));

type StartupWindow = Window & {
  CDTStartup?: { ready: () => void; fail: () => void; destroy: () => void };
};

function installLoader(appRoot = 'root', locale: 'zh' | 'en' | 'ru' = 'zh') {
  document.body.innerHTML = `${renderToStaticMarkup(createElement(StartupLoader, { locale }))}<div id="${appRoot}"><img data-startup-logo-target></div>`;
  window.eval(script);
  return document.querySelector<HTMLImageElement>('.cdt-startup__logo')!;
}

beforeEach(() => {
  vi.useFakeTimers();
  window.history.replaceState({}, '', '/');
  window.localStorage.clear();
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: () => ({ matches: false }),
  });
  window.requestAnimationFrame = callback => window.setTimeout(() => callback(performance.now()), 0);
  window.cancelAnimationFrame = timer => window.clearTimeout(timer);
  Element.prototype.animate = () => ({ finished: Promise.resolve() }) as unknown as Animation;
});

afterEach(() => {
  (window as StartupWindow).CDTStartup?.destroy();
  vi.useRealTimers();
  vi.restoreAllMocks();
  delete (window as StartupWindow).CDTStartup;
  document.body.innerHTML = '';
});

describe('startup logo fallback', () => {
  it('does not reveal the motion logo before it has loaded', () => {
    const logo = installLoader();

    expect(document.getElementById('startup-loader')?.dataset.logoReady).toBeUndefined();
    Object.defineProperty(logo, 'naturalWidth', { configurable: true, value: 640 });
    logo.dispatchEvent(new Event('load'));
    expect(document.getElementById('startup-loader')?.dataset.logoReady).toBe('true');
  });

  it('uses the static logo when the motion SVG fails and still opens the app', async () => {
    const logo = installLoader();
    logo.dispatchEvent(new Event('error'));
    expect(logo.getAttribute('src')).toContain('/static/frontend/logo-motion.webp');

    Object.defineProperty(logo, 'naturalWidth', { configurable: true, value: 640 });
    logo.dispatchEvent(new Event('load'));
    (window as StartupWindow).CDTStartup!.ready();
    await vi.runAllTimersAsync();

    expect(document.getElementById('startup-loader')).toBeNull();
    expect(document.body.classList.contains('cdt-starting')).toBe(false);
  });

  it('opens the app when both the motion image and static fallback fail', async () => {
    const logo = installLoader();
    logo.dispatchEvent(new Event('error'));
    expect(logo.getAttribute('src')).toContain('/static/frontend/logo-motion.webp');
    logo.dispatchEvent(new Event('error'));
    (window as StartupWindow).CDTStartup!.ready();
    await vi.runAllTimersAsync();

    expect(document.getElementById('startup-loader')).toBeNull();
    expect(document.body.classList.contains('cdt-starting')).toBe(false);
  });

  it('observes store-root and removes the overlay immediately for reduced motion', async () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: () => ({ matches: true }),
    });
    const logo = installLoader('store-root', 'ru');
    Object.defineProperty(logo, 'naturalWidth', { configurable: true, value: 640 });
    logo.dispatchEvent(new Event('load'));
    (window as StartupWindow).CDTStartup!.ready();
    await vi.runAllTimersAsync();

    expect(document.getElementById('startup-loader')).toBeNull();
    expect(document.body.classList.contains('cdt-starting')).toBe(false);
  });

  it('preserves the 2580 ms logo cycle and 400 ms docking animation', async () => {
    const animate = vi.fn(() => ({ finished: Promise.resolve() }) as unknown as Animation);
    Element.prototype.animate = animate;
    const logo = installLoader();
    Object.defineProperty(logo, 'naturalWidth', { configurable: true, value: 640 });
    logo.dispatchEvent(new Event('load'));
    (window as StartupWindow).CDTStartup!.ready();
    await vi.advanceTimersByTimeAsync(2579);
    expect(animate).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);

    expect(animate).toHaveBeenCalledWith(expect.any(Array), expect.objectContaining({ duration: 400 }));
  });
});

describe('server-rendered loader default', () => {
  it('invalidates cached startup scripts in all HTML entry points when the script changes', () => {
    const version = createHash('sha256').update(script).digest('hex').slice(0, 12);
    expect(siteStartupScriptUrl).toBe(`/static/frontend/startup-loader.js?v=${version}`);
    expect(shells[0].html).toContain(`src="${siteStartupScriptUrl}"`);
    expect(shells[1].html).toContain(`{% endif %}?v=${version}" defer></script>`);
    const html = renderStorePage({ page: backendPageFixture, origin: 'https://shop.example', assets: { js: [], css: [] } });
    expect(html).toContain(`src="${siteStartupScriptUrl}"`);
  });
  it.each(['zh', 'en', 'ru'] as const)('renders %s copy with the overlay hidden until JavaScript runs', locale => {
    const markup = renderToStaticMarkup(createElement(StartupLoader, { locale }));
    expect(markup).toContain(' hidden');
    expect(markup).toContain('/static/frontend/logo-opening-motion-v2.svg');
    expect(markup).toContain('/static/frontend/logo-motion.webp');
    expect(markup).not.toContain('/static/frontend/habanos-specialist.png');
    expect(markup).not.toContain('cdt-starting');
  });
});

describe('startup language matching', () => {
  function installShell(html: string, path: string, storefrontEnabled = false) {
    window.history.replaceState({}, '', path);
    const shell = new DOMParser().parseFromString(html, 'text/html');
    document.body.innerHTML = `${shell.getElementById('startup-loader')!.outerHTML}<div id="root"></div><script id="cdt-app-runtime-config" type="application/json">${JSON.stringify({ storefrontEnabled })}</script>`;
    expect(document.getElementById('startup-loader')!.hidden).toBe(true);
    expect(shell.querySelector('img[alt="Habanos Specialist"]')).toBeNull();
    expect(shell.querySelector('link[href*="habanos-specialist"]')).toBeNull();
    window.eval(script);
  }

  for (const shell of shells) {
    it.each(['zh', 'ru', 'en'] as const)(`localizes ${shell.path} introduction, slow loading and failure in %s`, async (locale) => {
      window.localStorage.setItem('cdt.customer.language', locale === 'zh' ? 'en' : 'zh');
      installShell(shell.html, locale === 'zh' ? '/catalog' : `/${locale}/catalog`);
      const text = customerMessages[locale];
      const root = document.getElementById('startup-loader')!;
      expect(root.hidden).toBe(false);
      expect(root.lang).toBe(locale === 'zh' ? 'zh-CN' : locale);
      expect(root.getAttribute('aria-label')).toBe(text.loading);
      expect(root.querySelector('.cdt-startup__status-label')!.textContent).toBe(text.loading);
      await vi.advanceTimersByTimeAsync(10_000);
      expect(root.querySelector('.cdt-startup__status-label')!.textContent).toBe(text.loading);
      const retry = root.querySelector<HTMLButtonElement>('.cdt-startup__retry')!;
      expect(retry.textContent).toBe(text.retry);
      expect(retry.hidden).toBe(false);
      (window as StartupWindow).CDTStartup!.fail();
      expect(root.querySelector('.cdt-startup__status-label')!.textContent).toBe(text.loadError);
      expect(root.getAttribute('aria-busy')).toBe('false');
    });
  }

  it.each(['zh', 'ru', 'en'] as const)('preserves the SSR %s locale over saved preferences and the URL', (locale) => {
    window.history.replaceState({}, '', '/en/');
    window.localStorage.setItem('cdt.customer.language', 'ru');
    installLoader('store-root', locale);
    expect(document.querySelector('.cdt-startup__status-label')!.textContent).toBe(customerMessages[locale].loading);
  });

  it('uses saved customer preferences for the legacy customer homepage', () => {
    window.localStorage.setItem('cdt.customer.language', 'ru');
    installShell(shells[0].html, '/');
    expect(document.getElementById('startup-loader')!.lang).toBe('ru');
  });

  it('uses Chinese for the enabled storefront root regardless of legacy preferences', () => {
    window.localStorage.setItem('cdt.customer.language', 'ru');
    installShell(shells[0].html, '/', true);
    expect(document.getElementById('startup-loader')!.lang).toBe('zh-CN');
  });

  it('falls back to a supported browser language when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Storage blocked'); });
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['fr-FR', 'ru-RU']);
    installShell(shells[0].html, '/brand/cohiba');
    expect(document.getElementById('startup-loader')!.lang).toBe('ru');
  });

  it('keeps management pages Chinese despite customer preferences or return URLs', () => {
    window.localStorage.setItem('cdt.customer.language', 'ru');
    installShell(shells[0].html, '/login?next=/en/catalog');
    expect(document.getElementById('startup-loader')!.lang).toBe('zh-CN');
  });
});
