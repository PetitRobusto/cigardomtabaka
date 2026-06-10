export function generateCigarSlugFromParts(
  brand: string,
  englishName: string,
  releaseType?: string,
  releaseName?: string
): string {
  const parts = [brand, englishName, releaseType, releaseName].filter(
    (p): p is string => !!p
  );

  let slug = parts
    .join(' ')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');

  if (slug.length > 100) {
    slug = slug.slice(0, 100).replace(/-+$/, '');
  }

  return slug || 'cigar';
}

export function generateCigarSlug(cigar: {
  brand?: string;
  english_name?: string;
  name?: string;
  release_type?: string;
  release_name?: string;
}): string {
  return generateCigarSlugFromParts(
    cigar.brand || '',
    cigar.english_name || cigar.name || '',
    cigar.release_type,
    cigar.release_name
  );
}
