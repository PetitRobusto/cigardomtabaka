import { describe, expect, it } from 'vitest';
import { MANUAL_CHAPTERS } from './guideContent';
import { manualTourDecision, manualTourDestination } from './manualTour';

describe('manual tour navigation', () => {
  it('builds a local route state for a chapter tour', () => {
    const chapter = MANUAL_CHAPTERS.find(item => item.id === 'first-order');
    expect(chapter).toBeDefined();
    expect(manualTourDestination(chapter!)).toEqual({
      route: '/sales',
      state: { guideTourId: 'sales-orders' },
    });
  });

  it('does not request a tour when the chapter has no target', () => {
    const chapter = { ...MANUAL_CHAPTERS[0], tourStepId: undefined };
    expect(manualTourDecision(chapter)).toEqual({ kind: 'unavailable', message: '本章暂无页面引导' });
  });

  it('keeps manual replay local and does not imply completion changes', () => {
    const chapter = MANUAL_CHAPTERS.find(item => item.id === 'inventory');
    expect(manualTourDecision(chapter!)).toEqual({
      kind: 'navigate',
      destination: { route: '/inventory', state: { guideTourId: 'inventory-summary' } },
    });
  });

  it('opens a completed Day 1 chapter as a read-only summary', () => {
    const chapter = MANUAL_CHAPTERS.find(item => item.id === 'day1');
    expect(manualTourDecision(chapter!, { day1Status: 'completed' })).toEqual({
      kind: 'readonly',
      destination: { route: '/accounting/day1', state: { guideTourId: 'day1-summary', readOnly: true } },
    });
  });

  it('opens the editable Day 1 wizard only before completion', () => {
    const chapter = MANUAL_CHAPTERS.find(item => item.id === 'day1');
    expect(manualTourDecision(chapter!, { day1Status: 'draft' })).toEqual({
      kind: 'navigate',
      destination: { route: '/accounting', state: {} },
    });
  });

  it('never models a write operation as part of manual navigation', () => {
    const chapter = MANUAL_CHAPTERS.find(item => item.id === 'first-order');
    const decision = manualTourDecision(chapter!);
    expect(decision.kind).toBe('navigate');
    if (decision.kind === 'navigate') {
      expect(decision.destination.route).toBe('/sales');
      expect(decision.destination.state).toEqual({ guideTourId: 'sales-orders' });
      expect(JSON.stringify(decision)).not.toMatch(/POST|PATCH|DELETE|confirm|reserve|ship|receive/i);
    }
  });
});
