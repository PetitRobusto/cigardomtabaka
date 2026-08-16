import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { Day1StatusNotice } from "./helpState";
import { day1StatusErrorState, day1StatusNavigation, type Day1StatusState } from "./helpState.helpers";

describe("help Day1 status safety", () => {
  it("turns a failed status read into a retryable safe state", () => {
    const state = day1StatusErrorState();
    expect(state.message).toBe("状态无法确认，将安全返回账务工作台");
    expect(day1StatusNavigation(state)).toBe("/accounting");
    const html = renderToStaticMarkup(<Day1StatusNotice state={state} onRetry={vi.fn()} />);
    expect(html).toContain("状态无法确认，将安全返回账务工作台");
    expect(html).toContain("重试");
  });

  it("only allows the completed summary route", () => {
    const draft: Day1StatusState = { status: "ready", day1Status: "draft" };
    const completed: Day1StatusState = { status: "ready", day1Status: "completed" };
    expect(day1StatusNavigation(draft)).toBe("/accounting");
    expect(day1StatusNavigation(completed)).toBe("/accounting/day1");
  });
});
