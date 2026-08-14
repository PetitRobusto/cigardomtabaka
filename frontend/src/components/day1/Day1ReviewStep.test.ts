import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { emptyDay1Draft } from '../../features/day1/day1State';
import Day1ReviewStep, { createDay1DialogFocusController, day1DialogFocusIndexForActiveElement, nextDay1DialogFocusIndex, restoreDay1DialogTriggerFocus } from './Day1ReviewStep';

describe('Day1 confirmation dialog keyboard loop', () => {
  it('wraps Tab and Shift+Tab within dialog focusable controls', () => {
    expect(nextDay1DialogFocusIndex(2, 3, false)).toBe(0);
    expect(nextDay1DialogFocusIndex(0, 3, true)).toBe(2);
    expect(nextDay1DialogFocusIndex(1, 3, false)).toBe(2);
  });

  it('returns the first or last control when focus entered from outside the modal', () => {
    // Mouse or programmatic focus outside still re-enters at the correct modal edge.
    expect(day1DialogFocusIndexForActiveElement(-1, 3, false)).toBe(0);
    expect(day1DialogFocusIndexForActiveElement(-1, 3, true)).toBe(2);
  });

  it('renders a real aria modal confirmation dialog', () => {
    // The semantic contract is required even where full DOM interaction is unavailable.
    const html = renderToStaticMarkup(
      createElement(Day1ReviewStep, { draft: emptyDay1Draft('2026-08-14'), errors: [], confirmationOpen: true, acknowledged: false }),
    );
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
  });

  it('captures Tab in both directions and reclaims focus from outside the dialog', () => {
    // Exercise the same controller attached by the production dialog effect.
    const first = { tabIndex: 0, hasAttribute: () => false, focus: vi.fn() } as unknown as HTMLElement;
    const second = { tabIndex: 0, hasAttribute: () => false, focus: vi.fn() } as unknown as HTMLElement;
    const outside = {} as HTMLElement;
    const dialog = { querySelectorAll: () => [first, second], contains: (target: Node) => target === first || target === second } as unknown as HTMLElement;
    let activeElement: HTMLElement | null = first;
    const listeners = new Map<string, EventListener>();
    const documentRef = {
      get activeElement() { return activeElement; },
      addEventListener: (type: string, listener: EventListener, capture: boolean) => { expect(capture).toBe(true); listeners.set(type, listener); },
      removeEventListener: (type: string) => { listeners.delete(type); },
    } as unknown as Document;
    const detach = createDay1DialogFocusController(dialog, documentRef).attach();
    const tab = listeners.get('keydown')!;
    const forward = { key: 'Tab', shiftKey: false, preventDefault: vi.fn() } as unknown as KeyboardEvent;
    tab(forward);
    expect(forward.preventDefault).toHaveBeenCalled();
    expect(second.focus).toHaveBeenCalled();
    activeElement = second;
    const reverse = { key: 'Tab', shiftKey: true, preventDefault: vi.fn() } as unknown as KeyboardEvent;
    tab(reverse);
    expect(first.focus).toHaveBeenCalled();
    listeners.get('focusin')!({ target: outside } as unknown as FocusEvent);
    expect(first.focus).toHaveBeenCalledTimes(2);
    detach();
    expect(listeners).toHaveLength(0);
  });

  it('restores the trigger only when the confirmation dialog closes', () => {
    // Closing must return keyboard focus without stealing it during ordinary renders.
    const focus = vi.fn();
    restoreDay1DialogTriggerFocus(true, false, () => ({ focus } as unknown as HTMLElement));
    expect(focus).toHaveBeenCalledTimes(1);
    restoreDay1DialogTriggerFocus(false, false, () => ({ focus } as unknown as HTMLElement));
    restoreDay1DialogTriggerFocus(true, true, () => ({ focus } as unknown as HTMLElement));
    expect(focus).toHaveBeenCalledTimes(1);
  });

  it('falls back to the completed summary when confirmation unmounts its trigger', () => {
    // Successful confirmation replaces the trigger, so the frozen summary receives focus.
    const summary = { focus: vi.fn() };
    restoreDay1DialogTriggerFocus(true, false, () => null, () => summary as unknown as HTMLElement);
    expect(summary.focus).toHaveBeenCalledTimes(1);
  });
});
