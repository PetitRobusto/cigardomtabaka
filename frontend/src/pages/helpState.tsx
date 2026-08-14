import type { ReactNode } from "react";

export type Day1StatusState = { status: "loading" | "ready" | "error"; day1Status?: string; message?: string };
export const DAY1_STATUS_ERROR_MESSAGE = "状态无法确认，将安全返回账务工作台";

export function day1StatusLoadingState(): Day1StatusState { return { status: "loading" }; }
export function day1StatusReadyState(day1Status: string): Day1StatusState { return { status: "ready", day1Status }; }
export function day1StatusErrorState(): Day1StatusState { return { status: "error", message: DAY1_STATUS_ERROR_MESSAGE }; }
export function day1StatusNavigation(state: Day1StatusState): "/accounting" | "/accounting/day1" {
  return state.status === "ready" && state.day1Status === "completed" ? "/accounting/day1" : "/accounting";
}

export function Day1StatusNotice({ state, onRetry }: { state: Day1StatusState; onRetry: () => void }): ReactNode {
  if (state.status !== "error") return null;
  return <div role="status" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded border border-gold/40 bg-gold/10 px-4 py-3 text-sm text-fg"><span>{state.message || DAY1_STATUS_ERROR_MESSAGE}</span><button type="button" onClick={onRetry} className="rounded border border-border bg-white px-3 py-1.5 text-xs font-semibold">重试</button></div>;
}
