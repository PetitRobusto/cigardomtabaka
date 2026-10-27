import QRCode from 'qrcode';

const MODULE_SCALE = 28;
const QUIET_ZONE_MODULES = 4;

/**
 * Create a self-contained PNG for a Privnote link. The supplied URL is encoded
 * verbatim; URL parsing below is only a safety check and its normalized value
 * is never used as the QR payload.
 */
export async function createPrivnoteQrImage(url: string): Promise<string> {
  if (typeof url !== 'string' || url.length === 0 || url.trim() !== url || containsControlCharacters(url)) {
    throw new TypeError('A valid HTTP(S) Privnote URL is required');
  }

  let parsedUrl: URL;
  try {
    parsedUrl = new URL(url);
  } catch {
    throw new TypeError('A valid HTTP(S) Privnote URL is required');
  }
  if ((parsedUrl.protocol !== 'https:' && parsedUrl.protocol !== 'http:') || !parsedUrl.hostname) {
    throw new TypeError('A valid HTTP(S) Privnote URL is required');
  }

  const pngDataUrl = await QRCode.toDataURL(url, {
    errorCorrectionLevel: 'Q',
    margin: QUIET_ZONE_MODULES,
    scale: MODULE_SCALE,
    color: { dark: '#000000ff', light: '#ffffffff' },
  });

  if (!pngDataUrl.startsWith('data:image/png;base64,')) {
    throw new Error('Could not export the Privnote QR image as PNG');
  }
  return pngDataUrl;
}

function containsControlCharacters(value: string): boolean {
  return [...value].some((character) => {
    const codePoint = character.codePointAt(0) ?? 0;
    return codePoint <= 0x1f || codePoint === 0x7f;
  });
}
