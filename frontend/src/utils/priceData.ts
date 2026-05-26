import type { PriceSnapshot, CigarGroup, Variant, HistoryPoint, BrandInfo } from '../types';

export const BRANDS_ORDER = [
  '高希霸', '蒙特', '罗密欧与朱丽叶', '帕特加斯',
  '好友', '乌普曼',
];

/** 品牌英文名 → logo URL 映射（来自 brand_logos.json） */
export const BRAND_LOGO_MAP: Record<string, string> = {
  'Cohiba': 'https://www.cubancigarwebsite.com/img/brandlogos/cohiba_316x200.jpg',
  'H. Upmann': 'https://www.cubancigarwebsite.com/img/brandlogos/h-upmann-_272x200.jpg',
  'Hoyo de Monterrey': 'https://www.cubancigarwebsite.com/img/brandlogos/hoyo-de-monterrey-_268x200.jpg',
  'Montecristo': 'https://www.cubancigarwebsite.com/img/brandlogos/montecristo-_212x200.jpg',
  'Partagás': 'https://www.cubancigarwebsite.com/img/brandlogos/partagas-_310x198.jpg',
  'Romeo y Julieta': 'https://www.cubancigarwebsite.com/img/brandlogos/romeo-y-julieta_278x198.jpg',
  'Bolívar': 'https://www.cubancigarwebsite.com/img/brandlogos/bolivar_280x200.jpg',
  'Punch': 'https://www.cubancigarwebsite.com/img/brandlogos/punch-_250x200.jpg',
  "Quai d'Orsay": 'https://www.cubancigarwebsite.com/img/brandlogos/quai-dorsay-_274x200.jpg',
  'Ramón Allones': 'https://www.cubancigarwebsite.com/img/brandlogos/ramon-allones-_260x200.jpg',
  'Trinidad': 'https://www.cubancigarwebsite.com/img/brandlogos/trinidad-_172x200.jpg',
  'José L. Piedra': 'https://www.cubancigarwebsite.com/img/brandlogos/jose-l-piedra_280x200.jpg',
  'Quintero': 'https://www.cubancigarwebsite.com/img/brandlogos/quintero-_260x200.jpg',
  'Vegueros': 'https://www.cubancigarwebsite.com/img/brandlogos/vegueros-_344x200.jpg',
  'Cuaba': 'https://www.cubancigarwebsite.com/img/brandlogos/cuaba-_228x200.jpg',
  'Diplomáticos': 'https://www.cubancigarwebsite.com/img/brandlogos/diplomaticos-_314x200.jpg',
  'El Rey del Mundo': 'https://www.cubancigarwebsite.com/img/brandlogos/el-rey-del-mundo-_220x200.jpg',
  'Fonseca': 'https://www.cubancigarwebsite.com/img/brandlogos/fonseca-_306x198.jpg',
  'Juan López': 'https://www.cubancigarwebsite.com/img/brandlogos/juan-lopez-_258x200.jpg',
  'La Flor de Cano': 'https://www.cubancigarwebsite.com/img/brandlogos/la-flor-de-cano-_284x200.jpg',
  'La Gloria Cubana': 'https://www.cubancigarwebsite.com/img/brandlogos/la-gloria-cubana-_280x200.jpg',
  'Por Larrañaga': 'https://www.cubancigarwebsite.com/img/brandlogos/por-larranaga-_216x200.jpg',
  'Rafael González': 'https://www.cubancigarwebsite.com/img/brandlogos/rafael-gonzalez-_274x200.jpg',
  'Saint Luis Rey': 'https://www.cubancigarwebsite.com/img/brandlogos/saint-luis-rey-_282x200.jpg',
  'San Cristóbal de la Habana': 'https://www.cubancigarwebsite.com/img/brandlogos/san-cristobal-de-la-habana-_310x200.jpg',
  'Sancho Panza': 'https://www.cubancigarwebsite.com/img/brandlogos/sancho-panza-_252x200.jpg',
  'Vegas Robaina': 'https://www.cubancigarwebsite.com/img/brandlogos/vegas-robaina-_282x200.jpg',
  'Belinda': 'https://www.cubancigarwebsite.com/img/brandlogos/belinda-_284x200.jpg',
  'Guantanamera': 'https://www.cubancigarwebsite.com/img/brandlogos/guantanamera-_238x200.jpg',
  'Small Cigars': 'https://www.cubancigarwebsite.com/img/brandlogos/puritos_184x184.jpg',
  'Troya': 'https://www.cubancigarwebsite.com/img/brandlogos/troya-_266x200.jpg',
  'Cubatabaco': 'https://www.cubancigarwebsite.com/img/brandlogos/cubatabaco_326x196.jpg',
  'Edmundo Dantes': 'https://www.cubancigarwebsite.com/img/brandlogos/edmundo-dantes_270x200.jpg',
  'Habanos': 'https://www.cubancigarwebsite.com/img/brandlogos/habanos_296x200.jpg',
  'Multi-Brand Releases': 'https://www.cubancigarwebsite.com/img/brandlogos/multi-brand-releases-_266x200.jpg',
  'Cabañas': 'https://www.cubancigarwebsite.com/img/brandlogos/cabanas-_152x200.jpg',
  'Caney': 'https://www.cubancigarwebsite.com/img/brandlogos/caney_334x200.jpg',
  'Cifuentes': 'https://www.cubancigarwebsite.com/img/brandlogos/_250x200.jpg',
  'Davidoff': 'https://www.cubancigarwebsite.com/img/brandlogos/davidoff_428x200.jpg',
  'Don Alfredo': 'https://www.cubancigarwebsite.com/img/brandlogos/don-alfredo-_424x200.jpg',
  'Don Cándido': 'https://www.cubancigarwebsite.com/img/brandlogos/don-candido-_328x200.jpg',
  'Dunhill': 'https://www.cubancigarwebsite.com/img/brandlogos/dunhill-_310x200.jpg',
  'Flor del Punto': 'https://www.cubancigarwebsite.com/img/brandlogos/flor-del-punto-_306x200.jpg',
  'Gispert': 'https://www.cubancigarwebsite.com/img/brandlogos/gispert-_222x200.jpg',
  'J. J. Fox Exclusives': 'https://www.cubancigarwebsite.com/img/brandlogos/j-j-fox-exclusives-_408x200.jpg',
  'La Corona': 'https://www.cubancigarwebsite.com/img/brandlogos/la-corona-_200x200.jpg',
  'La Escepción': 'https://www.cubancigarwebsite.com/img/brandlogos/la-escepcion_246x200.jpg',
  'La Flor del Caney': 'https://www.cubancigarwebsite.com/img/brandlogos/la-flor-del-caney-1_342x200.jpg',
  'Los Statos de Luxe': 'https://www.cubancigarwebsite.com/img/brandlogos/1_278x200.jpg',
  'María Guerrero': 'https://www.cubancigarwebsite.com/img/brandlogos/2_264x200.jpg',
  'San Luis Rey': 'https://www.cubancigarwebsite.com/img/brandlogos/san-luis-rey-_204x200.jpg',
  'Siboney': 'https://www.cubancigarwebsite.com/img/brandlogos/siboney-_252x200.jpg',
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
      logoUrl: BRAND_LOGO_MAP[g.brand_en || ''] || '',
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
