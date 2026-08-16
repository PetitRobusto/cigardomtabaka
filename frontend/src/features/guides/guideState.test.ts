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
      expect.arrayContaining(['quickstart', 'day1', 'exchange-purchase', 'first-order', 'accounting', 'privnote']),
    );

    expect(getManualChapter('quickstart')?.route).toBe('/');
    expect(getManualChapter('inventory')?.route).toBe('/inventory');
    expect(getManualChapter('first-order')?.route).toBe('/sales');
    expect(getManualChapter('accounting')?.route).toBe('/accounting');
    expect(getManualChapter('privnote')?.route).toBe('/privnote');
    expect(getManualChapter('first-order')?.tourStepId).toBe('sales-orders');
    expect(getManualChapter('accounting')?.tourStepId).toBe('accounting-reconciliation');
  });

  it("documents the complete order workflow with stable section titles", () => {
    expect(getManualChapter("first-order")?.sections.map(section => section.title)).toEqual([
      "创建销售草稿", "添加现货", "设置人肉费", "确认并预留", "出库与收款",
    ]);
    const text = getManualChapter("first-order")?.sections.flatMap(section => section.paragraphs).join(" ") || "";
    expect(text).toContain("/sales");
    expect(text).toContain("客户承担");
    expect(text).toContain("公司承担");
    expect(text).toContain("一次性人民币收款");
  });

  it("keeps Day 1 readable while exposing the four required business flows", () => {
    expect(getManualChapter("day1")?.route).toBe("/accounting");
    expect(getManualChapter("day1")?.tourStepId).toBeUndefined();
    expect(getManualChapter("exchange-purchase")?.route).toBe("/accounting");
    expect(getManualChapter("accounting")?.sections.map(section => section.title)).toEqual([
      "记录实际人肉成本", "记录日常费用", "完成对账", "查看月利润", "合伙人分红",
    ]);
  });

  it("resolves canonical routes and does not mistake public privnote links for the staff page", () => {
    expect(getManualChapterForRoute("/accounting")?.id).toBe("accounting");
    expect(getManualChapterForRoute("/sales")?.id).toBe("first-order");
    expect(getManualChapterForRoute("/sales#accounting")).toBeUndefined();
    expect(getManualChapterForRoute("/p/example-token")).toBeUndefined();
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

  it('rejects a successful response with an incomplete guide summary', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ version: 3 }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchGuideStatus()).rejects.toThrow('引导状态返回格式错误');
  });

  it('uses the current CSRF cookie and same-origin credentials for status/complete/replay', async () => {
    const summary = {
      version: 3,
      auto_show_enabled: true,
      should_show: true,
      completed_version: 2,
      force_show_next_time: false,
    };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => summary });
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
