// @vitest-environment jsdom
import React, { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { storeCopy } from "./copy";
import { emptyFilters, type BrowseFilters } from "./browsing";
import { DimensionPresets, PriceRangeSlider } from "./NumericFilters";
import type { StoreLocale } from "./types";

afterEach(cleanup);

function Harness({ initial = emptyFilters, locale = "en", onSubmit }: { initial?: BrowseFilters; locale?: StoreLocale; onSubmit?: () => void }) {
  const [filters, setFilters] = useState(initial);
  return <form onSubmit={(event) => { event.preventDefault(); onSubmit?.(); }}>
    <DimensionPresets kind="length" filters={filters} onChange={setFilters} labels={storeCopy[locale]} locale={locale} />
    <DimensionPresets kind="ring" filters={filters} onChange={setFilters} labels={storeCopy[locale]} locale={locale} />
    <PriceRangeSlider filters={filters} onChange={setFilters} labels={storeCopy[locale]} locale={locale} />
    <output data-testid="active-bounds">{JSON.stringify({ ...filters })}</output>
  </form>;
}

describe("numeric storefront filters", () => {
  it("preserves custom URL values exactly and does not mark a custom dimension preset", () => {
    const initial: BrowseFilters = {
      ...emptyFilters,
      length_min: "100",
      length_max: "500",
      ring_min: "40.5",
      ring_max: "50",
      price_min: "2500.50",
      price_max: "5000.00",
    };
    const onChange = vi.fn();
    const { container, rerender } = render(<>
      <DimensionPresets kind="length" filters={initial} onChange={onChange} labels={storeCopy.en} locale="en" />
      <DimensionPresets kind="ring" filters={initial} onChange={onChange} labels={storeCopy.en} locale="en" />
      <PriceRangeSlider filters={initial} onChange={onChange} labels={storeCopy.en} locale="en" />
    </>);

    expect(container.querySelectorAll('input[type="number"]')).toHaveLength(0);
    expect(container.querySelector('[name="length_min"]')?.getAttribute("value")).toBe("100");
    expect(container.querySelector('[name="length_max"]')?.getAttribute("value")).toBe("500");
    expect(container.querySelector('[name="ring_min"]')?.getAttribute("value")).toBe("40.5");
    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("2500.50");
    expect(container.querySelector('[name="price_max"]')?.getAttribute("value")).toBe("5000.00");
    expect(container.querySelectorAll('.numeric-dimension--length [aria-pressed="true"]')).toHaveLength(0);
    expect(container.querySelector(".numeric-dimension--length .numeric-dimension__current")?.textContent).toContain("100 mm – 500 mm");

    const updated = { ...initial, brands: ["cohiba"] };
    rerender(<>
      <DimensionPresets kind="length" filters={updated} onChange={onChange} labels={storeCopy.en} locale="en" />
      <DimensionPresets kind="ring" filters={updated} onChange={onChange} labels={storeCopy.en} locale="en" />
      <PriceRangeSlider filters={updated} onChange={onChange} labels={storeCopy.en} locale="en" />
    </>);
    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("2500.50");
    expect(container.querySelector('[name="price_max"]')?.getAttribute("value")).toBe("5000.00");
  });

  it("clears all bounds with the any preset and applies closed adjacent dimension intervals", () => {
    const { container } = render(<Harness initial={{ ...emptyFilters, length_min: "100", length_max: "500" }} />);
    fireEvent.click(container.querySelector(".numeric-dimension--length .numeric-dimension__preset")!);
    expect(container.querySelector('[name="length_min"]')?.getAttribute("value")).toBe("");
    expect(container.querySelector('[name="length_max"]')?.getAttribute("value")).toBe("");
    expect(container.querySelector('.numeric-dimension--length button[aria-pressed="true"]')?.textContent).toBe("Any");

    fireEvent.click(screen.getByRole("button", { name: "120–145" }));
    expect(container.querySelector('[name="length_min"]')?.getAttribute("value")).toBe("120");
    expect(container.querySelector('[name="length_max"]')?.getAttribute("value")).toBe("145");
    expect(container.querySelector('.numeric-dimension--length button[aria-pressed="true"]')?.textContent).toBe("120–145");

    fireEvent.click(container.querySelector(".numeric-dimension--ring .numeric-dimension__preset:last-child")!);
    expect(container.querySelector('[name="ring_min"]')?.getAttribute("value")).toBe("54");
    expect(container.querySelector('[name="ring_max"]')?.getAttribute("value")).toBe("");
  });

  it("uses real hidden RUB bounds, an explicit unlimited upper end, and never submits on slider input", () => {
    const onSubmit = vi.fn();
    const { container } = render(<Harness onSubmit={onSubmit} />);
    const minimum = container.querySelector<HTMLInputElement>(".numeric-price__range--min")!;
    const maximum = container.querySelector<HTMLInputElement>(".numeric-price__range--max")!;

    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("");
    expect(container.querySelector('[name="price_max"]')?.getAttribute("value")).toBe("");
    expect(maximum.getAttribute("aria-valuetext")).toBe("No upper limit");
    expect(container.querySelector(".numeric-price__current")?.textContent).toContain("Any – No upper limit");
    expect(maximum.max).toBe("13");

    fireEvent.change(minimum, { target: { value: "1" } });
    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("5000");
    expect(container.querySelector('[name="price_max"]')?.getAttribute("value")).toBe("");
    expect(onSubmit).not.toHaveBeenCalled();
    expect(container.querySelector<HTMLInputElement>('[name="price_min"]')?.value).toBe("5000");
    expect(container.querySelector<HTMLInputElement>(".numeric-price__range--min")?.value).toBe("1");
  });

  it("inserts exact custom prices into stable stops and prevents the endpoints crossing", () => {
    const initial = { ...emptyFilters, price_min: "100", price_max: "500" };
    const { container } = render(<Harness initial={initial} />);
    const minimum = container.querySelector<HTMLInputElement>(".numeric-price__range--min")!;
    const maximum = container.querySelector<HTMLInputElement>(".numeric-price__range--max")!;

    expect(minimum.value).toBe("1");
    expect(maximum.value).toBe("2");
    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("100");
    expect(container.querySelector('[name="price_max"]')?.getAttribute("value")).toBe("500");

    fireEvent.change(minimum, { target: { value: "2" } });
    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("500");
    expect(container.querySelector('[name="price_max"]')?.getAttribute("value")).toBe("500");
    expect(container.querySelector<HTMLInputElement>(".numeric-price__range--min")?.value).toBe("2");
    expect(container.querySelector<HTMLInputElement>(".numeric-price__range--max")?.value).toBe("2");

    fireEvent.change(maximum, { target: { value: "3" } });
    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("500");
    expect(container.querySelector('[name="price_max"]')?.getAttribute("value")).toBe("5000");
  });

  it("keeps an existing lower bound above one million on its exact slider stop", () => {
    const initial = { ...emptyFilters, price_min: "2000000" };
    const { container } = render(<Harness initial={initial} />);
    const minimum = container.querySelector<HTMLInputElement>(".numeric-price__range--min")!;

    expect(minimum.value).toBe(minimum.max);
    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("2000000");
    expect(container.querySelector(".numeric-price__current")?.textContent).toContain("RUB 2,000,000");

    fireEvent.change(minimum, { target: { value: String(Number(minimum.value) - 1) } });
    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("1000000");

    fireEvent.change(minimum, { target: { value: String(Number(minimum.value) + 1) } });
    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("2000000");
  });

  it("pushes an above-one-million lower bound when the upper thumb crosses it", () => {
    const initial = { ...emptyFilters, price_min: "2000000" };
    const { container } = render(<Harness initial={initial} />);
    const maximum = container.querySelector<HTMLInputElement>(".numeric-price__range--max")!;

    fireEvent.change(maximum, { target: { value: String(Number(maximum.value) - 3) } });
    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("500000");
    expect(container.querySelector('[name="price_max"]')?.getAttribute("value")).toBe("500000");
    expect(container.querySelector<HTMLInputElement>(".numeric-price__range--min")?.value).toBe("11");
    expect(container.querySelector<HTMLInputElement>(".numeric-price__range--max")?.value).toBe("11");
  });

  it("turns an actively selected zero lower bound into unlimited and clears only price bounds", () => {
    const { container } = render(<Harness initial={{ ...emptyFilters, q: "BHK", brands: ["cohiba"], price_min: "5000", price_max: "20000" }} />);
    const minimum = container.querySelector<HTMLInputElement>(".numeric-price__range--min")!;
    fireEvent.change(minimum, { target: { value: "0" } });
    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("");

    fireEvent.click(screen.getByRole("button", { name: "Clear price range" }));
    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("");
    expect(container.querySelector('[name="price_max"]')?.getAttribute("value")).toBe("");
    expect(container.querySelector('[data-testid="active-bounds"]')?.textContent).toContain('"q":"BHK"');
    expect(container.querySelector('[data-testid="active-bounds"]')?.textContent).toContain('"brands":["cohiba"]');
    expect(screen.queryByRole("button", { name: "Clear price range" })).toBeNull();
  });

  it("keeps zero as an explicit URL bound and localizes the range controls", () => {
    const onChange = vi.fn();
    const { container, rerender } = render(<PriceRangeSlider filters={{ ...emptyFilters, price_min: "0" }} onChange={onChange} labels={storeCopy.zh} locale="zh" />);
    expect(container.querySelector('[name="price_min"]')?.getAttribute("value")).toBe("0");
    expect(container.querySelector(".numeric-price__current")?.textContent).toContain("₽0");
    expect(screen.getByRole("slider", { name: /价格 \(RUB\).*最低/ })).toBeTruthy();

    rerender(<PriceRangeSlider filters={emptyFilters} onChange={onChange} labels={storeCopy.ru} locale="ru" />);
    expect(screen.getByRole("slider", { name: /Цена \(RUB\).*От/ })).toBeTruthy();
    expect(container.querySelector(".numeric-price__current")?.textContent).toContain("Любой – Без верхней границы");
  });
});
