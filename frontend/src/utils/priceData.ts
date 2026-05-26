import type { PriceSnapshot, CigarGroup, Variant, HistoryPoint, BrandInfo } from '../types';

export const BRANDS_ORDER = [
  '高希霸', '蒙特', '罗密欧与朱丽叶', '帕特加斯',
  '好友', '乌普曼',
];

/** 品牌英文名 → 本地logo URL 映射 */
export const BRAND_LOGO_LOCAL: Record<string, string> = {
  'Cohiba': '/media/brand_logos/cohiba.jpg',
  'H. Upmann': '/media/brand_logos/h-upmann.jpg',
  'Hoyo de Monterrey': '/media/brand_logos/hoyo-de-monterrey.jpg',
  'Montecristo': '/media/brand_logos/montecristo.jpg',
  'Partagás': '/media/brand_logos/partagas.jpg',
  'Romeo y Julieta': '/media/brand_logos/romeo-y-julieta.jpg',
  'Bolívar': '/media/brand_logos/bolivar.jpg',
  'Punch': '/media/brand_logos/punch.jpg',
  'Ramón Allones': '/media/brand_logos/ramon-allones.jpg',
  'Trinidad': '/media/brand_logos/trinidad.jpg',
  'José L. Piedra': '/media/brand_logos/jose-l-piedra.jpg',
  'Quintero': '/media/brand_logos/quintero.jpg',
  'Vegueros': '/media/brand_logos/vegueros.jpg',
  'Cuaba': '/media/brand_logos/cuaba.jpg',
  'Diplomáticos': '/media/brand_logos/diplomaticos.jpg',
  'El Rey del Mundo': '/media/brand_logos/el-rey-del-mundo.jpg',
  'Fonseca': '/media/brand_logos/fonseca.jpg',
  'Juan López': '/media/brand_logos/juan-lopez.jpg',
  'La Flor de Cano': '/media/brand_logos/la-flor-de-cano.jpg',
  'La Gloria Cubana': '/media/brand_logos/la-gloria-cubana.jpg',
  'Por Larrañaga': '/media/brand_logos/por-larranaga.jpg',
  'Rafael González': '/media/brand_logos/rafael-gonzalez.jpg',
  'Saint Luis Rey': '/media/brand_logos/saint-luis-rey.jpg',
  'San Cristóbal de la Habana': '/media/brand_logos/san-cristobal-de-la-habana.jpg',
  'Sancho Panza': '/media/brand_logos/sancho-panza.jpg',
  'Vegas Robaina': '/media/brand_logos/vegas-robaina.jpg',
  'Belinda': '/media/brand_logos/belinda.jpg',
  'Guantanamera': '/media/brand_logos/guantanamera.jpg',
  'Small Cigars': '/media/brand_logos/puritos.jpg',
  'Troya': '/media/brand_logos/troya.jpg',
};

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
        brand_en: s.cigar_brand,
        brand_cn: s.cigar_brand_cn || undefined,
        name: s.cigar_name,
        name_en: s.cigar_english_name,
        image_url: s.cigar_image_url || undefined,
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

export function extractBrands(groups: CigarGroup[]): BrandInfo[] {
  const seen = new Set<string>();
  const result: BrandInfo[] = [];
  groups.forEach((g) => {
    if (seen.has(g.brand)) return;
    seen.add(g.brand);
    result.push({
      name: g.brand,
      nameEn: g.brand_en,
      logoUrl: BRAND_LOGO_LOCAL[g.brand_en || ''] || '',
    });
  });
  // 按 BRANDS_ORDER 排序
  result.sort((a, b) => {
    const ai = BRANDS_ORDER.indexOf(a.name);
    const bi = BRANDS_ORDER.indexOf(b.name);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.name.localeCompare(b.name, 'zh');
  });
  return result;
}

export function extractSourceSlugs(snapshots: PriceSnapshot[]): string[] {
  const slugs = new Set<string>();
  snapshots.forEach((s) => {
    if (s.source_slug) slugs.add(s.source_slug);
  });
  return [...slugs];
}

/** 为价格走势图构建数据：所有 variant 按日期对齐，Y轴统一用 人民币 */
export function buildChartData(variants: Variant[]) {
  const dateMap: Record<string, Record<string, number | string>> = {};
  variants.forEach((v) => {
    const label = `${v.source_short_name || v.source_name} ${v.box_label}`;
    (v.points || []).forEach((p: HistoryPoint) => {
      const date = p.date?.split('T')[0] || p.date;
      if (!dateMap[date]) dateMap[date] = { date };
      // 用人民币价格，保证不同币种可对比
      dateMap[date][label] = p.price_cny ?? p.price;
    });
  });
  return Object.values(dateMap).sort((a, b) =>
    (a.date as string).localeCompare(b.date as string)
  );
}

export function variantLabel(v: Variant): string {
  return `${v.source_short_name || v.source_name} ${v.box_label}`;
}
