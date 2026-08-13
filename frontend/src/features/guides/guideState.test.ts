import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  GUIDE_STEP_COUNT,
  canShowGuide,
  createGuideProgress,
  isGuideComplete,
  nextGuideStep,
  previousGuideStep,
} from './guideState';
import {
  GUIDE_STEPS,
  MANUAL_CHAPTERS,
  getManualChapter,
  getManualChapterForRoute,
} from './guideContent';
import { completeGuide, fetchGuideStatus, replayGuide } from '../../api';

describe('guide state', () => {
  it('shows a guide only for an authenticated staff member with an eligible summary', () => {
    const summary = {
      version: 2,
      auto_show_enabled: true,
      should_show: true,
      completed_version: 1,
      force_show_next_time: false,
    };

    expect(canShowGuide(summary, { isAuthenticated: true, isStaff: true })).toBe(true);
    expect(canShowGuide(summary, { isAuthenticated: false, isStaff: true })).toBe(false);
    expect(canShowGuide(summary, { isAuthenticated: true, isStaff: false })).toBe(false);
    expect(canShowGuide({ ...summary, auto_show_enabled: false }, { isAuthenticated: true, isStaff: true })).toBe(false);
  });

  it('keeps six welcome steps and clamps next/previous at both boundaries', () => {
    expect(GUIDE_STEP_COUNT).toBe(6);
    expect(GUIDE_STEPS).toHaveLength(6);
    expect(previousGuideStep(0)).toBe(0);
    expect(nextGuideStep(0)).toBe(1);
    expect(nextGuideStep(GUIDE_STEP_COUNT - 1)).toBe(GUIDE_STEP_COUNT - 1);
    expect(previousGuideStep(GUIDE_STEP_COUNT - 1)).toBe(GUIDE_STEP_COUNT - 2);
    expect(previousGuideStep(-100)).toBe(0);
    expect(nextGuideStep(100)).toBe(GUIDE_STEP_COUNT - 1);
    expect(nextGuideStep(Number.NaN)).toBe(0);
    expect(previousGuideStep(Number.POSITIVE_INFINITY)).toBe(0);
  });

  it('marks completion only at the final step', () => {
    expect(isGuideComplete(0)).toBe(false);
    expect(isGuideComplete(GUIDE_STEP_COUNT - 2)).toBe(false);
    expect(isGuideComplete(GUIDE_STEP_COUNT - 1)).toBe(true);
    expect(createGuideProgress()).toEqual({ stepIndex: 0, isOpen: true });
  });
});

describe('manual content', () => {
  it('contains the required chapters with actual application routes and tour mappings', () => {
    expect(MANUAL_CHAPTERS.map(chapter => chapter.id)).toEqual(
      expect.arrayContaining(['quickstart', 'inventory', 'sales', 'accounting', 'privnote']),
    );

    expect(getManualChapter('quickstart')?.route).toBe('/');
    expect(getManualChapter('inventory')?.route).toBe('/inventory');
    expect(getManualChapter('sales')?.route).toBe('/sales');
    expect(getManualChapter('accounting')?.route).toBe('/sales#accounting');
    expect(getManualChapter('privnote')?.route).toBe('/privnote');
    expect(getManualChapter('sales')?.tourStepId).toBe('sales-orders');
    expect(getManualChapter('accounting')?.tourStepId).toBe('accounting-reconciliation');
  });

  it('resolves hash routes and does not mistake public privnote links for the staff page', () => {
    expect(getManualChapterForRoute('/sales#accounting')?.id).toBe('accounting');
    expect(getManualChapterForRoute('/sales')?.id).toBe('sales');
    expect(getManualChapterForRoute('/p/example-token')).toBeUndefined();
  });
});

describe('guide API clients', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(globalThis, 'document', {
      configurable: true,
      value: { cookie: 'foo=bar; csrftoken=csrf-before' },
    });
  });

  it('surfaces the server error for a non-2xx JSON response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ error: 'Forbidden' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchGuideStatus()).rejects.toThrow('Forbidden');
  });

  it('uses a stable Chinese error for a non-JSON non-2xx response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => { throw new Error('unexpected html'); },
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchGuideStatus()).rejects.toThrow('引导状态加载失败');
  });

  it('uses the current CSRF cookie and same-origin credentials for status/complete/replay', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValue({ ok: true, json: async () => ({ version: 3 }) });
    vi.stubGlobal('fetch', fetchMock);

    await fetchGuideStatus();
    Object.defineProperty(document, 'cookie', { value: 'csrftoken=csrf-after' });
    await completeGuide();
    await replayGuide();

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/guides/status/', expect.objectContaining({
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': 'csrf-before' },
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/guides/complete/', expect.objectContaining({
      method: 'POST',
      credentials: 'same-origin',
      headers: expect.objectContaining({ 'X-CSRFToken': 'csrf-after' }),
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/guides/replay/', expect.objectContaining({
      method: 'POST',
      credentials: 'same-origin',
      headers: expect.objectContaining({ 'X-CSRFToken': 'csrf-after' }),
    }));
  });
});
