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
  tourStepRoute,
  canAdvanceTourStep,
} from './guideInteractions';
import { MANUAL_CHAPTERS } from './guideContent';


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

  it('keeps sales creation separate from later fulfillment and return actions', () => {
    expect(CONTEXT_TOUR_GROUPS.salesCreate.map(step => step.id)).toEqual([
      'sales-orders', 'sales-customer', 'sales-transport-payer', 'sales-transport-fee',
      'sales-item-search', 'sales-item-unit', 'sales-item-quantity', 'sales-item-price',
      'sales-order-note', 'sales-save-draft', 'sales-fulfillment', 'sales-confirm',
    ]);
    expect(CONTEXT_TOUR_GROUPS.salesCreate.filter(step => step.waitForTarget).map(step => step.id)).toEqual([
      'sales-item-unit', 'sales-item-quantity', 'sales-item-price', 'sales-fulfillment', 'sales-confirm',
    ]);
    expect(CONTEXT_TOUR_GROUPS.salesReturn.map(step => step.id)).toEqual([
      'sales-return', 'sales-return-date', 'sales-return-reason', 'sales-return-submit',
    ]);
    expect(CONTEXT_TOUR_STEPS.every(step => step.target.startsWith('[data-guide="'))).toBe(true);
    expect(CONTEXT_TOUR_STEPS.map(step => step.id)).toEqual(expect.arrayContaining(['sales-orders', 'accounting-profit']));
    expect(resolveTourTarget('sales-orders', ['[data-guide="sales-orders"]'])).toBe('[data-guide="sales-orders"]');
    expect(resolveTourTarget('missing', ['[data-guide="sales-orders"]'])).toBeNull();
  });

  it('only resolves a tour sequence for the current route', () => {
    expect(tourStepsForRoute('/sales', 'sales-orders').map(step => step.id)).toEqual(CONTEXT_TOUR_GROUPS.salesCreate.map(step => step.id));
    expect(tourStepsForRoute('/sales', 'sales-return').map(step => step.id)).toEqual(CONTEXT_TOUR_GROUPS.salesReturn.map(step => step.id));
    expect(tourStepsForRoute('/accounting', 'accounting-actions-exchange').map(step => step.id)).toEqual(CONTEXT_TOUR_GROUPS.accountingExchange.map(step => step.id));
    expect(tourStepsForRoute('/accounting', 'accounting-actions-exchange').map(step => step.id)).not.toContain('accounting-actions-purchase');
    expect(tourStepsForRoute('/accounting', 'accounting-purchase-reverse-date').map(step => step.id)).toEqual([
      'accounting-purchase-reverse-date', 'accounting-purchase-reverse-reason', 'accounting-purchase-reverse-submit',
    ]);
    expect(tourStepsForRoute('/sales#accounting', 'accounting-reconciliation')).toEqual([]);
    expect(tourStepsForRoute('/prices', 'sales-orders')).toEqual([]);
    expect(tourStepsForRoute('/unknown', 'sales-orders')).toEqual([]);
    expect(tourStepsForRoute('/prices/cigar/7/example', 'prices-history-filter').map(step => step.id)).toEqual(['prices-history-filter', 'prices-history-table', 'prices-history-chart']);
  });

  it('registers every target used by contextual tours', () => {
    expect(Object.keys(GUIDE_TARGETS)).toEqual(expect.arrayContaining(['inventory-summary', 'privnote-create', 'prices-dashboard']));
    expect(new Set(Object.values(GUIDE_TARGETS)).size).toBe(Object.keys(GUIDE_TARGETS).length);
  });

  it('resolves every Help section tour to its real application route', () => {
    const guidedSections = MANUAL_CHAPTERS.flatMap(chapter => chapter.sections)
      .filter(section => section.tourStepId);
    expect(guidedSections.length).toBeGreaterThan(10);
    for (const section of guidedSections) {
      expect(tourStepRoute(section.tourStepId!), section.title).toMatch(/^\//);
    }
    expect(tourStepRoute('inventory-summary')).toBe('/inventory');
    expect(tourStepRoute('accounting-actions-exchange')).toBe('/accounting');
    expect(tourStepRoute('missing-step')).toBeNull();
  });

  it('keeps every major Help tour multi-step and target selectors unique', () => {
    for (const [group, steps] of Object.entries(CONTEXT_TOUR_GROUPS)) {
      expect(steps.length, group).toBeGreaterThan(1);
      expect(new Set(steps.map(step => step.target)).size, group).toBe(steps.length);
    }
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

  it('allows the tour to continue after a completed action removes its button', () => {
    expect(canAdvanceTourStep(false, false)).toBe(false);
    expect(canAdvanceTourStep(true, false)).toBe(true);
    expect(canAdvanceTourStep(false, true)).toBe(true);
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
