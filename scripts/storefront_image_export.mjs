#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import {
  existsSync, linkSync, mkdirSync, mkdtempSync, rmSync, rmdirSync,
  statSync, unlinkSync,
} from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = new Map();
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i];
  if (!key?.startsWith('--') || !process.argv[i + 1]) {
    throw new Error('Arguments must be --name value pairs.');
  }
  args.set(key.slice(2), process.argv[i + 1]);
}

const required = ['layer', 'detail', 'list', 'product-scale'];
for (const name of required) {
  if (!args.has(name)) throw new Error(`Missing --${name}.`);
}
const layer = resolve(root, args.get('layer'));
const detail = resolve(root, args.get('detail'));
const list = resolve(root, args.get('list'));
const logo = resolve(root, args.get('logo') ?? 'frontend/public/logo-original.png');
const productScale = Number(args.get('product-scale'));
if (detail === list) throw new Error('Detail and list outputs must use different paths.');
if (!Number.isFinite(productScale) || productScale <= 0 || productScale > 1) {
  throw new Error('--product-scale must be a number in (0, 1].');
}
if (![layer, logo].every(existsSync)) throw new Error('Layer or logo input is missing.');
if (existsSync(detail) || existsSync(list)) throw new Error('Refusing to overwrite an existing export.');

function run(command, argv, options = {}) {
  const result = spawnSync(command, argv, { encoding: null, maxBuffer: 16 * 1024 * 1024, ...options });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`${command} failed: ${result.stderr?.toString() ?? ''}`);
  }
  return result.stdout;
}

function alphaBounds(path) {
  const pixels = run('ffmpeg', [
    '-v', 'error', '-i', path, '-vf', 'alphaextract', '-f', 'rawvideo', '-pix_fmt', 'gray', 'pipe:1',
  ]);
  const probe = run('ffprobe', [
    '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
    '-of', 'csv=s=x:p=0', path,
  ], { encoding: 'utf8' }).trim();
  const [width, height] = probe.split('x').map(Number);
  if (pixels.length !== width * height) throw new Error(`Unexpected alpha plane size for ${path}.`);
  let minX = width;
  let minY = height;
  let maxX = -1;
  let maxY = -1;
  let hasTransparent = false;
  let hasOpaque = false;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const alpha = pixels[y * width + x];
      if (alpha > 0) {
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
        hasOpaque ||= alpha === 255;
      } else {
        hasTransparent = true;
      }
    }
  }
  if (maxX < minX || maxY < minY || !hasTransparent || !hasOpaque) {
    throw new Error(`Expected a useful transparent cutout/logo: ${path}`);
  }
  return { width, height, x: minX, y: minY, w: maxX - minX + 1, h: maxY - minY + 1 };
}

function ensureDirectory(directory, createdDirectories) {
  if (existsSync(directory)) return;
  const parent = dirname(directory);
  if (parent !== directory) ensureDirectory(parent, createdDirectories);
  try {
    mkdirSync(directory);
    createdDirectories.push(directory);
  } catch (error) {
    if (!existsSync(directory)) throw error;
  }
}

function probeDimensions(path) {
  return run('ffprobe', [
    '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,pix_fmt',
    '-of', 'default=noprint_wrappers=1', path,
  ], { encoding: 'utf8' }).trim();
}

function requireDimensions(path, width, height) {
  const probe = probeDimensions(path);
  const widthMatch = probe.match(/^width=(\d+)$/m);
  const heightMatch = probe.match(/^height=(\d+)$/m);
  if (Number(widthMatch?.[1]) !== width || Number(heightMatch?.[1]) !== height) {
    throw new Error(`Unexpected output dimensions for ${path}: ${probe}`);
  }
  return probe;
}

