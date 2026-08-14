import type { ManualChapter } from "./guideContent";

export interface ManualTourDestination {
  route: string;
  state: { guideTourId: string; readOnly?: boolean };
}

export interface ManualTourContext {
  day1Status?: string;
}

export type ManualTourDecision =
  | { kind: "navigate"; destination: ManualTourDestination }
  | { kind: "readonly"; destination: ManualTourDestination }
  | { kind: "unavailable"; message: string };

export function manualTourDestination(chapter: ManualChapter): ManualTourDestination | null {
  if (!chapter.tourStepId) return null;
  return { route: chapter.route, state: { guideTourId: chapter.tourStepId } };
}

export function manualTourDecision(chapter: ManualChapter, context: ManualTourContext = {}): ManualTourDecision {
  // Completed Day 1 can only open the frozen read-only summary; guides never write business data.
  if (chapter.id === "day1" && context.day1Status === "completed") {
    return { kind: "readonly", destination: { route: "/accounting/day1", state: { guideTourId: "day1-summary", readOnly: true } } };
  }
  const destination = manualTourDestination(chapter);
  if (chapter.id === "day1" && destination) return { kind: "navigate", destination: { ...destination, state: { ...destination.state, readOnly: false } } };
  return destination
    ? { kind: "navigate", destination }
    : { kind: "unavailable", message: "本章暂无页面引导" };
}
