import { useEffect, useRef, useState } from "react";
import type { BrowseFilters } from "./browsing";
import type { StoreLocale } from "./types";
import "./NumericFilters.css";

type NumericFilterProps = {
  filters: BrowseFilters;
  onChange: (filters: BrowseFilters) => void;
  labels: Record<string, string>;
  locale: StoreLocale;
};

type DimensionKind = "length" | "ring";
type BoundKey = "length_min" | "length_max" | "ring_min" | "ring_max" | "price_min" | "price_max";

const dimensionKeys: Record<DimensionKind, readonly [BoundKey, BoundKey]> = {
  length: ["length_min", "length_max"],
  ring: ["ring_min", "ring_max"],
};

const commonPriceStops = [0, 5_000, 10_000, 20_000, 30_000, 50_000, 70_000, 100_000, 150_000, 200_000, 300_000, 500_000, 1_000_000];
const priceBoundKeys = ["price_min", "price_max"] as const;

type DimensionPreset = {
  key: string;
  label: string;
  min?: string;
  max?: string;
};

function dimensionPresets(kind: DimensionKind, labels: Record<string, string>): DimensionPreset[] {
  const values = kind === "length"
    ? [{ min: undefined, max: "120" }, { min: "120", max: "145" }, { min: "145", max: "165" }, { min: "165", max: undefined }]
    : [{ min: undefined, max: "42" }, { min: "42", max: "48" }, { min: "48", max: "54" }, { min: "54", max: undefined }];
  return [
    { key: "any", label: labels.anyRange },
    ...values.map((range, index) => {
      const first = range.min === undefined ? labels.dimensionUpTo : range.max === undefined ? labels.dimensionFrom : undefined;
      const rangeLabel = first
        ? first.replace("{value}", (range.min ?? range.max)!)
        : `${range.min}–${range.max}`;
      return { key: `${kind}-${index}`, label: rangeLabel, min: range.min, max: range.max };
    }),
  ];
}

function isSameBound(actual: string | undefined, expected: string | undefined) {
  if (actual === undefined || expected === undefined) return actual === expected;
  return Number.isFinite(Number(actual)) && Number(actual) === Number(expected);
}

function dimensionDisplay(value: string | undefined, kind: DimensionKind, labels: Record<string, string>, endpoint: "min" | "max") {
  if (value === undefined) return endpoint === "min" ? labels.anyRange : labels.noUpperLimit;
  return kind === "length" ? `${value} mm` : value;
}

function HiddenBounds({ minName, maxName, minValue, maxValue }: { minName: BoundKey; maxName: BoundKey; minValue?: string; maxValue?: string }) {
  return <>
    <input type="hidden" name={minName} value={minValue ?? ""} readOnly />
    <input type="hidden" name={maxName} value={maxValue ?? ""} readOnly />
  </>;
}

export function DimensionPresets({ kind, filters, onChange, labels, locale }: NumericFilterProps & { kind: DimensionKind }) {
  const [minName, maxName] = dimensionKeys[kind];
  const presets = dimensionPresets(kind, labels);
  const currentMin = filters[minName];
  const currentMax = filters[maxName];
  const selectedKey = presets.find((preset) => isSameBound(currentMin, preset.min) && isSameBound(currentMax, preset.max))?.key;
  const title = kind === "length" ? `${labels.length} (mm)` : labels.ringGauge;
  const minText = dimensionDisplay(currentMin, kind, labels, "min");
  const maxText = dimensionDisplay(currentMax, kind, labels, "max");

  function selectPreset(preset: DimensionPreset) {
    onChange({ ...filters, [minName]: preset.min, [maxName]: preset.max });
  }

  return <fieldset className={`numeric-dimension numeric-dimension--${kind}`} lang={locale}>
    <legend>{title}</legend>
    <div className="numeric-dimension__current" aria-live="polite">
      <span>{labels.currentRange}</span>
      <strong>{minText} – {maxText}</strong>
    </div>
    <div className="numeric-dimension__presets" role="group" aria-label={title}>
      {presets.map((preset) => <button
        className="numeric-dimension__preset"
        type="button"
        key={preset.key}
        aria-pressed={selectedKey === preset.key}
        onClick={() => selectPreset(preset)}
      >{preset.label}</button>)}
    </div>
    <HiddenBounds minName={minName} maxName={maxName} minValue={currentMin} maxValue={currentMax} />
  </fieldset>;
}