const createdDirectories = [];
const temporaryDirectories = [];
const publishedFiles = [];
try {
  const layerBounds = alphaBounds(layer);
  const logoBounds = alphaBounds(logo);
  if (layerBounds.width !== layerBounds.height) throw new Error('Foreground layer must use a square canvas.');

  ensureDirectory(dirname(detail), createdDirectories);
  ensureDirectory(dirname(list), createdDirectories);
  const detailTemporaryDirectory = mkdtempSync(join(dirname(detail), '.storefront-export-'));
  temporaryDirectories.push(detailTemporaryDirectory);
  const listTemporaryDirectory = dirname(list) === dirname(detail)
    ? detailTemporaryDirectory
    : mkdtempSync(join(dirname(list), '.storefront-export-'));
  if (listTemporaryDirectory !== detailTemporaryDirectory) temporaryDirectories.push(listTemporaryDirectory);
  const temporaryDetail = join(detailTemporaryDirectory, 'detail.webp');
  const temporaryList = join(listTemporaryDirectory, 'list.webp');

  const canvas = 1200;
  const logoWidth = Math.round(canvas * 0.70);
  const productPixels = Math.round(layerBounds.width * productScale / 2) * 2;
  const filter = [
    `[2:v]crop=${logoBounds.w}:${logoBounds.h}:${logoBounds.x}:${logoBounds.y},scale=${logoWidth}:-1:flags=lanczos,format=rgba,colorchannelmixer=aa=0.09[watermark]`,
    `[0:v][watermark]overlay=x=(W-w)/2:y=(H-h)/2:format=auto[background]`,
    `[1:v]scale=${productPixels}:${productPixels}:flags=lanczos,format=rgba[foreground]`,
    `[background][foreground]overlay=x=(W-w)/2:y=(H-h)/2:format=auto[composite]`,
  ].join(';');
  run('ffmpeg', [
    '-v', 'error', '-n', '-f', 'lavfi', '-i', `color=c=white:s=${canvas}x${canvas}:r=1`,
    '-i', layer, '-i', logo, '-filter_complex', filter, '-map', '[composite]', '-frames:v', '1',
    '-c:v', 'libwebp', '-quality', '90', '-compression_level', '6', temporaryDetail,
  ]);
  run('ffmpeg', [
    '-v', 'error', '-n', '-i', temporaryDetail, '-vf', 'scale=480:480:flags=lanczos', '-frames:v', '1',
    '-c:v', 'libwebp', '-quality', '88', '-compression_level', '6', temporaryList,
  ]);

  const detailProbe = requireDimensions(temporaryDetail, 1200, 1200);
  const listProbe = requireDimensions(temporaryList, 480, 480);
  if (statSync(temporaryDetail).size === 0 || statSync(temporaryList).size === 0) {
    throw new Error('FFmpeg generated an empty output.');
  }

  for (const [temporaryPath, outputPath] of [[temporaryDetail, detail], [temporaryList, list]]) {
    // Hard-link publication is atomic and fails if another process created the destination meanwhile.
    const { dev, ino } = statSync(temporaryPath);
    linkSync(temporaryPath, outputPath);
    publishedFiles.push({ path: outputPath, dev, ino });
    unlinkSync(temporaryPath);
  }

  console.log(JSON.stringify({
    layer: layer.replace(`${root}/`, ''),
    product_scale: productScale,
    product_alpha_bounds: layerBounds,
    logo_alpha_bounds: logoBounds,
    watermark: { center: [0.5, 0.5], width_ratio: 0.7, opacity: 0.09 },
    detail: { path: detail.replace(`${root}/`, ''), probe: detailProbe },
    list: { path: list.replace(`${root}/`, ''), probe: listProbe },
  }, null, 2));
} catch (error) {
  for (const file of publishedFiles.reverse()) {
    try {
      const current = statSync(file.path);
      if (current.dev === file.dev && current.ino === file.ino) unlinkSync(file.path);
    } catch {}
  }
  for (const temporaryDirectory of temporaryDirectories.reverse()) {
    try { rmSync(temporaryDirectory, { recursive: true, force: true }); } catch {}
  }
  for (const directory of createdDirectories.reverse()) {
    try { rmdirSync(directory); } catch {}
  }
  throw error;
}

for (const temporaryDirectory of temporaryDirectories) {
  try { rmSync(temporaryDirectory, { recursive: true, force: true }); } catch {}
}
