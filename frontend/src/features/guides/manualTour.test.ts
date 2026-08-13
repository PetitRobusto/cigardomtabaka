import { describe, expect, it } from 'vitest';
import { MANUAL_CHAPTERS } from './guideContent';
import { manualTourDecision, manualTourDestination } from './manualTour';

describe('manual tour navigation', () => {
  it('builds a local route state for a chapter tour', () => {
    const chapter = MANUAL_CHAPTERS.find(item => item.id === 'sales');
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
});