function parsePrice(value: string | undefined): number | undefined {
  if (value === undefined || value.trim() === "") return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
}

function mergePriceStops(current: number[], filters: BrowseFilters): number[] {
  const extras = priceBoundKeys.flatMap((key) => {
    const value = parsePrice(filters[key]);
    return value === undefined || current.includes(value) ? [] : [value];
  });
  return [...new Set([...current, ...extras])].sort((a, b) => a - b);
}

function getPriceBounds(filters: BrowseFilters, finiteStops: number[]): [number, number] {
  const upperStops = [...finiteStops, null] as const;
  const lowerBound = parsePrice(filters.price_min);
  const upperBound = parsePrice(filters.price_max);
  const lowerIndex = lowerBound === undefined
    ? 0
    : Math.max(0, finiteStops.findIndex((stop) => stop === lowerBound) < 0
      ? finiteStops.filter((stop) => stop <= lowerBound).length - 1
      : finiteStops.findIndex((stop) => stop === lowerBound));
  const upperIndex = upperBound === undefined
    ? upperStops.length - 1
    : Math.max(0, upperStops.findIndex((stop) => stop === upperBound));
  return [Math.min(lowerIndex, finiteStops.length - 1), Math.max(upperIndex, 0)];
}

function priceLabel(value: string | undefined, locale: StoreLocale, labels: Record<string, string>, endpoint: "min" | "max") {
  if (value === undefined) return endpoint === "min" ? labels.anyRange : labels.noUpperLimit;
  const formatted = new Intl.NumberFormat(locale === "zh" ? "zh-CN" : locale === "ru" ? "ru-RU" : "en-US", {
    maximumFractionDigits: 2,
  }).format(Number(value));
  return locale === "zh" ? `₽${formatted}` : locale === "ru" ? `${formatted} ₽` : `RUB ${formatted}`;
}

function normalizePrice(value: number) {
  return String(value);
}

function pricePosition(index: number, lastIndex: number) {
  return lastIndex <= 0 ? 0 : index / lastIndex * 100;
}

