#!/usr/bin/env node
import { renderStorePages } from "../src/storefront/render.tsx";

async function readStdin() {
  let value = "";
  for await (const chunk of process.stdin) value += chunk;
  return JSON.parse(value);
}

try {
  const input = await readStdin();
  process.stdout.write(JSON.stringify(renderStorePages(input)));
} catch (error) {
  process.stderr.write(`storefront prerender: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
