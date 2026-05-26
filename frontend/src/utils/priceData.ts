import type { PriceSnapshot, CigarGroup, Variant, HistoryPoint } from '../types';

export const BRANDS_ORDER = [
  '高希霸', '蒙特', '罗密欧与朱丽叶', '帕特加斯',
  '好友', '乌普曼',
];

export function groupSnapshots(snapshots: PriceSnapshot[]): CigarGroup[] {
  const map: Record<string, CigarGroup> = {};
  snapshots.forEach((s) => {
    const cigarId = s.cigar;
    const brandCn = s.cigar_brand_cn || s.cigar_brand;
    const key = `${brandCn}|||${cigarId}`;
    if (!map[key]) {
      map[key] = {
        cigar_id: cigarId,
        brand: brandCn,
        name: s.cigar_name,
        name_en: s.cigar_english_name,
        prices: [],
      };
    }
    map[key].prices.push(s);
  });
  let list = Object.values(map);
  list.sort((a, b) => {
    const ai = BRANDS_ORDER.indexOf(a.brand);
    const bi = BRANDS_ORDER.indexOf(b.brand);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.brand.localeCompare(b.brand, 'zh');
  });
  return list;
}

export function extractBrands(groups: CigarGroup[]): string[] {
  return [...new Set(groups.map((g) => g.brand))];
}

export function extractSourceSlugs(snapshots: PriceSnapshot[]): string[] {
  const slugs = new Set<string>();
  snapshots.forEach((s) => {
    if (s.source_slug) slugs.add(s.source_slug);
  });
  return [...slugs];
}

export function buildChartData(variants: Variant[]) {
  const dateMap: Record<string, Record<string, number | string>> = {};
  variants.forEach((v) => {
    const label = `${v.source_name} ${v.box_label}`;
    (v.points || []).forEach((p: HistoryPoint) => {
      const date = p.date?.split('T')[0] || p.date;
      if (!dateMap[date]) dateMap[date] = { date };
      dateMap[date][label] = p.price;
    });
  });
  return Object.values(dateMap).sort((a, b) =>
    (a.date as string).localeCompare(b.date as string)
  );
}

export function variantLabel(v: Variant): string {
  return `${v.source_name} ${v.box_label}`;
}
