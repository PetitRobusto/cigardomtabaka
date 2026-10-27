import { createCanvas, Image as CanvasImage } from '@napi-rs/canvas';
import jsQR from 'jsqr';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPrivnoteQrImage } from './privnoteQr';

afterEach(() => vi.unstubAllGlobals());

function installCanvasBrowserShim() {
  vi.stubGlobal('document', {
    createElement: (tagName: string) => {
      if (tagName !== 'canvas') throw new Error(`Unexpected element: ${tagName}`);
      return createCanvas(1, 1);
    },
  });
  vi.stubGlobal('Image', CanvasImage as unknown as typeof Image);
}

describe('Privnote QR PNG helper', () => {
  it('encodes the complete original URL and exports a square PNG without a title', async () => {
    installCanvasBrowserShim();
    const originalUrl = 'https://privnote.com/AbC123?source=telegram&keep=%2F#private';

    const pngDataUrl = await createPrivnoteQrImage(originalUrl);
    const image = new CanvasImage();
    image.src = pngDataUrl;
    await image.decode();
    const canvas = createCanvas(image.naturalWidth, image.naturalHeight);
    const context = canvas.getContext('2d');
    context.drawImage(image, 0, 0);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
    const decoded = jsQR(pixels.data, canvas.width, canvas.height);

    expect(pngDataUrl).toMatch(/^data:image\/png;base64,/);
    expect(decoded?.data).toBe(originalUrl);
    expect(canvas.width).toBeGreaterThanOrEqual(768);
    expect(canvas.height).toBe(canvas.width);
    // Only the QR and its white quiet zone remain; no title is drawn above it.
    const rgb = (x: number, y: number) => {
      const offset = (y * canvas.width + x) * 4;
      return [...pixels.data.subarray(offset, offset + 3)];
    };
    expect(rgb(0, 0)).toEqual([255, 255, 255]);
    expect(rgb(canvas.width - 1, 0)).toEqual([255, 255, 255]);
    expect(rgb(0, canvas.height - 1)).toEqual([255, 255, 255]);
    expect(rgb(canvas.width - 1, canvas.height - 1)).toEqual([255, 255, 255]);
    const topQuietZone = pixels.data.subarray(0, 4 * 28 * canvas.width * 4);
    expect(topQuietZone.every(value => value === 255)).toBe(true);
  });

  it.each([
    '',
    'https://',
    'ftp://example.com/note',
    'javascript:alert(1)',
    ' https://privnote.com/note',
  ])('rejects invalid or unsafe URL %j', async (url) => {
    await expect(createPrivnoteQrImage(url)).rejects.toThrow(TypeError);
  });

  it('propagates QR encoder errors so the caller can retry', async () => {
    const { default: QRCode } = await import('qrcode');
    const encoderError = new Error('encoder unavailable');
    const encodeSpy = vi.spyOn(QRCode, 'toDataURL').mockRejectedValueOnce(encoderError);

    await expect(createPrivnoteQrImage('https://privnote.com/note')).rejects.toBe(encoderError);
    encodeSpy.mockRestore();
  });
});
