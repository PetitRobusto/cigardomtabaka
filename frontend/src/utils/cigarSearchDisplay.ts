export function cigarSearchDisplayName(cigar: { name: string; brand: string; brand_cn?: string }): string {
  const name = cigar.name.trim();
  const chineseBrand = cigar.brand_cn?.trim();
  if (!chineseBrand && /[\u3400-\u9fff]/u.test(name)) return name;
  const brand = (chineseBrand || cigar.brand).trim();
  if (!brand || name.toLocaleLowerCase().startsWith(brand.toLocaleLowerCase())) return name;
  return `${brand} ${name}`;
}

export function cigarSearchReleaseLabel(cigar: { is_regular: boolean; release_type_cn?: string }): string {
  return cigar.is_regular ? '常规款' : cigar.release_type_cn?.trim() || '特别款';
}
