import type { GuideSummary } from '../../api';

export const GUIDE_STEP_COUNT = 6;

export interface GuideUserContext {
  isAuthenticated: boolean;
  isStaff: boolean;
}

export interface GuideProgress {
  stepIndex: number;
  isOpen: boolean;
}

export function canShowGuide(
  summary: GuideSummary | null | undefined,
  user: GuideUserContext,
): boolean {
  return Boolean(user.isAuthenticated && user.isStaff && summary?.auto_show_enabled && summary.should_show);
}

export const isGuideEligible = canShowGuide;

export function createGuideProgress(stepIndex = 0): GuideProgress {
  return { stepIndex: clampStepIndex(stepIndex), isOpen: true };
}

export function nextGuideStep(stepIndex: number): number {
  return clampStepIndex(stepIndex + 1);
}

export function previousGuideStep(stepIndex: number): number {
  return clampStepIndex(stepIndex - 1);
}

export function isGuideComplete(stepIndex: number): boolean {
  return clampStepIndex(stepIndex) === GUIDE_STEP_COUNT - 1;
}

function clampStepIndex(stepIndex: number): number {
  if (!Number.isFinite(stepIndex)) return 0;
  return Math.min(Math.max(Math.trunc(stepIndex), 0), GUIDE_STEP_COUNT - 1);
}
