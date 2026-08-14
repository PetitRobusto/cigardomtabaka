import { describe, expect, it } from 'vitest';
import {
  CONTEXT_TOUR_STEPS,
  CONTEXT_TOUR_GROUPS,
  GUIDE_TARGETS,
  missingTargetAction,
  tourStepsForRoute,
  completionForAction,
  guideActionPlan,
  isGuideExcludedRoute,
  resolveTourTarget,
  createGuideActionRunner,
} from './guideInteractions';

describe('guide interaction contracts', () => {
  it('persists welcome actions but keeps contextual actions local', () => {
    expect(guideActionPlan('finish', 'welcome')).toEqual({ requiresPersistence: true, close: true });
    expect(guideActionPlan('escape', 'welcome')).toEqual({ requiresPersistence: true, close: true });
    expect(guideActionPlan('finish', 'context')).toEqual({ requiresPersistence: false, close: true });
    expect(guideActionPlan('escape', 'context')).toEqual({ requiresPersistence: false, close: true });
  });

  it('completes and closes for close, skip, and finish', () => {
    expect(completionForAction('close')).toEqual({ complete: true, open: false });
    expect(completionForAction('skip')).toEqual({ complete: true, open: false });
    expect(completionForAction('finish')).toEqual({ complete: true, open: false });
  });

  it('keeps contextual tour ids attached to real sales page targets', () => {
    expect(CONTEXT_TOUR_GROUPS.sales.map(step => step.id)).toEqual(['sales-orders', 'sales-fulfillment']);
    expect(CONTEXT_TOUR_GROUPS.accounting.map(step => step.id)).toEqual(['accounting-reconciliation', 'accounting-profit']);
    expect(CONTEXT_TOUR_STEPS.every(step => step.target.startsWith('[data-guide="'))).toBe(true);
    expect(CONTEXT_TOUR_GROUPS.inventory.map(step => step.id)).toEqual(['inventory-summary']);
    expect(CONTEXT_TOUR_GROUPS.privnote.map(step => step.id)).toEqual(['privnote-create']);
    expect(CONTEXT_TOUR_GROUPS.prices.map(step => step.id)).toEqual(['prices-dashboard']);
    expect(CONTEXT_TOUR_STEPS.map(step => step.id)).toEqual(expect.arrayContaining(['sales-orders', 'accounting-profit']));
    expect(resolveTourTarget('sales-orders', ['[data-guide="sales-orders"]'])).toBe('[data-guide="sales-orders"]');
    expect(resolveTourTarget('missing', ['[data-guide="sales-orders"]'])).toBeNull();
  });

  it('only resolves a tour sequence for the current route', () => {
    expect(tourStepsForRoute('/sales', 'sales-orders').map(step => step.id)).toEqual(['sales-orders', 'sales-fulfillment']);
    expect(tourStepsForRoute('/accounting', 'accounting-reconciliation').map(step => step.id)).toEqual(['accounting-reconciliation', 'accounting-profit']);
    expect(tourStepsForRoute('/sales#accounting', 'accounting-reconciliation')).toEqual([]);
    expect(tourStepsForRoute('/prices', 'sales-orders')).toEqual([]);
    expect(tourStepsForRoute('/unknown', 'sales-orders')).toEqual([]);
  });

  it('registers every target used by contextual tours', () => {
    expect(Object.keys(GUIDE_TARGETS)).toEqual(expect.arrayContaining(['inventory-summary', 'privnote-create', 'prices-dashboard']));
    expect(new Set(Object.values(GUIDE_TARGETS)).size).toBe(Object.keys(GUIDE_TARGETS).length);
  });


  it('only advances after completion succeeds', async () => {
    let resolve: (value: unknown) => void = () => undefined;
    const complete = () => new Promise<unknown>(done => { resolve = done; });
    const runner = createGuideActionRunner(complete);
    const first = runner.run('finish');
    const second = runner.run('finish');
    expect(await second).toBe(false);
    resolve({ ok: true });
    expect(await first).toBe(true);
  });

  it('returns false and reports completion failures', async () => {
    const failure = new Error('保存失败');
    const errors: Error[] = [];
    const runner = createGuideActionRunner(async () => { throw failure; });
    expect(await runner.run('finish', error => errors.push(error))).toBe(false);
    expect(errors).toEqual([failure]);
    expect(runner.isBusy()).toBe(false);
  });

  it('does not complete when a required target is missing', () => {
    expect(missingTargetAction()).toEqual({ complete: false, open: false, error: '当前页面暂时无法播放本页引导，请刷新后重试。' });
  });

  it('excludes public and login routes from the authenticated controller', () => {
    expect(isGuideExcludedRoute('/p/example-token')).toBe(true);
    expect(isGuideExcludedRoute('/login')).toBe(true);
    expect(isGuideExcludedRoute('/sales')).toBe(false);
  });

  it('recognises Escape as a close action', () => {
    expect(completionForAction('escape')).toEqual({ complete: true, open: false });
  });
});
