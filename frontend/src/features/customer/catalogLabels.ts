import type { CustomerLocale } from './messages';

// The catalogue API currently returns Chinese section headings. Translate known
// headings only; preserve unknown data and counts rather than guessing names.
const headings: Record<string, [string, string]> = {
  '常规款': ['Regular production', 'Регулярное производство'],
  '限量版': ['Limited editions', 'Лимитированные выпуски'],
  '地区限量版': ['Regional editions', 'Региональные выпуски'],
  '纪念版': ['Commemorative editions', 'Юбилейные выпуски'],
  '哈瓦那收藏系列': ['Habanos Collection', 'Коллекция Habanos'],
  '珍藏系列': ['Reserve series', 'Серия Reserva'],
  '特级珍藏系列': ['Grand Reserve series', 'Серия Gran Reserva'],
  '千禧珍藏系列': ['Millennium Reserve series', 'Серия Millennium Reserva'],
  '陈年哈瓦那系列': ['Aged Habanos', 'Выдержанные Habanos'],
  '免税及旅行零售系列': ['Duty Free and Travel Retail', 'Duty Free и Travel Retail'],
  '中国年份系列': ['Chinese Year series', 'Серия китайского календаря'],
  '复刻古董保湿盒系列': ['Replica Antique Humidor series', 'Реплики старинных хьюмидоров'],
  '年份系列': ['Vintage series', 'Винтажная серия'],
  '特别活动': ['Special events', 'Специальные мероприятия'],
  '其他特别版': ['Other special editions', 'Другие специальные выпуски'],
  'LCDH 独享': ['LCDH exclusives', 'Эксклюзивы LCDH'],
  '专家店独享': ['Specialist exclusives', 'Эксклюзивы специализированных магазинов'],
  '独立特别发行': ['Standalone special releases', 'Отдельные специальные выпуски'],
  '停产款': ['Discontinued cigars', 'Снятые с производства'],
  '小雪茄': ['Small cigars', 'Малые сигары'],
};

export function catalogSectionLabel(label: string, locale: CustomerLocale): string {
  if (locale === 'zh') return label;
  const match = /^(.*?)( \(\d+\))?$/.exec(label);
  const translated = match && headings[match[1]]?.[locale === 'en' ? 0 : 1];
  return translated ? `${translated}${match?.[2] ?? ''}` : label;
}
