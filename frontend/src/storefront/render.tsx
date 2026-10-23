import React from "react";
import { renderToString } from "react-dom/server";
import { Storefront } from "./Storefront";
import { storeStructuredData } from "./metadata";
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
  const canonical = absolute(origin, page.path);
  const defaultPath = page.alternates.find((alt) => alt.locale === "zh")?.path || page.path;
  const links = [`<link rel="alternate" hreflang="x-default" href="${escapeAttribute(absolute(origin, defaultPath))}">`];
  for (const alt of page.alternates) links.push(`<link rel="alternate" hreflang="${alt.locale === "zh" ? "zh-CN" : alt.locale}" href="${escapeAttribute(absolute(origin, alt.path))}">`);
  const scripts = assets.js.map((src) => `<script type="module" crossorigin src="${escapeAttribute(src)}"></script>`).join("");
  const styles = assets.css.map((href) => `<link rel="stylesheet" href="${escapeAttribute(href)}">`).join("");
  const imageUrl = page.product?.image_url || page.site.photo;
  const ogImage = imageUrl ? `<meta property="og:image" content="${escapeAttribute(absolute(origin, imageUrl))}">` : "";
  const htmlLang = page.locale === "zh" ? "zh-CN" : page.locale === "ru" ? "ru-RU" : "en";
  const rendered = renderToString(<Storefront page={page} />);
  const jsonLd = storeStructuredData(page, origin);
  const html = `<!doctype html><html lang="${htmlLang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(page.title)}</title><meta name="description" content="${escapeAttribute(page.description)}"><link rel="canonical" href="${escapeAttribute(canonical)}">${links.join("")}${styles}<meta property="og:type" content="website"><meta property="og:title" content="${escapeAttribute(page.title)}"><meta property="og:description" content="${escapeAttribute(page.description)}"><meta property="og:url" content="${escapeAttribute(canonical)}">${ogImage}<script type="application/ld+json">${safeJson(jsonLd)}</script></head><body><div id="store-root">${rendered}</div><script id="store-data" type="application/json">${safeJson({ page, origin })}</script>${scripts}</body></html>`;
  if (!/<h1\b/.test(html)) throw new Error("Store page requires an H1");
  return html;
}

export function renderStorePages(input: { pages: StorePageData[]; origin: string; assets: StoreAssets }): Array<{ path: string; html: string }> {
  if (!Array.isArray(input.pages) || typeof input.origin !== "string" || !input.assets) throw new Error("Expected pages, origin, and assets");
  return input.pages.map((page) => ({ path: page.path, html: renderStorePage({ page, origin: input.origin, assets: input.assets }) }));
}
