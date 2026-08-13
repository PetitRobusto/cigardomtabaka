import type { ManualChapter } from './guideContent';

export interface ManualTourDestination {
  route: string;
  state: { guideTourId: string };
}

export type ManualTourDecision =
  | { kind: 'navigate'; destination: ManualTourDestination }
  | { kind: 'unavailable'; message: string };

export function manualTourDestination(chapter: ManualChapter): ManualTourDestination | null {
  if (!chapter.tourStepId) return null;
  return { route: chapter.route, state: { guideTourId: chapter.tourStepId } };
}

export function manualTourDecision(chapter: ManualChapter): ManualTourDecision {
  const destination = manualTourDestination(chapter);
  return destination
    ? { kind: 'navigate', destination }
    : { kind: 'unavailable', message: '本章暂无页面引导' };
}
