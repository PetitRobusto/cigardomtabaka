// @vitest-environment jsdom

// @ts-expect-error Node types are intentionally absent from the browser app config.
import { readFileSync } from 'node:fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const script = readFileSync('public/startup-loader.js', 'utf8');

type StartupWindow = Window & {
  CDTStartup?: { ready: () => void };
};

function installLoader() {
  document.documentElement.setAttribute('data-cdt-starting', 'true');
  document.body.className = 'cdt-starting';
  document.body.innerHTML = `
    <section id="startup-loader" data-phase="intro" aria-busy="true">
      <div class="cdt-startup__surface"></div>
      <img class="cdt-startup__logo" data-motion-src="/motion.svg" data-static-src="/static.webp">
      <p class="cdt-startup__status"><span class="cdt-startup__status-label">加载中</span></p>
      <button class="cdt-startup__retry" hidden></button>
    </section>
    <div id="root"></div>`;
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
  it('uses the static logo when the motion SVG fails and still opens the app', async () => {
    const logo = installLoader();
    logo.dispatchEvent(new Event('error'));
    expect(logo.getAttribute('src')).toContain('/static.webp');

    Object.defineProperty(logo, 'naturalWidth', { configurable: true, value: 640 });
    logo.dispatchEvent(new Event('load'));
    (window as StartupWindow).CDTStartup!.ready();
    await vi.runAllTimersAsync();

    expect(document.getElementById('startup-loader')).toBeNull();
    expect(document.body.classList.contains('cdt-starting')).toBe(false);
  });

  it('opens the app even when both logo files fail', async () => {
    const logo = installLoader();
    logo.dispatchEvent(new Event('error'));
    logo.dispatchEvent(new Event('error'));
    (window as StartupWindow).CDTStartup!.ready();
    await vi.runAllTimersAsync();

    expect(document.getElementById('startup-loader')).toBeNull();
    expect(document.body.classList.contains('cdt-starting')).toBe(false);
  });
});
