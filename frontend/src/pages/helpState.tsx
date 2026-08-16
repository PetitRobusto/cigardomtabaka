import type { ReactNode } from "react";
import { DAY1_STATUS_ERROR_MESSAGE, type Day1StatusState } from './helpState.helpers';


export function Day1StatusNotice({ state, onRetry }: { state: Day1StatusState; onRetry: () => void }): ReactNode {
  if (state.status !== "error") return null;
  return <div role="status" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded border border-gold/40 bg-gold/10 px-4 py-3 text-sm text-fg"><span>{state.message || DAY1_STATUS_ERROR_MESSAGE}</span><button type="button" onClick={onRetry} className="rounded border border-border bg-white px-3 py-1.5 text-xs font-semibold">重试</button></div>;
}
