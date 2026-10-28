import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { ProductCard } from "./ProductDisplay";
import { homePath } from "./browsing";
import type { StoreLocale, StoreProduct } from "./types";
import "./ProductCarousel.css";

export function ProductCarousel({ id, products, locale, labels, title, href, linkLabel, sectionClass = "", linkClass = "" }: {
  id: string;
  products: StoreProduct[]; locale: StoreLocale; labels: Record<string, string>;
  title: string; href: string; linkLabel: string; sectionClass?: string; linkClass?: string;
}) {
  const items = products.slice(0, 12);
  const productKey = items.map((product) => product.id).join(",");
  const viewport = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ previous: false, next: items.length > 5 });

  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const measure = () => {
      const previous = element.scrollLeft > 1;
      const next = element.scrollWidth - element.clientWidth - element.scrollLeft > 1;
      setEdges((current) => current.previous === previous && current.next === next ? current : { previous, next });
    };
    element.scrollLeft = 0;
    const frame = requestAnimationFrame(measure);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    element.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      element.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
    };
  }, [productKey]);

  function move(direction: -1 | 1 | "start" | "end") {
    const element = viewport.current;
    const first = element?.firstElementChild as HTMLElement | null;
    if (!element || !first) return;
    const gap = Number.parseFloat(getComputedStyle(element).columnGap) || 0;
    const step = first.getBoundingClientRect().width + gap;
    const perView = Math.max(1, Math.floor((element.clientWidth + gap + 1) / step));
    const maximum = Math.max(0, element.scrollWidth - element.clientWidth);
    const target = direction === "start" ? 0 : direction === "end" ? maximum
      : (Math.round(element.scrollLeft / step) + direction * perView) * step;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    element.scrollTo({ left: Math.max(0, Math.min(maximum, target)), behavior: reducedMotion ? "instant" : "smooth" });
  }

  return <section className={`sec store-section store-carousel ${sectionClass}`} aria-labelledby={`${id}-title`}>
    <div className="sec-h">
      <h2 id={`${id}-title`}>{title}</h2>
      <div className="store-carousel__actions">
        {items.length > 0 && <div className="store-carousel__controls" hidden={!edges.previous && !edges.next}>
          <button type="button" className="store-carousel__arrow" aria-label={`${labels.carouselPrevious}: ${title}`} aria-controls={`${id}-items`} disabled={!edges.previous} onClick={() => move(-1)}><ChevronLeft aria-hidden="true" size={16} /></button>
          <button type="button" className="store-carousel__arrow" aria-label={`${labels.carouselNext}: ${title}`} aria-controls={`${id}-items`} disabled={!edges.next} onClick={() => move(1)}><ChevronRight aria-hidden="true" size={16} /></button>
        </div>}
        <a className={`store-carousel__all ${linkClass}`} href={href}>{linkLabel} →</a>
      </div>
    </div>
    {items.length > 0 ? <div ref={viewport} id={`${id}-items`} className="store-product-grid store-carousel__viewport" role="region" aria-labelledby={`${id}-title`} aria-roledescription={labels.carousel} tabIndex={0} onKeyDown={(event) => {
      if (event.target !== event.currentTarget) return;
      const direction = { ArrowLeft: -1, ArrowRight: 1, Home: "start", End: "end" }[event.key] as -1 | 1 | "start" | "end" | undefined;
      if (direction !== undefined) { event.preventDefault(); move(direction); }
    }}>
      {items.map((product) => <ProductCard key={product.id} product={product} locale={locale} labels={labels} from={homePath(locale)} />)}
    </div> : <p className="store-empty-note">{labels.noResults}</p>}
  </section>;
}