export function PriceRangeSlider({ filters, onChange, labels, locale }: NumericFilterProps) {
  const [stops, setStops] = useState(() => mergePriceStops(commonPriceStops, filters));
  const [indices, setIndices] = useState<[number, number]>(() => getPriceBounds(filters, mergePriceStops(commonPriceStops, filters)));
  const indicesRef = useRef(indices);
  const expectedBoundsRef = useRef({ min: filters.price_min, max: filters.price_max });
  const lowerStops = stops;
  const unlimitedIndex = stops.length;
  const lowerMaxIndex = Math.max(0, lowerStops.length - 1);
  const lowerRaw = filters.price_min;
  const upperRaw = filters.price_max;
  const lowerLabel = priceLabel(lowerRaw, locale, labels, "min");
  const upperLabel = priceLabel(upperRaw, locale, labels, "max");
  const title = `${labels.priceRange} · ${labels.packagePrice}`;
  const left = pricePosition(indices[0], unlimitedIndex);
  const right = pricePosition(indices[1], unlimitedIndex);
  const ratio = unlimitedIndex > 0 ? lowerMaxIndex / unlimitedIndex : 1;
  const upperStops: Array<number | null> = [...stops, null];

  useEffect(() => {
    if (filters.price_min === expectedBoundsRef.current.min && filters.price_max === expectedBoundsRef.current.max) return;
    const nextStops = mergePriceStops(stops, filters);
    const nextIndices = getPriceBounds(filters, nextStops);
    expectedBoundsRef.current = { min: filters.price_min, max: filters.price_max };
    indicesRef.current = nextIndices;
    setStops(nextStops);
    setIndices(nextIndices);
  }, [filters, stops]);

  function updatePriceEndpoint(endpoint: "min" | "max", rawIndex: number) {
    const previous = indicesRef.current;
    const next: [number, number] = [...previous];
    const changes: Partial<Pick<BrowseFilters, "price_min" | "price_max">> = {};

    if (endpoint === "min") {
      const index = Math.max(0, Math.min(lowerMaxIndex, rawIndex));
      const selected = lowerStops[index];
      next[0] = index;
      changes.price_min = selected === 0 ? undefined : normalizePrice(selected);
      const currentMax = parsePrice(filters.price_max);
      if (currentMax !== undefined && selected > currentMax) {
        const pushedMaxIndex = stops.findIndex((value) => value === selected);
        next[1] = Math.max(0, pushedMaxIndex);
        changes.price_max = normalizePrice(selected);
      }
    } else {
      const index = Math.max(0, Math.min(unlimitedIndex, rawIndex));
      const selected = upperStops[index];
      next[1] = index;
      changes.price_max = selected === null ? undefined : normalizePrice(selected);
      const currentMin = parsePrice(filters.price_min);
      if (selected !== null && currentMin !== undefined && selected < currentMin) {
        const pushedMinIndex = lowerStops.findIndex((value) => value === selected);
        next[0] = Math.max(0, pushedMinIndex);
        changes.price_min = selected === 0 ? undefined : normalizePrice(selected);
      }
    }

    indicesRef.current = next;
    setIndices(next);
    const nextFilters = { ...filters, ...changes };
    expectedBoundsRef.current = { min: nextFilters.price_min, max: nextFilters.price_max };
    onChange(nextFilters);
  }

  function clearPriceRange() {
    const nextFilters = { ...filters, price_min: undefined, price_max: undefined };
    const nextIndices: [number, number] = [0, unlimitedIndex];
    indicesRef.current = nextIndices;
    expectedBoundsRef.current = { min: undefined, max: undefined };
    setIndices(nextIndices);
    onChange(nextFilters);
  }

  function inputValue(which: "min" | "max", event: React.ChangeEvent<HTMLInputElement>) {
    const parsed = Number(event.currentTarget.value);
    updatePriceEndpoint(which, Number.isFinite(parsed) ? parsed : 0);
  }

  const minValueText = lowerRaw === undefined ? labels.anyRange : lowerLabel;
  const maxValueText = upperRaw === undefined ? labels.noUpperLimit : upperLabel;

  return <fieldset className="numeric-price" lang={locale}>
    <legend>{labels.packagePrice}</legend>
    <div className="numeric-price__current" aria-live="polite">
      <span>{labels.currentRange}</span>
      <strong>{minValueText} – {maxValueText}</strong>
      {(lowerRaw !== undefined || upperRaw !== undefined) && <button className="numeric-price__clear" type="button" onClick={clearPriceRange}>{labels.clearPriceRange}</button>}
    </div>
    <div className="numeric-price__track" role="group" aria-label={title}>
      <div className="numeric-price__rail" aria-hidden="true">
        <span className="numeric-price__fill" style={{ left: `${left}%`, width: `${Math.max(0, right - left)}%` }} />
      </div>
      <input
        className="numeric-price__range numeric-price__range--min"
        type="range"
        min={0}
        max={lowerMaxIndex}
        step={1}
        value={Math.min(indices[0], lowerMaxIndex)}
        style={{ width: `calc(${ratio * 100}% + ${(1 - ratio) * 44}px)`, zIndex: indices[0] === indices[1] && indices[0] > lowerMaxIndex / 2 ? 5 : 3 }}
        aria-label={`${title} · ${labels.minimum}`}
        aria-valuetext={lowerLabel}
        onChange={(event) => inputValue("min", event)}
      />
      <input
        className="numeric-price__range numeric-price__range--max"
        type="range"
        min={0}
        max={unlimitedIndex}
        step={1}
        value={Math.min(indices[1], unlimitedIndex)}
        style={{ zIndex: indices[0] === indices[1] && indices[0] <= lowerMaxIndex / 2 ? 5 : 4 }}
        aria-label={`${title} · ${labels.maximum}`}
        aria-valuetext={upperLabel}
        onChange={(event) => inputValue("max", event)}
      />
    </div>
    <div className="numeric-price__scale" aria-hidden="true">
      <span>₽0</span><span>{labels.noUpperLimit}</span>
    </div>
    <div className="numeric-price__hidden">
      <HiddenBounds minName="price_min" maxName="price_max" minValue={lowerRaw} maxValue={upperRaw} />
    </div>
  </fieldset>;
}
