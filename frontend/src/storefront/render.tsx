import React from "react";
import { renderToString } from "react-dom/server";
import { Storefront } from "./Storefront";
import { StartupLoader } from "../components/shared/StartupLoader";
import { storeOpenGraph, storePageTitle, storeStructuredData } from "./metadata";
import { siteFaviconUrl, siteStartupMotionUrl, siteStartupScriptUrl } from "../components/site/siteAssets";
import type { StoreAssets, StorePageData, StoreRenderInput } from "./types";

function absolute(origin: string, path: string): string {
  return new URL(path, origin).toString();
}

function safeJson(value: unknown): string {
  return JSON.stringify(value).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function escapeAttribute(value: string): string { return escapeHtml(value); }

export function renderStorePage(input: StoreRenderInput): string {
  const { page, origin, assets } = input;
  if (!page.title.trim()) throw new Error("Store page requires a title");
  if (!page.description.trim()) throw new Error("Store page requires a description");
  const title = storePageTitle(page);
  const canonical = absolute(origin, page.path);
  const defaultPath = page.alternates.find((alt) => alt.locale === "zh")?.path || page.alternates[0]?.path;
  const links = defaultPath ? [`<link rel="alternate" hreflang="x-default" href="${escapeAttribute(absolute(origin, defaultPath))}">`] : [];
  for (const alt of page.alternates) links.push(`<link rel="alternate" hreflang="${alt.locale === "zh" ? "zh-CN" : alt.locale}" href="${escapeAttribute(absolute(origin, alt.path))}">`);
  const scripts = assets.js.map((src) => `<script type="module" crossorigin src="${escapeAttribute(src)}"></script>`).join("");
  const styles = assets.css.map((href) => `<link rel="stylesheet" href="${escapeAttribute(href)}">`).join("");
  // The loader sets img.src after its deferred script runs; discover its image in the head.
  const startupPreload = `<link rel="preload" as="image" href="${escapeAttribute(siteStartupMotionUrl)}" type="image/svg+xml">`;
  const openGraph = storeOpenGraph(page, origin).map(([property, content]) => `<meta property="${escapeAttribute(property)}" content="${escapeAttribute(content)}">`).join("");
  const htmlLang = page.locale === "zh" ? "zh-CN" : page.locale === "ru" ? "ru-RU" : "en";
  const rendered = renderToString(<Storefront page={page} />);
  const startup = renderToString(<StartupLoader locale={page.locale} />);
  const robots = page.indexable === false ? '<meta name="robots" content="noindex, nofollow">' : '';
  const jsonLd = storeStructuredData(page, origin);
  const html = `<!doctype html><html lang="${htmlLang}"><head><meta charset="utf-8"><link rel="icon" type="image/png" sizes="96x96" href="${escapeAttribute(siteFaviconUrl)}"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(title)}</title><meta name="description" content="${escapeAttribute(page.description)}"><link rel="canonical" href="${escapeAttribute(canonical)}">${links.join("")}${robots}${styles}${startupPreload}${openGraph}<script type="application/ld+json">${safeJson(jsonLd)}</script></head><body>${startup}<div id="store-root">${rendered}</div><script id="store-data" type="application/json">${safeJson({ page, origin })}</script><script src="${escapeAttribute(siteStartupScriptUrl)}" defer></script>${scripts}</body></html>`;
  if (!/<h1\b/.test(html)) throw new Error("Store page requires an H1");
  return html;
}

export function renderStorePages(input: { pages: StorePageData[]; origin: string; assets: StoreAssets }): Array<{ path: string; html: string }> {
  if (!Array.isArray(input.pages) || typeof input.origin !== "string" || !input.assets) throw new Error("Expected pages, origin, and assets");
  return input.pages.map((page) => ({ path: page.path, html: renderStorePage({ page, origin: input.origin, assets: input.assets }) }));
}
