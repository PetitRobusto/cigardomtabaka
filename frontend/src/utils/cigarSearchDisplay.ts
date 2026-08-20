export function cigarSearchDisplayName(cigar: { name: string; brand: string; brand_cn?: string }): string {
  const name = cigar.name.trim();
  const brand = (cigar.brand_cn || cigar.brand).trim();
  if (!brand || name.toLocaleLowerCase().startsWith(brand.toLocaleLowerCase())) return name;
  return `${brand} ${name}`;
}

export function cigarSearchReleaseLabel(cigar: { is_regular: boolean; release_type_cn?: string }): string {
  return cigar.is_regular ? '常规款' : cigar.release_type_cn?.trim() || '特别款';
}
