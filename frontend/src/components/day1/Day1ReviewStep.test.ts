import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { describe, expect, it } from 'vitest';
import { emptyDay1Draft } from '../../features/day1/day1State';
import Day1ReviewStep, { day1DialogFocusIndexForActiveElement, nextDay1DialogFocusIndex } from './Day1ReviewStep';

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
});
