const homeImageWidths = [320, 480, 640, 800] as const;

const imageWidthFractions = {
  bhk56: 0.96,
  siglo: 0.82,
  casilda: 0.74,
  bhk52: 0.66,
  ingenios: 0.58,
} as const;

function imageSizes(widthFraction: number) {
  const fixedAtMax = Math.round(widthFraction * (1052 * 6 / 11));
  return [
    `(max-width: 679px) min(calc(${(widthFraction * 100).toFixed(2)}vw - ${(widthFraction * 64).toFixed(2)}px), ${(widthFraction * 480).toFixed(2)}px)`,
    `(max-width: 1023px) calc(${(widthFraction * 50).toFixed(2)}vw - ${(widthFraction * 36).toFixed(2)}px)`,
    `(max-width: 1120px) calc(${(widthFraction * 54.54545).toFixed(2)}vw - ${(widthFraction * 37.09).toFixed(2)}px)`,
    `${fixedAtMax}px`,
  ].join(", ");
}

export const homeHeroImageSizes = {
  bhk56: imageSizes(imageWidthFractions.bhk56),
  siglo: imageSizes(imageWidthFractions.siglo),
  casilda: imageSizes(imageWidthFractions.casilda),
  bhk52: imageSizes(imageWidthFractions.bhk52),
  ingenios: imageSizes(imageWidthFractions.ingenios),
};

export function homeHeroImageSrcSet(stem: string, maxWidth: number) {
  return [...homeImageWidths, maxWidth]
    .map((width) => `/media/home-hero-v1/${stem}-${width}.webp ${width}w`)
    .join(", ");
}

export const homeHeroFirstImageSizes = homeHeroImageSizes.bhk56;
export const homeHeroFirstImageSrcSet = homeHeroImageSrcSet("cohiba-bhk-56", 997);
