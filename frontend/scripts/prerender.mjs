import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { renderPage } from '../.seo-build/entry-server.js';

const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const sha = value => createHash('sha256').update(value).digest('hex');
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const json = value => JSON.stringify(value).replaceAll('<', '\\u003c').replaceAll('>', '\\u003e').replaceAll('&', '\\u0026').replaceAll('\u2028', '\\u2028').replaceAll('\u2029', '\\u2029');
const contentSource = await read('../site-content.json');
const content = JSON.parse(contentSource);
const pagesSource = await read('../seo/pages.json');
const pages = JSON.parse(pagesSource);
const catalog = JSON.parse(await read('../seo/catalog.json'));
if (catalog.contentDigest !== sha(contentSource)) throw new Error('Public content changed. Run export_public_catalog before building.');
const template = await read('../../static/frontend/index.html');
const output = new URL('../../.seo-rendered/', import.meta.url);
const generated = [];

for (const page of pages) {
  const result = await renderPage(page, catalog);
  result.html = '';
  for await (const chunk of result.prelude) result.html += chunk.toString();
  if (!result.html.includes('<h1') || /<template id="B:|<div hidden|Switched to client rendering/.test(result.html)) throw new Error(`Missing static content: ${page.path}`);
  const alternateTags = Object.entries(page.alternates).map(([locale, path]) => `<link rel="alternate" hreflang="${locale}" href="${escape(content.origin + path)}">`).join('');
  const head = `<meta name="robots" content="index,follow"><link rel="canonical" href="${escape(content.origin + page.path)}">${alternateTags}`
    + (page.alternates['zh-CN'] ? `<link rel="alternate" hreflang="x-default" href="${escape(content.origin + page.alternates['zh-CN'])}">` : '')
    + `<script type="application/ld+json" data-seo-structured="true">${json(result.structured)}</script>`;
  const html = template
    .replace(/<html[^>]*>/, `<html lang="${page.locale}" data-cdt-prerendered="true">`)
    .replace(/<title>[\s\S]*?<\/title>/, `<title>${escape(page.title)}</title>`)
    .replace(/<meta name="description"[^>]*>/, `<meta name="description" content="${escape(page.description)}">`)
    .replace('</head>', `${head}</head>`)
    .replace('<body class="cdt-starting">', '<body>')
    .replace(/<section id="startup-loader"[\s\S]*?<\/section>/, '')
    .replace(/<script[^>]*src="[^"]*startup-loader\.js"[^>]*><\/script>/, '')
    .replace('<div id="root"></div>', () => `<div id="root">${result.html}</div><script id="cdt-public-state" type="application/json">${json(result.state)}</script>`);
  const file = `${sha(page.path)}.html`;
  generated.push({ page, file, html });
}
await mkdir(output, { recursive: true });
const manifest = { schemaVersion: 1, contentDigest: sha(contentSource), definitionsDigest: sha(pagesSource), pages: {} };
for (const { page, file, html } of generated) {
  await writeFile(new URL(file, output), html);
  manifest.pages[page.path] = { file, sha256: sha(html), fingerprint: catalog.fingerprints[page.path] };
}
await writeFile(new URL('manifest.json', output), JSON.stringify(manifest, null, 2) + '\n');
console.log(`Pre-rendered ${generated.length} public React pages.`);
