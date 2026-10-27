import QRCode from 'qrcode';

const MODULE_SCALE = 28;
const QUIET_ZONE_MODULES = 4;
const BRAND_HEADER_MODULES = 7;

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

  const qrDataUrl = await QRCode.toDataURL(url, {
    errorCorrectionLevel: 'Q',
    margin: QUIET_ZONE_MODULES,
    scale: MODULE_SCALE,
    color: { dark: '#000000ff', light: '#ffffffff' },
  });

  const qrImage = await loadQrImage(qrDataUrl);
  const canvas = document.createElement('canvas');
  canvas.width = qrImage.naturalWidth;
  canvas.height = qrImage.naturalHeight + BRAND_HEADER_MODULES * MODULE_SCALE;

  const context = canvas.getContext('2d');
  if (!context) throw new Error('Could not create a canvas for the Privnote QR image');

  context.fillStyle = '#ffffff';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = '#000000';
  context.font = `600 ${MODULE_SCALE * 3}px Arial, sans-serif`;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText('CigarDomTabaka', canvas.width / 2, (BRAND_HEADER_MODULES * MODULE_SCALE) / 2);
  // Draw at the source dimensions so QR modules remain crisp and uniformly scaled.
  context.drawImage(qrImage, 0, BRAND_HEADER_MODULES * MODULE_SCALE);

  const pngDataUrl = canvas.toDataURL('image/png');
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

function loadQrImage(source: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('Could not render the Privnote QR code'));
    image.src = source;
  });
}
