#!/usr/bin/env node
import { renderStorePages } from "../src/storefront/render.tsx";
import { renderNotFoundDocument } from "../src/storefront/renderNotFound.tsx";
import { mkdir, writeFile } from "node:fs/promises";

async function readStdin() {
  let value = "";
  for await (const chunk of process.stdin) value += chunk;
  return JSON.parse(value);
}

try {
  if (process.argv.includes('--errors')) {
    const directory = new URL('../errors/', import.meta.url);
    await mkdir(directory, { recursive: true });
    for (const locale of ['zh', 'ru', 'en']) {
      await writeFile(new URL(`404-${locale}.html`, directory), renderNotFoundDocument(locale), 'utf8');
    }
    process.stdout.write('Built 3 localized HTTP 404 documents.\n');
  } else {
    const input = await readStdin();
    process.stdout.write(JSON.stringify(renderStorePages(input)));
  }
} catch (error) {
  process.stderr.write(`storefront prerender: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
