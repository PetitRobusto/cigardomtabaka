// @vitest-environment jsdom

// @ts-expect-error Node types are intentionally absent from the browser app config.
import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { StartupLoader } from './components/shared/StartupLoader';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const script = readFileSync('public/startup-loader.js', 'utf8');

type StartupWindow = Window & {
  CDTStartup?: { ready: () => void; fail: () => void };
};

function installLoader(appRoot = 'root', locale: 'zh' | 'en' | 'ru' = 'zh') {
  document.body.innerHTML = `${renderToStaticMarkup(createElement(StartupLoader, { locale }))}<div id="${appRoot}"><img data-startup-logo-target></div>`;
  window.eval(script);
  return document.querySelector<HTMLImageElement>('.cdt-startup__logo')!;
}

beforeEach(() => {
  vi.useFakeTimers();
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: () => ({ matches: false }),
  });
  window.requestAnimationFrame = callback => window.setTimeout(() => callback(performance.now()), 0);
  window.cancelAnimationFrame = timer => window.clearTimeout(timer);
  Element.prototype.animate = () => ({ finished: Promise.resolve() }) as unknown as Animation;
});

afterEach(() => {
  vi.useRealTimers();
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
  it.each(['zh', 'en', 'ru'] as const)('renders %s copy with the overlay hidden until JavaScript runs', locale => {
    const markup = renderToStaticMarkup(createElement(StartupLoader, { locale }));
    expect(markup).toContain(' hidden');
    expect(markup).toContain('/static/frontend/logo-opening-motion-v2.svg');
    expect(markup).toContain('/static/frontend/logo-motion.webp');
    expect(markup).toContain('/static/frontend/habanos-specialist.png');
    expect(markup).not.toContain('cdt-starting');
  });
});
