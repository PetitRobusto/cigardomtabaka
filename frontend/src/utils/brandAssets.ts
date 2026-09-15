const base = import.meta.env.BASE_URL;
const moduleOrigin = new URL(import.meta.url).origin;

// During Django + Vite HMR, the document and JS module have different origins.
// Resolve public assets against the module host in-browser, and keep a relative
// URL fallback for file-based test environments.
export const brandLogoUrl = moduleOrigin === 'null'
  ? `${base}logo-opening.webp`
  : new URL(`${base}logo-opening.webp`, moduleOrigin).href;
